# 🔐 Security Review — TREEHOUSE-BUGBOUNTY

---

## Scope

|                                  |                                                        |
| -------------------------------- | ------------------------------------------------------ |
| **Mode**                         | ALL                                                    |
| **Files reviewed**               | `InternalAccountingUnit.sol` · `TAsset.sol` · `Vault.sol`<br>`TreehouseRouter.sol` · `TreehouseRedemptionV2.sol` · `TreehouseFastlane.sol`<br>`RedemptionController.sol` · `TreehouseAccounting.sol` · `PnlAccounting.sol`<br>`NavRegistry.sol` · `NavLens.sol` · `NavHelper.sol`<br>`RateProviderRegistry.sol` · `TEthRateProvider.sol` · `ChainlinkRateProvider.sol`<br>`WstETHRateProvider.sol` · `FixedRateProvider.sol` · `DWSTETHV3RateProvider.sol`<br>`FastlaneFee.sol` · `SimpleStakingERC20.sol` · `BlacklistableUpgradeable.sol`<br>`Rescuable.sol` · `Strategy.sol` · `StrategyStorage.sol`<br>`StrategyExecutor.sol` · `ActionExecutor.sol` · `ActionRegistry.sol`<br>`ProtocolPoolController.sol` · `TokenUtils.sol` · `VaultPull.sol`<br>`VaultSend.sol` · `AaveV3Supply.sol` · `AaveV3Borrow.sol`<br>`AaveV3Withdraw.sol` · `AaveV3Payback.sol` · `SparkSupply.sol`<br>`SparkBorrow.sol` · `SparkWithdraw.sol` · `SparkPayback.sol`<br>`LidoStake.sol` · `LidoWrap.sol` · `LidoUnwrap.sol`<br>`LidoWithdrawStart.sol` · `LidoWithdrawClaim.sol` · `GearboxDeposit.sol`<br>`GearboxRedeem.sol` · `NavErc20.sol` · `NavErc20WithDebt.sol`<br>`NavUnStEth.sol` · `NavAaveV3.sol` · `AaveV3HealthFactorCheck.sol` |
| **Confidence threshold (1-100)** | 70                                                     |

---

## Findings

[95] **1. IAU burnFrom arbitrary burn to zero bricks accounting and enables share inflation**

`InternalAccountingUnit.burnFrom` · Confidence: 95

**Description**
`burnFrom` is `onlyMinters` with no allowance and checks `msg.sender` is minter, allowing any minter to burn `TAsset`'s entire IAU balance to 0, which makes `totalAssets=0`, `lastNav=0`, `maxPnl=0`, freezing `PnlAccounting.doAccounting` and enabling 1 wei deposit to mint `totalSupply+1` shares.

**Fix**

```diff
- function burnFrom(address _burnAddress, uint _burnAmount) external onlyMinters {
-     _burn(_burnAddress, _burnAmount);
- }
+ function burnFrom(address _burnAddress, uint _burnAmount) external onlyMinters {
+     require(_burnAddress == address(this) || _burnAddress == tAsset || _burnAddress == msg.sender, "restricted");
+     _burn(_burnAddress, _burnAmount);
+ }
```

---

[92] **2. Redemption fee can be set to 100% rug pending 7-day redemptions**

`TreehouseRedemptionV2.setRedemptionFee` · Confidence: 92

**Description**
`setRedemptionFee` caps at `PRECISION=1e4=100%` and pending redemptions are locked 7 days; owner can front-run `finalizeRedeem` with fee=10000 leaving user 0.

**Fix**

```diff
- if (_newFee > PRECISION) revert FeeExceeded();
+ if (_newFee > 500) revert FeeExceeded(); // 5% max per spec 0.05%
```

---

[90] **3. Rescuable can rescue core Vault underlying and tAsset pending redemptions**

`Rescuable.rescueERC20` · Confidence: 90

**Description**
`Vault`, `Router`, `Fastlane`, `RedemptionV2` inherit `Rescuable` with no exclusion; `rescuer` can call `rescueERC20(wstETH, attacker, balanceOf(Vault))` draining TVL.

**Fix**

```diff
  function rescueERC20(IERC20 tokenContract, address to, uint256 amount) external onlyRescuer {
+     require(tokenContract != IERC20(UNDERLYING) && tokenContract != IERC20(TASSET) && tokenContract != IERC20(IAU), "protected");
      tokenContract.safeTransfer(to, amount);
  }
```

---

[88] **4. Share inflation via burn-to-zero then tiny deposit mints huge shares**

`TAsset._convertToShares` · Confidence: 88

**Description**
`ERC4626Upgradeable._convertToShares = assets * (totalSupply+1)/(totalAssets+1)` with offset 0; if `totalAssets=0` and `totalSupply=1000e18`, deposit 1 wei mints `1000e18` shares, then later `IAU.mintTo(TASSET, 1000e18)` makes attacker 50% owner for 1 wei.

**Fix**

```diff
  function _decimalsOffset() internal view virtual override returns (uint8) {
-     return 0;
+     return 6;
  }
```

---

[85] **5. Blacklist permanently locks user funds with no redemption escape**

`TAsset._update` · Confidence: 85

**Description**
`_update` modifier `notBlacklisted(from) notBlacklisted(to) notBlacklisted(msg.sender)` – `Fastlane.redeemAndFinalize` uses `safeTransferFrom(user, Fastlane)` where `from=user`, `msg.sender=Fastlane`; blacklisted user reverts `AccountBlacklisted` and cannot redeem or transfer.

**Fix**

```diff
  function _update(address from, address to, uint value) internal virtual override notBlacklisted(to) notBlacklisted(msg.sender) {
+     if (to == address(this) || to == redemption || to == fastlane) {} else {
+         if (_isBlacklisted(from)) revert AccountBlacklisted();
+     }
      super._update(from,to,value);
  }
```

---

[84] **6. RateProvider instant update and Chainlink staleness missing allows NAV inflation**

`RateProviderRegistry.update` + `TEthRateProvider.getRate` · Confidence: 84

**Description**
`update` is `onlyOwner` instant, no timelock; `TEthRateProvider` calls `latestRoundData()` without checking `updatedAt` staleness or `answer<=0`, allowing owner to set malicious provider returning huge rate inflating `vaultNav` and minting profit via `mark`.

**Fix**

```diff
  function getRate() external view returns (uint256) {
-     (, int256 answer, , , ) = stethRateProvider.latestRoundData();
+     ( , int256 answer, , uint256 updatedAt, ) = stethRateProvider.latestRoundData();
+     require(answer > 0 && block.timestamp - updatedAt < 3600, "stale");
      return (wstETH.getStETHByWstETH(tETH.convertToAssets(1e18)) * uint(answer)) / 1e18;
  }
```

---

[82] **7. Vault approval not revoked on RedemptionController.removeRedemption**

`RedemptionController.removeRedemption` · Confidence: 82

**Description**
`Vault.setRedemption` revokes old via `approve(0)` and approves new max, but `RedemptionController.removeRedemption` only removes from `_redemptionContracts` set, does not call `Vault.setRedemption`; Vault still has `allowance[Vault][removed]=max`, removed contract can still `safeTransferFrom(Vault)`.

**Fix**

```diff
  function removeRedemption(address _remove) external onlyOwner {
      bool success = _redemptionContracts.remove(_remove);
+     IERC20(UNDERLYING).safeTransferFrom(address(VAULT), address(VAULT), 0); // force check? actually need Vault to revoke via new call
+     // Call Vault to approve 0 for _remove if Vault exposes per-redemption approval mapping
  }
```

---

[80] **8. Deposit cap bypass via direct transfer to Vault**

`TreehouseRouter._checkEthCap` · Confidence: 80

**Description**
Cap checks `IAU.totalSupply` converted to ETH, but direct `wstETH.transfer(Vault, amount)` increases Vault balance without minting IAU, making `getRedeemableAmount` overstate free liquidity and allowing fastlane to redeem unbacked underlying.

**Fix**

```diff
+ function syncVault() external { /* enforce IAU.totalSupply >= vaultNav */ }
  // Or make Vault's underlying balance only increase via Router with IAU mint
```

---

[78] **9. Fastlane earmark only accounts for single redemption contract**

`TreehouseFastlane.getRedeemableAmount` · Confidence: 78

**Description**
`getRedeemableAmount = vaultBalance - convertToAssets(totalRedeeming)` where `totalRedeeming` comes from single `REDEMPTION_CONTRACT`; if multiple RedemptionV2 contracts exist via `RedemptionController`, earmark underestimates reserved, allowing drain of funds reserved for other redemption track.

**Fix**

```diff
- uint _approximateEarmark = IERC4626(TASSET).convertToAssets(ITreehouseRedemption(REDEMPTION_CONTRACT).totalRedeeming());
+ uint _approximateEarmark = IERC4626(TASSET).convertToAssets(redemptionController.totalRedeemingAll());
```

---

[78] **10. PnlAccounting deviation freeze when lastNav small causes maxPnl=0**

`PnlAccounting.maxPnl` · Confidence: 78

**Description**
`maxPnl = deviation * lastNav / PRECISION`; if `lastNav` (IAU.balanceOf(TASSET)) small after burn or early protocol, `maxPnl` rounds to 0 due to integer division, any `currentNav>0` reverts `DeviationExceeded`, freezing positive PnL forever unless owner bypasses via direct `mark`.

**Fix**

```diff
  function maxPnl() public view returns (uint) {
-     return (deviation * NAV_LENS.lastRecordedProtocolNav()) / PRECISION;
+     uint base = (deviation * NAV_LENS.lastRecordedProtocolNav()) / PRECISION;
+     return base < 1e18 ? 1e18 : base; // floor 1 wstETH
  }
```

---

[75] **11. NavRegistry unchecked NAV overflow and bytes32 decode**

`NavRegistry.getStrategyNav` · Confidence: 75

**Description**
`unchecked { _navInUnderlying += uint(bytes32(info)) }` overflow wraps to 0, and `uint(bytes32(info))` assumes 32-byte return but `staticcall` could return >32 bytes (truncated) or <32 (zero-padded via bytes32 conversion reading length), underreporting NAV causing burn instead of mint.

**Fix**

```diff
- (bool success, bytes memory info) = modules[moduleId].addr.staticcall(cd);
- _navInUnderlying += uint(bytes32(info));
+ (bool success, bytes memory info) = modules[moduleId].addr.staticcall(cd);
+ require(success && info.length>=32);
+ _navInUnderlying += abi.decode(info, (uint256));
```

---

[75] **12. SimpleStakingERC20 rescue can drain staked tokens**

`SimpleStakingERC20.rescueERC20` · Confidence: 75

**Description**
`rescueERC20` is `onlyOwner` and rescues `_token` to `owner()`, but `_token` can be a supported staking token; owner can drain all staked balances, no exclusion.

**Fix**

```diff
  function rescueERC20(IERC20 _token) external onlyOwner {
+     require(supported[_token].exists==false, "protected");
      _token.safeTransfer(owner(), _token.balanceOf(address(this)));
  }
```

---

[70] **13. Strategy execute empty revert hides failure and delegatecall gas buffer**

`Strategy.execute` · Confidence: 70

**Description**
`delegatecall(sub(gas(),5000), ...)` then `if eq(succeeded,0) { revert(0,0) }` reverts with empty data, hiding reason; gas buffer 5000 may be insufficient for complex actions, causing silent failure misattributed.

**Fix**

```diff
- if eq(succeeded, 0) { revert(0,0) }
+ if eq(succeeded, 0) { returndatacopy(0,0,returndatasize()) revert(0,returndatasize()) }
```

---

---

[65] **14. addAllowableAsset vs Router conversion mismatch DoS**

`Vault.addAllowableAsset` + `TreehouseRouter._convertToUnderlying` · Confidence: 65

**Description**
`addAllowableAsset` checks rate provider but Router only handles WETH/stETH/underlying, others revert `ConversionToUnderlyingFailed` despite being allowable.

---

[60] **15. NavErc20 unchecked loop overflow**

`NavErc20.nav` · Confidence: 60

**Description**
Loop `unchecked { if token==wstETH ... else _nav += rate*wip/1e18 }` overflow wraps if token balances huge (>1e38).

---

Findings List

| # | Confidence | Title |
|---|---|---|
| 1 | [95] | IAU burnFrom arbitrary burn to zero bricks accounting and enables share inflation |
| 2 | [92] | Redemption fee can be set to 100% rug pending 7-day redemptions |
| 3 | [90] | Rescuable can rescue core Vault underlying and tAsset pending redemptions |
| 4 | [88] | Share inflation via burn-to-zero then tiny deposit mints huge shares |
| 5 | [85] | Blacklist permanently locks user funds with no redemption escape |
| 6 | [84] | RateProvider instant update and Chainlink staleness missing allows NAV inflation |
| 7 | [82] | Vault approval not revoked on RedemptionController.removeRedemption |
| 8 | [80] | Deposit cap bypass via direct transfer to Vault |
| 9 | [78] | Fastlane earmark only accounts for single redemption contract |
| 10 | [78] | PnlAccounting deviation freeze when lastNav small causes maxPnl=0 |
| 11 | [75] | NavRegistry unchecked NAV overflow and bytes32 decode |
| 12 | [75] | SimpleStakingERC20 rescue can drain staked tokens |
| 13 | [70] | Strategy execute empty revert hides failure and delegatecall gas buffer |
| 14 | [65] | addAllowableAsset vs Router conversion mismatch DoS |
| 15 | [60] | NavErc20 unchecked loop overflow |

---

## Leads

- **Vault withdraw no reentrancy guard** — `Vault.withdraw` calls `IERC20.safeTransfer` after `isActiveStrategy` check, no `nonReentrant`; Strategy via delegatecall could re-enter via another strategy or via token callback (ERC777) to drain multiple assets.
- **Router receive only allows WETH, forced ETH via selfdestruct** — `receive()` reverts if `msg.sender!=WETH`; ETH forced via `selfdestruct` to Router locks, needs rescue; no `rescueETH` in Router? Actually inherits Rescuable with rescueETH onlyRescuer, so recoverable but requires rescuer.
- **RedemptionV2 leftover IAU donation vs fee inconsistency** — `finalizeRedeem` computes fee but transfers leftover including fee to `TASSET`, not treasury; event emits fee but fee not actually taken, spec says 0.05% to treasury, code donates to holders.
- **ActionRegistry single-level previous address** — `revertToPreviousAddress` only restores one previous; if two bad updates, recovery limited, and `previousAddresses` not cleared after revert allowing repeated revert to same old.
- **AaveV3Supply type(uint).max handling vs VaultPull no max** — Supply action handles `type(uint).max` as whole balance, VaultPull does not, asymmetry could cause partial withdrawal leaving dust.
- **TEthExchangeRateProvider and DWSTETHV3RateProvider not audited for staleness** — similar to TEthRateProvider, may read stale Chainlink.

---

> ⚠️ This review was performed by an AI assistant. AI analysis can never verify the complete absence of vulnerabilities and no guarantee of security is given. Team security reviews, bug bounty programs, and on-chain monitoring are strongly recommended. For a consultation regarding your projects' security, visit [https://www.pashov.com](https://www.pashov.com)

