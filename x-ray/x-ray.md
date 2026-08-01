# X-Ray Report

> Treehouse tAsset | 3760 nSLOC | 0cea5cb (`arena/019fbf18-treehouse-bugbounty`) | Foundry | 01/08/26

---

## 1. Protocol Overview

**What it does:** Liquid staking token (tETH) denominated in wstETH that generates extra yield via leveraged LST arbitrage on Aave/Spark/Gearbox/Lido and distributes PnL via ERC4626 share price.

- **Users**: Deposit ETH/WETH/stETH/wstETH to mint tETH, redeem via fastlane (instant 0.5% fee) or normal 7-day queue
- **Core flow**: Router deposits → IAU minted → TAsset shares minted → Vault holds underlying → Strategies deploy via delegatecall actions → NAV calculated → PnlAccounting marks profit/loss to TAsset
- **Key mechanism**: ERC4626 vault with IAU internal accounting unit, NAV via NavRegistry modules, StrategyExecutor delegatecall system with whitelist
- **Token model**: tAsset (ERC4626 share), IAU (internal ERC20 tracking), wstETH underlying, various LSTs allowable
- **Admin model**: Ownable2Step with 5-day timelock per docs, roles: owner/admin, executor (strategy + accounting), blacklister, rescuer/pauser, strategy storage owner

For a visual overview of the protocol's architecture, see the [architecture diagram](architecture.svg).

### Contracts in Scope

| Subsystem | Key Contracts | nSLOC | Role |
|-----------|--------------|------:|------|
| Core Vault | Vault, TAsset, InternalAccountingUnit, TreehouseRouter | 420 | Deposit, share accounting, underlying custody |
| Redemption | TreehouseRedemptionV2, TreehouseFastlane, RedemptionController, FastlaneFee | 450 | 7-day and instant redemption tracks |
| Accounting & NAV | TreehouseAccounting, PnlAccounting, NavRegistry, NavLens, NavHelper, RateProviderRegistry, NavErc20/WithDebt | 800 | PnL marking and NAV calculation |
| Strategy System | Strategy, StrategyStorage, StrategyExecutor, ActionExecutor, ActionRegistry, ProtocolPoolController | 600 | Strategy whitelist and execution |
| Actions | VaultPull/Send, AaveV3Supply/Borrow/Withdraw/Payback, Spark*, Lido*, Gearbox*, HealthFactorCheckers | 1200 | Delegatecall actions operating on strategy |
| Periphery | SimpleStakingERC20, rate providers (Chainlink, Fixed, TEth, WstETH, DWSTETH) | 290 | Fee, staking, pricing |

### How It Fits Together

The core trick: IAU is minted 1:1 with wstETH deposited to Vault, then deposited to TAsset ERC4626; share price appreciates via accounting minting IAU directly to TAsset (profit) or burning (loss), while underlying stays in Vault/Strategies.

### Deposit
```
User → TreehouseRouter.deposit()/depositETH()
├─ WETH → withdraw → ETH → stETH.submit → wstETH.wrap
├─ stETH → wstETH.wrap
├─ wstETH → Vault transfer
└─ IAU.mintTo(Router) → TAsset.deposit(IAU) → tAsset shares to User
   *emits Deposited, checks depositCap*
```

### Normal Redemption (7-day)
```
User → TAsset.approve(RedemptionV2) → RedemptionV2.redeem(shares)
├─ TAsset.transferFrom(User → RedemptionV2)
├─ push RedemptionInfo {startTime, assets=previewRedeem, shares, baseRate=stEthPerToken}
└─ User → RedemptionV2.finalizeRedeem(index) after 7 days
   ├─ TAsset.redeem(shares → IAU)
   ├─ IAU.burn(netReturn)
   ├─ _getReturnAmount(min(b0,bn)*min(c)/max(c)) → fee → net
   └─ RedemptionController.redeem(net, User) → Vault pulls wstETH to User + leftover IAU → TAsset (donation)
```

### Fastlane Instant Redemption
```
User → TAsset.approve(Fastlane) → Fastlane.redeemAndFinalize(shares)
├─ getRedeemableAmount = Vault.wstETH - convertToAssets(totalRedeeming)
├─ TAsset.transferFrom → TAsset.redeem → IAU.burn
└─ RedemptionController.redeem(gross-fee → User, fee → Treasury)
   *0.5% fee capped at 5% via FastlaneFee*
```

### Accounting (PnL)
```
Executor → NavLens.currentProtocolNav() → vaultNav + Σ strategyNav via NavRegistry.getStrategyNav(staticcall modules)
       → PnlAccounting.doAccounting(dynamicParams)
       ├─ lastNav = IAU.balanceOf(TASSET)
       ├─ currentNav = vault + strategies
       ├─ netPnl = |current-last|, maxPnl = deviation*last/1e4 (250=2.5%)
       └─ TreehouseAccounting.mark(MINT+fee → Treasury shares + amount → TASSET totalAssets OR BURN from TASSET)
          *share price up/down*
```

### Strategy Execution
```
Owner → ActionRegistry.addNewContract(id, addr) → StrategyStorage.whitelistActions/Assets()
Executor → StrategyExecutor.executeOnStrategy(strategyId, actionIds, calldata, paramMapping)
├─ checks executor active, strategy active, actions whitelisted
└─ Strategy.callExecute(ACTION_EXECUTOR) → Strategy.execute() delegatecall → ActionExecutor.executeActions()
   └─ for each actionId: delegatecall action contract's executeAction() with paramMapping return injection
      ├─ VaultPull → Vault.withdraw(asset, amount) → Strategy gets funds
      ├─ AaveV3Supply/Borrow/Withdraw etc → external Aave/Spark/Gearbox/Lido
      └─ VaultSend → IERC20.safeTransfer(Vault)
```

---

## 2. Threat & Trust Model

### Protocol Threat Profile

> Protocol classified as: **Yield Aggregator with Liquid Staking** characteristics with **Lending/Borrowing** secondary

Yield aggregator signals: ERC4626 `deposit/withdraw/convertToShares/convertToAssets/totalAssets`, strategy pattern with `vault` and `harvest` via `PnlAccounting`, `harvest` via `mark`. Liquid staking signals: `stETH.submit`, `wstETH.wrap/unwrap`, exchange rate `stEthPerToken`, `getStETHByWstETH`. Lending signals: `AaveV3Supply/Borrow/Payback/Withdraw`, `healthFactorCheck`, E-Mode, `Vault.withdraw`.

### Actors & Adversary Model

| Actor | Trust Level | Capabilities |
|-------|-------------|-------------|
| User/Depositor | Untrusted | Permissionless deposit via Router, redeem via Fastlane/RedemptionV2, transfer tAsset. Cannot mint IAU directly. |
| Owner/Admin | Trusted (Timelock 5-day per docs) | Instant: add/remove minters, set deposit cap, set pause on Router, add/remove allowable assets, set redemption fee up to 100%, set min redeem, waiting period, set treasury/executor, update RateProviders, register Nav modules, attach/detach strategies, whitelist actions/assets, pause/unpause strategies, upgrade TAsset UUPS. Timelock 5-day per spec, but code shows onlyOwner no delay. |
| Executor/Keeper | Bounded (can mint/burn PnL within deviation) | doAccounting (if cooldown passed + deviation OK), executeOnStrategy (if whitelisted), mark via TreehouseAccounting (if owner grants). Can burn TASSET IAU via mark BURN. |
| Blacklister | Bounded (can freeze tAsset transfers) | blacklist/unBlacklist any address, blocking transfer/redeem for that account. |
| Rescuer/Pauser | Bounded (can drain if malicious) | rescueERC20/rescueETH any token from Vault/Router/Redemption contracts (no exclusion), setPause on RedemptionController and PnlAccounting. |
| Strategy (active) | Bounded (can pull allowable assets from Vault) | Vault.withdraw only if isActiveStrategy + asset whitelisted. Holds funds during execution via delegatecall. |

**Adversary Ranking**

1. **Share inflation attacker (first depositor / empty vault)** — ERC4626 vault with donation/burn to zero totalAssets allows tiny deposit to get huge shares, then profit on subsequent large mint/restore.
2. **Compromised Owner/Admin** — Can set 100% redemption fee, blacklist users permanently, add malicious RateProvider inflating NAV, add malicious action, rescue all Vault funds, upgrade TAsset.
3. **Malicious/Compromised Strategy or Executor** — Strategies hold actual funds; executor can run arbitrary whitelisted actions via delegatecall, potentially retaining approvals or reporting fake NAV via module manipulation.
4. **Oracle/RateProvider manipulator** — Chainlink stETH/ETH feed + RateProviderRegistry determines vaultNav and strategy NAV; owner can change provider instantly, no staleness check in TEthRateProvider.
5. **Reentrancy via external callbacks** — VaultPull/Send and Aave/Lido actions make external calls while Strategy state is via delegatecall; token callbacks (ERC777) could re-enter.

See [entry-points.md](entry-points.md) for the full permissionless entry point map.

### Trust Boundaries

- **Owner → Protocol** — 5-day timelock per docs but code onlyOwner with no delay; worst instant actions: `setRedemptionFee(10000)` rug pending 7-day redemptions, `addMinter(attacker)` + `burnFrom(TASSET)` bricks accounting, `rescueERC20` drains Vault via Rescuer role, `update` RateProvider to malicious returning huge rate inflates NAV → mint profit. *Git signal: 1 commit, squashed_import — no history of timelock deployment.*
- **Executor → Accounting** — Deviation 2.5% bounds PnL per window, but executor can call `TreehouseAccounting.mark` directly if also owner, bypassing deviation; worst: burn all IAU from TASSET to 0 → share price 0, depositCap bypass via direct transfer.
- **RedemptionController → Vault** — Trust that only registered redemption contracts pull underlying; Vault approves new redemption unlimited but old approval revoked only via `setRedemption`, not via `removeRedemption` in controller → removed contract could still have allowance until Vault.setRedemption called.
- **NavRegistry → Modules** — Modules are staticcalled to get NAV; if module reverts GetNavFailed reverts whole accounting, DoS. Owner can update module instantly.
- **Strategy → Vault** — Vault trusts isActiveStrategy check; if StrategyStorage compromised, inactive strategy could still be considered active if storage not updated? Actually isActive checked via contains + isActive bool.

### Key Attack Surfaces

- **IAU burnFrom arbitrary & mintTo** &nbsp;[I-1](invariants.md#i-1) — `InternalAccountingUnit.burnFrom:74` + `mintTo:84` onlyMinters, no allowance; minters are trusted contracts but addMinter is onlyOwner → any minter can burn TASSET IAU to 0, bricking `PnlAccounting.maxPnl` and enabling share inflation worth tracing convertToShares path.

- **Rescuable drains core assets** &nbsp;[X-3](invariants.md#x-3) — `Rescuable.rescueERC20:57` in Vault/Router/Fastlane/RedemptionV2 has no exclusion for underlying wstETH or tAsset; owner sets rescuer, rescuer can instantly rescue. Worth checking if rescue of underlying is intended vs only dust.

- **Redemption fee 100% rug** &nbsp;[I-4](invariants.md#i-4), [G-16](invariants.md#g-16) — `TreehouseRedemptionV2.setRedemptionFee:165` caps at 1e4 =100%, pending redemptions locked 7 days; owner can front-run finalize with fee 10000. Worth confirming fee goes to treasury vs donated to TASSET (current code donates leftover to TASSET, inconsistency).

- **Blacklist permanent lock** &nbsp;[X-5](invariants.md#x-5) — `TAsset._update:101` checks notBlacklisted(from,to,msg.sender); `Fastlane.redeemAndFinalize:78` uses safeTransferFrom which triggers _update; blacklisted cannot redeem or transfer. Worth checking escape hatch.

- **Fastlane redeemable estimation manipulation** &nbsp;[E-3](invariants.md#e-3), [I-10](invariants.md#i-10) — `TreehouseFastlane.getRedeemableAmount:91` uses `convertToAssets(totalRedeeming)` which depends on share price that can be inflated via IAU donation to TASSET by minter, causing DoS inflating earmark to 0.

- **Accounting deviation freeze** &nbsp;[G-17](invariants.md#g-17), [E-1](invariants.md#e-1) — `PnlAccounting.doAccounting:68` `maxPnl=deviation*lastNav/1e4`; if lastNav=0 after burn, maxPnl=0 → any currentNav>0 reverts DeviationExceeded, freezing positive PnL. Owner can recover via direct mark, but deviation logic worth checking floor.

- **RateProviderRegistry instant update & no staleness** &nbsp;[X-2](invariants.md#x-2) — `RateProviderRegistry.update:53` onlyOwner instant, `TEthRateProvider.getRate:65` calls Chainlink `latestRoundData` without staleness/answer>0 check; malicious provider can inflate vaultNav → mint huge profit.

- **Strategy delegatecall arbitrary actions** — `Strategy.execute:47` does `delegatecall(sub(gas(),5000), _target, ...)` with empty revert; `ActionRegistry` owner can add malicious action contract, executor can then run it via whitelisted actionId, pulling Vault funds beyond whitelist if action not validating? Worth tracing action whitelist vs asset whitelist separation.

- **Vault allowable asset vs Router conversion mismatch** &nbsp;[X-1](invariants.md#x-1) — `Vault.addAllowableAsset:140` checks hasRateProvider, but `Router._convertToUnderlying:118` only handles WETH/stETH, reverts otherwise → allowable asset can be added but deposit reverts, DoS for that asset.

- **Upgrade and storage** — `TAsset` is UUPS upgradeable with `_authorizeUpgrade onlyOwner`, no timelock in code; implementation uses `__ERC4626_init` etc. Worth confirming storage gaps and initializer disabled.

### Upgrade Architecture Concerns

- **TAsset UUPS upgradeable without timelock in code** — `TAsset._authorizeUpgrade:108` onlyOwner; docs say 5-day timelock but no on-chain timelock contract in scope → upgrade can be instant if owner key compromised.
- **Storage gaps missing?** — OZ upgradeable pattern uses `__Gap` but TAsset inherits multiple upgradeables; need to check storage layout collision between `BlacklistableUpgradeable` and `ERC4626Upgradeable` (both use custom storage slots via ERC7201, okay).
- **Implementation not initialized** — Constructor disables initializers, good.
- **NavRegistry previous addresses single level** — `revertModule` only restores one previous, not full history; if two bad updates, recovery limited.

### Protocol-Type Concerns

**As a Yield Aggregator:**
- **Share price uses `totalAssets+1` / `totalSupply+1` offset 0** &nbsp;[I-6](invariants.md#i-6) — `ERC4626Upgradeable._convertToShares:204` default offset 0 makes first depositor inflation non-profitable for classic donation but reverse burn-to-zero attack still profitable worth checking.
- **totalAssets via `balanceOf` donation attack** — `TAsset.totalAssets()` reads `IAU.balanceOf(this)`; IAU transfer requires minter involvement per `_update:130`, so donation via non-minter impossible, but minter can donate → share price manipulation.
- **Strategy retains approvals after migration** — `StrategyStorage.pauseStrategy` does not revoke token approvals given by Strategy to external protocols (Aave, etc). Old strategy could still pull if approval left.

**As a Liquid Staking:**
- **stETH submit ↔ wstETH wrap conversion no slippage check** — `Router._ethToWsteth:116` calls `stETH.submit{value}()` then `getPooledEthByShares` then `wrap`; if Lido staking paused or rate manipulated, conversion loss not checked.
- **wstETH `stEthPerToken` as baseRate** — `RedemptionV2._getBaseRate:236` uses `stEthPerToken()` which is Lido's internal exchange rate, not Chainlink; assumes Lido honest.

### Temporal Risk Profile

**Deployment & Initialization:**
- **Initializer front-run** — `TAsset.initialize` is `initializer` modifier, but proxy deployment separate from init could be front-run if deployer doesn't atomically init; codebase uses UUPS but deployment script not in scope, can't confirm atomic.
- **Empty vault share inflation** — `totalAssets=0` + `totalSupply>0` after burn allows tiny deposit to get huge shares per `I-6`; no minimum initial deposit enforced.

**Market Stress:**
- **Oracle latency** — `TEthRateProvider.latestRoundData` no staleness check; heartbeat 1h could be stale under volatility → NAV wrong → mint/burn wrong.
- **Liquidity evaporation** — Fastlane relies on Vault idle balance; during stress Vault idle low, fastlane reverts InsufficientFundsInVault, users forced to 7-day queue.
- **Gas spikes** — `NavRegistry.getStrategyNav` loops over modules + dynamic params + `getStrategyNav` staticcalls; with many strategies/modules gas could exceed block limit, bricking accounting when most needed.

**Governance & Upgrade Windows:**
- **Timelock in docs not in code** — Owner can instantly set redemption fee to 100% or rescue, timelock exploitation via queued tx visibility still applies; users cannot exit 7-day locked redemptions before fee hike executes.

---

## 3. Invariants

> ### 📋 Full invariant map: **[invariants.md](invariants.md)**
>
> A dedicated reference file contains the complete invariant analysis — do not look here for the catalog.
>
> - **18 Enforced Guards** (`G-1` … `G-18`) — per-call preconditions with `Check` / `Location` / `Purpose`
> - **12 Single-Contract Invariants** (`I-1` … `I-12`) — Conservation, Bound, Ratio, StateMachine, Temporal
> - **5 Cross-Contract Invariants** (`X-1` … `X-5`) — caller/callee pairs that cross scope boundaries
> - **3 Economic Invariants** (`E-1` … `E-3`) — higher-order properties deriving from `I-N` + `X-N`
>
> Every inferred block cites a concrete Δ-pair, guard-lift + write-sites, state edge, temporal predicate, or NatSpec quote. The **On-chain=No** blocks are the high-signal ones — each is simultaneously an invariant and a potential bug. Attack-surface bullets above cross-link directly into the relevant blocks (e.g. `[X-4]`, `[I-17]`).

---

## 4. Documentation Quality

| Aspect | Status | Notes |
|--------|--------|-------|
| README | Present | `docs/README.md` lists reading order, but not security relevant |
| NatSpec | ~79 annotations | Sparse, mostly interface, missing for critical _getReturnAmount, _convertToUnderlying |
| Spec/Whitepaper | Present | `docs/*.pdf` Treehouse whitepapers, tAsset_Whitepaper, MiCAR; spec extraction shows fees 20% perf, 0.5% fastlane, 0.05% redemption (per TASSET.md) vs code allows 100% |
| Inline Comments | Sparse | Some TODOs? No HACK/FIXME found |

Spec-derived claims tagged per spec: performance fee 20% (per spec) vs code 100% allowed, redemption fee 0.05% (per spec) vs 100% allowed, fastlane 0.5% (per spec) vs 5% max in FastlaneFee.

---

## 5. Test Analysis

| Metric | Value | Source |
|--------|-------|--------|
| Test files | 0 | File scan (always reliable) |
| Test functions | 0 | File scan (always reliable) |
| Line coverage | Unavailable — forge not installed | Coverage tool (requires compilation) |
| Branch coverage | Unavailable — forge not installed | Coverage tool |

### Test Depth

| Category | Count | Contracts Covered |
|----------|-------|-------------------|
| Unit | 0 | none |
| Stateless Fuzz | 0 | none |
| Stateful Fuzz (Foundry) | 0 | none |
| Stateful Fuzz (Echidna) | 0:0 | none |
| Stateful Fuzz (Medusa) | 0:0 | none |
| Formal Verification (Certora) | 0:0 | none |
| Formal Verification (Halmos) | 0:0 | none |
| Formal Verification (HEVM) | 0 | none |

### Gaps

- No test files detected in repo (0). Critical gap: no unit, no fuzz, no invariant, no fork.
- If tests exist elsewhere (private repo), coverage unavailable due to missing forge toolchain in CI.
- Missing formal verification for ERC4626 share math, NAV calculation, rate provider bounds.
- Missing stateful fuzz for deposit/redeem interleavings and strategy execution.
- Missing fork tests for Lido staking, Aave supply/borrow, Chainlink price.
- All security-relevant flows (share inflation, redemption fee rug, rescue) have zero test coverage in this repo.

---

## 6. Developer & Git History

> Repo shape: squashed_import — All source arrived in 1 commit (aee3741); only 2 commits total, 1 touches source files.

### Contributors

| Author | Commits | Source Lines (+/-) | % of Source Changes |
|--------|--------:|--------------------|--------------------:|
| MEDISETTI LAKSHMAN VENKATA PHANI | 1 | +7170 / -0 | 100% |

### Review & Process Signals

| Signal | Value | Assessment |
|--------|-------|------------|
| Unique contributors | 2 | Small team (2 authors but 1 did source) |
| Merge commits | 0 of 2 (0%) | No merge commits — likely no peer review |
| Repo age | 2026-08-01 → 2026-08-02 | 1 day — fresh import, recent burst |
| Recent source activity (30d) | 1 commit | Late burst before audit (initial commit) |
| Test co-change rate | 0% | No test files co-modified |

### File Hotspots

| File | Modifications | Note |
|------|-------------:|------|
| contracts/strategy/libs/TokenUtils.sol | 1 | Initial import only — no churn history |
| All other contracts | 1 | Single import |

### Security-Relevant Commits

No development history — fix detection not applicable (squashed_import). Only commits: aee3741 Initial commit (score 10, adds guards, tightens access, changes accounting across 6 domains), 0cea5cb audit report addition.

### Dangerous Area Evolution

Skipped for squashed_import — only 1 source-touching commit.

### Forked Dependencies

| Library | Path | Upstream | Status | Notes |
|---------|------|----------|--------|-------|
| OpenZeppelin | @openzeppelin/ | OZ v5 | Internalized copy | Custom @openzeppelin/ dir, not submodule — upstream fixes won't auto-propagate |
| Chainlink | @chainlink/ | Chainlink | Internalized copy | Same, internalized |

Internalized libs with no submodule: risk of divergent pragma and missing upstream patches.

### Security Observations

- **Single-dev dominance** — 100% source lines by one author, 2 total authors, no peer review signals.
- **Squashed import** — No evolutionary history, all 7170 lines arrived at once, cannot assess incremental security fixes.
- **No tests in repo** — 0 test files, critical gap for vault/strategy logic.
- **Internalized OZ/Chainlink** — Not submodules, pragma 0.8.24 vs OZ v5 0.8.20, need to verify no modifications.
- **Large initial commit** — 7170 lines, 6 security domains (access_control, fund_flows, liquidation, oracle_price, signatures, state_machines) in one commit, elevated defect density risk.

### Cross-Reference Synthesis

- **TAsset + IAU is #1 in redemption & accounting attack surfaces** → highest-leverage review: _deposit/_withdraw unauthorized check, burnFrom arbitrary, totalAssets via balanceOf, blacklist lock.
- **Vault + RedemptionController approval chain** → X-3 gap: removeRedemption doesn't revoke Vault approval, old redemption contract could still pull.
- **RateProviderRegistry single-owner instant update aligns with X-2** → owner can inflate NAV via malicious provider, then executor mints profit.
- **No test files + squashed import** → Cannot trust that share inflation fix (virtual offset) was tested; need manual verification of _convertToShares.

---

## X-Ray Verdict

**EXPOSED** — Single-dev squashed import with zero tests, internalized OZ, owner can instantly set 100% redemption fee, rescue all vault funds, and minters can burn TASSET to zero bricking accounting.

**Structural facts:**
1. 3760 nSLOC across 6 subsystems, 79 Solidity files, 0 test files, 0 fuzz/invariant/formal verification.
2. 4 actor roles (User, Owner 5-day timelock per docs but no on-chain timelock in code, Executor, Rescuer/Blacklister) with owner having 20+ instant setters + upgrade + rescue + blacklist.
3. UUPS upgradeable TAsset with onlyOwner authorize, no on-chain timelock, internalized OZ v5.
4. ERC4626 share math uses offset 0 (virtual 1 share/asset) which mitigates classic donation but not reverse burn-to-zero inflation.
5. Git history shows squashed_import, 1 source-touching commit, 100% by single author, 0 merge commits, internalized deps.

**Key action items:**
1. Add comprehensive tests + fuzz for share inflation (totalAssets=0, totalSupply>0), redemption fee cap, and NAV deviation.
2. Cap redemption fee at 5% (500 bips) and performance fee at 20% to match spec, add timelock contract on-chain for all owner setters.
3. Exclude underlying/tAsset/IAU from Rescuable or remove Rescuable from Vault/Router/Redemption; enforce Vault approval revocation on removeRedemption.
4. Fix IAU burnFrom to only allow burning from TASSET via dedicated function or require allowance; restrict addMinter to timelock and reduce minter set.
5. Add blacklist redemption escape: allow burning from blacklisted account or forced redemption after compliance.
