# Security Audit — `RedemptionController.sol`
### (senior researcher + present-generation black-hat lens)

**Target:** `src/treehouse/contracts/RedemptionController.sol` (113 LoC)
**Type:** Non-upgradeable `Ownable2Step, Pausable, Rescuable`; the **vault-outflow arm** of the exit side.
**Role:** The single spender the `Vault` approves for `type(uint).max` of the underlying. Its `redeem(amount, recipient)` pulls underlying **out of the Vault** to any recipient, gated only to an owner-managed set of registered redemption contracts (`TreehouseRedemptionV2`, `TreehouseFastlane`). It is also the shared pause authority both members inherit.
**Dependencies read:** `Vault` (custody + `setRedemption` max-approval), `TreehouseRedemptionV2` (registered member — prior audit), `TreehouseFastlane` (registered atomic member), `Rescuable`, OZ `EnumerableSet`/`Pausable`/`SafeERC20`/`Ownable2Step`.
**Date:** 2026-08-09

---

## Trust model & flow (established, not assumed)

```
Vault.setRedemption(controller)   [onlyOwner]                     (Vault.sol:86-97)
   └─ underlying.approve(controller, type(uint).max)   // ONE spender, infinite allowance
                                                        // on rotation, revokes ONLY the previous addr

RedemptionController.redeem(amount, recipient)   [whenNotPaused]   (:48-51)
   ├─ require _redemptionContracts.contains(msg.sender)     // the ONLY gate
   └─ underlying.transferFrom(VAULT → recipient, amount)    // NO amount validation whatsoever

registered set = { TreehouseRedemptionV2, TreehouseFastlane }   (owner-managed)
   • V2.finalizeRedeem        → redeem(R, user)                     // R = conservative min-rate math + vault-liquidity check
   • Fastlane.redeemAndFinalize → redeem(assets-fee, user); redeem(fee, treasury)  // approximate earmark check

paused() (Pausable) gates redeem; BOTH V2 and Fastlane override paused() → return THIS.paused()
setPause(bool)  → owner OR pauser        (:78-86)
```

**The one sentence that governs this contract:** it holds the Vault's entire liquid balance behind an infinite allowance and hands it out on demand — and it validates **nothing** about the amount. Every property that makes an outflow *correct* (shares were burned, backing existed, liquidity was earmarked) lives in the **registered redemption contracts**; `redeem` re-checks none of it. It is the `TreehouseAccounting.mark` delegation pattern applied to the Vault's wstETH.

- The real cap on a single drain = the Vault's **liquid** wstETH balance (`transferFrom` reverts past it). Funds deployed to strategies are momentarily out of reach, not protected.
- `owner` (registers/removes members, sets pauser), `pauser` (freeze), `rescuer` = trusted. **The membership set *is* the security boundary.**

---

## How I'd actually attack this (black-hat, every angle)

**1. Call `redeem` directly and drain the Vault.** `redeem(vaultBalance, me)` — no cap, arbitrary recipient. → **Blocked by exactly one line:** `_redemptionContracts.contains(msg.sender)`. I must *be* a registered contract; no permissionless path exists. But note how thin the wall is — one `require` stands between any caller and 100% of the liquid Vault (H-1).

**2. Get myself registered.** `addRedemption` is `onlyOwner` with **no zero/contract check** — an EOA or a hand-crafted `Attacker.sol` can be added. One compromised or socially-engineered `addRedemption(attacker)` and then `attacker.redeem(liquidVaultBalance, attacker)` empties the liquid Vault in a single tx. This is the true H-1 surface: drain funnel + unvalidated, owner-controlled membership.

**3. Reentrancy — and there's no `nonReentrant` here.** The controller imports no `ReentrancyGuard`. → **Safe today, latent.** `redeem` makes one wstETH `transferFrom` (no recipient hook) and both registered callers are themselves `nonReentrant`. But safety rests entirely on the *token* and *every future member* being non-reentrant — a later callback-capable underlying or member could re-enter `redeem` to defeat its own accounting (L-1).

**4. Race Fastlane against a pending V2 finalize.** Fastlane's `getRedeemableAmount` (`TreehouseFastlane.sol:110-117`) nets an *approximate* earmark (`convertToAssets(REDEMPTION_CONTRACT.totalRedeeming())`) off the live Vault balance to avoid eating liquidity reserved for pending V2 redemptions. → **No theft, imperfect availability:** the earmark is approximate and covers only the *one* `REDEMPTION_CONTRACT` Fastlane was wired to. A large atomic Fastlane redemption can front-run a V2 `finalizeRedeem`, dropping Vault liquidity below what V2 needs → V2 reverts `InsufficientFundsInVault` (retry-able, no loss).

**5. Freeze everyone.** `setPause(true)` (owner **or** `pauser`) reverts `redeem`, and since V2 and Fastlane both inherit `paused()` from here, **all** redemptions across both paths freeze at once. With V2 having no `cancelRedeem`, escrowed tETH is locked for the duration of the pause (M-1).

**6. Strand a member's in-flight escrow.** `removeRedemption(V2)` → every future `V2.finalizeRedeem → controller.redeem` reverts `Unauthorized`, permanently. V2 still custodies the escrowed tETH, can't finalize, can't cancel → the escrow is bricked by one owner tx (M-2).

**7. Abuse the controller's own rescuer.** → **Low blast radius here.** `rescueERC20` moves the *controller's own* balance (`safeTransfer`), and the controller custodies ~0 — it moves Vault funds via allowance strictly inside the gated `redeem`. The rescuer here **cannot** reach the Vault allowance, unlike the Vault's own rescuer (L-2).

What survives are **trust-concentration and availability** issues — the controller adds no independent safety of its own.

### H-1 — `redeem` is an uncapped Vault-drain funnel; the only bound is the membership set (High, centralization-critical)
`RedemptionController.sol:48-51` — `redeem(_amount, _recipient)` validates `_amount` against **nothing** (shares, backing, NAV, earmark) and `_recipient` is arbitrary. The Vault has approved this contract `type(uint).max` (`Vault.sol:94`), so the effective ceiling on one call is the Vault's **liquid** wstETH balance. Security thus reduces entirely to: *every registered redemption contract is correct, non-compromised, non-upgradeable, and the owner never registers a bad one.* Two concrete drain paths:
- **Mis-registration:** owner (compromised/tricked) calls `addRedemption(attacker)` — no contract/zero validation (`:57-61`) — then `attacker.redeem(liquidVaultBalance, attacker)` takes 100% of the liquid Vault in one tx.
- **Downstream bug / inflated NAV:** any correctness bug in `TreehouseRedemptionV2`/`TreehouseFastlane`, or the inflated-share-price path from the `TreehouseAccounting` H-1, translates *directly* into a Vault outflow here, because the controller re-checks nothing.

This is the exit-side twin of `TreehouseAccounting.mark`: an unbounded, safety-delegating funnel over protocol funds. **Recommend:** enforce an invariant in the controller rather than trusting callers — track burned-IAU / outflow per window and cap it, require `_recipient` non-zero and `!= address(this)`, validate `addRedemption(_add)` is a contract, and put membership changes behind a timelock. At minimum multisig+timelock the owner and keep the registered set minimal, audited, and non-upgradeable.

### M-1 — Pause is a protocol-wide redemption kill-switch held by two keys (Medium, availability/centralization)
`setPause` (`:78-86`) is callable by `owner` **or** `pauser`, and because both `TreehouseRedemptionV2.paused()` and `TreehouseFastlane.paused()` return `REDEMPTION_CONTROLLER.paused()`, one pause freezes **all** redemptions across both paths. Given V2 has no `cancelRedeem`, a `pauser` — a lower-attention key than owner, set with no zero-check (`:92-94`) — can freeze all in-flight escrowed tETH indefinitely. **Recommend:** multisig the pauser; add a user-side cancel in V2 so a pause can't indefinitely trap escrow; consider a max-pause duration / guardian model.

### M-2 — `removeRedemption` permanently bricks a member's in-flight redemptions (Medium, owner-triggered fund lock)
`removeRedemption(V2)` (`:67-71`) makes every subsequent `V2.finalizeRedeem → controller.redeem` revert `Unauthorized`. V2 still holds users' escrowed tETH and (prior audit) has no cancel path, so those redemptions become **permanently unfinalizable and unrecoverable** — an owner-only action with no drain/migration safeguard. **Recommend:** require the member's `totalRedeeming == 0` (or provide controller-level migration) before removal, and gate removal behind a timelock so users can exit first.

### L-1 — No reentrancy guard on `redeem` (Low, latent/defense-in-depth)
The controller imports no `ReentrancyGuard`; `redeem`'s reentrancy safety rests entirely on a hook-free underlying (wstETH ✓) and every registered caller being `nonReentrant` (V2 ✓, Fastlane ✓). That holds today but is a standing assumption on all *future* members and underlyings. Add `nonReentrant` to `redeem` as cheap insurance.

### L-2 — Controller rescuer is low-impact, but note the contrast (Low)
`rescueERC20`/`rescueETH` move only the controller's *own* balance (~0; it never custodies). The rescuer here **cannot** touch the Vault's allowance — far weaker than the Vault's rescuer. Still, keep it behind a multisig for consistency.

### L-3 — Membership & pauser setters lack validation (Low, feeds H-1)
`addRedemption` (`:57`) doesn't check `_add` is a non-zero contract — an EOA/zero can be registered (an EOA member is a direct H-1 drain caller). `setPauser` (`:92`) has no zero-check. `EnumerableSet` correctly rejects duplicate add / missing remove (returns false → `RedemptionUpdateFailed`), so those are handled. Add `_add.code.length > 0` and zero-address guards.

### L-4 — Conditional recipient-blacklist & cached-underlying coupling (Low)
- `safeTransferFrom(VAULT, recipient, amount)` (`:50`) is fine for wstETH (no blacklist); a future blacklistable underlying + blacklisted `recipient` would revert and (via V2) trap that user's escrow.
- `UNDERLYING` is cached immutably from `VAULT.getUnderlying()`, which resolves through the **UUPS-upgradeable** `TAsset`. If the TAsset's underlying were ever changed by upgrade, the controller's cached `UNDERLYING` and the Vault's approval target desync and break redemptions. Document underlying as immutable-by-policy.

---

## Vectors checked and cleared (full checklist)

| Vector | Result |
|---|---|
| **Access Control** | `redeem` gated to the registered set; `addRedemption`/`removeRedemption`/`setPauser`/`transferOwnership` → `onlyOwner`; `setPause` → owner-or-pauser; `rescue*` → `onlyRescuer`. Correctly wired. |
| **Missing Access Control** | No externally-reachable state mutator is left ungated. The flaw (H-1) is *delegated* safety, not a missing modifier. |
| **Business Logic** | The controller has essentially none — and that *is* H-1: zero amount-correctness validation; all logic lives in V2/Fastlane. |
| **Price Oracle Manipulation** | No oracle/pricing in this file. A manipulated price only matters upstream (V2's rate math); the controller just moves a number it's handed. N/A here. |
| **Flash Loan** | Buys no primitive — a flash loan can't pass the membership gate, and there's no price/oracle to swing. Neutral. |
| **Input Validation** | Missing zero/contract checks on `addRedemption`/`setPauser` (L-3); `redeem` amount deliberately unvalidated (H-1). |
| **Unchecked External Calls** | `SafeERC20` for the transfer; `EnumerableSet.add/remove` return values checked (`:58-59`, `:68-69`). Only low-level call is `Rescuable.rescueETH` (rescuer-only, success-checked). Clean. |
| **Arithmetic Errors** | No arithmetic in `redeem`; amount flows straight to `transferFrom`, which reverts past Vault balance. No `unchecked`. N/A. |
| **Reentrancy** | No guard, but wstETH is hook-free and both members are `nonReentrant`; membership check is a pure set lookup with no state to corrupt. Safe today; L-1 hardening advised. |
| **Integer Overflow/Underflow** | 0.8.24 checked math; no counters or `unchecked` blocks. Not affected. |
| **Proxy & Upgradeability** | Controller is non-upgradeable (immutables + Ownable2Step). Residual coupling is the upstream UUPS `TASSET` underlying (L-4). |
| **Front-Running / TOD** | Fastlane-vs-V2 liquidity race (attack #4, retry-able) and pause/removal races (M-1/M-2). No value-extracting ordering primitive. |
| **DoS** | Pause kill-switch (M-1), `removeRedemption` strand (M-2), and the Fastlane/V2 liquidity race are the real availability items; no state corruption; no unbounded loops. |
| **Insecure Randomness** | No RNG used anywhere. N/A. |
| **Timestamp Manipulation** | No `block.timestamp`/`block.number` logic in this contract. N/A. |
| **Delegatecall to Untrusted Callee** | No `delegatecall`; all calls are typed external calls to the underlying token / EnumerableSet. Not present. |
| **Signature Replay** | No signatures, permits, or nonces. N/A. |
| **Short Address / Parameter** | ABI decoding is compiler-handled (≥0.8); no manual calldata parsing/assembly. Negligible. |
| **Uninitialized Storage Pointer** | No memory/storage struct pointers; `EnumerableSet` handled by OZ. Not affected. |
| **Approval Phishing** | The dangerous approval is the **Vault's** `type(uint).max` to this controller (`Vault.sol:94`), exercisable only via gated `redeem`. No user allowances routed here. |
| **Multisig Hijacking** | `owner`/`pauser` should be multisigs; today they're single trusted keys with drain/freeze power (H-1/M-1/M-2). Harden governance. |
| **Private Key Compromise** | Owner-key compromise ⇒ register malicious member → **full liquid-Vault drain** (H-1) or strand escrow (M-2); pauser-key ⇒ freeze-all (M-1). This is the dominant real-world risk. Timelock + multisig. |
| **Supply Chain** | Deps are OZ + in-repo protocol contracts (no exotic third-party libs). Risk is the **registered-member** set — treat each member as a supply-chain dependency of the Vault: audit and pin them. |
| **Drainer Malware** | No client/signing surface in-contract; a compromised owner signer is the on-chain equivalent (H-1). Use hardware-backed multisig for owner/pauser/rescuer. |
| **CEX & Web2 Infrastructure** | Off-chain; not applicable to this contract beyond the key-custody guidance above. |

---

## Summary

`RedemptionController.sol` is small and, at the Solidity level, correct — the membership `require`, `SafeERC20`, `EnumerableSet`, two-step ownership, and event/return-value handling are all sound. The risk is **architectural trust-concentration**, identical in shape to `TreehouseAccounting.mark`:

1. **H-1 (High, centralization-critical)** — `redeem` is an uncapped drain of the Vault's liquid balance (behind an infinite Vault approval) whose *only* bound is the owner-managed membership set. It validates nothing about the amount, so a compromised/tricked owner registering a malicious contract, or any bug in a registered member (or the inflated-NAV `TreehouseAccounting` H-1), converts directly into a full liquid-Vault drain. Move a real outflow bound into the controller; validate and timelock membership.
2. **M-1 (Medium)** — pause is a two-key (owner-or-pauser) protocol-wide redemption kill-switch that, with V2's missing cancel, can freeze all escrowed tETH indefinitely.
3. **M-2 (Medium)** — `removeRedemption` permanently bricks a member's in-flight redemptions (V2 escrow becomes unfinalizable and uncancelable). Require zero pending / provide migration before removal.
4. **L-1…L-4** — no reentrancy guard (latent); low-impact local rescuer (contrast the Vault's); missing zero/contract validation on `addRedemption`/`setPauser` (feeds H-1); conditional recipient-blacklist and cached-underlying coupling to the upgradeable TAsset.

**Adjacent (out of file scope, but they define this controller's envelope):**
- **`Vault.setRedemption` (`Vault.sol:86-97`)** grants the controller `type(uint).max` and, on rotation, revokes only the *previous* `redemption` address — the whole exit side's safety is this single infinite approval plus the controller's one `require`.
- **`TreehouseFastlane.getRedeemableAmount`** earmarks only the *one* `REDEMPTION_CONTRACT.totalRedeeming()` it was wired to, via an *approximate* `convertToAssets`; if additional V2-style members are registered, their pending redemptions aren't earmarked and Fastlane can over-draw shared liquidity (V2 then revert-and-retry — availability, not theft).
- **`Vault.withdraw` (`Vault.sol:64-70`)** lets active strategies pull assets checking `isAssetWhitelisted` but **not** `isAllowableAsset` — confirm that divergence is intended, as it governs how much Vault liquidity strategies can pull vs. what's earmarked for redemptions.
