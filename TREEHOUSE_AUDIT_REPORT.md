# Treehouse Bug Bounty - Security Audit Report
**Date:** 2026-08-01
**Repo:** `phani2582/TREEHOUSE-BUGBOUNTY`
**Commit:** `aee3741`
**Scope:** `contracts/` (Treehouse protocol core)

## Overview
Treehouse is a decentralized fixed-income layer with:
- **tAssets** (tETH) : ERC4626 wrapper over Internal Accounting Unit (IAU) denominated in wstETH, accumulates yield via leveraged LST arbitrage.
- **Vault** : holds underlying wstETH and other allowable assets, only active strategies can `withdraw`.
- **Router** : entrypoint for deposits (ETH, WETH, stETH, wstETH) -> mints IAU -> deposits into TAsset.
- **Redemption** : two tracks:
  - `TreehouseRedemptionV2` - 7-day waiting, min 250 eth default, fee up to 100%, returns `min(b0,bn) * min(c0,cn)/max(c0,cn)` to protect against rate changes.
  - `TreehouseFastlane` - instant redeem from vault idle balance, 0.5% fee to treasury.
- **Accounting** : `NavRegistry` + `NavLens` + `NavHelper` compute protocol NAV from strategies, `PnlAccounting` calls `TreehouseAccounting.mark()` to mint/burn IAU into TAsset (profit adds to share price, fee mints shares to treasury).
- **Strategies** : delegatecall based actions (AaveV3, Spark, Gearbox, Lido, VaultPull/Send) executed by trusted `StrategyExecutor`.

All contracts use Ownable2Step, Rescuable, Pausable.

---

## Critical & High Findings

### [CRITICAL-01] `InternalAccountingUnit.burnFrom` allows arbitrary burn
**File:** `contracts/InternalAccountingUnit.sol:55-62`
```solidity
function burnFrom(address _burnAddress, uint _burnAmount) external onlyMinters {
    _burn(_burnAddress, _burnAmount);
}
```
- No allowance check, no restriction to self.
- Any minter (Fastlane, RedemptionV2, Accounting, Router) can burn IAU from ANY address, including `TAsset` (which holds IAU as `totalAssets`).

**Impact 1 - Brick accounting:**
`lastRecordedProtocolNav = IAU.balanceOf(TASSET)`. If minter burns all IAU from TAsset, lastNav -> 0, then `maxPnl = deviation * lastNav / 1e4 -> 0`. `PnlAccounting.doAccounting()` will revert `DeviationExceeded` for any PNL !=0, freezing profit distribution forever.

**Impact 2 - Share price manipulation:**
ERC4626 `totalAssets = IAU.balanceOf(this)`. Burning TAsset's IAU to near 0 makes share price ~0. Next depositor gets huge shares for tiny deposit (OpenZeppelin has offset + virtual assets but still exploitable for large supply). When accounting later mints IAU back, attacker with huge shares can redeem large underlying.

**PoC:**
```solidity
// If Fastlane is compromised or owner adds attacker as minter:
IAU.addMinter(attacker);
IAU.burnFrom(TASSET, IAU.balanceOf(TASSET)); // totalAssets -> 0
// Router now deposits 1 wei wstETH, gets 1e18 shares worth ~totalSupply?
// Accounting mints 1000 wstETH back via mark(MINT), attacker holds huge % of supply.
```

**Recommendation:** Restrict `burnFrom` to burn only from `msg.sender` or require allowance, or add `onlyOwnerOrTimelock`. If burn from TASSET is needed, create dedicated `burnFromTAsset(uint)` callable only by Accounting.

---

### [HIGH-01] Rescuable can rescue core protocol assets
**Files:** `contracts/libs/Rescuable.sol`, `Vault.sol`, `TreehouseRouter.sol`, `TreehouseFastlane.sol`, `TreehouseRedemptionV2.sol`, `RedemptionController.sol`

```solidity
function rescueERC20(IERC20 tokenContract, address to, uint amount) external onlyRescuer {
    tokenContract.safeTransfer(to, amount);
}
```
- No exclusion list. Vault's underlying is `wstETH`, its balance is users' idle liquidity. Rescuer can call `Vault.rescueERC20(wstETH, attacker, type(uint).max)`.
- `Fastlane` and `RedemptionV2` hold users' tAssets pending redemption. Rescuer can steal them.
- Owner can set rescuer arbitrarily via `updateRescuer(newRescuer)` (onlyOwner).

**Impact:** Full protocol TVL drain by owner+rescuer collusion or rescuer key compromise. Violates least privilege.

**Fix:**
```solidity
function rescueERC20(...) external onlyRescuer {
    require(token != UNDERLYING && token != IAU && token != TASSET, "protected");
    ...
}
```
Or remove Rescuable from Vault/Router entirely, or timelock + restrict to non-core tokens.

---

### [HIGH-02] Redemption fee can be set to 100% - rug of pending redemptions
**File:** `contracts/TreehouseRedemptionV2.sol:128-132`
```solidity
function setRedemptionFee(uint32 _newFee) external onlyOwner {
    if (_newFee > PRECISION) revert FeeExceeded(); // PRECISION=1e4 => 100% allowed
```
- Waiting period 7 days. Users call `redeem()` locking shares for 7 days. Owner can front-run finalize and set fee to 10000 (100%). `finalizeRedeem` computes `_fee = _returnAmount * redemptionFee / 10000`, then `_returnAmount -= _fee` -> 0 to user.
- Funds? In current implementation fee is NOT sent to treasury but donated to TAsset holders (see MEDIUM-02), but if fixed to send to treasury, owner treasury gets 100% of redemption. Either way user loses.

**Fix:** Cap fee to e.g., 500 bips (5%) like Fastlane, and timelock.

---

### [HIGH-03] Blacklist permanently locks user funds
**File:** `contracts/TAsset.sol:101-105` and `libs/BlacklistableUpgradeable.sol`

```solidity
function _update(address from, address to, uint value) internal notBlacklisted(from) notBlacklisted(to) notBlacklisted(msg.sender) {
```
- Both `Fastlane.redeemAndFinalize` and `RedemptionV2.redeem` use `safeTransferFrom(msg.sender, address(this), shares)`. This triggers `_update` with `from=user, to=RedemptionContract, msg.sender=RedemptionContract`. If user blacklisted, modifier reverts `AccountBlacklisted`.
- User cannot transfer, cannot redeem, no escape. No forced redemption path for blacklisted.

**Fix:** Allow burning from blacklisted? Or add `redeem` function that checks only `to` not `from`, or provide owner rescue path after compliance.

---

### [HIGH-04] `TreehouseAccounting` fee can be 100% and executor can mint infinite profit
**File:** `contracts/TreehouseAccounting.sol:90-93`

MINT path:
```solidity
IInternalAccountingUnit(IAU).mintTo(address(this), _fee);
IERC4626(TASSET).deposit(_fee, treasury); // mints shares to treasury
IInternalAccountingUnit(IAU).mintTo(TASSET, _amountLessFee); // inflates share price
```
- `fee` is settable by owner up to 100% (10k). If 100%, all PNL goes to treasury as shares.
- `executor` (set by owner) can call `mark(MINT, hugeAmount, 0)` with no supply cap, minting unlimited IAU to TAsset, inflating share price arbitrarily, making depositors think they earned huge yield, then executor can set fee 100% and extract.

**Fix:** Cap fee at e.g., 20% (as docs say performance fee 20%), and restrict `mark` amount via deviation already in `PnlAccounting` but direct `mark` bypasses deviation if owner calls it (owner can call mark as well, onlyOwnerOrExecutor). Add timelock.

---

## Medium Findings

### [MEDIUM-01] RedemptionV2 fee not actually taken
**File:** `TreehouseRedemptionV2.sol:106-132`
- Computes `_fee = _returnAmount * redemptionFee / PRECISION`, then `_returnAmount -= _fee`, burns net, redeems net to user. Leftover including fee (`bn - net`) transferred to `TASSET`:
```solidity
_assets = IERC20(IAU).balanceOf(address(this));
if (_assets >0) IERC20(IAU).safeTransfer(TASSET, _assets);
```
- Fee ends up as donation to all TAsset holders, not treasury, contradicting spec that fee offsets interest and goes to treasury. Event emits fee but fee never transferred to treasury.

**Fix:** Burn net + fee, or transfer fee portion to treasury via accounting.

---

### [MEDIUM-02] Fastlane redeemable amount manipulation via donation
**File:** `TreehouseFastlane.sol:90-105`
```solidity
function getRedeemableAmount() public view returns (uint) {
    uint _underlyingInVault = IERC20(UNDERLYING).balanceOf(address(VAULT));
    uint _approximateEarmark = IERC4626(TASSET).convertToAssets(totalRedeeming());
    return _approximateEarmark > _underlyingInVault ? 0 : _underlyingInVault - _approximateEarmark;
}
```
- `convertToAssets` share price can be inflated by minting IAU directly to TAsset (via Accounting or any minter transferring IAU to TAsset). That inflates earmark, making `_totalRedeemable` 0, DoSing fastlane.
- Similarly, vault balance could be artificially inflated via direct transfer of underlying to vault (not via router) without minting IAU, making fastlane appear to have liquidity but without backing.

**Fix:** Use `previewRedeem(totalRedeeming)` not `convertToAssets`, or use stored `assets` from redemptionInfo sum, not share conversion.

---

### [MEDIUM-03] `NavRegistry.getStrategyNav` unchecked overflow + decoding
**File:** `contracts/NavRegistry.sol:195-210`
```solidity
unchecked {
  _navInUnderlying += uint(bytes32(info));
}
```
- Unchecked addition can wrap to 0 if sum exceeds 2^256-1, underreporting NAV, causing burn.
- `uint(bytes32(info))` assumes return data is exactly bytes32. If module returns malformed data >32 bytes, truncation.

**Recommendation:** Use checked addition (default in Solidity 0.8) and `abi.decode(info, (uint))` instead of casting.

---

### [MEDIUM-04] `PnlAccounting` deviation freeze
**File:** `contracts/periphery/PnlAccounting.sol:60-80`
- `maxPnl = deviation * lastNav / 1e4`. If lastNav small (early or after burn), maxPnl tiny, any normal market movement >2.5% reverts. Also if strategies added, `currentProtocolNav` loops could cost >30M gas, DoSing accounting.
- `nextWindow` set via `unchecked` - if cooldown set max 2 days, addition safe, but still.

**Fix:** Add minimum maxPnl floor (e.g., 1 eth) and pagination for strategy NAV.

---

### [MEDIUM-05] Rate provider manipulation
**File:** `contracts/rate-providers/RateProviderRegistry.sol:30-48` and `NavErc20.sol`
- Owner can add arbitrary rate provider returning huge rate, inflating `vaultNav` and `strategy NAV`, causing `PnlAccounting` to mint huge profit.
- `TEthRateProvider.getRate()` uses Chainlink but no staleness check (`updatedAt` not validated, answer <=0 not rejected).

**Fix:** Timelock rate provider updates, add sanity bounds, check `latestRoundData` freshness.

---

## Low / Info

- **Zero address checks missing:** `TreehouseFastlane` treasury, `TreehouseAccounting` treasury, `FastlaneFee` owner, `Vault` redemption.
- **Rescue ETH:** `Rescuable.rescueETH` can rescue ETH forced via selfdestruct, but Vault/Router not designed to hold ETH.
- **TreehouseRouter.receive()** only allows WETH, but forced ETH via coinbase could lock.
- **Deposit cap bypass:** Direct `wstETH.transfer(VAULT, amount)` increases vault balance without increasing `IAU.totalSupply`, so `getRedeemableAmount` shows more liquidity than backed by shares? Accounting will later mint PNL for it, but instant fastlane could redeem more than backed.
- **Strategy storage:** No limit on number of strategies, gas DoS in `NavLens.currentProtocolNav`.
- **Empty revert data in Strategy.execute:** `delegatecall` failure reverts with `revert(0,0)`, hiding reason, hard to debug.

---

## Recommendations Summary
1. **Fix IAU privileges**: Remove `burnFrom(address,uint)` arbitrary burn, replace with `burnFrom(address,uint)` that checks allowance or restrict to `TASSET` only via dedicated function. Similarly restrict `mintTo` to accounting only, not redemption contracts.
2. **Remove or harden Rescuable**: Exclude underlying, IAU, TAsset from rescue, or remove inheritance from Vault and redemption contracts.
3. **Fee caps & timelocks**: All fee setters (RedemptionV2, Accounting, FastlaneFee) cap at <=5% (500 bips) or 20% performance, and use TimelockController 2-day.
4. **Blacklist**: Provide redemption escape for blacklisted users (allow burn even if blacklisted) or allow owner to force redeem to underlying after compliance.
5. **Accounting**: Ensure PNL deviation has floor, use checked math, use `abi.decode`, and validate Chainlink feeds (staleness, answer>0).
6. **Redemption fee handling:** Fix to send fee to treasury rather than donate.

---

## PoC Code Snippets

### PoC 1 - Brick accounting via burnFrom
```solidity
// Assume attacker controls Fastlane (minter) - e.g., owner adds attacker contract as minter
interface IIAU { function burnFrom(address,uint) external; function balanceOf(address) external view returns(uint); }

contract Attack {
    function attack(address iau, address tasset) external {
        uint bal = IIAU(iau).balanceOf(tasset);
        IIAU(iau).burnFrom(tasset, bal); // totalAssets -> 0
        // Now PnlAccounting.doAccounting will revert DeviationExceeded for any positive PNL
    }
}
```

### PoC 2 - Rescue drain
```solidity
Vault vault = Vault(payable(VAULT_ADDR));
vault.updateRescuer(attacker);
vault.rescueERC20(wstETH, attacker, IERC20(wstETH).balanceOf(address(vault)));
```

### PoC 3 - 100% redemption fee rug
```solidity
// User redeems 250 wstETH worth, waiting 7 days
redemption.redeem(250 ether);
vm.warp(block.timestamp + 7 days);
redemption.setRedemptionFee(10000); // owner
redemption.finalizeRedeem(0); // user gets 0
```

---

## Conclusion
Core architecture is sound (ERC4626 + IAU accounting + strategy delegatecall), but privileged roles (owner, minter, rescuer, executor, blacklister) have excessive power to brick, steal, or rug. Most critical fix is to harden `InternalAccountingUnit` burn/mint privileges and remove `Rescuable` from Vault.

**Severity breakdown:** 1 Critical, 3 High, 5 Medium, several Low.

*Prepared for Treehouse bug bounty - phani2582/TREEHOUSE-BUGBOUNTY.*
