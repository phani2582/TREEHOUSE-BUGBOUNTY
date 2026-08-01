# Entry Point Map

> Treehouse tAsset | 37 entry points | 5 permissionless | 12 role-gated | 20 admin-only

---

## Protocol Flow Paths

### Setup (Owner)
`Vault.constructor()` → `StrategyStorage.storeStrategy()` → `NavRegistry.registerModule()` → `RateProviderRegistry.update()` → `Vault.setStrategyStorage()` → `Vault.setRedemption()` → `RedemptionController.addRedemption()` → `TreehouseRouter.constructor()`

### User Deposit Flow
`[setup]` → `TreehouseRouter.deposit()` / `depositETH()` → `InternalAccountingUnit.mintTo()` → `TAsset.deposit()` ◄── must be allowable asset + depositCap not exceeded
                                                    ├─→ `TAsset.transfer()` (secondary market)
                                                    └─→ `SimpleStakingERC20` LP staking

### User Redemption Flow
`[deposit above]` → `TAsset.approve()` → `TreehouseRedemptionV2.redeem()` ◄── min 250 eth, waiting 7 days → `RedemptionV2.finalizeRedeem()` ◄── block.timestamp >= start+waitingPeriod + vault has enough underlying → `RedemptionController.redeem()` → `Vault` transfer
                                                    └─→ `TreehouseFastlane.redeemAndFinalize()` ◄── getRedeemableAmount > assets, instant, 0.5% fee

### Maintenance (Executor/Keeper)
`[deposit above]` → `NavLens.currentProtocolNav()` → `PnlAccounting.doAccounting()` ◄── cooldown passed + netPnl <= maxPnl → `TreehouseAccounting.mark()` → `TAsset` totalAssets changes

### Strategy Execution Flow
`[setup]` → `ActionRegistry.addNewContract()` → `StrategyStorage.whitelistActions()` → `StrategyStorage.whitelistAssets()` → `StrategyExecutor.updateExecutor()` → `StrategyExecutor.executeOnStrategy()` ◄── executor active + strategy active + actions whitelisted → `Strategy.callExecute()` → `Strategy.execute()` delegatecall → `ActionExecutor.executeActions()` → `VaultPull/VaultSend/AaveV3Supply/etc.`

---

## Permissionless

### `TreehouseRouter.deposit()`
| Aspect | Detail |
|--------|--------|
| Visibility | public, nonReentrant, whenNotPaused |
| Caller | User / Depositor |
| Parameters | _asset (user-controlled), _amount (user-controlled) |
| Call chain | → IERC20.safeTransferFrom → _convertToUnderlying → _ethToWsteth → Vault transfer → _mintAndStake → IAU.mintTo → TAsset.deposit |
| State modified | IAU.totalSupply, IAU.balanceOf, TAsset.balanceOf, Vault underlying balance |
| Value flow | Tokens: User → Vault (wstETH) + User → Router → TAsset shares to receiver |
| Reentrancy guard | yes |

### `TreehouseRouter.depositETH()`
| Aspect | Detail |
|--------|--------|
| Visibility | public payable, nonReentrant, whenNotPaused |
| Caller | User |
| Parameters | msg.value (user-controlled) |
| Call chain | → _ethToWsteth → stETH.submit → wstETH.wrap → Vault transfer → _mintAndStake |
| State modified | Same as deposit |
| Value flow | ETH in → wstETH to Vault, tAsset shares to msg.sender |
| Reentrancy guard | yes |

### `TreehouseFastlane.redeemAndFinalize()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, nonReentrant, whenNotPaused |
| Caller | tAsset holder |
| Parameters | _shares (user-controlled, uint96) |
| Call chain | → TAsset.previewRedeem → getRedeemableAmount → TAsset.safeTransferFrom → TAsset.redeem → IAU.burn → RedemptionController.redeem (user + treasury) |
| State modified | TAsset.totalSupply, IAU.totalSupply, Vault underlying balance |
| Value flow | tAsset shares: User → Fastlane (burn) → wstETH: Vault → User + Treasury |
| Reentrancy guard | yes |

### `TreehouseRedemptionV2.redeem()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, nonReentrant, whenNotPaused |
| Caller | tAsset holder |
| Parameters | _shares (user-controlled, uint96) |
| Call chain | → TAsset.previewRedeem → TAsset.safeTransferFrom → push RedemptionInfo |
| State modified | redemptionInfo[msg.sender], redeeming, totalRedeeming |
| Value flow | tAsset shares locked in contract |
| Reentrancy guard | yes |

### `TreehouseRedemptionV2.finalizeRedeem()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, nonReentrant, whenNotPaused, validateRedeem |
| Caller | Original redeemer |
| Parameters | _redeemIndex (user-controlled) |
| Call chain | → TAsset.redeem → IAU.burn → RedemptionController.redeem → IAU.balanceOf → transfer leftover to TASSET |
| State modified | redeeming, totalRedeeming, IAU.totalSupply, Vault balance, TAsset.totalAssets |
| Value flow | wstETH: Vault → User, leftover IAU → TAsset |
| Reentrancy guard | yes |

---

## Role-Gated

### `RedemptionController` role (redemption contracts)
#### `RedemptionController.redeem()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, whenNotPaused |
| Caller | RedemptionV2 / Fastlane (must be in _redemptionContracts) |
| Parameters | _amount, _recipient (contract-controlled) |
| Call chain | → IERC20.safeTransferFrom Vault → recipient |
| State modified | Vault underlying balance (via transferFrom) |
| Value flow | wstETH Vault → recipient |
| Reentrancy guard | no |

### `Strategy` role (active strategy)
#### `Vault.withdraw()`
| Aspect | Detail |
|--------|--------|
| Visibility | external |
| Caller | Active strategy (isActiveStrategy + isAssetWhitelisted) |
| Parameters | _asset, _amount (strategy-controlled) |
| Call chain | → IERC20.safeTransfer → strategy |
| State modified | Vault token balances |
| Value flow | Token Vault → Strategy |
| Reentrancy guard | no |

### `Executor` role
#### `StrategyExecutor.executeOnStrategy()`
| Aspect | Detail |
|--------|--------|
| Visibility | external payable |
| Caller | Executor (executors mapping true) |
| Parameters | _strategyId, _actionIds, _actionCalldata, _paramMapping (executor-controlled) |
| Call chain | → StrategyStorage.getStrategyAddress → isActiveStrategy → isActionWhitelisted → Strategy.callExecute → Strategy.execute delegatecall → ActionExecutor.executeActions → actions |
| State modified | Strategy storage (via delegatecall), Vault balances (via VaultPull/Send) |
| Value flow | Various, depends on actions |
| Reentrancy guard | no |

#### `Strategy.callExecute()`
| Aspect | Detail |
|--------|--------|
| Visibility | external payable |
| Caller | StrategyExecutor (must equal strategyStorage.strategyExecutor) |
| Parameters | _target, _data |
| Call chain | → Strategy.execute |
| State modified | via delegatecall |
| Value flow | may send ETH |
| Reentrancy guard | no |

#### `PnlAccounting.doAccounting()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, whenNotPaused, onlyOwnerOrExecutor |
| Caller | Owner or executor |
| Parameters | dynamicModuleParams (executor-controlled) |
| Call chain | → NavLens.lastRecordedProtocolNav → NavLens.currentProtocolNav → maxPnl → TreehouseAccounting.mark |
| State modified | nextWindow, IAU.totalSupply, TAsset.totalAssets, TAsset treasury shares |
| Value flow | None direct, but changes share price |
| Reentrancy guard | no |

#### `TreehouseAccounting.mark()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, onlyOwnerOrExecutor |
| Caller | Owner or executor |
| Parameters | _type (BURN/MINT), _amountLessFee, _fee |
| Call chain | → IAU.mintTo / burnFrom → TAsset.deposit |
| State modified | IAU.totalSupply, TAsset.totalAssets, TAsset treasury shares |
| Value flow | IAU mint/burn affects share price |
| Reentrancy guard | no |

### `Blacklister` role
#### `BlacklistableUpgradeable.blacklist()` / `unBlacklist()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, onlyBlacklister |
| Caller | Blacklister |
| Parameters | _account (blacklister-controlled) |
| Call chain | → _blacklist/_unBlacklist |
| State modified | _blacklistedAccounts |
| Value flow | none |
| Reentrancy guard | no |

### `Rescuer` role
#### `Rescuable.rescueERC20()` / `rescueETH()`
| Aspect | Detail |
|--------|--------|
| Visibility | external, onlyRescuer |
| Caller | Rescuer |
| Parameters | tokenContract, to, amount |
| Call chain | → safeTransfer |
| State modified | Token balances of contract |
| Value flow | Tokens contract → to |
| Reentrancy guard | no |

---

## Admin-Only

| Contract | Function | Parameters | State Modified |
|----------|----------|------------|----------------|
| InternalAccountingUnit | addMinter | _newMinter | _minters |
| InternalAccountingUnit | removeMinter | _oldMinter | _minters |
| InternalAccountingUnit | setTimelock | _newTimelock | timelock |
| TAsset | initialize | _creator, _iau, _name, _symbol | UNDERLYING, ERC4626 asset |
| NavRegistry | registerModule | id, addr, name | modules, _moduleIds |
| NavRegistry | updateModule | id, newAddr, name | modules, previous |
| NavRegistry | revertModule | id | modules.addr |
| NavRegistry | attachTo | strategy, params | strategyModuleCd, moduleIds |
| NavRegistry | detachFrom | strategy, moduleId | strategyModuleCd, moduleIds |
| NavRegistry | updateParams | strategy, params | strategyModuleCd |
| RedemptionController | addRedemption | _add | _redemptionContracts |
| RedemptionController | removeRedemption | _remove | _redemptionContracts |
| RedemptionController | setPause | _paused | _paused, pauser check |
| RedemptionController | setPauser | _pauser | pauser |
| TreehouseAccounting | updateExecutor | _newExecutor | executor |
| TreehouseAccounting | updateTreasury | _newTreasury | treasury |
| TreehouseAccounting | setFee | _newFee | fee |
| TreehouseFastlane | setMinRedeem | _newMin | minRedeem |
| TreehouseFastlane | setFeeContract | _newContract | feeContract |
| TreehouseRedemptionV2 | setWaitingPeriod | _new | waitingPeriod |
| TreehouseRedemptionV2 | setMinRedeem | _new | minRedeem |
| TreehouseRedemptionV2 | setRedemptionFee | _newFee | redemptionFee |
| TreehouseRouter | setDepositCap | _newCap | depositCapInEth |
| TreehouseRouter | setPause | _paused | _paused |
| Vault | setStrategyStorage | _new | strategyStorage |
| Vault | setRedemption | _new | redemption + approval |
| Vault | addAllowableAsset | _asset | _allowableAssets |
| Vault | removeAllowableAsset | _asset | _allowableAssets |
| RateProviderRegistry | update | _asset, _rateProvider | rateProviders |
| FastlaneFee | setFee | _newFee | fee |
| PnlAccounting | setPause | _paused | _paused |
| PnlAccounting | setPauser | _pauser | pauser |
| PnlAccounting | setCooldownSeconds | _new | cooldown |
| PnlAccounting | updateExecutor | _new | executor |
| PnlAccounting | setDeviation | _new | deviation |
| StrategyStorage | storeStrategy | _strategy, actions, assets | strategies, parameters |
| StrategyStorage | whitelistActions | _strategyId, actions | whitelistedActions |
| StrategyStorage | unwhitelistActions | _strategyId, actions | whitelistedActions |
| StrategyStorage | whitelistAssets | _strategyId, assets | whitelistedAssets |
| StrategyStorage | unwhitelistAssets | _strategyId, assets | whitelistedAssets |
| StrategyStorage | pauseStrategy | _strategyId | isActive |
| StrategyStorage | unpauseStrategy | _strategyId | isActive |
| StrategyStorage | setStrategyExecutor | _new | strategyExecutor |
| ActionRegistry | addNewContract | _id, addr | entries |
| ActionRegistry | revertToPreviousAddress | _id | entries |
| ActionRegistry | startContractChange | _id, newAddr | pending, inChange |
| ActionRegistry | approveContractChange | _id | entries, previous |
| ActionRegistry | cancelContractChange | _id | pending, inChange |

---

## Initialization

| Contract | Function | Notes |
|----------|----------|-------|
| TAsset | initialize | initializer, sets IAU asset, owner, UNDERLYING from IAU |
| InternalAccountingUnit | constructor | sets UNDERLYING, owner |

All upgradeable contracts use `_disableInitializers` in constructor.
