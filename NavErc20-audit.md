# Security Audit — `NavErc20.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/modules/nav/NavErc20.sol` (60 LoC)
**Type:** **Stateless, ownerless, immutable NAV pricing module.** No admin, no funds, no state, no `delegatecall`. Two immutables (`wstETH`, `RATE_PROVIDER_REGISTRY`); one `view` function `nav`.
**Role:** The **pricing engine for the Vault leg** of protocol NAV. `NavLens.vaultNav()` resolves this module by the hardcoded id `0x7bc1fd06` and calls `nav(VAULT, Vault.getAllowableAssets())`; `NavRegistry.getStrategyNav` also drives it for strategy legs (static path with stored cd, or the executor-controlled **dynamic** path with caller-supplied `(target, tokens)`). It sums a target's native ETH + each ERC20's `balanceOf`, priced to **wstETH terms**.
**Where it sits:** `RateProviderRegistry`→ rate providers (Chainlink/wstETH/tETH/Gearbox) → **`NavErc20`** → `NavLens.vaultNav`/`NavRegistry.getStrategyNav` → `PnlAccounting.doAccounting` → `TreehouseAccounting.mark` → `IAU.balanceOf(TASSET)` = tETH price.
**Dependencies read:** `RateProviderRegistry` (+ all 6 providers: `ChainlinkRateProvider`, `WstETHRateProvider`, `FixedRateProvider`, `TEthRateProvider`, `TEthExchangeRateProvider`, `DWSTETHV3RateProvider`), Lido `IwstETH`, `Vault` (`getAllowableAssets`/`addAllowableAsset` decimal rule), `NavErc20WithDebt` (sibling), `NavHelper` (twin math), `NavLens`/`NavRegistry` (consumers — prior audits).
**Date:** 2026-08-10

---

## Trust model & flow (established, not assumed)

```
NavErc20.nav(_target, _tokens[])   [view → STATICCALL]                         (:37-59)
  _nav  = _target.balance                          // native ETH, added 1:1 (force-feedable via selfdestruct)
  wstETHBalance = 0
  for t in _tokens:
      wip = IERC20(t).balanceOf(_target)           // LIVE balance — donation-inflatable
      if wip == 0: continue
      unchecked {
        if t == wstETH:        wstETHBalance = wip  // ASSIGNMENT (idempotent under dups) — held aside in wstETH terms
        elif t == wstETH.stETH(): _nav += wip       // stETH added 1:1 (accumulates → dups double-count)
        else:  _nav += getRateInEth(t) * wip / 1e18 // asset→ETH via registry (accumulates; 18-dec ASSUMED; unchecked mul)
      }
  _nav = wstETH.getWstETHByStETH(_nav) + wstETHBalance   // stETH-sum → wstETH, then add wstETH held aside
                                                          // ⇒ implicit assumption: 1 ETH == 1 stETH for the non-wstETH legs

RateProviderRegistry.getRateInEth(asset)   [view]                              (:38-43)
  if asset == WETH: return 1e18                    // WETH hardcoded 1:1
  if rateProviders[asset] == 0: revert RateProviderNotFound
  return IRateProvider(rateProviders[asset]).getRate()   // owner-set provider; value BLINDLY trusted

ChainlinkRateProvider.getRate()   [view]                                       (:45-49)
  (,price,,,) = feed.latestRoundData(); require price > 0; return price * scale
  // NO updatedAt staleness check, NO answeredInRound/roundId completeness check, NO L2 sequencer check
```

**The one sentence that governs this file:** NavErc20 is an honest arithmetic summer of **whatever `balanceOf`/`.balance`/`getRateInEth` hand it** — it validates none of the three (magnitude, freshness, decimals), so every correctness property is delegated upward to the token balances (donation-controllable), the native balance (force-feedable), and the owner-set rate providers (unguarded for staleness). It is the point where all three manipulable inputs enter the NAV that mints tETH.

- **No privileged roles, no state, no funds** (positive): nothing to escalate, pause, or reinitialize *in this contract*.
- **EVM-enforced read-only:** `nav` is `view` and reached via `STATICCALL` from every consumer → no write-reentrancy anywhere in this tree, even with a malicious token/provider (worst case: manipulated number or revert).
- **Denomination:** output is wstETH-terms (18-dec), matching `IAU.balanceOf(TASSET)` in the accounting comparison — correct *for 18-decimal assets under the stETH≈ETH peg* (both are load-bearing assumptions; see M-2 / L-2).

---

## How I'd actually attack this (black-hat, every angle)

**1. Move NAV directly with a permissionless action.** `nav` is `view`; the only state consumer is `doAccounting` (executor-gated). So I can't call my way to a mint. I attack the **inputs** the sum reads without permission: the target's token balances, its native balance, and the freshness of the rate.

**2. Donate an allowable asset to the Vault → inflate the Vault leg.** `wip = balanceOf(_target)` is the **live** balance (`:43`). Anyone can `transfer` wstETH/stETH/an allowable asset to the Vault with no deposit and no minted IAU. → `nav` rises → `currentProtocolNav` outruns `lastRecordedProtocolNav`. Either it's within `maxPnl` (an attacker gifts NAV that mints tETH to *existing* holders — grief/donation) or it exceeds it and `doAccounting` reverts `DeviationExceeded` → **accounting bricks protocol-wide** until the owner widens `deviation`. This is exactly the in-repo `TreehouseDonationBricksAccounting` PoC, and **`:43` is the line that prices it** (M-3).

**3. Force native ETH in — the cheapest force-feed.** `_nav += _target.balance` (`:38`) counts native ETH. Even if the Vault never holds ETH by design, I can `selfdestruct(vault)` or coinbase-transfer ETH in — no token, no allowlist, no approval. → same inflation/brick as #2, but requires no allowable token at all (M-3).

**4. Ride a stale or manipulated rate.** `getRateInEth` (`:52`) is trusted with **zero** sanity checks, and `ChainlinkRateProvider.getRate` ignores `updatedAt` and `answeredInRound` — a frozen/stale feed keeps returning its last value, and an L2 sequencer outage isn't detected. → For any non-wstETH/non-stETH allowable asset, its price can be stale or (for a thin feed) market-manipulable, and NavErc20 will mint/burn against it without flinching (M-1). `TEthRateProvider` is worse — it doesn't even check `answer > 0`, so a zero/negative feed round yields `uint(answer)` = 0 or ~2²⁵⁶.

**5. Wait for a non-18-decimal allowable asset, then desync NAV.** `getRateInEth(t) * wip / 1e18` (`:52`) assumes `wip` is 18-decimal. The Vault's `addAllowableAsset` only rejects `> 18` decimals (`Vault.sol:141`), so an 8-dec (WBTC-style) or 6-dec asset is admissible — and would be **under-counted by 10^(18−dec)** (e.g. ×10⁻¹² for a 6-dec token). → The instant governance adds such an asset (with a matching provider), the Vault leg silently misprices. A black-hat watches the allowlist governance tx and front-runs the desync (M-2, latent/config-gated).

**6. Double-count via the dynamic path's caller-supplied token list.** The stETH/other branches **accumulate** (`+=`), and NavErc20 does **not** dedupe `_tokens`. Via `NavLens.vaultNav` the list is `Vault.getAllowableAssets()` (an `EnumerableSet` → no dups, safe). But via `NavRegistry.getStrategyNav`'s dynamic path the executor supplies `_tokens` verbatim → passing `[stETH, stETH, …]` double-counts stETH each time. → An executor-lever NAV inflation (the NavRegistry H-1, realized here). (wstETH dups are *safe* — the `wstETHBalance = wip` **assignment** at `:48` is idempotent, so the inline `@audit` there resolves benign.) (L-2).

**7. Overflow the price silently.** `getRateInEth(t) * wip` sits inside `unchecked` (`:46-52`). A misconfigured or compromised rate provider returning a huge value wraps mod 2²⁵⁶ **without reverting** → arbitrary NAV instead of a safe revert. Owner-set providers are trusted, but the `unchecked` turns a provider bug into silent corruption rather than a fail-closed (L-1).

**8. Break the stETH-peg assumption.** Native ETH and every ETH-priced asset are converted to wstETH via `getWstETHByStETH` (`:58`), i.e. treated as if **1 ETH = 1 stETH**. During a stETH depeg they're mispriced — and NavErc20 diverges from `NavHelper`, which converts ETH→stETH via the *rate* first (`NavHelper.sol:168-169`). Two protocol NAV paths, two answers under stress (L-3).

**9. Recursive/reflexive pricing.** `TEthRateProvider`/`TEthExchangeRateProvider`/`DWSTETHV3RateProvider` price via `ERC4626.convertToAssets(1e18)` — and tETH's `convertToAssets` is a function of `IAU.balanceOf(TASSET)`, *the very NAV this loop feeds*. If any tETH-derivative is ever an allowable asset or a priced strategy holding, NAV becomes self-referential (a mark moves the price that the next mark reads) (L-4, latent/config-gated).

**10. Reentrancy / proxy / signatures / AA / cross-chain / NFT / governance.** None present — stateless `view` module, no `delegatecall`, no proxy, no signatures, no funds. Structurally N/A (table below).

What survives are **oracle-reliability, decimal-scaling, and donation/force-feed inflation issues** — plus NavErc20 being the concrete pricing engine through which the inherited systemic NAV→mint→drain High is realized. **No standalone theft primitive originates in the module's own arithmetic; the danger is that it trusts inputs no one else bounds.**

---

### M-1 — `getRateInEth` is blindly trusted; rate providers have no staleness / round-completeness / bounds checks (Medium, oracle reliability)
NavErc20 prices every non-wstETH/non-stETH asset at `getRateInEth(t) * wip / 1e18` (`:52`) and consumes the result with **no** sanity check (no min/max, no zero-guard, no freshness). The registry (`RateProviderRegistry.sol:38-43`) forwards `provider.getRate()` verbatim, and the providers are unguarded:
- **`ChainlinkRateProvider.getRate` (`:45-49`)** reads `latestRoundData()` but uses only `price > 0` — it **ignores `updatedAt`** (staleness), **ignores `answeredInRound`/`roundId`** (incomplete round), and has **no L2 sequencer-uptime check**. A frozen feed returns its last value indefinitely; NavErc20 mints/burns against it.
- **`TEthRateProvider.getRate` (`:61-64`)** takes `uint(answer)` from `latestRoundData()` with **no `answer > 0` check** → a 0/negative round yields 0 or ~2²⁵⁶.

Because this value flows straight into `doAccounting`'s mint/burn, a stale or thin-feed-manipulated rate is a direct NAV-integrity failure. **Recommend:** validate `updatedAt` against a per-feed heartbeat + `answeredInRound >= roundId` in `ChainlinkRateProvider`, add an L2 sequencer check where relevant, add `answer > 0` in `TEthRateProvider`, and have NavErc20/registry bound or sanity-check returned rates (reject 0 / absurd magnitudes) rather than blindly trusting them.

### M-2 — `rate * wip / 1e18` assumes 18-decimal tokens; the Vault admits ≤18-dec allowable assets → silent under-count (Medium, decimal scaling, latent/config-gated)
The pricing formula (`:52`) treats `wip = balanceOf` as an 18-decimal quantity — but nothing normalizes for the token's own decimals, and `Vault.addAllowableAsset` (`Vault.sol:140-146`) only rejects assets with **more** than 18 decimals. So a 6- or 8-decimal allowable asset is admissible and would be under-valued by `10^(18 − decimals)` (e.g. a 6-dec asset contributes 10⁻¹² of its true NAV). The guard and the math disagree: the Vault says "≤18 is fine," the pricing says "must be exactly 18." Today the protocol is wstETH/stETH-centric (all 18-dec) so it doesn't fire — but the moment governance whitelists a non-18-dec asset, the Vault leg desyncs, under-reporting NAV (and `NavHelper` shares the identical flaw at `NavHelper.sol:186`). **Recommend:** either enforce `decimals() == 18` in `addAllowableAsset`, or normalize by token decimals in the pricing (`* 10^(18-dec)`), and add a test that adds a <18-dec asset and asserts NAV correctness.

### M-3 — Prices raw `balanceOf` + native `.balance` with no tracked/earmarked notion → permissionless donation & force-feed inflation (Medium, DoS / NAV inflation)
`nav` values the target's **live** ERC20 balances (`:43`) and native ETH (`:38`) with no concept of "expected" vs "donated." Both are permissionlessly increasable — an ERC20 `transfer` of an allowable asset, or `selfdestruct`/coinbase-forced ETH — with no deposit and no IAU minted. The inflated Vault leg either mints tETH backed by an attacker's gift (griefing existing holders) or, more usefully to an attacker, pushes `currentNav − lastNav` past `maxPnl` so `doAccounting` reverts `DeviationExceeded` and **all** marks freeze protocol-wide (the `TreehouseDonationBricksAccounting.t.sol` result, priced right here at `:38`/`:43`). Native ETH is the cheapest vector — it needs no allowable token at all. **Recommend:** price *tracked* balances (a deposit-accounted figure) rather than raw `balanceOf`; drop native `.balance` from the sum unless the Vault is intended to custody ETH; and (defense-in-depth) replace `PnlAccounting`'s per-window deviation rate-limit with a hard reconciled NAV bound so a genuine donation can't brick liveness.

### L-1 — `rate * wip` inside `unchecked` → a misbehaving provider corrupts NAV silently instead of failing closed (Low, robustness)
The multiplication at `:52` (and `:46-54` block) is `unchecked`, so a rate provider returning a huge value wraps mod 2²⁵⁶ with no revert, producing an arbitrary NAV rather than a safe failure. Providers are owner-set/trusted, but this converts a provider bug or misconfiguration into silent accounting corruption. **Recommend:** perform the `rate * wip` multiplication in checked math (or bound the rate), reserving `unchecked` only for the provably-safe additions.

### L-2 — No dedup of `_tokens`; accumulating branches double-count in the caller-controlled dynamic path (Low, inherited executor lever)
The stETH branch (`:50`) and the else/rate branch (`:52`) use `+=`, and `_tokens` is never de-duplicated. Under `NavLens.vaultNav` the list is `Vault.getAllowableAssets()` (`EnumerableSet`, no dups → safe), but under `NavRegistry.getStrategyNav`'s dynamic path the executor supplies `_tokens` verbatim, so a list like `[stETH, stETH]` double-counts. This is the NavRegistry H-1 executor lever surfacing in the pricing math. (The wstETH branch's `wstETHBalance = wip` **assignment** at `:48` is idempotent, so duplicate wstETH is *not* a bug — the inline `@audit` note there resolves benign.) **Recommend:** dedupe `_tokens` (or reject duplicates) in NavErc20, and — the durable fix — bind the priced `target`/`tokens` to the resolved strategy in `NavRegistry` rather than accepting them from the caller.

### L-3 — Implicit "1 ETH = 1 stETH" peg assumption, and divergence from `NavHelper` (Low, mispricing under depeg)
Native ETH and every ETH-priced asset are folded into `_nav` and converted to wstETH via `getWstETHByStETH` at `:58` — i.e. their ETH value is treated as a stETH value (1:1). Under a stETH depeg this misprices those legs, and NavErc20 disagrees with `NavHelper`, which first converts ETH→stETH via the rate (`NavHelper.sol:168-169`) — so the accounting path (NavErc20) and the helper path report different NAVs precisely when stETH is stressed. **Recommend:** make the ETH→stETH treatment explicit and consistent across both paths (convert via the stETH rate, or document the peg assumption as an accepted invariant), so a depeg doesn't silently split the two NAV figures.

### L-4 — Reflexive pricing risk if any tETH-derivative is ever priced here (Low, latent/config-gated)
`TEthRateProvider`/`TEthExchangeRateProvider`/`DWSTETHV3RateProvider` derive their rate from `ERC4626.convertToAssets(1e18)`; for tETH that value is a function of `IAU.balanceOf(TASSET)` — the same protocol NAV this loop feeds. If a tETH-derivative is ever registered as an allowable asset or a priced strategy holding, a mark would move the price the next mark reads (self-referential NAV). Not triggerable today, but the providers exist. **Recommend:** never register a tETH-derivative for pricing through this module; if unavoidable, break the cycle with an independent (non-`convertToAssets`) valuation.

### Systemic drain confirmation (High, inherited — NavErc20 is the pricing engine, not the origin)
NavErc20 is the module `NavLens.vaultNav` resolves at `0x7bc1fd06` and the workhorse of `NavRegistry.getStrategyNav`, so the entire inflate-NAV → MINT unbacked IAU → inflate tETH → redeem via Fastlane/V2 → drain Vault chain **is priced here**: this loop is where donation-controlled balances, force-feedable native ETH, and unguarded oracle rates enter the number that mints. The module's arithmetic is honest given honest inputs and adds no trust of its own; the durable fix is upstream — a **hard, reconciled NAV bound** in `PnlAccounting`/`NavRegistry` plus **input hardening** (tracked balances, staleness-checked oracles) — not a per-window deviation rate-limiter.

---

## Vectors checked and cleared (grouped — full expanded checklist)

NavErc20 is stateless, ownerless, fund-less, `view`/`STATICCALL`-only, non-upgradeable, with no signatures/callbacks. Most of the expanded list is **structurally N/A**. Grouped honestly:

| Group | Result |
|---|---|
| **Access Control / AuthZ / Privilege Escalation / Role Misconfig** | **No roles, no owner, no mutators, no state.** Nothing to escalate or misconfigure here. Privilege lives in `RateProviderRegistry.update` (owner-set providers) and the `NavRegistry`/`PnlAccounting` executor, not in this module. |
| **Business Logic / State-Machine / Invariant / Protocol-Assumption** | No state machine. The live logic is the `Σ balances → wstETH` sum: peg assumption (L-3), decimal assumption (M-2), dynamic-path dedup (L-2), reflexive pricing (L-4). The wstETH-held-aside vs stETH-conversion split is **correct** (no double-count). |
| **Price Oracle / Oracle Reliability / Data Integrity** | **The core live class.** `getRateInEth` blindly trusted; providers lack staleness/round/bounds checks (M-1); balances donation-inflatable (M-3); unchecked mul (L-1); reflexive tETH pricing (L-4). This module is where oracle risk concentrates. |
| **Flash-Loan / Economic / MEV / Front-run / Back-run / Sandwich / TOD** | No atomic permissionless NAV→state path in-module → no flash-loan/sandwich primitive here. The MEV-flavored angle is front-running a *governance* allowlist change to hit the decimal desync (M-2) or a stale-feed window (M-1). Donations need no loan. |
| **Input Validation / Unchecked & Unsafe External Calls** | No zero/code checks on `_tokens[i]` — but a codeless address → `balanceOf` returns empty → decodes 0 → skipped (harmless). `getRateInEth` result unvalidated (M-1) and multiplied `unchecked` (L-1). All external calls are `view` to trusted Lido/registry. No value transfers. |
| **Reentrancy — cross-fn / cross-contract / read-only** | **Impossible to write-reenter:** `nav` is `view` → `STATICCALL`; static context propagates to every token/provider call. Read-only reentrancy has no privileged permissionless consumer in-protocol (only `doAccounting`); external-integrator advisory only (attack #10 / Info). |
| **Arithmetic / Overflow-Underflow / Precision / Decimal / Fixed-Point** | Decimal scaling is the real bug (M-2); `unchecked` mul can wrap silently (L-1); rounding is down (`/1e18`) — no over-count from rounding. The additions are safe in range for realistic balances. |
| **Proxy / Upgrade / Init / Storage-Layout / Delegatecall / Diamond** | Non-upgradeable, no proxy, no initializer, no `delegatecall`, no storage layout (two immutables only). Entire group N/A. |
| **Collateral / Lending / Liquidation / Health-Factor / Borrow** | No lending logic in this module. (Debt/underwater handling lives in the sibling `NavErc20WithDebt` and `NavAaveV3`.) N/A here. |
| **Vault / ERC4626 / Inflation / Donation / Share-Price / Yield** | NavErc20 holds no shares and mints nothing. It **reads** the donatable Vault balance (M-3); the ERC4626 share-price surface is in `TAsset`. The reflexive-`convertToAssets` risk is L-4. |
| **AMM / LP / Liquidity / Fee-calc / IL / JIT** | No AMM/LP/fee logic. N/A. |
| **Token Compatibility — non-standard ERC20 / ERC777 / FoT / rebasing / deflationary** | Pure `balanceOf` read (no transfers) → FoT/deflationary irrelevant to a price read; rebasing (stETH) is intentionally captured by live `balanceOf`. ERC777 callbacks can't fire on a `view` read. The one compatibility bite is **non-18-decimals** (M-2). |
| **Approvals / Permit / Signatures / EIP-712 / Nonce** | No approvals, signatures, permits, or nonces anywhere. Entire group N/A. |
| **Governance / Timelock / Voting / Emergency** | No governance in-module. Adjacent governance action that matters: `RateProviderRegistry.update` (repoint a provider) and `Vault.addAllowableAsset` (introduce M-2). Timelock those. |
| **Cross-Chain / Bridge / Validator / Finality** | Single-chain view module. N/A (except the L2-sequencer note folded into M-1 for Chainlink providers). |
| **Account Abstraction / ERC-4337 / Paymaster / Intents / Solvers** | None. N/A. |
| **Randomness / Timestamp / Block-Attribute / Crypto / ZK** | No RNG, no `block.*`, no crypto/ZK in-module. (Timestamp *should* be read — for oracle staleness — and isn't; that absence is M-1.) |
| **DoS — gas / unbounded loops / storage-bloat / forced-revert / dependency** | Loop is bounded by the allowable-asset set (owner-controlled, small). The real availability item is donation/force-feed → `DeviationExceeded` brick downstream (M-3), and provider reverts propagating up (dependency DoS, akin to NavLens M-1). No state to bloat. |
| **Integration / External-Dependency / Callback / Hook** | Depends on Lido `wstETH` (trusted) and owner-set rate providers (M-1/L-1 the integration risks). No untrusted callbacks/hooks (STATICCALL context). |
| **NFT / ERC721 / ERC1155 / Royalty** | No NFTs in this module (Lido withdrawal NFTs live in `NavUnStEth`). N/A. |
| **Supply-Chain / Dependency-Compromise / Malicious-Package** | Deps are OZ + Lido + in-repo. The de-facto dependencies are the **registered rate providers** — pin/audit each; a compromised provider silently corrupts NAV (L-1/M-1). |
| **Key Compromise / Multisig / Drainers / Approval-Phishing / Social Eng** | No keys/approvals in-module. The relevant key is the `RateProviderRegistry` owner (can repoint a provider → mispriced NAV) and the accounting executor — multisig/timelock upstream. N/A here. |
| **CEX/Web2 / RPC / Frontend / DNS / API-Key** | Off-chain; N/A. Note (attack #10): integrators reading `NavErc20.nav` as a spot price should treat it as donation-inflatable and staleness-exposed, not a hardened oracle. |
| **AI-assisted / agent-permission / benchmark-poisoning** | Not applicable to on-chain view logic. N/A. |

---

## Summary

`NavErc20.sol` is a small, stateless, ownerless `view` pricing module, and at the Solidity level its own arithmetic is sound: wstETH is correctly held aside from the stETH→wstETH conversion (no double-count), rounding is down (no over-count), and it's `STATICCALL`-only so **no reentrancy/proxy/signature class applies**. It originates **no standalone theft primitive and no High.** Its risk is that it is an *honest summer of inputs nobody bounds*, and it is the pricing engine for the Vault leg of protocol NAV:

1. **M-1 (oracle reliability)** — `getRateInEth` is trusted with zero checks, and the rate providers behind it lack staleness / round-completeness / sequencer / `answer>0` guards (`ChainlinkRateProvider`, `TEthRateProvider`). Stale or thin-feed-manipulated prices flow straight into mint/burn.
2. **M-2 (decimal scaling, latent)** — `rate * wip / 1e18` assumes 18 decimals, but `Vault.addAllowableAsset` admits ≤18-dec assets; a non-18-dec allowable asset is under-counted by `10^(18−dec)` the moment governance adds it (`NavHelper` shares the flaw).
3. **M-3 (donation / native-ETH force-feed)** — prices raw `balanceOf` + `.balance`, so permissionless donations or forced ETH inflate the Vault leg → mint unbacked tETH or trip `DeviationExceeded` and brick accounting (the in-repo donation-brick PoC, priced at `:38`/`:43`).
4. **L-1…L-4** — `unchecked` multiplication lets a bad provider corrupt NAV silently rather than fail closed; no `_tokens` dedup makes the accumulating branches double-count in the caller-controlled dynamic path (NavRegistry executor lever); an implicit "1 ETH = 1 stETH" peg treatment that diverges from `NavHelper` under a depeg; and a latent reflexive-pricing cycle if any tETH-derivative (`convertToAssets`-based provider) is ever priced here.
5. **Inherited High** — NavErc20 is where donation-controlled balances, force-feedable native ETH, and unguarded oracle rates enter the number that mints tETH; the systemic NAV→mint→drain chain is *priced* in this loop. Fix upstream (hard reconciled NAV bound) **and** here (tracked balances, staleness-checked oracles, checked math, decimal normalization).

**Adjacent (define this module's envelope):**
- **`RateProviderRegistry` + the 6 providers** — the actual oracle surface; `ChainlinkRateProvider`/`TEthRateProvider` need staleness/`answer>0`/sequencer guards (M-1). `update` (repoint a provider) is an owner action to timelock.
- **`Vault.addAllowableAsset` (`Vault.sol:140-146`)** — its "≤18 decimals" rule is what makes M-2 reachable; tightening it to `==18` closes the decimal desync at the source.
- **`NavHelper.sol`** — a twin of this math that shares the decimal (M-2) and peg (L-3) issues and additionally diverges on the ETH→stETH conversion; keep the two in sync or consolidate.
- **`NavErc20WithDebt`** — the sibling with the same asset-pricing loop plus a checked debt subtraction (`InvariantViolation` when debt > nav), which is a *revert-brick* leg for the NavLens aggregator (its M-1).
