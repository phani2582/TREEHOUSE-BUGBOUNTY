# Security Audit — `NavRegistry.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/NavRegistry.sol` (264 LoC)
**Type:** Non-upgradeable `Ownable2Step`; the protocol's **NAV oracle / module aggregator**. Holds **no funds**.
**Role:** Two registries in one: (a) a `moduleId → {addr,name}` map of NAV-pricing view contracts (`NavErc20`, `NavErc20WithDebt`, `NavAaveV3`, `NavUnStEth`), and (b) a `strategy → attached-modules + calldata` map. `getStrategyNav(strategy, dynamicParams)` **staticcalls each attached module** with stored (or caller-supplied "dynamic") calldata and **sums the first return word** into `navInUnderlying`.
**Where it feeds:** `NavRegistry.getStrategyNav` → `NavLens.currentProtocolNav` → `PnlAccounting.doAccounting` → `TreehouseAccounting.mark(MINT|BURN)` → `IAU.balanceOf(TASSET)` = **tETH share price**. This contract *is* the number that mints/burns unbacked IAU.
**Dependencies read:** `NavLens`, `PnlAccounting`, `TreehouseAccounting` (consumer chain), all four `modules/nav/*` pricers, `NavErc20`→`RateProviderRegistry`, `StrategyStorage`, `docs/flow.md`, and the in-repo `TreehouseDonationBricksAccounting.t.sol` PoC. Cast/decode semantics **verified live** with `solc`/`chisel`.
**Date:** 2026-08-09

---

## Trust model & flow (established, not assumed)

```
PnlAccounting.doAccounting(dynamicParams[][])   [whenNotPaused, onlyOwnerOrExecutor]   (PnlAccounting:51)
  lastNav    = IAU.balanceOf(TASSET)                                   // stored NAV
  currentNav = NavLens.currentProtocolNav(dynamicParams)              // ← THIS FILE drives it
  netPnl     = |currentNav - lastNav|
  require netPnl ≤ maxPnl() = deviation(250)/1e4 · lastNav            // per-window rate limit only
  MINT netPnl-fee (profit)  |  BURN netPnl (loss)   → moves tETH price

NavLens.currentProtocolNav(dynamicParams[][])                          (NavLens:83)
  nav  = vaultNav()                                                    // NavErc20.nav(Vault, allowableAssets)
  for i in 0..getStrategyCount():                                      // append-only; paused strats INCLUDED
      nav += getStrategyNav( strategyAt(i), dynamicParams[i] )

NavRegistry.getStrategyNav(strategy, dynamicParams[])                  (:225-263)
  for moduleId in _strategyModuleIds[strategy]:                        // EnumerableSet (unique)
    cd = strategyModuleCd[strategy][moduleId]
    if bytes32(cd) != DYNAMIC:                                         // STATIC: owner-attached calldata
        (ok, info) = modules[moduleId].addr.staticcall(cd)            // ← arbitrary target+cd, owner-set
        if !ok revert GetNavFailed
        unchecked { nav += uint(bytes32(info)) }                       // ← FIRST WORD only; wraps
    else:                                                              // DYNAMIC: CALLER supplies cd
        find first dynamicParams[j].moduleId == moduleId
        (ok, info) = modules[moduleId].addr.staticcall(dynamicParams[j].cd)  // ← caller-chosen cd
        if !ok revert GetNavFailed
        unchecked { nav += uint(bytes32(info)) }
        if none matched revert MissingDynamicModule
```

**Verified cast semantics (chisel):**
- `bytes32(bytesMemory)` = **first 32 bytes, right-padded**; empty bytes → `0x0`.
- `uint(bytes32(info))` = **first return word only**. A module returning a `uint` → the value ✓. A module returning a dynamic type (`bytes`/array/struct) → the ABI **offset** `0x20`, *not* the value.
- **`staticcall` to an address with no code returns `success = true` with empty returndata** → decodes to `0`, **no revert**.

**The one sentence that governs this file:** NavRegistry is a *trust-delegating oracle* — it decides tETH's price by summing whatever a set of owner-registered contracts return, under calldata that is **owner-set for static modules and caller-set for dynamic modules**, with **no magnitude bounds, no code-existence check, and no per-module isolation**. Every correctness property lives upstream (the module contracts, the deviation guard); the registry re-checks none of it. It is the `RedemptionController.redeem` / `TreehouseAccounting.mark` delegation pattern applied to *pricing*.

- `owner` (register/update/revert modules, attach/detach/updateParams) and **`executor`** (supplies dynamic calldata every `doAccounting`) are trusted. The executor is the load-bearing surprise — see H-1.

---

## How I'd actually attack this (black-hat, every angle)

**1. Call `getStrategyNav` to move the price directly.** It's a `view` — I can't mint/burn by calling it. → The only *state-changing* consumer is `doAccounting`, gated `onlyOwnerOrExecutor`. So there's no permissionless call that turns a NAV read into a mark. The value of attacking NAV is entirely about what a **privileged caller** or a **permissionless input** (donations, market state) can do to the number `doAccounting` consumes.

**2. Be the executor (or steal its key) and forge NAV through the *dynamic* path.** This is the real one. For any strategy with a dynamic module attached, `getStrategyNav` uses `dynamicParams[j].cd` **verbatim** as the module calldata — the registry never binds that calldata to `strategy`. For `NavErc20`, the canonical cd is `nav(target, tokens)`; the executor picks **both** `target` and `tokens`. So the executor can call `NavErc20.nav(anyWhale_or_theVault, [wstETH])` and have the result **added to protocol NAV**. Point it at the Vault → double-counts Vault holdings; point it at a whale → invents NAV; point it at an empty address → 0. → **Bidirectional NAV control by the executor**, rate-limited *only* by `maxPnl` per window (default 2.5% / hour), and repeatable every cooldown. A hot automation/keeper key thus gets share-price steering — a large privilege *de-escalation* of the "inflate NAV → mint unbacked IAU → drain via redemption" chain from **owner** down to **executor** (H-1).

**3. Register a module at an address with no code (or updateModule to one).** `registerModule`/`updateModule` accept any `addr` incl. `address(0)`/an EOA — no `extcodesize` check. `staticcall` to codeless → `success=true`, `info=""` → `uint(bytes32("")) = 0`. → **Silent 0-NAV** for that module: no revert to catch the misconfig, protocol NAV silently drops by that module's value → next `doAccounting` takes the **BURN** branch → tETH price cut, redeemers short-changed. A self-destructing/mis-migrated module does the same (M-1).

**4. Brick all accounting with a single failing module.** Aggregation is **all-or-nothing**: `if (!success) revert GetNavFailed`. `NavAaveV3:32` does a **checked** `totalCollateralBase - totalDebtBase` → **reverts on underflow** the moment that strategy's Aave position goes underwater; `NavErc20WithDebt:75` reverts `InvariantViolation` if debt>assets; `NavUnStEth:39-40` reverts if a priced Lido NFT is claimed/transferred. Any one of these → `currentProtocolNav` reverts → **`doAccounting` bricked protocol-wide** until the owner detaches the module. Several triggers are **market-driven or third-party-reachable**, not owner-only (M-2).

**5. Donate to a priced address and brick accounting permissionlessly.** `NavErc20` prices `balanceOf(target)` and `target.balance`. **Anyone** can `transfer` wstETH/stETH to a strategy (or the Vault) → `currentProtocolNav` jumps > `maxPnl` → `doAccounting` reverts `DeviationExceeded`. The donated funds are *really there*, so no single window can absorb the jump — accounting stays stuck until the owner widens `deviation`. This is exactly the in-repo `TreehouseDonationBricksAccounting.t.sol` thesis; NavRegistry is the unbounded aggregation surface that lets it through (L-4/M-2 family).

**6. Overflow / truncate the sum.** `nav += uint(bytes32(info))` is `unchecked`. A module returning ~2²⁵⁶ wraps the sum; a module returning >32 bytes or a dynamic type is read as its first word (offset `0x20`), silently mispriced. Realistic values sit far below 2²⁵⁶, so this needs a malicious/compromised module (owner-trust) — but the `unchecked` removes the only backstop (L-1).

**7. Duplicate-moduleId trick in `dynamicParams` (the inline `@audit` note at `:244`).** → **No gate to bypass.** The outer loop is over an `EnumerableSet` (each attached module priced **once**); the inner scan `break`s on the **first** match, so duplicates in `dynamicParams` are simply ignored. The only caller-controlled risk is the *content* of that first matching cd (attack #2), not its multiplicity. The `executed` flag correctly forces `MissingDynamicModule` if no match. Resolved — benign.

**8. Reentrancy / read-only reentrancy.** `getStrategyNav` is `view`/`staticcall` — cannot write state, cannot `delegatecall`. Classic read-only reentrancy needs an *outsider* to force the NAV read mid-callback, but every NAV consumer is either executor-gated (`doAccounting`) or a pure external view. → **No reentrancy exposure through this file.**

What survives is a **NAV-oracle trust-concentration High (with a novel executor lever), silent-mispricing and all-or-nothing DoS Mediums, and robustness/hygiene Lows** — plus the confirmation that this contract is the *oracle root* of the systemic mint-inflate-then-drain chain.

---

### H-1 — NavRegistry is the trusted NAV oracle with unbounded, caller-influenced returns; the *dynamic* path hands share-price control to the executor (High, systemic / centralization)
`getStrategyNav` (`:225-263`) sums `uint(bytes32(info))` from staticcalls whose **magnitude is never bounded** and whose **calldata is caller-supplied on the dynamic branch** (`:246-258`), and this sum flows straight into `PnlAccounting.doAccounting` → `TreehouseAccounting.mark` → tETH price. Two escalation facts make this High rather than "expected owner trust":
- **Executor, not just owner, can manipulate NAV.** The dynamic calldata (`dynamicParams[j].cd`) is used verbatim and is **not bound to `strategy`**. For `NavErc20`, the executor freely chooses the priced `target` and `tokens`, so it can over-report (price the Vault/a whale — double-count or invent NAV) or under-report (price an empty address → 0). The `executor` is a hot automation role set by `updateExecutor` — a far more exposed key than `owner`. This drops the entire "inflate NAV → mint unbacked IAU → redeem → drain Vault" chain (documented as the systemic High in the Accounting/Redemption reports) from an owner-only capability to an **executor-key** capability.
- **The only limiter is a soft, per-window rate cap.** `maxPnl = deviation·lastNav/1e4` (default 2.5%) bounds a *single* window, but `doAccounting` can run every `cooldown` (min 60s, default 1h). A malicious/compromised executor drifts the price 2.5%/window, compounding — no absolute bound, no reconciliation against real deposits.

**Recommend:** bind dynamic calldata to the strategy in-contract (e.g. the registry constructs `nav(strategy, …)` and only lets the caller supply the genuinely-variable tail such as Lido request IDs — never the target); add absolute sanity bounds per module and per protocol NAV; require the mark to reconcile against a deposit-principal counter; and treat the executor as a drain-capable role (multisig + tight monitoring), not a bot key.

### M-1 — No code-existence / returndata check before `staticcall` → silent 0-NAV mispricing (Medium)
`registerModule` (`:109-118`) and `updateModule` (`:126-136`) accept any `addr` including `address(0)` and EOAs — no `_addr.code.length > 0` check — and `getStrategyNav`'s `staticcall` (`:233`, `:248`) treats **`success=true` + empty returndata** (the EVM result for a codeless target) as a valid `0` (`uint(bytes32("")) == 0`, verified). So a module pointed at an undeployed CREATE2 address, an EOA, or a self-destructed contract **silently contributes 0** instead of reverting — protocol NAV drops by that module's true value with **no error to surface the misconfig**, and the next `doAccounting` takes the **BURN** branch, cutting tETH price and short-changing redeemers. **Recommend:** require `code.length > 0` on register/update/attach, and in `getStrategyNav` require `info.length >= 32` (reject empty/short returndata) so a dead module reverts loudly instead of mispricing silently.

### M-2 — All-or-nothing aggregation: one attached module reverting bricks *all* protocol accounting (Medium, DoS)
`getStrategyNav` reverts the **entire** call if any single module staticcall fails (`:237`, `:249`) or a dynamic cd is missing (`:260`), and `NavLens.currentProtocolNav` sums every strategy with no isolation, so one bad module → `doAccounting` reverts protocol-wide. Reachable triggers that are **not** owner-only:
- `NavAaveV3:32` — **checked** `totalCollateralBase - totalDebtBase` underflows and reverts the instant a strategy's Aave position is underwater (market-/oracle-driven; an attacker manipulating Aave can force it).
- `NavErc20WithDebt:75` — `InvariantViolation` when debt>assets.
- `NavUnStEth:39-40` — reverts if a priced Lido withdrawal NFT is `isClaimed` or no longer owner-held (a third party's claim between windows can trip it).
- Donation → `DeviationExceeded` in `doAccounting` (permissionless; see L-4).

Any of these **freezes marks** (tETH price goes stale, redemptions keep using the last mark) until the owner detaches/repairs the offending module. **Recommend:** isolate per-module failures (try/catch with an explicit, logged fallback or skip-with-flag rather than a hard revert), and give `NavAaveV3`/`WithDebt` a defined value (e.g. 0 or signed handling) for underwater positions instead of reverting.

### M-3 — Strategies are never removed and paused ones are still priced → perpetual brittle NAV loop + gas creep (Medium)
`StrategyStorage` has **no `removeStrategy`** (only `pauseStrategy` flipping `isActive=false`, `:155-158`), and `NavLens.currentProtocolNav` (`:83-92`) iterates `0..getStrategyCount()` **without checking `isActive`**. So once added, a strategy is priced **forever**: it must be given a `dynamicParams[i]` entry every window, and if any of its modules ever starts reverting (its Aave position closed, its Lido NFT claimed, its dynamic cd stale), it bricks accounting per M-2 — even though the strategy is "retired." The loop also grows unbounded over the protocol's life, trending `doAccounting` toward the block gas limit. **Recommend:** skip `!isActive` strategies in the NAV loop (or add a real `removeStrategy`/decommission path), and cap/prune the iterated set.

### L-1 — `unchecked` NAV summation + first-word-only decode (Low, robustness)
`nav += uint(bytes32(info))` (`:239-241`, `:251-253`) is `unchecked` (overflow wraps — needs a malicious/compromised module, but the guard is gone), and `bytes32(info)` reads **only the first return word** (verified): a module returning a dynamic type/struct yields the ABI **offset** (`0x20`), not the value — a silent misread. **Recommend:** drop `unchecked` on the aggregate (the per-call values are small; the checked add is cheap insurance), and `abi.decode(info,(uint))` after a length check instead of a raw `bytes32` cast.

### L-2 — `DYNAMIC` sentinel is multiplexed in-band into the `cd` field (Low, design)
The static/dynamic decision is `bytes32(cd) != DYNAMIC` (`:232`) — a magic 32-byte value packed into the same `bytes` slot that otherwise holds real calldata. It works because real calldata (4-byte selector + args) won't collide with `keccak256('NavRegistry.dynamic')`, and the owner sets static cd deliberately — but overloading a data field as a type flag is fragile. **Recommend:** store an explicit `bool isDynamic` (or an enum) on the attachment struct rather than encoding it into `cd`. (Inline `@audit` at `:244` resolved under attack #7 — duplicate `dynamicParams` are benign.)

### L-3 — Module bookkeeping & missing zero/contract validation (Low, hygiene, feeds M-1)
- `registerModule`/`updateModule`/`attachTo`/`updateParams` perform **no zero-address or contract-code checks** on `addr`/`newAddr`/`strategy` (`:114`, `:132`, `:165`, `:186`) — the root enabler of M-1.
- `revertModule` (`:143-155`) restores `modules[id].addr` from `previousModuleAddresses[id]` but **doesn't refresh `previousModuleAddresses` or `name`** — after a revert the human-readable `name` still describes the *faulty* module, and there's no true toggle (a second `revertModule` is a no-op to the same address). `updateModule` also overwrites `previousModuleAddresses` on every call, so only one level of rollback exists.
- `AddNewContract`/`UpdateContract` events omit the `name`. **Recommend:** add `code.length > 0` + non-zero guards; keep `name` and `previousModuleAddresses` consistent through `revertModule`.

### L-4 — Donation-driven `DeviationExceeded` brick (Low here / systemic; NavRegistry is the aggregation point)
Because `NavErc20` prices raw `balanceOf(target)`/`target.balance` and `getStrategyNav` aggregates it with **no sanity bound**, a permissionless token donation to any priced address inflates `currentProtocolNav` past `maxPnl` → `doAccounting` reverts `DeviationExceeded` (the `TreehouseDonationBricksAccounting.t.sol` scenario). No funds lost, but marks stall until the owner widens `deviation`. Root cause is shared with `NavErc20`/`PnlAccounting`; the registry's contribution is unbounded aggregation. **Recommend:** price *tracked/expected* balances rather than live `balanceOf`, or clamp per-window deltas instead of hard-reverting.

### Systemic drain confirmation (High, inherited — this is the *oracle root* of the mint-inflate chain)
This closes the loop from the Accounting/Redemption reports. `IAU.balanceOf(TASSET)` (tETH price) is moved by `doAccounting`, whose `currentNav` is **entirely produced by this file**. So NavRegistry is where the "unbacked NAV" originates:
1. Over-report NAV — via the executor's dynamic cd (H-1), a donation (L-4), or an owner-registered malicious module — so `currentNav > lastNav` by ≤`maxPnl`.
2. `doAccounting` **MINTs** unbacked IAU into `TASSET` → tETH price inflates.
3. Redeem the attacker's tETH at the inflated price via `TreehouseFastlane` (atomic, no wait) or `TreehouseRedemptionV2` → `RedemptionController.redeem` pulls **real wstETH** from the Vault (the prior-report drain sink).

NavRegistry behaves correctly given honest modules and honest calldata, but it is the mechanism that decides the price, and it delegates that trust to owner+executor with only a soft per-window cap. **The durable fix is a hard, reconciled NAV bound** (against deposit principal) rather than a deviation-rate limiter — enforced here or in `PnlAccounting`.

---

## Vectors checked and cleared (full checklist)

| Vector | Result |
|---|---|
| **Access Control** | `registerModule`/`updateModule`/`revertModule`/`attachTo`/`detachFrom`/`updateParams`/`transferOwnership` → `onlyOwner`; getters are `view`. Correctly gated. The risk is *delegated* trust (H-1), and the **executor's** NAV influence via the dynamic path — an under-appreciated privileged surface. |
| **Missing Access Control** | No externally-reachable state mutator is ungated. `getStrategyNav` is `view`; it can only *move funds* via the executor-gated `doAccounting` downstream. |
| **Business Logic** | Aggregation logic is thin and that *is* the issue: no magnitude bounds, no strategy-binding of dynamic cd, all-or-nothing failure, paused strategies still priced (H-1/M-2/M-3). |
| **Price Oracle Manipulation** | **This is the oracle.** Manipulable by the executor (dynamic cd, H-1), permissionlessly by donation (L-4), and by owner-registered modules. tETH price flows from here — the central finding. |
| **Flash Loan** | No atomic permissionless path reads NAV into a state change (only executor-gated `doAccounting`), so a flash loan can't turn a NAV swing into profit within one tx. Donations to brick accounting don't need a loan. Neutral-to-DoS, not a theft primitive here. |
| **Input Validation** | Missing zero/contract checks on module/strategy addresses (L-3, feeds M-1); dynamic cd entirely unvalidated (H-1); no returndata-length check (M-1). |
| **Unchecked External Calls** | `staticcall` return `success` **is** checked (`:237`,`:249`) — but codeless-target `success=true`+empty is mis-accepted as `0` (M-1). No `SafeERC20`/value calls (it's a pure registry). |
| **Arithmetic Errors** | Aggregate `+=` is `unchecked` (wrap; L-1); first-word `bytes32` decode truncates multi-word returns (L-1). Downstream `NavAaveV3` checked subtraction underflows underwater (M-2). |
| **Reentrancy** | `getStrategyNav` is `view`/`staticcall` — no state writes, no `delegatecall`. All NAV consumers are executor-gated or pure views, so no read-only-reentrancy hook for outsiders. Safe. |
| **Integer Overflow/Underflow** | 0.8.24 checked math except the two `unchecked` NAV adds (L-1). No counters. |
| **Proxy & Upgradeability** | NavRegistry is non-upgradeable (Ownable2Step, no proxy/`delegatecall`). The referenced modules are plain immutable view contracts. Residual coupling is the upstream UUPS `TASSET` (out of file scope). |
| **Front-Running / TOD** | `getStrategyNav` is a view; `doAccounting` is executor-gated with a cooldown → no permissionless ordering game. NAV *inputs* (donations, Aave state) can be moved by anyone to grief marks (M-2/L-4), not to extract value by ordering. |
| **DoS** | The dominant native class: single-module-revert brick (M-2), donation `DeviationExceeded` brick (L-4), never-shrinking/paused-still-priced loop + gas creep (M-3), silent 0-NAV (M-1). No state corruption. |
| **Insecure Randomness** | No RNG anywhere. N/A. |
| **Timestamp Manipulation** | No `block.timestamp`/`block.number` in this file (the window/cooldown lives in `PnlAccounting`, ±15s irrelevant vs a ≥60s cooldown). N/A. |
| **Delegatecall to Untrusted Callee** | No `delegatecall` — module calls are `staticcall` (read-only, cannot mutate registry state). Not present. |
| **Signature Replay** | No signatures, permits, or nonces. N/A. |
| **Short Address / Parameter** | ABI decoding is compiler-handled (≥0.8); the only manual decode is `bytes32(info)` first-word extraction (L-1), not calldata parsing. Negligible. |
| **Uninitialized Storage Pointer** | Mappings/`EnumerableSet`/arrays handled by OZ; no dangling `storage` pointer. `Entry`/`Enumerable` structs written whole. Not affected. |
| **Approval Phishing** | No token approvals — the contract holds and moves no assets. N/A. |
| **Multisig Hijacking** | `owner` should be a multisig (register-malicious-module = NAV control). Newly emphasized: **`executor` also needs multisig/tight control** (H-1) — it's a NAV-manipulation key, not merely a keeper. |
| **Private Key Compromise** | `owner` compromise ⇒ malicious module → NAV → mint/drain. **`executor` compromise ⇒ same NAV manipulation via dynamic cd (H-1)** — the more likely hot-key breach. Timelock owner; harden executor. |
| **Supply Chain** | Deps are OZ + in-repo module contracts. Each **registered module** is effectively a pricing oracle dependency — pin, audit, and make them immutable; a swapped/upgradeable/destructible module silently mis-prices (M-1). |
| **Drainer Malware** | No client/signing surface in-contract; the on-chain equivalents are owner- or executor-key compromise (above). Hardware-backed multisig for both, plus rescuer elsewhere. |
| **CEX & Web2 Infrastructure** | Off-chain; not applicable beyond the executor/owner key-custody guidance. |

---

## Summary

`NavRegistry.sol` holds no funds and is Solidity-level clean (gated setters, checked staticcall `success`, `EnumerableSet` correctness, two-step ownership). Its risk is **architectural: it is the protocol's price oracle, and it delegates all trust** — summing whatever a set of registered contracts return, under calldata that is owner-set for static modules and **caller-set for dynamic modules**, with **no magnitude bounds, no code-existence check, and no per-module fault isolation.**

1. **H-1 (High, systemic)** — the NAV that mints/burns unbacked IAU (tETH price) is produced here with no absolute bound, and the **dynamic-module path lets the executor supply arbitrary calldata — including the address being priced** — so a hot **executor** key (not just the owner) can steer share price, limited only by a soft per-window deviation cap. This is the oracle root of the inflate-NAV → mint → redeem → drain chain and de-escalates it from owner to executor.
2. **M-1 (Medium)** — no `code.length`/returndata check before `staticcall`; a module at an empty/EOA/destructed address returns `success`+empty → silently priced as **0** → BURN mispricing with no revert to catch it.
3. **M-2 (Medium, DoS)** — all-or-nothing aggregation: one attached module reverting (Aave underflow when underwater, `WithDebt` invariant, claimed Lido NFT, stale dynamic cd) **bricks all protocol accounting** until the owner detaches it; several triggers are market- or third-party-reachable.
4. **M-3 (Medium)** — strategies are never removed and paused ones are still priced, so the NAV loop is perpetual and brittle (M-2 forever) and grows toward the gas limit.
5. **L-1…L-4** — `unchecked` sum + first-word-only decode; in-band `DYNAMIC` sentinel; missing zero/contract validation and `revertModule` name/rollback bookkeeping; permissionless donation `DeviationExceeded` brick.

**Adjacent (out of file scope, but they define this oracle's envelope):**
- **`PnlAccounting.doAccounting`** is the sole state-changing consumer; its `maxPnl` deviation guard is a **soft per-window rate limit, not an absolute bound**, and it is the executor-gated trigger that turns any NAV mis-read here into an IAU mint/burn.
- **`NavErc20`/`NavErc20WithDebt`/`NavAaveV3`/`NavUnStEth`** price live `balanceOf`/on-chain positions with internal `unchecked` math and hard reverts on edge states — they supply both the donation-inflation (L-4) and the revert-brick (M-2) surfaces this registry aggregates.
- **`StrategyStorage`** has no `removeStrategy` and, unrelated to this audit, its `isActiveStrategy` (`:216-217`) is missing a closing brace in the reviewed source (its docblock runs into `isAssetWhitelisted`) — flag for the core-contracts pass.
