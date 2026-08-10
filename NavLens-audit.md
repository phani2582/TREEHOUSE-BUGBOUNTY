# Security Audit — `NavLens.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/periphery/NavLens.sol` (93 LoC)
**Type:** **Stateless, ownerless, immutable view helper.** No admin, no funds, no state, no `delegatecall`. Inherits only `INavLens` (its imports of `Ownable2Step`/`Pausable` are unused).
**Role:** The read layer that `PnlAccounting.doAccounting` calls to get the two numbers a mark compares: `lastRecordedProtocolNav()` (stored) and `currentProtocolNav()` (live). It stitches together the **Vault leg** (`vaultNav` → `NavErc20`) and the **strategy legs** (`strategyNav` → `NavRegistry.getStrategyNav`) into one protocol NAV.
**Where it sits:** `NavRegistry`/`NavErc20`/`Vault`/`StrategyStorage` → **`NavLens`** → `PnlAccounting.doAccounting` → `TreehouseAccounting.mark` → `IAU.balanceOf(TASSET)` = tETH price.
**Dependencies read:** `NavRegistry` (prior audit), `NavErc20`, `PnlAccounting` (consumer), `Vault` (`getAllowableAssets`/`getUnderlying`/`getTAsset`), `StrategyStorage` (`getStrategyCount`/`getStrategyAddress`), `InternalAccountingUnit` (IAU, 18-dec OZ ERC20). Module-ID and STATICCALL-context facts **verified** (`chisel`; Solidity compiles calls to `view` externals as `STATICCALL`).
**Date:** 2026-08-09

---

## Trust model & flow (established, not assumed)

```
doAccounting(dynamicParams[][])  [executor]                       (PnlAccounting:51, NON-view)
  lastNav    = NAV_LENS.lastRecordedProtocolNav()                 // STATICCALL (view fn)
  currentNav = NAV_LENS.currentProtocolNav(dynamicParams)         // STATICCALL (view fn) → whole tree is read-only

NavLens.lastRecordedProtocolNav()                                 (:75-77)
  return IERC20(IAU).balanceOf(T_ASSET)                            // = tETH.totalAssets(); IAU minter-gated

NavLens.vaultNav()                                                (:54-59)
  m = NAV_REGISTRY.getModuleAddress(0x7bc1fd06)                    // 0x7bc1fd06 == bytes4(keccak256("nav(address,address[])"))
  if m == 0 revert NavModuleNotSet
  return INavErc20(m).nav(VAULT, VAULT.getAllowableAssets())       // prices Vault's live balances + VAULT.balance (native ETH)

NavLens.currentProtocolNav(dynamicParams[][])                     (:83-92)
  _nav  = vaultNav()
  n     = STRATEGY_STORAGE.getStrategyCount()                      // append-only; INCLUDES paused strategies
  for i in 0..n:
      _nav += strategyNav(i, dynamicParams[i])                     // dynamicParams[i] positional; OOB reverts if too short
                                                                   //   → NAV_REGISTRY.getStrategyNav(strategyAt(i), params)
```

**The one sentence that governs this file:** NavLens is a pure summation — `vaultNav + Σ strategyNav` — with **no bounds, no `isActive` filter, no per-leg fault isolation, and a positional caller-array coupling**; it originates no trust of its own but is the point where the Vault leg and every strategy leg (including retired ones) are fused into the single number that mints/burns IAU. Everything that can go wrong here is a *concentration* of an upstream property, made concrete at the sum.

- **No privileged roles at all** (positive): nothing to compromise, pause, or misconfigure *in this contract*. All immutables set once at deploy from the Vault.
- **EVM-enforced read-only:** because `currentProtocolNav`/`vaultNav`/`strategyNav`/`lastRecordedProtocolNav` are `view`, `doAccounting` reaches them via `STATICCALL`, and every downstream module call inherits static context → **no write-reentrancy is possible anywhere in the NAV read tree**, even if a module were malicious.

---

## How I'd actually attack this (black-hat, every angle)

**1. Turn a NavLens read into a mint/burn directly.** All four functions are `view`; the only state-changing consumer is `doAccounting` (executor-gated). → No permissionless path from a NavLens call to a price move. Attacking NAV = attacking (a) what a privileged caller can pass, or (b) permissionless *inputs* the sum reads (donations, forced ETH, market state).

**2. Inflate `currentProtocolNav` by double-counting the Vault through a dynamic strategy module.** `currentProtocolNav = vaultNav() + Σ strategyNav()`. `vaultNav` prices the Vault; `strategyNav`'s dynamic path (NavRegistry H-1) lets the caller (executor) hand `NavErc20.nav(target, tokens)` **any** `target`. Point one strategy's dynamic module at the **Vault address** → the Vault's balance is counted **twice** → `currentNav` jumps → MINT unbacked IAU → tETH price up → redeem/drain. → This is the NavRegistry executor-lever, but **NavLens is where the double-count becomes real** (it's the only place vault + strategy legs are added). Bounded per window by `maxPnl`, repeatable each cooldown (M-2 / inherited High).

**3. Donate to the Vault (or force ETH in) to brick accounting.** `vaultNav` → `NavErc20.nav` counts `VAULT.balance` (native ETH) **and** live `balanceOf` of every allowable asset. **Anyone** can `selfdestruct`/coinbase-force ETH into the Vault, or transfer an allowable asset (WETH/stETH/wstETH) to it, with no deposit. → `vaultNav` rises → `currentNav - lastNav > maxPnl` → `doAccounting` reverts `DeviationExceeded` → **marks freeze protocol-wide** until the owner widens `deviation`. Permissionless liveness DoS; the donated funds are genuinely present so no single window absorbs the jump (M-3; the `TreehouseDonationBricksAccounting.t.sol` thesis, here via the Vault leg).

**4. Brick accounting by reverting any single leg.** `currentProtocolNav` is a **hard-revert aggregator** — no try/catch. If `vaultNav` reverts (module unset → `NavModuleNotSet`; or `NavErc20` reverts), or **any** `strategyNav(i)` reverts (Aave underflow when a position is underwater, `NavErc20WithDebt` invariant, claimed Lido NFT, a stale/missing dynamic cd → `MissingDynamicModule`), the **entire** `currentProtocolNav` reverts → `doAccounting` bricks. Several triggers are market- or third-party-reachable. → Protocol-wide accounting DoS (M-1).

**5. Race a strategy addition against the executor's params (positional coupling).** `currentProtocolNav` indexes `dynamicParams[i]` for `i in 0..getStrategyCount()`. Strategies can only be **added** (no remove), so if the owner `storeStrategy`s a new one **between** the executor building its `dynamicParams[][]` and the tx mining, `getStrategyCount()` increments → `dynamicParams[i]` goes **out of bounds** → panic revert → `doAccounting` reverts. → TOD/liveness grief (retry-able; executor rebuilds params). Also: a wrong-length or mis-ordered outer array silently prices the wrong strategy's params against a module (M-2 family).

**6. Reent… no.** `vaultNav` calls `NavErc20` via a **direct typed call**, not the registry's `staticcall` — but `vaultNav` is `view`, so the EVM runs it (and everything it calls) under `STATICCALL`. A malicious `NavErc20`/module therefore **cannot** write state or reenter; worst case it returns a manipulated number (covered by #2/#3) or reverts (#4). → No cross-function/cross-contract/read-only *write* reentrancy through NavLens.

**7. Read-only reentrancy against *external integrators*.** NavLens is a public "lens." If a third-party protocol reads `vaultNav()`/`currentProtocolNav()` as a spot price, it inherits `NavErc20`'s Lido `getWstETHByStETH` and rate-provider reads and the live-`balanceOf` sensitivity — classic read-only-reentrancy / donation staleness for *them*. → No impact on Treehouse (its only consumer is executor-gated), but an integration-safety advisory (Info).

**8. Overflow the sum.** `_nav += ...` in `currentProtocolNav` (`:86`,`:90`) is **checked** math (no `unchecked` here, unlike NavRegistry's inner sum). A wrap would revert, not silently corrupt. → Safe at the NavLens layer; the `unchecked` risk lives one level down in `NavRegistry.getStrategyNav` (its L-1).

What survives are **DoS/liveness concentrations and deploy/robustness hygiene** — plus NavLens being the concrete fusion point of the inherited systemic NAV→mint→drain High. **No High originates in this file.**

---

### M-1 — `currentProtocolNav` is a hard-revert aggregator: any single leg failing bricks all protocol accounting (Medium, DoS)
`currentProtocolNav` (`:83-92`) sums `vaultNav()` plus every `strategyNav(i)` with **no per-leg isolation**. A revert in *any* leg propagates and reverts the whole read, freezing `doAccounting`:
- `vaultNav` reverts if module `0x7bc1fd06` is unregistered (`NavModuleNotSet`, `:56`) or `NavErc20` reverts.
- `strategyNav(i)` reverts on `NavAaveV3` underflow (underwater position), `NavErc20WithDebt` `InvariantViolation`, a claimed/transferred Lido NFT in `NavUnStEth`, or a missing dynamic cd (`MissingDynamicModule`).

Some of these are market-driven or third-party-reachable, so marks can be frozen without any privileged action, and tETH price goes stale (redemptions keep pricing off the last mark) until the owner detaches/repairs the offending module. **Recommend:** this is fixed upstream (per-module try/catch isolation in `NavRegistry` / defined values for edge states in the modules), but NavLens should at minimum let a caller compute per-leg NAV so operators can localize the failing strategy off-chain quickly.

### M-2 — Positional `dynamicParams[i]` ↔ strategy-index coupling + full caller control of dynamic legs (Medium, TOD / inherited NAV manipulation)
`currentProtocolNav` binds the outer array `dynamicParams` to strategy index by position (`dynamicParams[i]`, `:90`) over an **append-only, never-filtered** strategy list. Two consequences:
- **Liveness/TOD:** a `storeStrategy` landing between the executor building params and the tx mining bumps `getStrategyCount()`, pushing `dynamicParams[i]` out of bounds → panic revert → `doAccounting` fails (retry-able, no loss).
- **Manipulation surface (inherited NavRegistry H-1, concrete here):** the executor supplies each strategy's dynamic cd verbatim; because NavLens then **adds the Vault leg and the strategy legs together**, pointing a dynamic module's `target` at the Vault (or a whale) double-counts/invents NAV in the very sum that drives the mint. Bounded per window by `maxPnl`, compounding across cooldowns.

**Recommend:** bind dynamic calldata to the resolved `strategy` in `NavRegistry` (never let the caller choose the priced target); skip `!isActive` strategies (see M-3) and key params by strategyId rather than loop position.

### M-3 — Vault-leg donation / forced-ETH inflation and paused-strategy inclusion (Medium, DoS)
`vaultNav` (`:54-59`) prices the Vault's **live** allowable-asset balances **and** `VAULT.balance` (native ETH, via `NavErc20`). Both are permissionlessly increasable — ERC20 transfer of an allowable asset, or `selfdestruct`/coinbase-forced ETH — with no deposit and no minted IAU, so `currentNav` outruns `lastNav` and trips `DeviationExceeded`, freezing marks. Separately, `currentProtocolNav` iterates **all** strategies including paused ones (no `isActive` check), so retired strategies keep demanding valid params and keep able to revert-brick the sum (M-1) forever. **Recommend:** price *tracked/expected* balances rather than raw `balanceOf`/`.balance`; exclude native ETH unless intended; and skip `!isActive` strategies in the loop.

### L-1 — Hardcoded magic module ID `0x7bc1fd06` with no fallback/configurability (Low, coupling)
`vaultNav` looks up the ERC20 NAV module by the literal `0x7bc1fd06` (`:55`) — verified to be `bytes4(keccak256("nav(address,address[])"))`. If the ERC20 nav module is registered under a different id, or `updateModule(0x7bc1fd06, badAddr)` repoints it, the entire Vault leg (and thus every mark) breaks or misprices, with the id invisible/unchangeable in NavLens. **Recommend:** store the module id as a named immutable/constant with a comment on its derivation, and consider passing it at construction so the lens isn't welded to one magic selector.

### L-2 — Deploy-time hygiene: no zero-checks, cascading immutable, dead code (Low)
The constructor (`:42-49`) resolves `UNDERLYING/T_ASSET/VAULT/IAU` from `_vault` with **no zero/contract validation**; a bad `_vault` bakes in permanently, and since `PnlAccounting` holds `NAV_LENS` as an immutable, a bad NavLens deploy forces redeploying `PnlAccounting` too. Also: `UNDERLYING` is set but **never read** (dead immutable), and the `Ownable2Step`/`Pausable` imports are unused (NavLens inherits only `INavLens`). **Recommend:** validate constructor inputs are non-zero contracts; drop the dead immutable and unused imports.

### L-3 — Denomination/decimal consistency is an unstated protocol assumption (Low, informational)
`lastRecordedProtocolNav` returns `IAU.balanceOf(T_ASSET)` — IAU is a plain OZ `ERC20` (18 decimals, no `decimals()` override) — while `currentProtocolNav` is wstETH-denominated (18) via `NavErc20`. The comparison in `PnlAccounting` is only valid because the underlying is wstETH (18 decimals) and `Vault.addAllowableAsset` caps allowable assets at ≤18 decimals. A future non-18-decimal underlying would desync `lastNav` (IAU, always 18) from `currentNav` (underlying scale) and silently corrupt every mark. **Recommend:** document “underlying MUST be 18-decimal / wstETH-denominated” as an invariant, or normalize explicitly.

### Systemic drain confirmation (High, inherited — NavLens is the fusion point, not the origin)
`doAccounting`’s `currentNav` is produced **entirely** by `NavLens.currentProtocolNav`. So the inflate-NAV → MINT unbacked IAU → inflate tETH → redeem via Fastlane/V2 → drain Vault chain (documented across the Accounting/Redemption/NavRegistry reports) **passes through this file**: NavLens is where the manipulable Vault leg and the executor-controlled strategy legs are summed into the number that mints. NavLens itself is correct given honest inputs and adds no trust; the durable fix is a **hard, reconciled NAV bound** (against deposit principal) in `PnlAccounting`/`NavRegistry`, not a per-window deviation-rate limiter.

---

## Vectors checked and cleared (grouped — full expanded checklist)

NavLens is stateless, ownerless, fund-less, and `STATICCALL`-only, so the overwhelming majority of the expanded list is **structurally N/A**. Grouped honestly:

| Group | Result |
|---|---|
| **Access Control / AuthZ / Privilege Escalation / Role Misconfig** | **No roles, no owner, no mutators.** Nothing to escalate or misconfigure in this contract. All state is immutable-at-deploy. The privileged surface lives in `NavRegistry`/`PnlAccounting` (executor), not here. |
| **Business Logic / State-Machine / Invariant / Protocol-Assumption** | No state machine. The live logic is the `vaultNav + Σ strategyNav` sum: no `isActive` filter (M-3), positional params coupling (M-2), hard-revert aggregation (M-1), and the 18-dec/wstETH denomination assumption (L-3). |
| **Price Oracle / Oracle Reliability / Data Integrity** | NavLens *is* the read aggregator; manipulability (double-count via dynamic cd, donation/forced-ETH) is real but originates upstream (NavRegistry H-1 / NavErc20). Concentrated here at the sum (M-1/M-2/M-3). |
| **Flash-Loan / Economic / Incentive / MEV / Front-run / Back-run / Sandwich / TOD** | No atomic permissionless NAV→state path → no flash-loan or sandwich primitive. The only ordering issue is the benign strategy-add-vs-params TOD (M-2, retry-able). Donations need no loan. |
| **Input Validation / Unchecked & Unsafe External Calls** | Constructor lacks zero/contract checks (L-2). External calls are to trusted in-protocol contracts under `STATICCALL`; `vaultNav` checks the module `!= 0` (`:56`). No value/token transfers. |
| **Reentrancy — cross-fn / cross-contract / read-only** | **Impossible to write-reenter:** all functions `view` → `doAccounting` reaches them via `STATICCALL`, static context propagates to every module call. Read-only reentrancy has no privileged permissionless consumer inside Treehouse; only an *integrator* advisory (Info, attack #7). |
| **Arithmetic / Overflow-Underflow / Precision / Decimal / Fixed-Point** | `currentProtocolNav` sum is **checked** (wrap reverts, not corrupts). No division/rounding/fixed-point here. Decimal consistency is an upstream assumption (L-3). The `unchecked` sum risk is in `NavRegistry`, not NavLens. |
| **Proxy / Upgrade / Init / Storage-Layout / Delegatecall / Diamond** | NavLens is **non-upgradeable, no proxy, no initializer, no `delegatecall`, no storage layout** (only immutables). Entire group N/A. |
| **Collateral / Lending / Liquidation / Health-Factor / Interest / Borrow** | NavLens has no lending logic. It *reads* `NavAaveV3`’s net position (which can underflow-revert → M-1), but performs no liquidation/health math itself. N/A here. |
| **Vault / ERC4626 / Inflation / Donation / Share-Price / Yield / Reward** | NavLens holds no shares and mints nothing. It **reads** `IAU.balanceOf(TASSET)` (the tETH share basis) and the donatable Vault balance (M-3), but the ERC4626/inflation surface is in `TAsset`, not here. |
| **AMM / LP / Liquidity / Fee-calc / IL / JIT** | No AMM/LP/fee logic in this file. N/A. |
| **Token Compatibility — ERC20 non-standard / ERC777 / FoT / rebasing / deflationary** | NavLens does no transfers. It *reads* balances via `NavErc20`; a rebasing/FoT allowable asset would mis-price at the `NavErc20` layer, not here. Native-ETH counting is the one live-balance sensitivity (M-3). |
| **Approvals / Permit / Signatures / EIP-712 / Nonce** | No approvals, no signatures, no permits, no nonces anywhere. Entire group N/A. |
| **Governance / Timelock / Voting / Emergency** | No governance or emergency functions in NavLens. (The `emergency`/pause surface is in `PnlAccounting`/`RedemptionController`.) N/A. |
| **Cross-Chain / Bridge / Validator / Finality** | Single-chain view contract. N/A. |
| **Account Abstraction / ERC-4337 / Paymaster / Intents / Solvers** | None. N/A. |
| **Randomness / Timestamp / Block-Attribute / Crypto / ZK** | No RNG, no `block.*` reads (the cooldown/window lives in `PnlAccounting`), no crypto/ZK. N/A. |
| **DoS — gas / unbounded loops / storage-bloat / forced-revert / dependency** | **The live class.** Unbounded strategy loop that never shrinks and includes paused strategies (M-3, storage-bloat/gas-creep); forced-revert brick via any leg (M-1); dependency-induced DoS from the modules. No state to corrupt. |
| **Integration / External-Dependency / Callback / Hook** | Reads trusted in-protocol contracts; the hardcoded module-id coupling (L-1) and per-leg dependency reverts (M-1) are the integration risks. No external untrusted callbacks/hooks (STATICCALL context). |
| **NFT / ERC721 / ERC1155 / Royalty / Marketplace / Metadata** | NavLens touches no NFTs. (`NavUnStEth` reads Lido withdrawal NFTs, but that’s a separate module.) N/A. |
| **Supply-Chain / Dependency-Compromise / Malicious-Package** | Deps are OZ + in-repo. The de-facto dependency is the ERC20 nav module at `0x7bc1fd06` — pin/audit it (L-1). |
| **Key Compromise / Multisig / Drainers / Approval-Phishing / Social Eng** | No keys or approvals in NavLens. Owner/executor-key risk is upstream. N/A here. |
| **CEX/Web2 / RPC / Frontend / DNS / API-Key** | Off-chain; N/A. Note (attack #7): frontends/integrators reading this lens as a price should treat it as manipulable-by-donation, not a hardened oracle. |
| **AI-assisted / agent-permission / benchmark-poisoning** | Not applicable to on-chain view logic. N/A. |

---

## Summary

`NavLens.sol` is the safest contract in the exit/accounting set to audit in isolation: **no owner, no state, no funds, no `delegatecall`, and EVM-enforced read-only execution** (every consumer reaches its `view` functions via `STATICCALL`, so no write-reentrancy is possible anywhere in the NAV read tree). It originates **no High**. What it does is *concentrate* upstream properties at the point where the Vault leg and all strategy legs are summed:

1. **M-1 (DoS)** — hard-revert aggregation with no per-leg isolation; any single leg reverting (Vault module unset, `NavErc20`/`NavAaveV3`/`WithDebt`/`NavUnStEth` edge states, missing dynamic cd) bricks *all* protocol accounting until the owner intervenes.
2. **M-2 (TOD / inherited manipulation)** — positional `dynamicParams[i]`↔strategy-index coupling over an append-only list (strategy-add races revert `doAccounting`), and full caller control of each strategy’s dynamic cd makes the Vault-leg **double-count** concrete here (the NavRegistry executor-lever, realized at the sum).
3. **M-3 (DoS)** — `vaultNav` prices raw Vault `balanceOf` + native `.balance`, so permissionless donations / forced ETH inflate `currentNav` and trip `DeviationExceeded`; paused strategies are still summed forever (no `isActive` filter).
4. **L-1…L-3** — welded magic module id `0x7bc1fd06` (the `nav` selector) with no fallback; deploy hygiene (no zero-checks, a cascading immutable into `PnlAccounting`, dead `UNDERLYING`, unused `Ownable2Step`/`Pausable` imports); and the unstated 18-decimal/wstETH denomination invariant that keeps `lastNav` and `currentNav` comparable.

**Adjacent (define this lens’s envelope):**
- **`PnlAccounting.doAccounting`** — sole consumer; its `maxPnl` is a *soft per-window rate limit*, the thing that turns any NavLens mis-read into an IAU mint/burn.
- **`NavRegistry.getStrategyNav`** — supplies the strategy legs and the dynamic-cd manipulation surface (its H-1); NavLens is where those legs meet the Vault leg.
- **`NavErc20` + `Vault.getAllowableAssets`** — the donatable/forced-value Vault leg (M-3) and the `0x7bc1fd06` coupling (L-1).
