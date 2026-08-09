# Security Audit — `InternalAccountingUnit.sol`
### (senior researcher + adversarial / black-hat lens)

**Target:** `src/treehouse/contracts/InternalAccountingUnit.sol`
**Type:** Non-upgradeable ERC20 (`ERC20` + `Ownable2Step`), 155 LoC
**Role in system:** The IAU is the accounting token that backs `TAsset` (TAsset is an ERC4626 vault whose `asset()` is this IAU). It is intentionally near-soulbound: transfers only succeed when a minter is a party.
**Dependencies:** OZ `ERC20`, `Ownable2Step`/`Ownable`, `EnumerableSet.AddressSet`, `IERC20Metadata`. All standard; no custom math, no external protocol calls, no oracle, no delegatecall, no upgradeability.
**Date:** 2026-08-07

**Trust model:** `owner` = trusted admin. `minters` = trusted protocol contracts (router, redemption, TAsset flows). `timelock` = intended governance address.

---

## The core attack surface (how I'd actually attack this)

The whole security of this token collapses to one sentence: **any single minter can mint unlimited IAU to anyone and burn any holder's IAU with no allowance.** There is no supply cap, no backing check, and no per-minter limit. So the real target isn't the Solidity — it's the minter set and the two keys that control it.

### H-1 — Unbacked/unlimited mint: one compromised minter drains the protocol (High, centralization-critical)
`mintTo` (`InternalAccountingUnit.sol:84`) mints arbitrary amounts with only `onlyMinters`. Nothing ties a mint to a real-underlying deposit; the "1 IAU = 1 underlying" invariant is enforced entirely off-chain / in the minter contracts, not here.

Black-hat path: compromise **any** address in `_minters` (a buggy router action, a delegatecall sink in a strategy, a leaked key) → `mintTo(attacker, 1e30)` → deposit that IAU into `TAsset` → `TAsset` shares now claim a huge fraction of real assets → redeem → drain. The blast radius of a single minter is the entire TVL.
**Mitigations to recommend:** minimize the minter set; each minter should itself be a minimal, audited, non-`delegatecall` contract; consider a mint cap or a supply-vs-collateral invariant check; monitor `Minted` events with alerting.

### H-2 — `burnFrom` burns any account with no allowance (High, by-design but dangerous)
`burnFrom(_burnAddress, _burnAmount)` (`:74`) calls `_burn(_burnAddress, ...)` with **no allowance check** — any minter can destroy any holder's IAU balance. This is deliberate for redemption flows, but it means a compromised/misbehaving minter can wipe balances arbitrarily (griefing, or resetting balances to enable accounting manipulation). Combined with H-1, a single rogue minter has total control over the IAU supply and distribution.
**Recommend:** document explicitly; ideally scope which minter may burn-from (role separation between "mint" and "burn-from" minters), and emit richer events for off-chain reconciliation.

### M-1 — `timelock` is a self-perpetuating co-owner, not an actual timelock (Medium)
`_checkOwner` is overridden (`:150-154`) so `onlyOwner` passes for **either** `owner()` **or** `timelock`. There is no verification that `timelock` is a contract, enforces any delay, or is even non-EOA (`setTimelock` at `:113` takes any address, no zero/contract check). Consequences:

- `timelock` can call **every** owner function: `addMinter`, `removeMinter`, `setTimelock`, and — because `Ownable2Step.transferOwnership` is `onlyOwner` — even `transferOwnership`.
- So a compromised `timelock` key can `addMinter(attacker)` (→ H-1), or `transferOwnership(attacker)` + `setTimelock(attacker)` and **lock the legitimate owner out entirely**.
- The name "timelock" implies delayed governance, but as written it's just a second, equally-powerful admin key with no delay. This is a classic naming-vs-behavior trap that leads operators to under-protect the key.

**Recommend:** if it's meant to be a timelock, deploy an actual `TimelockController` and document that the address must be that contract; add a zero-address guard; consider scoping timelock to a subset of functions rather than full owner-equivalence.

### L-1 — Removing/rotating a minter is front-runnable (TOD) and can freeze non-minter holders (Low)
- `removeMinter` (`:103`) can be front-run: a minter about to be removed can, in the same block, `mintTo`/`burnFrom` before losing rights. Trusted-role, but note the race exists when de-authorizing a suspected-compromised minter — removal is not atomic protection.
- Because `_update` (`:144-146`) requires a minter among `{from, to, msg.sender}`, if the relevant minters are removed, IAU held by ordinary addresses becomes **non-transferable and non-burnable** (frozen). Owner-triggered, but a foot-gun during minter rotation.

### L-2 — Constructor makes external calls to `_underlying` (Low / deployment-time)
The constructor (`:45-53`) calls `_underlying.name()` and `_underlying.symbol()` inside `string.concat`. A malicious or non-standard underlying could revert (bricking deployment) or return oversized strings (gas). Deployment is owner-controlled so impact is limited to the deploy tx, but pass a vetted underlying.

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Reentrancy | Plain ERC20, no hooks, no external calls in mint/burn/transfer paths. Safe. |
| Access Control / Missing Checks | `mintTo`/`burn`/`burnFrom` → `onlyMinters`; `addMinter`/`removeMinter`/`setTimelock` → `onlyOwner`. All state-changers gated. The *design* concerns (H-1, H-2, M-1) are privilege scope, not missing checks. |
| Arithmetic / Overflow-Underflow | Solidity 0.8.24 checked math; no `unchecked`, no custom math. Not affected. |
| Approval Phishing | IAU is effectively non-transferable for non-minters (`_update` gate), so ERC20 allowances are inert for ordinary users — no meaningful phishing surface. `burnFrom` ignores allowance entirely (see H-2). |
| Proxy & Upgradeability | Non-upgradeable, no proxy, immutable `UNDERLYING`. Not applicable. |
| Delegatecall to untrusted callee | None in this contract. (Risk lives in strategy contracts that may *be* minters — see H-1.) |
| Price Oracle / Flash Loan | No pricing logic here. Flash loans can't obtain IAU (mint is minter-only, transfers gated). Not applicable to this file. |
| Signature Replay | No signatures/permit in IAU (permit lives on TAsset). Not applicable. |
| Insecure Randomness / Timestamp | None used. Not applicable. |
| Uninitialized Storage Pointer | No storage-pointer usage; constructor-set immutable. Not affected. |
| Integer / Short-Address | ABI-level; handled by compiler ≥0.8 + standard calldata decoding. Negligible. |
| DoS | No unbounded loops in write paths; `getMinters`/`getUnderlying` are view. Only owner-induced freeze (L-1). |
| Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain vectors. **These are the dominant real risk here**: the owner key, the timelock key (M-1), and every minter key are each catastrophic single points (H-1). Put owner behind a multisig, use a real timelock, and treat every minter contract as in-scope for the same rigor. |

---

## Summary

No memory-safety or arithmetic bugs — the contract is small and correct at the Solidity level. The risk is **entirely in privilege design**, and it is significant:

1. **H-1 / H-2** — unlimited mint + allowance-free burn means **any single compromised minter drains or wrecks the protocol.** The on-chain code enforces no backing invariant; minters must be minimal and fully trusted, and the set kept as small as possible.
2. **M-1** — `timelock` is a mislabeled, self-perpetuating **co-owner with no delay**; a compromised timelock key = full takeover and owner lockout. Use an actual `TimelockController`, add a zero-address guard, and consider scoping its powers.
3. **L-1 / L-2** — minter-removal is front-runnable and can freeze holders; constructor trusts the underlying's `name()/symbol()`.

