# Security Audit — `TreehouseRouter.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/TreehouseRouter.sol` (183 LoC)
**Type:** Non-upgradeable `Ownable2Step, ReentrancyGuard, Pausable, Rescuable`; the **deposit entry-point** and an IAU + TAsset **minter**.
**Role:** Takes user wstETH / WETH / stETH / native ETH, converts everything to wstETH, pushes it into the `Vault` as backing, mints an equal amount of IAU, and stakes that IAU into `TAsset` (tETH) to mint shares to the depositor.
**Dependencies read:** `Vault`, `TAsset` (ERC4626, UUPS), `InternalAccountingUnit` (IAU), `IstETH`/`IwstETH` (Lido), `IWETH9`, `Rescuable` (Circle), OZ `ReentrancyGuard`/`Pausable`/`SafeERC20`.
**Date:** 2026-08-09

---

## Trust model & deposit flow (established, not assumed)

```
deposit(asset, amount)  [nonReentrant, whenNotPaused]           depositETH()  [nonReentrant, whenNotPaused]
  require Vault.isAllowableAsset(asset)                            v = ethToWsteth(msg.value)   // Lido submit+wrap
  if asset == Vault.getUnderlying() (wstETH):                      wstETH.transfer(VAULT, v)    // BACKING → vault
      wstETH.transferFrom(user → VAULT, amount); v = amount        shares = mintAndStake(v, user)
  else:                                                            checkEthCap(); require shares>0
      asset.transferFrom(user → this, amount)
      v = convertToUnderlying(asset, amount)   // WETH/stETH→wstETH
      wstETH.transfer(VAULT, v)                // BACKING → vault
  shares = mintAndStake(v, user)                     mintAndStake(v, receiver):
  checkEthCap(); require shares>0                       IAU.mintTo(this, v)              // 1 wstETH ⇒ 1 IAU
                                                        TASSET.deposit(v, receiver)      // pulls IAU, mints tETH
  checkEthCap(): stETHValue(IAU.totalSupply()) ≤ depositCapInEth
```

- **The one invariant the whole thing rests on:** the router mints IAU **only** in an amount equal to wstETH it has **already** delivered to the `Vault`. I traced all three paths and this holds on every one (backing is transferred to the vault *before* `mintAndStake` mints). This is the property that makes it safe to hand a permissionless `deposit()` the power of an IAU + TAsset minter.
- `owner` = trusted admin (pause, cap, ownership). `rescuer` = trusted (drains only router-held dust; router doesn't custody). Both **weaker** here than on the Vault/IAU because the router holds ~0 balance between transactions.
- Deposit share pricing depends on `IAU.balanceOf(TASSET)` (tETH `totalAssets`), which permissionless actions **cannot** move — see the adversarial section.

---

## How I'd actually attack this (black-hat, all angles)

I went at the router as if there were a bounty on draining it. Here is every angle I tried and what happened — the negative results matter as much as the findings, because they show *why* it holds.

**1. Unbacked mint (the crown jewel).** The router can `IAU.mintTo`. If I can reach `_mintAndStake` without funding the vault, I mint free tETH and drain. → **Blocked.** `_mintAndStake` is `internal`, reachable only via `deposit`/`depositETH`, and both send wstETH to the vault *before* minting. Backing strictly precedes mint on all three paths. No unbacked path exists.

**2. ERC4626 inflation / first-depositor / donation.** Classic: donate assets to `TASSET` to inflate share price and steal a victim's rounding. → **Blocked at the IAU layer.** tETH's asset is IAU, and `IAU._update` is minter-gated — I can't acquire or transfer IAU, so I can't donate it to `TASSET`. OZ virtual shares add a second layer. Dead.

**3. Donate wstETH straight to the Vault to move the share price.** → **Doesn't touch the router's price.** tETH `totalAssets = IAU.balanceOf(TASSET)`, not vault balance. A vault donation only perturbs `currentProtocolNav` (the *accounting/mark* path), which is the known, **profitless** donation-brick DoS — it never lets me steal from a router depositor.

**4. Sandwich a victim deposit.** → **No price impact to exploit.** Deposits add `X` assets and `X·supply/assets` shares — share price is invariant under permissionless deposits/redeems. Only privileged, cooldown'd, ≤2.5% PnL *marks* move it. There is no permissionless primitive to move price within a block, so there's nothing to sandwich (this is also why the missing `minShares` param, L-3, is low-impact).

**5. Reentrancy via ETH.** WETH `withdraw` sends ETH to `receive()`; Lido `submit`/`wrap` are the callees. → **Blocked.** `receive()` rejects all senders except WETH; both entry points are `nonReentrant`; Lido/WETH don't call back into `deposit`.

**6. Force-feed / stuck ETH to confuse accounting.** → **No confusion.** `_wethToWsteth`/`_ethToWsteth` submit the *explicit* `amount`, never `address(this).balance`, so pre-seeded ETH can't inflate a submit. Stuck ETH is just rescuer-recoverable dust.

**7. Zero / dust deposit to mint 0 shares or grief.** → Reverts cleanly (`NoSharesMinted`, or `previewDeposit → 0` at high share price). No partial state.

What *did* stick were **feature-breakage and availability** issues, not theft:

### M-1 — The direct **stETH deposit path is broken** by Lido's 1–2 wei rounding (Medium, functional DoS)
`_convertToUnderlying → _stethToWsteth(_amount)` (`:154`, `:170-172`) calls `wstETH.wrap(_amount)` with the **user-supplied** `_amount`. But stETH is share-based: `safeTransferFrom(user, router, _amount)` (`:88`) credits the router `getPooledEthByShares(getSharesByPooledEth(_amount)) ≈ _amount − 1 wei`. So the router holds slightly **less** than `_amount`, and `wrap(_amount)` — which pulls `_amount` stETH from the router — **reverts for insufficient balance**. Result: if stETH is a whitelisted allowable asset, exact-amount stETH deposits revert essentially always.

Note the **ETH/WETH path already dodges this** (`:167`) by wrapping `getPooledEthByShares(shares)` — i.e. the *actual* received balance — proving the author knew the pattern but didn't apply it to the direct-stETH branch.
**Fix:** wrap the router's realized balance, e.g. `_stethToWsteth(IERC20(stETH).balanceOf(address(this)))`, or snapshot the balance delta around the `transferFrom`. No fund risk, but the feature silently fails.

### M-2 — Deposit cap conflates PnL with deposits → yield growth DoSes deposits (Medium/Low, availability)
`_checkEthCap` (`:139-143`) bounds `getStETHByWstETH(IAU.totalSupply())`. But `IAU.totalSupply()` includes IAU minted by `TreehouseAccounting.mark` (positive PnL), not just router deposits. So as the protocol earns yield, `totalSupply` rises toward the cap **with no new deposits**, and at the boundary all deposits revert with `DepositCapExceeded` until the owner raises `depositCapInEth`. The cap is really a cap on *total protocol IAU*, which drifts up with yield and down with redemptions — operationally surprising and an ongoing DoS foot-gun. Consider tracking a dedicated deposit-principal counter, or documenting that the cap must be actively managed against accrued PnL.

### L-1 — Owner/rescuer centralization (Low, weaker than siblings)
- `setPause(true)` (`:125`) → deposits frozen; `setDepositCap(0)` (`:116`) → deposits frozen. Pure DoS levers, no theft.
- `rescueERC20` (`Rescuable.sol:57`) drains **any** ERC20 from the router — but the router holds ~0 between txs (funds flow through atomically), so the blast radius is dust/mis-sent tokens, **far** smaller than the Vault's rescuer. Still: put owner + rescuer behind a multisig/timelock. Router owner has **no** minting authority, so a compromise here is DoS, not drain.

### L-2 — Constructor `type(uint).max` approvals to an upgradeable `TASSET` (Low)
`IERC20(IAU).approve(TASSET, max)` and `approve(wstETH, max)` (`:66-67`) — raw `approve` (return ignored, inconsistent with the `SafeERC20` import). Low-risk today because the router carries ~0 standing IAU/stETH, **but `TASSET` is UUPS-upgradeable**: a malicious/compromised TAsset implementation (owner action) could `transferFrom` on the infinite IAU allowance. Prefer `forceApprove` and/or exact per-call approvals; note the standing allowance in the upgrade threat model.

### L-3 — No `minShares` / slippage param; MEV around PnL marks (Low, bounded)
`deposit`/`depositETH` mint at the instantaneous price with no user-supplied minimum. Because permissionless actions can't move price (adversarial #4), the only mover is a PnL mark (≤ `deviation` ≈2.5%, cooldown-gated, privileged). A depositor landing just before a positive/negative mark gains/loses up to the deviation — standard rebasing-vault MEV, bounded and small. Adding a `minSharesOut` is cheap defense-in-depth.

### L-4 — External-dependency liveness (Low, informational)
The ETH/WETH/stETH paths depend on Lido `submit` (subject to the protocol staking rate-limit) and `wrap`. If Lido pauses or the daily stake limit is hit, those deposits revert. Only the **direct wstETH** path is Lido-independent. Worth documenting so ops/users know wstETH is the resilient path.

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Access Control / Missing Checks | `deposit`/`depositETH` permissionless **by design**, gated by the 1:1-backing invariant; `setDepositCap`/`setPause`/`transferOwnership` → `onlyOwner`; `rescue*` → `onlyRescuer`. No missing gate. |
| Reentrancy | Both entry points `nonReentrant`; `receive()` restricted to WETH; Lido/WETH callees don't re-enter. Backing-before-mint ordering also removes CEI concerns. Safe. |
| Business Logic — unbacked mint | **Cleared.** Every path funds the Vault before `IAU.mintTo`; IAU minted == wstETH delivered. Core invariant holds. |
| Price Oracle / Flash Loan | No oracle; share price = `IAU.balanceOf(TASSET)`, unmovable by permissionless calls. A flash loan buys no primitive here (can't mint IAU, can't donate to TASSET, deposits don't move price). Conversion uses Lido's canonical rate, not a spot AMM. |
| Arithmetic / Overflow-Underflow | 0.8.24 checked math. The lone `unchecked` (`:140`) wraps only `getStETHByWstETH(totalSupply)` — no realistic overflow (product ≪ 2²⁵⁶). Not exploitable. |
| Proxy & Upgradeability | Router is non-upgradeable (immutables + `Ownable2Step`). Residual risk is the **upstream** UUPS `TASSET` (L-2), not this file. |
| Delegatecall | None. All calls are typed external calls to protocol/Lido contracts. |
| Front-Running / TOD | Cap race and mark-timing MEV only (M-2, L-3), both bounded/griefing. No value-extracting ordering primitive. |
| Signature Replay / Randomness / Timestamp | No signatures/permit, no RNG, no timestamp-dependent logic. N/A. |
| Integer / Short-Address / Uninitialized Storage Pointer | ABI/calldata compiler-handled; no assembly, no storage-pointer structs. Not affected. |
| Approval Phishing | Only the router's own outbound max approvals (L-2); no user allowance routed through unexpected sinks. |
| DoS | Real availability items are M-1 (stETH path), M-2 (cap-vs-PnL), L-1 (pause/cap), L-4 (Lido). None cause loss. |
| Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain. Router-key compromise ⇒ **DoS only** (no mint/drain power via owner/rescuer). Multisig + timelock recommended; smaller centralization surface than Vault/IAU/Accounting. |

---

## Summary

`TreehouseRouter.sol` is the **strongest** contract in the set reviewed so far. It hands a permissionless `deposit()` the authority of an IAU + TAsset minter, and it earns that safely: on all three asset paths it delivers wstETH to the Vault **before** minting an equal amount of IAU, and the ERC4626 layer is protected from inflation/donation by IAU's minter-gating. No unbacked-mint path, no reentrancy, no price-manipulation primitive, no arithmetic bug. A router key compromise is DoS, not theft.

The real issues are **feature-breakage and availability**, not fund loss:

1. **M-1** — the direct **stETH deposit path reverts** on Lido's 1-wei rounding (`wrap(_amount)` vs realized balance); wrap the *received* balance as the ETH path already does.
2. **M-2** — the deposit cap is measured on `IAU.totalSupply()`, which grows with PnL, so accrued yield silently DoSes deposits until the owner raises the cap.
3. **L-1…L-4** — owner/rescuer DoS levers (no drain power); raw infinite approvals to an upgradeable `TASSET`; no `minShares`; Lido-liveness dependence.

**Adjacent (define the router's safety envelope, out of file scope):** the router's minter role is only as safe as the *other* IAU minters — the systemic High lives in `TreehouseAccounting.mark` (unbounded mint/burn) and IAU's unlimited-mint design, already reported. The router doesn't add a new unbacked path, but it shares the blast radius if any minter key is compromised.
