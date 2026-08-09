# Security Audit — `TreehouseRedemptionV2.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/TreehouseRedemptionV2.sol` (260 LoC)
**Type:** Non-upgradeable `Ownable2Step, ReentrancyGuard, Pausable, Rescuable`; an IAU + TAsset **minter**; the **exit** half of the deposit flow.
**Role:** Two-phase tETH → wstETH redemption. `redeem()` escrows tETH shares and snapshots value; after a 7-day wait `finalizeRedeem()` burns the shares for IAU, computes a conservative payout, burns that IAU, and has `RedemptionController` pull the wstETH from the `Vault` to the user.
**Dependencies read:** `RedemptionController` (the vault-drain arm), `Vault`, `TAsset` (ERC4626, UUPS), `InternalAccountingUnit` (IAU), `IwstETH` (Lido rate), `Rescuable`, OZ `ReentrancyGuard`/`Pausable`/`SafeCast`/`SafeERC20`.
**Date:** 2026-08-09

---

## Trust model & redemption flow (established, not assumed)

```
redeem(shares)  [nonReentrant, whenNotPaused=Controller.paused()]
  b0 = TASSET.previewRedeem(shares)               // IAU value now
  require b0 ≥ minRedeemInUnderlying (250e18)
  tETH.transferFrom(user → this, shares)          // ESCROW (not burned yet)
  push RedemptionInfo{ startTime, shares, assets=b0, baseRate=c0=stEthPerToken() }
  redeeming[user]+=shares; totalRedeeming+=shares // unchecked, non-gating bookkeeping

finalizeRedeem(i)  [nonReentrant, whenNotPaused, validateRedeem]
  require now ≥ startTime + waitingPeriod         // 7 days, read LIVE (not snapshotted)
  bn = TASSET.redeem(shares, this, this)          // burn tETH → IAU to this
  redeeming[user]-=shares; totalRedeeming-=shares
  R  = _getReturnAmount(b0, c0, bn, cn=stEthPerToken())
     = min(b0,bn) · min(c0,cn)/max(c0,cn)         // ≤ min(b0,bn) ≤ bn — always conservative
  fee = R · redemptionFee/1e4      (redemptionFee read LIVE)
  R  -= fee
  require R ≤ b0                                   // dead guard (R ≤ b0 always)
  require underlying.balanceOf(VAULT) ≥ R          // else revert (whole tx unwinds)
  IAU.burn(R)                                       // burns from this (minter)
  RedemptionController.redeem(R, user)              // pulls R wstETH: Vault → user
  IAU.transfer(TASSET, IAU.balanceOf(this))         // leftover (haircut+fee) → remaining holders
  delete entry (swap-and-pop)

RedemptionController.redeem(amt, to)  [whenNotPaused]
  require msg.sender ∈ registered redemption contracts
  underlying.transferFrom(VAULT, to, amt)          // Vault pre-approved Controller for max
```

- **Payout is provably bounded:** `R ≤ min(b0,bn)·(minRate/maxRate) ≤ bn` = the IAU actually backing the redeemed shares. A redeemer can **never** extract more IAU-equivalent than their own shares are currently worth. The haircut and fee both flow back to `TASSET` (remaining holders), not treasury.
- **Vault-drain authority is concentrated in the Controller:** the `Vault` grants `RedemptionController` a `type(uint).max` allowance; the Controller will `transferFrom(VAULT, recipient, amount)` for **any** registered redemption contract, with `amount`/`recipient` fully controlled by that contract. The set of registered redemption contracts is therefore fully trusted with the Vault's liquid balance.
- `owner`/`pauser`/`rescuer` = trusted; `paused()` is inherited from `RedemptionController` (so a Controller pause freezes redemptions here).

---

## How I'd actually attack this (black-hat, every angle)

I treated the 7-day escrow as a challenge and tried to break it from all sides. The negatives matter — they show *why* it holds.

**1. Flash-loan redemption.** Borrow tETH → redeem → profit in one tx. → **Neutralized by design.** The position must be *held for 7 days* between `redeem` and `finalizeRedeem`; no flash loan survives that. Flash loans are irrelevant to this contract.

**2. Snapshot-high, crash-later.** Redeem when NAV is high (lock `b0`), finalize after a negative mark to still get `b0`. → **Blocked.** Payout is `min(b0,bn)` — if NAV falls, `bn<b0` and you get `bn`. You eat your own downside; you can't lock in a stale high value.

**3. Ride the appreciation.** Redeem, then finalize after a positive mark to capture the gain. → **Blocked (and punitive).** `min(b0,bn)=b0`, plus the `minRate/maxRate` ratio (<1, since Lido `stEthPerToken` rises), so you get *less* than `b0`. The appreciation is forfeited to remaining holders (see L-2).

**4. Manipulate `bn` inside my finalize tx (sandwich/flash).** → **No permissionless price mover exists.** tETH price = `IAU.balanceOf(TASSET)`; deposits and redemptions are price-neutral (assets and supply move together), IAU is minter-gated so I can't donate to `TASSET`, and only a privileged, cooldown'd, ≤2.5% *mark* moves price. Nothing to sandwich.

**5. Manipulate the Lido rate `c0/cn`.** → **Not manipulable.** `stEthPerToken()` is Lido's protocol-wide pooled-ETH/shares accounting, not an AMM spot or donation-movable value. The min/max-across-two-snapshots design makes it conservative regardless.

**6. Reentrancy through the value transfers.** `TASSET.redeem`, `IAU.burn`, `Controller.redeem`(wstETH), `IAU.transfer`. → **Blocked.** All callees are plain ERC20s / trusted protocol contracts with no attacker callback; both externals are `nonReentrant`; and share-accounting is decremented before the value transfer (CEI-clean). Even the `InsufficientFundsInVault` revert cleanly unwinds the `TASSET.redeem`, so no half-finalized state.

**7. Double-finalize / index games.** Finalize the same entry twice, or exploit swap-and-pop. → **Blocked.** Each finalize deletes its entry; `nonReentrant` blocks re-entry; arrays are keyed by `msg.sender` (no cross-user access). Swap-and-pop can only make a user revert *their own* second same-block finalize (self-inflicted).

**8. Steal via rounding in `_getReturnAmount`.** → **No leak.** Integer division rounds **down**, always toward the protocol; `c0==cn` cleanly gives ratio 1 (no div-by-zero, `maxC>0`).

What survived are **centralization / in-flight-fairness** issues, plus one **cross-contract drain confirmation**.

### M-1 — Escrowed tETH has no cancel / emergency exit; it can be frozen or seized (Medium)
Once `redeem()` escrows shares, the **only** way out is `finalizeRedeem()`. There is no `cancelRedeem`. Consequences for a user mid-redemption:
- **Pause freeze:** `paused()` follows `RedemptionController` (`:247-249`), and `RedemptionController.setPause(true)` is callable by owner **or** a separate `pauser` key (`RedemptionController.sol:78-79`). A pause blocks `finalizeRedeem`, locking the escrowed tETH indefinitely with no user-side recovery.
- **Rescuer seizure:** `Rescuable.rescueERC20(tETH, attacker, amount)` lets the `rescuer` transfer the **users' escrowed tETH** out of this contract. Unlike the Router (which holds ~0), this contract *custodies* user shares for 7+ days — so the rescuer here is a direct user-fund-seizure path, not just dust recovery.

**Recommend:** add a `cancelRedeem(index)` that returns escrowed tETH to the user (respecting `totalRedeeming`); exclude tETH from `rescueERC20` (or scope the rescuer to non-escrow tokens); put rescuer/pauser behind a multisig/timelock.

### M-2 — Fee and waiting period are applied at finalize, not snapshotted at redeem → retroactive rug/extension (Medium, TOD/centralization)
`finalizeRedeem` reads `redemptionFee` (`:120`) and `waitingPeriod` (`:112`) **live**, but `redeem` snapshots neither (only `startTime`, `shares`, `assets`, `baseRate` are stored, `:86-93`). So the owner can, *after* users have committed and even after they've served the 7 days:
- `setRedemptionFee(1e4)` → 100% fee → `R` becomes 0; the user's shares are consumed and **the entire redemption value is confiscated** to remaining holders. A single owner tx front-running a batch of pending `finalizeRedeem` calls rugs all of them.
- `setWaitingPeriod(365 days)` → extends the lock on already-escrowed positions.

`setRedemptionFee`'s only bound is `≤ PRECISION` (100%, `:166`). **Recommend:** snapshot `fee` (and ideally the effective `waitingPeriod`) into `RedemptionInfo` at `redeem`; cap `redemptionFee` at a sane maximum; consider a timelock on these setters.

### L-1 — Vault-liquidity DoS on finalize (Low, no loss)
If the Vault's liquid wstETH is deployed to strategies, `balanceOf(VAULT) < R` reverts finalize (`:125`). The whole tx unwinds (the `TASSET.redeem` at `:113` is rolled back too — **no corruption, retry-able**), but a user who served 7 days still can't exit until liquidity returns — and with no `cancelRedeem` (M-1), they're stuck waiting. Availability, not loss.

### L-2 — Redeemers systematically forfeit waiting-period yield + a rate haircut (Low / business logic)
The `min(b0,bn)·minRate/maxRate` design (`:220-233`) means redeemers always receive the **worse** of the two NAVs and are additionally scaled by `stEthPerToken_redeem / stEthPerToken_finalize < 1` (Lido rate rises ~0.05–0.07%/week). Net: redeeming forfeits all appreciation during the wait *and* eats a ~yield-sized haircut, on top of `redemptionFee`. Likely intended anti-gaming / holder-value capture, but it's an undocumented hidden haircut — surface it to users, and confirm the rate-ratio double-penalty is intended.

### L-3 — Minor hardening (Low / informational)
- `totalRedeeming += _shares` is `unchecked` and `uint96` (`:95-98`); it and `redeeming[user]` are **bookkeeping only** (gate nothing), so even a (wildly unrealistic ~7.9e10-token) wrap has no security impact — but the checked decrement (`:114-115`) vs unchecked increment is asymmetric; make both checked.
- `PRECISION` is a **mutable storage `uint32`** (`:46`), not `constant` — wastes a slot and an SLOAD per finalize; mark it `constant`.
- Constructor (`:61-66`) sets `VAULT/TASSET/IAU/REDEMPTION_CONTROLLER` with no zero-address checks (immutable → bad deploy bricks permanently).
- Inline `@audit` notes resolved: **no** missing waiting-period check (it's enforced at finalize, `:112`, not redeem — the `:96` note is a false positive); `balanceOf(this)` sweep at `:130` is safe (nonReentrant finalize holds only this redemption's leftover IAU); `c0==cn` at `:227` is handled (ratio 1, no div-by-zero); division at `:232` rounds down toward the protocol (no leak).

### L-4 — `RedemptionController.redeem` recipient assumes a non-blacklisting underlying (Low, conditional)
`Controller.redeem` → `underlying.transferFrom(VAULT, recipient, amount)` (`RedemptionController.sol:50`). For wstETH (no blacklist) this is fine. If the allowable underlying were ever a blacklistable token (USDC-style), a blacklisted `recipient` would revert finalize and trap that user's escrow (again, no `cancelRedeem`). Note for future underlyings.

### Cross-contract confirmation (High severity, *inherited* — this is the sink for `TreehouseAccounting` H-1)
This closes the loop flagged in the Router/Accounting reports. `finalizeRedeem` pays `R` wstETH out of the Vault whenever `balanceOf(VAULT) ≥ R`; it does **not** independently verify that `R` is genuinely backed — it trusts tETH's share price (`IAU.balanceOf(TASSET)`). So an attacker holding the `TreehouseAccounting.{owner,executor}` key can:
1. `mark(MINT, huge, 0)` → unbacked IAU into TASSET → tETH price inflates (`bn`, `b0` inflated).
2. `redeem()` their tETH at the inflated valuation, wait 7 days, `finalizeRedeem()`.
3. `RedemptionController.redeem(R_inflated, attacker)` drains **real wstETH from other users' deposits**, capped only by the Vault's live balance (up to 100%).

RedemptionV2 behaves correctly given a trustworthy NAV — but it is the mechanism that turns the accounting-layer H-1 into an actual vault drain. **The fix belongs upstream** (bound `mark` / remove unbacked mint), but RedemptionV2 could add defense-in-depth by capping system-wide outflow per window or reconciling against a deposit-principal counter.

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Reentrancy | `redeem`/`finalizeRedeem` `nonReentrant`; callees are plain ERC20/trusted; share-accounting decremented before value transfer (CEI). Failed-liquidity revert unwinds cleanly. Safe. |
| Flash Loan | Neutralized by the 7-day hold between redeem and finalize; no atomic redemption exists. |
| Price Oracle Manipulation | tETH price unmovable by permissionless actions; Lido `stEthPerToken` is protocol-wide (not spot/donation-movable); min/max-of-two-snapshots is conservative. |
| Business Logic — payout | `R ≤ min(b0,bn) ≤ bn`; cannot extract more than shares are worth. Haircut/fee → remaining holders. Sound (see L-2 for fairness note). |
| Arithmetic / Overflow-Underflow | 0.8.24 checked math in the payout; the only `unchecked` is non-gating bookkeeping (L-3). Products fit uint256. SafeCast reverts on out-of-range (griefs nobody but the caller). |
| Access Control / Missing Checks | Redeem/finalize permissionless per-user (own array only); setters `onlyOwner`; Controller.redeem gated to registered contracts; Vault outflow behind the Controller allowance. No missing gate. |
| Front-Running / TOD | The real TOD is the **retroactive fee/waiting-period** rug (M-2). No price-sandwich primitive exists (attack #4). |
| Proxy & Upgradeability | Non-upgradeable (immutables + Ownable2Step). Upstream UUPS `TASSET` is out of scope here. |
| Delegatecall / Signature Replay / Randomness / Timestamp | None. Cooldown uses `block.timestamp` vs a 7-day window (±15s irrelevant). N/A. |
| Integer / Short-Address / Uninitialized Storage Pointer | Compiler-handled; no assembly; `_redeem` storage pointer read only before the end-of-function swap-and-pop (no stale read). Not affected. |
| Approval Phishing | Only the contract's own IAU/wstETH flows; no user allowance routed to unexpected sinks. |
| DoS | Vault-liquidity revert (L-1) and pause-freeze/no-cancel (M-1) are the real availability items; no state corruption. |
| Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain — and the **native** on-chain exposure is the escrow-custody centralization: rescuer can seize escrowed tETH, owner/pauser can freeze, owner can retro-rug fees (M-1/M-2). The **inherited** exposure is the H-1 drain sink above. |

---

## Summary

`TreehouseRedemptionV2.sol` is well-constructed on the parts that matter for theft: the 7-day escrow kills flash-loan attacks outright, the `min(b0,bn)·minRate/maxRate` payout provably caps a redeemer at their shares' real worth, rounding always favors the protocol, and reentrancy/CEI are clean. I could not find a way for an ordinary attacker to extract more than they deposited.

The real risks are **custody-centralization** and **in-flight fairness**, plus the **inherited** drain path:

1. **M-1** — escrowed tETH has no cancel/emergency exit; the `rescuer` can seize it and the owner/pauser can freeze it indefinitely. Add `cancelRedeem`, exclude escrow from `rescueERC20`, multisig the privileged keys.
2. **M-2** — `redemptionFee` and `waitingPeriod` are read at finalize, not snapshotted at redeem, so the owner can retroactively confiscate (100% fee) or extend locks on already-committed redemptions. Snapshot the fee at `redeem` and cap it.
3. **L-1…L-4** — vault-liquidity finalize DoS (no loss); undocumented yield/rate haircut; `unchecked`/non-`constant` hygiene and missing zero-checks; blacklisting-underlying assumption in the Controller.
4. **Inherited High (drain sink)** — `finalizeRedeem` pays out inflated NAV from the shared Vault without independent backing verification, realizing the `TreehouseAccounting` H-1 (mint-inflate → redeem → finalize → drain). Fix belongs upstream; add outflow-cap defense-in-depth here.

**Adjacent (dependency, out of file scope):** `RedemptionController` concentrates the Vault's entire liquid balance behind a `type(uint).max` allowance and will pay any registered redemption contract — so registering a buggy/compromised redemption contract, or an inflated `R`, is one `redeem()` call from draining the Vault. Its `setPause` is a two-key (owner **or** pauser) surface, and it is itself `Rescuable`. Keep the registered-redemption set minimal and audited.
