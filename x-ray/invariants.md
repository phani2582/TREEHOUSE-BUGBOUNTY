# Invariant Map

> Treehouse tAsset | 18 guards | 12 inferred | 5 not enforced on-chain

---

## 1. Enforced Guards (Reference)

#### G-1
`if (!_minters.contains(msg.sender)) revert NotMinter()` · `InternalAccountingUnit.sol:32` · Enforces only minters can mint/burn IAU

#### G-2
`if (!(_minters.contains(from) || _minters.contains(to) || _minters.contains(msg.sender))) revert Unauthorized()` · `InternalAccountingUnit.sol:130` · Restricts IAU transfers to involve a minter

#### G-3
`if (!IInternalAccountingUnit(asset()).isMinter(caller)) revert Unauthorized()` · `TAsset.sol:46,56` · Only IAU minters can deposit/withdraw underlying via ERC4626

#### G-4
`if (_isBlacklisted(_account)) revert AccountBlacklisted()` · `BlacklistableUpgradeable.sol:28` · Prevents blacklisted from transferring tAsset

#### G-5
`if (strategyStorage.isActiveStrategy(msg.sender) && isAssetWhitelisted) else revert InvalidStrategy()` · `Vault.sol:64` · Only active whitelisted strategies can pull from vault

#### G-6
`if (_redemptionContracts.contains(msg.sender)==false) revert Unauthorized()` · `RedemptionController.sol:48` · Only registered redemption contracts can pull underlying from vault

#### G-7
`if (VAULT.isAllowableAsset(_asset)==false) revert NotAllowableAsset()` · `TreehouseRouter.sol:81` · Deposit only allowable assets

#### G-8
`if (_getUnderlyingInEth(IERC20(IAU).totalSupply()) > depositCapInEth) revert DepositCapExceeded()` · `TreehouseRouter.sol:115` · Enforces deposit cap in ETH terms

#### G-9
`if (_shares==0) revert NoSharesMinted()` · `TreehouseRouter.sol:86,104` · Prevents zero-share deposit

#### G-10
`if (_assets < minRedeemInUnderlying) revert MinimumNotMet()` · `TreehouseFastlane.sol:73` · Minimum for fastlane redeem

#### G-11
`if (getRedeemableAmount() < _assets) revert InsufficientFundsInVault()` · `TreehouseFastlane.sol:74` · Fastlane only redeemable if vault has enough beyond earmark

#### G-12
`if (_assets < minRedeemInUnderlying) revert MinimumNotMet()` · `TreehouseRedemptionV2.sol:83` · Minimum for normal redemption

#### G-13
`if (block.timestamp < _redeem.startTime + waitingPeriod) revert InWaitingPeriod()` · `TreehouseRedemptionV2.sol:110` · Enforces 7-day wait

#### G-14
`if (_returnAmount > _redeem.assets) revert RedemptionError()` · `TreehouseRedemptionV2.sol:120` · Return cannot exceed initial preview

#### G-15
`if (IERC20(_underlying).balanceOf(VAULT) < _returnAmount) revert InsufficientFundsInVault()` · `TreehouseRedemptionV2.sol:122` · Finalize requires vault liquidity

#### G-16
`if (_newFee > PRECISION) revert FeeExceeded()` · `TreehouseRedemptionV2.sol:130` · Redemption fee max 100% (1e4)

#### G-17
`if (_netPnl > maxPnl()) revert DeviationExceeded()` · `PnlAccounting.sol:68` · PnL per window bounded by deviation * lastNav

#### G-18
`if (block.timestamp < nextWindow) revert StillInWaitingPeriod()` · `PnlAccounting.sol:62` · Cooldown between accounting

---

## 2. Inferred Invariants (Single-Contract)

#### I-1

`Conservation` · On-chain: **Yes**

> IAU totalSupply == Σ IAU balanceOf

**Derivation** — Δ-pair: `InternalAccountingUnit.sol:84 mintTo Δ(totalSupply)=+_mintAmount ↔ Δ(balanceOf[_mintAddress])=+_mintAmount`; `74 burnFrom Δ(totalSupply)=-_burnAmount ↔ Δ(balanceOf[_burnAddress])=-_burnAmount`

**If violated** — Accounting desync, share price wrong

#### I-2

`Conservation` · On-chain: **Yes**

> TAsset totalAssets == IAU.balanceOf(TASSET)

**Derivation** — Δ-pair: ERC4626 `totalAssets() = IAU.balanceOf(address(this))` per `ERC4626Upgradeable.sol:96`. Any mint/burn of IAU to/from TASSET changes both `totalAssets` implicitly and `IAU.balanceOf(TASSET)`.

**If violated** — Share price misreported

#### I-3

`Bound` · On-chain: **Yes**

> Fastlane fee ∈ [0,500] (5%)

**Derivation** — guard-lift: `FastlaneFee.sol:43 require(_newFee <=500)` enforced at only writer `setFee:41`. All write sites checked via grep `fee =` → only one writer.

**If violated** — Excessive fee drains user

#### I-4

`Bound` · On-chain: **No**

> Redemption fee ∈ [0,10000] allows 100%

**Derivation** — guard-lift: `TreehouseRedemptionV2.sol:130 require(_newFee <= PRECISION)` where PRECISION=1e4. Writer only `setRedemptionFee`. On-chain=No because 100% (=10000) passes guard and is effectively rug, no lower bound enforced beyond protocol intent of 0.05%.

**If violated** — Owner can rug pending redemptions (7-day lock then 100% fee)

#### I-5

`Bound` · On-chain: **No**

> TreehouseAccounting fee ∈ [0,10000] allows 100%

**Derivation** — guard-lift: `TreehouseAccounting.sol:90 require(_newFee <= PRECISION)` but NatSpec says performance fee 20%. Single writer `setFee`. On-chain=No because upper bound too high vs spec.

**If violated** — All PnL goes to treasury

#### I-6

`Ratio` · On-chain: **Yes**

> convertToShares(assets) = assets * (totalSupply+1)/(totalAssets+1)

**Derivation** — Δ-pair from `ERC4626Upgradeable.sol:204` `_convertToShares: assets.mulDiv(totalSupply+10**offset, totalAssets+1)`. Offset 0 → +1.

**If violated** — Share inflation attack

#### I-7

`Ratio` · On-chain: **Yes**

> convertToAssets(shares) = shares * (totalAssets+1)/(totalSupply+1)

**Derivation** — `ERC4626Upgradeable.sol:210` `_convertToAssets`.

**If violated** — Redemption value wrong

#### I-8

`Temporal` · On-chain: **Yes**

> finalizeRedeem allowed only after startTime+waitingPeriod

**Derivation** — guard: `TreehouseRedemptionV2.sol:110 require(block.timestamp >= startTime+waitingPeriod)` enforced at only finalization path.

**If violated** — Bypass 7-day wait, fast outflow

#### I-9

`StateMachine` · On-chain: **Yes**

> Strategy active: true → pauseStrategy → false → unpauseStrategy → true

**Derivation** — edge: `StrategyStorage.sol:135 isActive=false @L false` → `140 isActive=true`. No latch, togglable but guarded by onlyOwner.

**If violated** — Inactive strategy could still withdraw

#### I-10

`Conservation` · On-chain: **No**

> totalRedeeming shares == Σ redeeming[users] (?) Not enforced

**Derivation** — Δ-pair: `TreehouseRedemptionV2.sol:87 redeeming[msg.sender] += _shares` paired with `totalRedeeming += _shares`; finalize subtracts both. But `redeeming` mapping not summed and compared to `totalRedeeming` automatically, and no check that `totalRedeeming` equals sum of array lengths? On-chain=No gap if array manipulation via _deleteRedeemEntry swap-pop could desync if reverted? Actually swap-pop maintains sum? Still, invariant not explicitly enforced.

**If violated** — getRedeemableAmount uses totalRedeeming to earmark vault, mismatch could allow fastlane to drain reserved for pending redemptions

#### I-11

`Bound` · On-chain: **Yes**

> depositCapInEth >= _getUnderlyingInEth(IAU.totalSupply) after deposit

**Derivation** — guard-lift: `TreehouseRouter.sol:115 _checkEthCap` enforced at end of deposit/depositETH after mint. All deposit paths check.

**If violated** — Cap bypass via direct transfer to vault not minting IAU

#### I-12

`Conservation` · On-chain: **No**

> Vault underlying balance + strategies NAV ≈ IAU.totalSupply (mod fees)

**Derivation** — No single function enforces; lastRecordedProtocolNav = IAU.balanceOf(TASSET) while currentProtocolNav = vaultNav + strategyNav. Delta only via PnlAccounting.doAccounting which does deviation check, not equality.

**If violated** — Share price drifts from real backing

---

## 3. Inferred Invariants (Cross-Contract)

#### X-1

On-chain: **No**

> Router.deposit assumes isAllowableAsset implies rate provider exists

**Caller side** — `TreehouseRouter.sol:81 isAllowableAsset` → then `_convertToUnderlying` only handles WETH/stETH/underlying, reverts ConversionToUnderlyingFailed for other allowable assets

**Callee side** — `Vault.sol:140 addAllowableAsset` checks `RATE_PROVIDER_REGISTRY.checkHasRateProvider` but `isAllowableAsset` can be true for assets not handled by Router

**If violated** — Deposit of allowable asset (e.g., sAVAX) would revert despite being allowed, DoS

#### X-2

On-chain: **No**

> NavLens.vaultNav assumes NavRegistry module 0x7bc1fd06 registered

**Caller side** — `NavLens.sol:39 getModuleAddress(0x7bc1fd06)` → if 0 reverts NavModuleNotSet

**Callee side** — `NavRegistry.sol:109 registerModule` onlyOwner, can be unregistered? No unregister, but updateModule can set to zero address? Actually updateModule sets newAddr, could be zero, causing vaultNav to call address(0).nav → revert.

**If violated** — Accounting bricks

#### X-3

On-chain: **Yes**

> RedemptionController.redeem assumes Vault approved redemption contracts

**Caller side** — `RedemptionController.sol:50 safeTransferFrom(VAULT, recipient, amount)` requires allowance

**Callee side** — `Vault.sol:86 setRedemption` approves new redemption unlimited and revokes old via approve(0). Also `RedemptionController` removal doesn't revoke Vault approval? Actually Vault.setRedemption revokes old, but RedemptionController.removeRedemption does not call Vault.setRedemption, so Vault still approves removed redemption contract until owner calls setRedemption. Gap?

**If violated** — Removed redemption contract could still pull from Vault if Vault approval not revoked

#### X-4

On-chain: **No**

> TreehouseAccounting.mark assumes caller is minter of IAU and can deposit fee to TASSET

**Caller side** — `TreehouseAccounting.sol:73 mintTo(this)` + `74 TASSET.deposit(_fee, treasury)` requires Accounting is IAU minter (checked in TAsset._deposit) and has approval (constructor approves max).

**Callee side** — `InternalAccountingUnit.sol:93 addMinter` onlyOwner; if Accounting minter role removed, mark() will revert Unauthorized in TAsset._deposit and IAU.mintTo

**If violated** — PnL accounting fails, share price frozen

#### X-5

On-chain: **No**

> TAsset blacklist assumes redemption contracts can still burn

**Caller side** — `TreehouseFastlane.sol:78 safeTransferFrom(msg.sender)` triggers TAsset._update which checks notBlacklisted(from,to,msg.sender). If user blacklisted, transferFrom reverts AccountBlacklisted.

**Callee side** — `BlacklistableUpgradeable.sol:68 blacklist` onlyBlacklister can set. No exception for redemption.

**If violated** — Blacklisted user funds permanently locked, cannot redeem

---

## 4. Economic Invariants

#### E-1

On-chain: **No**

> Share price monotonic non-decreasing except via BURN mark, bounded by PnL deviation

**Follows from** — I-6 + I-7 + I-12 + G-17 + G-18

**If violated** — Inflation attack via burning TAsset IAU to 0 then small deposit gets huge shares (see I-6), then large mint restores value profitably

#### E-2

On-chain: **No**

> Deposit cap prevents vault oversubscription beyond available arbitrage

**Follows from** — I-11 + X-1

**If violated** — Direct wstETH transfer to Vault inflates Vault balance without increasing IAU.totalSupply, bypassing cap check, making getRedeemableAmount overstate free liquidity

#### E-3

On-chain: **No**

> Fastlane redeemable = Vault balance - earmark for pending normal redemptions

**Follows from** — G-11 + I-10 + X-3

**If violated** — If totalRedeeming conversion uses share price that can be inflated via donation to TASSET (minter can transfer IAU to TASSET increasing totalAssets without minting shares), earmark inflated → fastlane DoS. Conversely, if Vault balance inflated via direct transfer, redeemable overstates and can drain funds reserved for normal redemptions.
