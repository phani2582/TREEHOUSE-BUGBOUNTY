# Security Audit — `TreehouseAccounting.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/TreehouseAccounting.sol` (112 LoC)
**Type:** Non-upgradeable `Ownable2Step` accounting module; a **minter** on the IAU
**Role:** The single funnel that mints/burns IAU into/out of `TAsset` to mark protocol PnL. Called by `PnlAccounting.doAccounting`.
**Dependencies read:** `InternalAccountingUnit` (IAU), `TAsset` (ERC4626), `PnlAccounting` (the caller), `NavLens` (NAV derivation), OZ `Ownable2Step`/`SafeERC20`/`IERC4626`. Plus the in-repo PoC `TreehouseDonationBricksAccounting.t.sol` for ecosystem context.
**Date:** 2026-08-08

---

## Trust model & call graph (established, not assumed)

```
PnlAccounting.doAccounting(params)          [whenNotPaused, onlyOwnerOrExecutor]
   ├─ _lastNav    = IAU.balanceOf(TASSET)                (NavLens.lastRecordedProtocolNav)
   ├─ _currentNav = vaultNav + Σ strategyNav(params)     (NavLens.currentProtocolNav)
   ├─ _netPnl     = |current − last|
   ├─ require _netPnl ≤ maxPnl()  = deviation·lastNav/1e4   ← THE ONLY SAFETY BOUND
   └─ TreehouseAccounting.mark(MINT|BURN, netPnl−fee, fee) [onlyOwnerOrExecutor]
          ├─ MINT: IAU.mintTo(this,fee); TASSET.deposit(fee,treasury); IAU.mintTo(TASSET, amountLessFee)
          └─ BURN: IAU.burnFrom(TASSET, amountLessFee)
```

- `TreehouseAccounting.owner` = trusted admin. `TreehouseAccounting.executor` = whoever is wired to trigger marks (see M-1).
- For the legitimate path to work, `PnlAccounting` must be registered as `TreehouseAccounting`'s `owner` or `executor`.
- IAU is a plain ERC20; `TreehouseAccounting` is one of its `minters`, so `mintTo`/`burnFrom` succeed and its `TASSET.deposit` passes TAsset's `isMinter(caller)` gate.

**The one sentence that governs this contract:** every check that makes a mark *correct and bounded* — deviation cap, cooldown, the NAV-delta computation itself — lives in **`PnlAccounting`**. `mark` re-checks **nothing**. It mints or burns exactly the numbers it is handed.

---

## How I'd actually attack this (black-hat)

The Solidity is clean — no reentrancy, no arithmetic bug, no bad `msg.sender`. So I don't attack the code; I attack the **trust delegation**. The deviation guard that everyone points to as "the protocol can't over-mint" is in `PnlAccounting.doAccounting`. But `mark` is independently callable by `TreehouseAccounting.{owner, executor}`. **I never call `doAccounting`. I call `mark` directly** and the guard, cooldown, and NAV math simply don't exist on that path.

### H-1 — `mark` is an unbounded, unbacked mint/burn funnel; the deviation guard is trivially bypassed (High, centralization-critical)
`TreehouseAccounting.sol:71` — `mark(...) onlyOwnerOrExecutor` performs no validation of `_amountLessFee`/`_fee` against NAV, supply, deviation, or a cooldown.

- **Drain via MINT:** `mark(MINT, X, 0)` → `IAU.mintTo(TASSET, X)` with arbitrary `X`. `TAsset.totalAssets()` *is* `IAU.balanceOf(TASSET)`, so the tETH share price inflates instantly against **unbacked** IAU. Hold (or pre-deposit) tETH, inflate, then redeem via the redemption path → pull real wstETH out of the `Vault` far exceeding anything deposited. This is the concrete realization of the IAU **H-1** ("any single minter can mint unlimited IAU → inflate → drain") — `TreehouseAccounting` *is* that minter and `mark` is the funnel.
- **Destroy via BURN:** `mark(BURN, IAU.balanceOf(TASSET), 0)` → `burnFrom(TASSET, …)` zeroes the vault's IAU backing in one tx, taking every tETH holder's shares to ~0. Bounded only by TAsset's balance (over-burn reverts on `_burn` underflow).
- **No brakes:** no cooldown, no `maxPnl`, no timelock — a single transaction. Contrast the legitimate `doAccounting` path, which caps a mark at `deviation` (≈2.5%) of NAV per `cooldown` window.

**Why the "donation-brick" PoC does *not* soften this:** that known Medium (`TreehouseDonationBricksAccounting.t.sol`) pushes `currentNav` up by donating wstETH to the ungated `Vault`, but it is *bounded by the deviation guard* (it only ever DoS-reverts `doAccounting`; attacker profit = 0). H-1 is the opposite: it **skips** the guard entirely and is directly profitable. Different path, different severity.

**Recommend:** `mark` must enforce its own invariant rather than trusting the caller — e.g. restrict `mark` to *only* `PnlAccounting` (drop the `owner`/EOA bypass), and/or re-assert a deviation/`maxPnl` bound and cooldown inside `mark` itself. At minimum, put `owner` behind a timelock+multisig and document that `mark` is a full-supply-control function, not a routine keeper call.

### M-1 — The `executor` key is a hidden second god-key (Medium, deployment-dependent)
`onlyOwnerOrExecutor` (`:60-63`) gives `executor` the **same** unbounded `mark` power as `owner`. If deployment sets `TreehouseAccounting.executor = address(PnlAccounting)`, only `owner` can bypass — still H-1, but one key. If `executor` is an **EOA** (a hot "accounting cron" key, exactly like `PnlAccounting.executor = 0x608a…` in the PoC), then that operationally-low-attention key silently holds full mint/burn authority over the entire tETH backing, bypassing every safety in `PnlAccounting`. This is the classic naming-vs-power trap: operators harden the deviation/cooldown config and the `PnlAccounting` executor, unaware the *TreehouseAccounting* executor is god-mode. `updateExecutor` (`:89`) has no zero/contract check and emits the event **before** the state change (`:90`, cosmetic).
**Recommend:** set `executor` to the `PnlAccounting` contract (never an EOA); if an EOA keeper is required, it should call `doAccounting`, never `mark`. Verify the deployed wiring.

### L-1 — `setFee` permits a 100% protocol fee (Low / centralization)
`setFee` (`:107`) allows up to `PRECISION` = `1e4` bips = **100%**. At `fee = 1e4`, `doAccounting` computes `_fee = _netPnl`, `_netPnl -= _fee → 0`, so `mark(MINT, 0, netPnl)` routes **all** yield to `treasury` as shares and 0 to holders. Owner-gated and reversible, but the cap should be a sane maximum (e.g. ≤ 20–30%).

### L-2 — MINT fee-share ordering is treasury-favorable (Low / informational)
In `mark` MINT (`:73-75`): `deposit(_fee, treasury)` mints treasury shares at the **pre-yield** price, *then* `mintTo(TASSET, _amountLessFee)` lifts the price for all shares — so treasury's fee shares also ride the same-window PnL lift. Second-order over-allocation to the fee-taker; not externally exploitable (TAsset deposits are minter-gated, so no outsider can sandwich the `deposit`). Flag for intent.

### L-3 — Constructor / setters lack zero-address & return-value checks (Low)
- Constructor (`:43-58`) sets `IAU`, `TASSET`, `treasury`, `executor`, `fee` with **no zero-address checks**; `IAU`/`TASSET` are immutable, so a bad deploy bricks permanently.
- `IERC20(IAU).approve(TASSET, type(uint).max)` (`:57`) — raw `approve`, return ignored (inconsistent with the `SafeERC20` import; use `forceApprove`). The infinite approval itself is low-risk because `TreehouseAccounting`'s standing IAU balance is ~0 (each `_fee` is minted then immediately deposited), but note `TASSET` is **UUPS-upgradeable** — a malicious TAsset implementation could `transferFrom` on this standing allowance; keep it minimal or approve exact amounts per `mark`.
- `updateTreasury` (`:98`) allows `treasury = address(0)` → `deposit(_fee, address(0))` would mint fee shares to `address(0)` (fee value burned). Recoverable via another `updateTreasury`. Add zero-guards.

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Reentrancy | `mark` calls IAU (plain ERC20, no hooks) and `TASSET.deposit`/`burnFrom`; no callback to an attacker, no ERC777. State only `emit`s after calls. No guard needed. Safe. |
| Access Control / Missing Checks | `mark` → `onlyOwnerOrExecutor`; `updateExecutor`/`updateTreasury`/`setFee` → `onlyOwner`. Nothing is *missing*; the flaw (H-1/M-1) is that `mark` **delegates** its safety upward to `PnlAccounting` and to over-powerful keys. |
| Arithmetic / Overflow-Underflow | 0.8.24 checked math in `mark`; no `unchecked`. Over-burn reverts on `_burn`. (The `unchecked` block is in `PnlAccounting`, not here — see adjacent notes.) |
| Price Oracle / Flash Loan | No oracle in this file. Flash loans can't obtain `owner`/`executor`; the bounded donation-vector is a `Vault`/`NavLens`/`PnlAccounting` concern, not `mark`. |
| Proxy & Upgradeability | `TreehouseAccounting` is non-upgradeable; immutable `IAU`/`TASSET`. (`TASSET` upgradeability is noted under L-3.) |
| Delegatecall to untrusted callee | None. All calls are typed external calls to protocol contracts. |
| Front-Running / TOD | `mark`/`doAccounting` are privilege-gated; TAsset minter-gating prevents outsiders sandwiching the fee `deposit`. The donation-brick TOD lives upstream (bounded, profitless). |
| Signature Replay / Randomness / Timestamp | No signatures/permit/RNG here. Cooldown uses `block.timestamp` in `PnlAccounting` (±15 s irrelevant vs 3600 s). N/A. |
| Integer / Short-Address | ABI/calldata handled by compiler ≥0.8. Negligible. |
| Uninitialized Storage Pointer | No memory/storage struct pointers. Not affected. |
| DoS | No unbounded loops in `mark`. Protocol-level mark DoS (donation-brick) is upstream; not a property of this file. |
| Approval Phishing | Only the module's own `approve(TASSET, max)` (L-3). No user allowances flow through here. |
| Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain — and **the dominant real risk**: the `owner` key (H-1) and, depending on wiring, the `executor` key (M-1) are each a single-tx, no-timelock, full mint/burn authority over all tETH backing. Multisig + timelock the owner; make `executor` the `PnlAccounting` contract. |

---

## Summary

No memory-safety, reentrancy, or arithmetic bug — `TreehouseAccounting.sol` is small and correct at the Solidity level. The risk is **architectural privilege delegation**:

1. **H-1 (High, centralization-critical)** — `mark` is an unbounded mint/burn funnel over the entire tETH backing. The deviation guard, cooldown, and NAV computation that make marks safe all live in `PnlAccounting.doAccounting`; `mark` re-validates none of them, so any `owner`/`executor` calling `mark` **directly** bypasses every safety and can mint unbacked IAU (inflate → redeem → drain the Vault) or burn the backing to zero, in one transaction. Move the invariant into `mark` (restrict caller to `PnlAccounting` and/or re-assert `maxPnl`+cooldown).
2. **M-1 (Medium)** — `executor` wields the same power as `owner`. Wire it to the `PnlAccounting` **contract**, never an EOA keeper; verify on-chain.
3. **L-1/L-2/L-3** — 100%-fee ceiling; treasury-favorable fee-share ordering; missing zero-address/return checks and an infinite (raw) `approve` to an upgradeable `TASSET`.

**Adjacent (out of file scope, but they define `mark`'s safety envelope):**
- `PnlAccounting.sol:33` comments claim `deviation` is `1e6 base … 250 == 0.025%`, but `maxPnl = deviation·lastNav/1e4` → **2.5%** (the PoC confirms ≈2.5%). A 100× documentation error that could lead an operator to set a tolerance 100× larger than intended.
- `PnlAccounting.doAccounting` wraps its **entire** body in `unchecked` (`:54-73`). Currently safe (differences are ordered, products fit uint256), but fragile — any future edit to the PnL/fee math loses overflow protection silently.
- The known **donation-brick** (in-repo PoC): `Vault` has no inbound gate + `lastRecordedProtocolNav` is derived from `IAU.balanceOf(TASSET)` + the deviation guard → a cheap, profitless protocol-wide accounting DoS. It reverts *before* reaching `mark`, so it corrupts availability, not `mark`'s output — but it's the same NAV-derivation fragility worth fixing alongside H-1.
