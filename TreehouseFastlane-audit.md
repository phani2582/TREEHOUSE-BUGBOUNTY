# Security Audit — `TreehouseFastlane.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/TreehouseFastlane.sol` (145 LoC)
**Type:** Non-upgradeable `Ownable2Step, ReentrancyGuard, Pausable, Rescuable`; an IAU + TAsset **minter**; the **atomic (no-wait) redemption** path and a registered member of `RedemptionController`.
**Role:** `redeemAndFinalize(shares)` burns tETH for IAU in one tx, computes a ≤5% fee, burns the IAU, and has `RedemptionController` pull wstETH from the `Vault` — splitting it between the user and `treasury`. Liquidity is gated by `getRedeemableAmount()`, which reserves the current-NAV value of all pending `TreehouseRedemptionV2` redemptions.
**Dependencies read:** `FastlaneFee` (the ≤5% fee module), `RedemptionController` (vault-outflow arm — prior audit), `TreehouseRedemptionV2` (earmark source — prior audit), `Vault`, `TAsset` (ERC4626, UUPS), `IAU`, `Rescuable`, OZ `ReentrancyGuard`/`Pausable`/`SafeERC20`.
**Date:** 2026-08-09

---

## Trust model & flow (established, not assumed)

```
redeemAndFinalize(shares)   [nonReentrant, whenNotPaused=Controller.paused()]     (:70-85)
  a = previewRedeem(shares)                         // IAU value now
  require a ≥ minRedeemInUnderlying                 // NOTE: defaults to 0 until owner sets it
  require getRedeemableAmount() ≥ a                 // vault-liquid MINUS V2 earmark
  tETH.transferFrom(user → this, shares)
  a = TASSET.redeem(shares, this, this)             // burn tETH → IAU (reassigned to ACTUAL amount)
  fee = feeContract.applyFee(a)                     // view; (fee_bips * a)/1e4, fee_bips ≤ 500
  IAU.burn(a)                                        // burn FULL a (this is an IAU minter)
  Controller.redeem(a - fee, user)                  // vault → user
  Controller.redeem(fee, treasury)                   // vault → treasury
                                                     // Σ = a burned == a pulled  (1:1 preserved)

getRedeemableAmount()                                                               (:110-117)
  liquid   = UNDERLYING.balanceOf(VAULT)
  earmark  = TASSET.convertToAssets( V2.totalRedeeming() )   // current-NAV value of pending V2
  return   liquid > earmark ? liquid - earmark : 0

FastlaneFee.setFee(bips)  [onlyOwner]  require bips ≤ 500 (5% HARD CAP)              (FastlaneFee.sol:41-45)
```

- **Invariant preserved:** it burns exactly the IAU it just redeemed (`a`) and pulls exactly `a` wstETH (split user/treasury). No leftover, no haircut — Fastlane pays **full current NAV minus the fee**, in contrast to V2's conservative min-rate math.
- **Well-behaved controller member:** recipients are constrained to `{msg.sender, treasury}` — Fastlane never exercises the controller's arbitrary-recipient power.
- **Holds ~0 between txs** (atomic flow), so its `rescuer` blast radius is dust — like the Router, unlike V2.
- `owner` (min-redeem, fee-contract pointer), `treasury` (fixed — no setter), `rescuer`, and the shared `pauser` = trusted.

---

## How I'd actually attack this (black-hat, every angle)

**1. Flash-loan tETH → atomic redeem → profit.** Fastlane has no waiting period, so unlike V2 this is *timing-feasible*. → **No profit on its own.** Redeeming burns the tETH and returns ≤NAV wstETH (minus fee); to repay a tETH loan I'd have to buy tETH back at market → net loss (fee + slippage). Redemptions are price-neutral, so there's nothing to arb. A flash loan buys no primitive here **by itself**.

**2. …but pair atomicity with a NAV-inflation primitive.** This is the real one. Fastlane pays *full current NAV, instantly, with no min-rate haircut*. So whoever can inflate tETH's share price — the `TreehouseAccounting` H-1 unbacked `mark(MINT,…)` — can, **in the same block**, `redeemAndFinalize` their tETH and pull real wstETH from the Vault, capped only by `getRedeemableAmount()`. → **Fastlane is the *preferred* drain sink for H-1**: V2 forces a 7-day wait (a detection/response window) and min-rate math; Fastlane removes both. Not a Fastlane bug — it correctly pays NAV — but it materially worsens H-1's blast radius by making the drain atomic (see the inherited-High below).

**3. Suppress Fastlane liquidity by inflating the V2 earmark.** `getRedeemableAmount` subtracts `convertToAssets(V2.totalRedeeming())`. Anyone can raise `V2.totalRedeeming` by calling `V2.redeem(largeShares)`. → **Capital-intensive DoS (M-1).** Park a large V2 redemption → earmark balloons → `getRedeemableAmount → 0` → Fastlane refuses everyone. Cost to the griefer: lock ≥`minRedeem` (250 ether) of tETH for 7 days with no cancel and eat V2's haircut. Expensive and self-harming, but a well-funded actor can freeze the atomic path; it also degrades organically under legitimate large pending V2 redemptions.

**4. Reenter through the fee contract or the payout.** `feeContract.applyFee` is an external call to an owner-set address; `Controller.redeem` transfers wstETH. → **Blocked.** `nonReentrant`; `applyFee` is a `view`; wstETH has no recipient hook; the tETH is already burned and there's no exploitable mid-call state. A *malicious* `feeContract` returning `fee > a` would underflow `a - fee` → revert (DoS, not theft) — and it's owner-set/trusted (L-3).

**5. Front-run a victim's redeem with a fee bump.** Owner calls `FastlaneFee.setFee(500)` right before a user's tx; the user has no `maxFee`/`minAssetsOut`. → **Bounded to 5% (L-1).** Because the fee is hard-capped at 500 bips and applied atomically (no escrow), the worst-case surprise is a few percentage points — nothing like V2's retroactive 100% confiscation. Still worth a slippage param.

**6. Dust / zero-share redemption.** → **Harmless.** `previewRedeem` rounds down (never over-pays), IAU is minter-gated (no inflation), and `applyFee` truncates dust fees to 0 — the attacker only burns their own gas. Exposed only because `minRedeemInUnderlying` defaults to 0 until the owner sets it (L-2).

**7. Race two Fastlane redeems in one block.** Both read the pre-drain Vault balance and pass `getRedeemableAmount`; the second's `Controller.redeem` then reverts on insufficient Vault balance. → Availability only, retry-able, no loss.

What survives are **one inherited High, availability/DoS, and deploy-time hygiene** — no native theft primitive.

### Inherited H-1 — Fastlane is the *atomic* drain sink that amplifies `TreehouseAccounting` H-1 (High)
Fastlane pays full current NAV minus a ≤5% fee, with **no waiting period and no min-rate haircut**. An attacker holding the `TreehouseAccounting.{owner,executor}` key (or any NAV-inflation primitive) can bundle `mark(MINT, huge, 0)` → `Fastlane.redeemAndFinalize(theirShares)` in a single block and pull real wstETH from the Vault up to `getRedeemableAmount()`. Versus the V2 path, Fastlane removes the 7-day detection/response window and the conservative-rate limiter — so it is the *preferred* realization of H-1. Fastlane itself is not buggy (it correctly pays NAV and preserves burn==payout), but it widens the systemic blast radius. **Fix belongs upstream** (bound `mark`); as defense-in-depth, Fastlane/Controller could cap system-wide outflow per block/window so an atomic inflate-and-drain can't clear the whole liquid Vault in one tx.

### M-1 — Atomic-path liquidity is DoS-able by inflating the V2 earmark (Medium, capital-intensive)
`getRedeemableAmount` (`:110-117`) reserves `convertToAssets(REDEMPTION_CONTRACT.totalRedeeming())`. Since anyone can raise `V2.totalRedeeming` by opening a large V2 redemption, a well-capitalized actor can drive `getRedeemableAmount` to 0 and freeze Fastlane protocol-wide. It self-costs (≥250 ether tETH locked 7 days, no cancel, min-rate haircut) and no funds are stolen, but the atomic path can be denied to everyone; it also degrades organically whenever large legitimate V2 redemptions are pending. **Recommend:** document the coupling; consider a dedicated per-path liquidity reserve or a bounded earmark rather than the full current-NAV valuation of all pending V2 shares.

### M-2 — Constructor lacks zero-checks; `treasury == 0` + no setter = permanent brick (Medium, deploy-time, unrecoverable)
The constructor (`:48-64`) validates none of `_vault/_treasury/_redemptionController/_redemptionContract/_feeContract`, and `treasury` is a plain storage var with **no setter anywhere** in the contract. If deployed with `treasury == address(0)` (or if the treasury address later needs rotation), every `redeemAndFinalize` with `fee > 0` calls `Controller.redeem(fee, address(0))` → wstETH `transferFrom` to zero reverts (`ERC20InvalidReceiver`) → **Fastlane is permanently bricked** with no on-chain recovery except setting `FastlaneFee.fee = 0` (and even `Controller.redeem(0, address(0))` reverts on zero-recipient). **Recommend:** require `_treasury != 0` (and the other immutables `!= 0`) in the constructor; either make `treasury` `immutable` or add a guarded `updateTreasury` with a zero-check so a compromised/incorrect treasury can be rotated.

### L-1 — No user slippage / `maxFee` parameter (Low, bounded)
`redeemAndFinalize` reads the live fee with no `minAssetsOut`/`maxFee`, so an owner `setFee` bump (or a fee-contract swap) between submission and mining changes the user's payout. Bounded by the 5% hard cap and applied atomically, so impact is small — but a `minAssetsOut` param is cheap defense-in-depth.

### L-2 — `minRedeemInUnderlying` is uninitialized (0) until the owner sets it (Low)
Unlike V2 (`250 ether` in the declaration), Fastlane's `minRedeemInUnderlying` defaults to 0 and the constructor doesn't set it, so between deploy and `setMinRedeem` dust/zero redemptions are permitted (harmless — dust pays 0 fee via truncation — but spammy). Set it atomically in the deploy sequence.

### L-3 — `feeContract` is a mutable owner-set external dependency (Low, trust)
`setFeeContract` (non-zero-checked) lets the owner repoint `feeContract` to any contract; a malicious/buggy one returning `fee > grossAmount` underflows `a - fee` → revert (DoS, not theft), and `applyFee` runs mid-flow each redemption. The canonical `FastlaneFee` is clean and 5%-capped, so this is a trust/hygiene note: treat the fee contract as part of the trusted set and change it only via multisig/timelock.

## Vectors checked and cleared (full checklist)

| Vector | Result |
|---|---|
| **Access Control** | `redeemAndFinalize` permissionless (acts on the caller's own shares only); `setMinRedeem`/`setFeeContract` → `onlyOwner`; `rescue*` → `onlyRescuer`; pause is inherited from the Controller. Correctly wired. |
| **Missing Access Control** | No externally-reachable mutator is left ungated. The gap is the **missing `treasury` setter** (M-2) — an *absent* privileged path, not an open one. |
| **Business Logic** | Burn==payout preserved (`a` burned, `a` pulled, split user/treasury); recipients constrained to `{msg.sender, treasury}`; pays full current NAV−fee. Sound. Risks are inherited-H-1 amplification and the earmark DoS (M-1). |
| **Price Oracle Manipulation** | tETH price = `IAU.balanceOf(TASSET)`, unmovable by permissionless actions; no AMM/spot read here. Fastlane just consumes `previewRedeem`/`redeem`. The only price lever is upstream `mark` (inherited H-1). |
| **Flash Loan** | Atomic path makes flash loans *timing-feasible* but **profitless alone** (redemption is price-neutral; repaying a tETH loan costs fee+slippage). Dangerous only when *paired* with a NAV-inflation primitive (attack #2 → inherited H-1). |
| **Input Validation** | `_shares`/fee handled safely (previewRedeem rounds down, IAU minter-gated, dust fee truncates to 0); `minRedeemInUnderlying` defaults to 0 (L-2). Constructor validates **none** of its immutables (M-2). |
| **Unchecked External Calls** | `SafeERC20` for tETH pull and (via Controller) wstETH push; `IAU.burn`/`TASSET.redeem`/`feeContract.applyFee` are typed calls to trusted/minter-gated contracts. No low-level `.call` in the redeem path. Clean. |
| **Arithmetic Errors** | `a - fee` is checked math; fee ≤ 5% of `a` so it can't underflow with the canonical `FastlaneFee`. A *malicious* fee contract returning `fee > a` would revert (DoS, not theft — L-3). No `unchecked` in this file. |
| **Reentrancy** | `nonReentrant` on `redeemAndFinalize`; `applyFee` is `view`; wstETH/tETH have no recipient hooks; tETH is burned before payout. No exploitable mid-call state (attack #4). Safe. |
| **Integer Overflow/Underflow** | 0.8.24 checked math; `uint96` share/min-redeem inputs fit; `previewRedeem`/`convertToAssets` products fit uint256. Not affected. |
| **Proxy & Upgradeability** | Fastlane is non-upgradeable (immutables + Ownable2Step). Residual coupling is the upstream **UUPS `TASSET`** (its `previewRedeem`/`redeem`/`convertToAssets` are trusted). |
| **Front-Running / TOD** | Fee-bump front-run bounded to 5% (L-1); earmark-inflation DoS (M-1); same-block liquidity race (attack #7, retry-able). No value-extracting ordering primitive native to Fastlane. |
| **DoS** | The real availability items: earmark-inflation freeze (M-1), `treasury==0` permanent brick (M-2), malicious-fee-contract underflow (L-3), and the liquidity race. No state corruption; no unbounded loops. |
| **Insecure Randomness** | No RNG anywhere. N/A. |
| **Timestamp Manipulation** | No `block.timestamp`/`block.number` logic — Fastlane is atomic with no cooldown. N/A. |
| **Delegatecall to Untrusted Callee** | No `delegatecall`; all calls are typed external calls to token/minter/controller/fee contracts. Not present. |
| **Signature Replay** | No signatures, permits, or nonces. N/A. |
| **Short Address / Parameter** | ABI decoding is compiler-handled (≥0.8); no manual calldata parsing/assembly. Negligible. |
| **Uninitialized Storage Pointer** | No memory/storage struct pointers; simple scalar state. Not affected. |
| **Approval Phishing** | User grants Fastlane a tETH allowance to pull `_shares`; it's consumed atomically in the same tx (no lingering standing allowance exploitable across txs). The dangerous approval is the **Vault→Controller** `max` (upstream). |
| **Multisig Hijacking** | `owner` (fee-contract pointer, min-redeem) and `rescuer` should be multisigs; owner-key compromise ⇒ repoint `feeContract` (DoS) or bump fee to 5% — bounded, no drain. Harden governance. |
| **Private Key Compromise** | Owner-key compromise here is **bounded** (5% fee cap, fee-contract repoint = DoS not theft). The catastrophic key is upstream `TreehouseAccounting.{owner,executor}` → inherited H-1 realized *through* Fastlane. Timelock+multisig that. |
| **Supply Chain** | Deps are OZ + in-repo protocol contracts. The live external dependency is the **owner-set `feeContract`** — treat it as a pinned, audited, multisig-changed member of the trusted set (L-3). |
| **Drainer Malware** | No client/signing surface in-contract. On-chain equivalent is a compromised owner signer (bounded here) or upstream accounting key (inherited H-1). Hardware-backed multisig for owner/rescuer. |
| **CEX & Web2 Infrastructure** | Off-chain; not applicable to this contract beyond the key-custody guidance above. |

---

## Summary

`TreehouseFastlane.sol` is the **atomic (no-wait) redemption path**, and on the parts that matter for theft it is sound: it burns exactly the IAU it redeems and pulls exactly that much wstETH (split user/treasury), it constrains payout recipients to `{msg.sender, treasury}`, it is `nonReentrant`, and — thanks to `FastlaneFee`'s hard 5% cap — it carries **none** of V2's retroactive-100%-fee confiscation risk. An ordinary attacker cannot extract more than their shares are worth; a standalone flash loan buys no primitive.

The material risks are **one inherited High plus availability / deploy-time hygiene**:

1. **Inherited H-1 (High)** — Fastlane is the *preferred, atomic* drain sink for the `TreehouseAccounting` unbacked-`mark` NAV-inflation bug: full current NAV, no 7-day wait, no min-rate haircut, so an inflate-and-drain clears in a single block up to `getRedeemableAmount()`. Not a Fastlane defect (it correctly pays NAV) but it widens the systemic blast radius. Fix upstream; add per-window outflow caps as defense-in-depth.
2. **M-1 (Medium)** — the atomic path's liquidity (`getRedeemableAmount`) subtracts the full current-NAV value of all pending V2 redemptions, so a well-capitalized actor (or organic large V2 demand) can drive it to 0 and freeze Fastlane protocol-wide. Self-costly, no theft.
3. **M-2 (Medium)** — the constructor zero-checks nothing and `treasury` has **no setter**; a `treasury==0` deploy (or any later need to rotate it) permanently bricks the fee-split path. Add constructor zero-checks and a guarded `updateTreasury`.
4. **L-1…L-3** — no user `minAssetsOut`/`maxFee` slippage param (bounded by the 5% cap); `minRedeemInUnderlying` defaults to 0 until the owner sets it (unlike V2's 250 ether); `feeContract` is a mutable owner-set external dependency whose malicious variant returning `fee > a` reverts the redeem (DoS, not theft).

**Adjacent (out of file scope, but they define Fastlane's envelope):**
- **`FastlaneFee` (periphery/FastlaneFee.sol)** is clean and 5%-capped — the positive contrast to V2/Accounting's 100% fee ceilings; it removes retroactive-confiscation risk from this path entirely. (Its `applyFee` dust-truncation-to-0 `@audit` note is benign — it only ever *under*-charges the protocol.)
- **`RedemptionController.redeem`** is the uncapped Vault-outflow funnel both of Fastlane's `redeem` calls rely on (prior audit H-1); Fastlane is a *well-behaved* member of it (bounded recipients, burn==payout), but inherits its uncapped-drain and pause-freeze envelope.
- **Vault liquid-balance contention** — Fastlane, active strategies (`Vault.withdraw`), and the V2 earmark all draw on the same `UNDERLYING.balanceOf(VAULT)`; `getRedeemableAmount` only nets the *one* wired V2 `REDEMPTION_CONTRACT`, so additional future redemption members or strategy draws aren't reflected and can cause revert-and-retry (availability, not loss).
