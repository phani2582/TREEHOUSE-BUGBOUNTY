# Security Audit — `TAsset.sol`

**Auditor role:** Senior smart contract security researcher
**Target:** `src/treehouse/contracts/TAsset.sol` (real source; the top-level `src/treehouse/TAsset.sol` is a standard-JSON build artifact, not source)
**Dependencies read:** `ERC4626Upgradeable`, `ERC20PermitUpgradeable`, `Ownable2StepUpgradeable`, `UUPSUpgradeable`, `Initializable` (OZ v5, ERC-7201 namespaced storage), `BlacklistableUpgradeable` (Circle, non-namespaced), `InternalAccountingUnit`
**Date:** 2026-08-06

---

## Trust model

- `owner` is a trusted admin (also holds UUPS upgrade authority).
- `minters` on the IAU are trusted protocol contracts (router / redemption).
- `blacklister` is a trusted compliance role.
- IAU is a plain ERC20 (no transfer hooks).

---

## Architecture note (critical to the analysis)

`TAsset` is an ERC4626 vault whose **asset is the IAU** (`InternalAccountingUnit`), not the real underlying token. The dependency chain is: real underlying token → IAU → TAsset. `TAsset.asset()` returns the IAU; `TAsset.getUnderlying()` returns the real token.

Two gates stack on every deposit/withdraw:
1. `TAsset._deposit/_withdraw` require `IAU.isMinter(caller)`.
2. `IAU._update` requires `from`, `to`, or `msg.sender` to be a minter.

This double-gating neutralizes most of the classic ERC4626 attack surface.

---

## Findings

### 1. `_deposit` "caller should be msg.sender" — NOT a bug (correcting the inline note)
`TAsset.sol:65`
```solidity
if (!IInternalAccountingUnit(asset()).isMinter(caller)) revert Unauthorized(); //@audit caller should be msg.sender!
```
The inline `@audit` note is a **false positive**. `_deposit` is `internal` and reachable only via ERC4626 `deposit()` / `mint()`, both of which call `_deposit(_msgSender(), ...)`. Therefore `caller == msg.sender` on every reachable path. The check already gates on the actual caller. No change needed; changing it to `msg.sender` would be equivalent and purely cosmetic. Same holds for `_withdraw` at `TAsset.sol:79`.

### 2. Upgradeability — mixed namespaced/plain storage with no gap in `BlacklistableUpgradeable` (Medium, upgrade-safety)
`TAsset.sol:31`, `BlacklistableUpgradeable.sol:27-28`
All OZ v5 bases use ERC-7201 namespaced storage, so the **only** contract state occupying sequential slots is: `Blacklistable.blacklister` (slot 0), `Blacklistable._blacklistedAccounts` (slot 1), `TAsset.UNDERLYING` (slot 2). `BlacklistableUpgradeable` (Circle) is **not namespaced and has no `__gap`**. Consequence: a future upgrade can never add storage to `Blacklistable` without colliding with `TAsset.UNDERLYING`, and any change to inheritance order or variable ordering corrupts state. **Recommendation:** document this layout explicitly, freeze the inheritance order, and only ever append new variables at the end of `TAsset`. Consider migrating Blacklistable to namespaced storage.

### 3. `blacklister` never initialized (Low / operational)
`initialize` (`TAsset.sol:37-45`) never sets `blacklister`, so it defaults to `address(0)`. Since `onlyBlacklister` requires `msg.sender == blacklister`, the blacklist feature is **dormant until the owner calls `updateBlacklister`** (which correctly rejects `address(0)`). No exploit, but the compliance control is off by default — flag so ops sets it at deployment if blacklisting is expected from day one.

### 4. Front-running of `initialize` (Low / deployment-dependent)
`initialize` is `public initializer`. The implementation constructor calls `_disableInitializers()` (good — implementation can't be hijacked). Residual risk: if the deploy script deploys the proxy and calls `initialize` in a **separate transaction**, an attacker can front-run it to seize ownership (and thus UUPS upgrade rights). **Recommendation:** initialize atomically via the `ERC1967Proxy` constructor `_data` argument. Verify the deploy script does this.

### 5. Centralization — owner is upgrade admin; blacklister can freeze funds (Informational)
- `_authorizeUpgrade` is `onlyOwner` (`TAsset.sol:94`) — correct, but a single owner key can replace the entire implementation and drain/rewrite everything. Recommend a timelock/multisig owner.
- `blacklister` can freeze any holder's TAsset (by design for a compliance token, like USDC). Blacklisting `from`/`to`/`msg.sender` blocks transfers, mint, and burn via the `_update` override. Acceptable but note the censorship power.

### 6. Donation / inflation attack — mitigated, residual noted (Informational)
OZ v5 virtual-shares (+1) mitigation is active (`_decimalsOffset() == 0`). More importantly, **deposits are minter-gated** (#1), so a non-minter cannot be the first depositor or front-run one. A direct "donation" of IAU to `TAsset` to inflate `totalAssets()` also requires the donor to pass `IAU._update` (must be a minter, or `TAsset` registered as a minter making `to==TAsset` valid). IAU itself is only obtainable through protocol minters. Net: not exploitable by an external actor under the current trust model. Confirm whether `TAsset` is registered as an IAU minter and that this matches intent — it affects whether withdrawals succeed (IAU transfer out needs `TAsset` to be a minter).

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Reentrancy | IAU asset is a plain ERC20 (no ERC777/hooks). `_deposit` = transferFrom→mint, `_withdraw` = burn→transfer (OZ ordering). No external callback surface. Safe. |
| Access Control / Missing Checks | Deposit/withdraw minter-gated; `blacklist`/`unBlacklist` → `onlyBlacklister`; `updateBlacklister`/`addMinter`/`_authorizeUpgrade` → owner. `_transferOwnership` correctly left unmodified (internal hook). Sound. |
| Arithmetic / Overflow-Underflow | Solidity 0.8.24 checked math; share math via OZ `Math.mulDiv`. Not affected. |
| Signature Replay (permit) | OZ `ERC20PermitUpgradeable`: per-owner nonce + EIP-712 domain binding `chainid` and `address(this)` (proxy). Replay-safe across chains/forks. |
| Delegatecall to untrusted callee | Only UUPS `upgradeToAndCall` (owner-gated to a vetted implementation). No arbitrary delegatecall. |
| Price Oracle / Flash Loan | No oracle in TAsset; share price derived from `totalAssets()`/`totalSupply()`. Flash-loan share manipulation blocked by minter-gated deposits (#6). |
| Uninitialized Storage Pointer | No memory/storage struct pointers. Implementation locked via `_disableInitializers()`. Not affected. |
| Timestamp / Randomness | None used (permit deadline is standard). Not applicable. |
| Front-Running / TOD | Value flows are minter-restricted; no user-vs-user ordering advantage. Only #4 (init) is relevant. |
| DoS | No unbounded loops in TAsset. Blacklisting a minter could stall flows, but that's a trusted-role action. Negligible. |
| Short Address / Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain/client-side; not properties of this contract. On-chain exposure is the owner/blacklister centralization in #5. |

---

## Summary

No high/critical on-chain vulnerabilities in `TAsset.sol` under its trust model. The minter-gating on `_deposit`/`_withdraw` is the key control and correctly neutralizes the usual ERC4626 inflation/first-depositor concerns. Priorities:

1. **#2** — document and freeze the storage layout; `BlacklistableUpgradeable` has no gap and is non-namespaced. This is the main upgrade-safety risk.
2. **#4** — ensure `initialize` is called atomically in the proxy constructor to prevent front-running ownership.
3. **#3** — set `blacklister` at deployment if the blacklist must be live immediately.
4. **Correct the inline `@audit` note at `TAsset.sol:65`** — `caller` already equals `msg.sender` on all reachable paths; not a bug.

