# Security Audit — `Vault.sol`

**Auditor role:** Senior smart contract security researcher
**Target:** `src/treehouse/contracts/Vault.sol` (132 LoC core)
**Reviewed with:** `Rescuable.sol`, `StrategyStorage.sol`, `Strategy.sol` (to establish the trust model)
**Date:** 2026-08-06

---

## Trust model (established, not assumed)

- `owner` is a trusted protocol admin (`Ownable2Step`).
- Active strategies are registered by the owner and, via `Strategy.execute`, already run arbitrary `delegatecall` code — so an active strategy is a fully trusted component.
- `getUnderlying()` resolves to a single fixed ERC20 (the TAsset underlying).

Findings are graded against this model.

---

## Findings by attack vector

### 1. Access Control — `withdraw` ignores `_allowableAssets` (Informational / by design)
`Vault.sol:64`
```solidity
if (strategyStorage.isActiveStrategy(msg.sender) && strategyStorage.isAssetWhitelisted(msg.sender, _asset)) {
```
The inline `@audit` note asks whether skipping the allowable-asset check is intended. It is defensible: `_allowableAssets` gates *deposits*, while per-strategy `whitelistedAssets` gates *strategy withdrawals*. These are intentionally separate sets. The only consequence is that an active strategy can pull the full vault balance of *any asset whitelisted for it* — but since active strategies are owner-registered and run arbitrary delegatecall anyway, this is inside the trust boundary. **No fix required**; recommend documenting the two-set distinction.

### 2. `_transferOwnership` "missing `onlyOwner`" — NOT a bug (correcting the inline note)
`Vault.sol:164`
The `@audit` comment suggesting `onlyOwner` be added here is **wrong and would introduce a bug**. `_transferOwnership` is the internal hook called by the constructor (via `Ownable(_creator)`) and by `acceptOwnership()` (called by the *pending* owner, not the current owner). Adding `onlyOwner` would brick deployment and the accept step. Leave it as-is. Access control on the external surface (`transferOwnership` → `onlyOwner`, `acceptOwnership` → pending-owner check) is correct.

### 3. Unchecked External Call — `approve` return value not checked (Low)
`Vault.sol:91,94`
```solidity
IERC20(getUnderlying()).approve(redemption, 0);
IERC20(getUnderlying()).approve(_newRedemption, type(uint).max);
```
These use raw `approve` rather than `SafeERC20.forceApprove`, so the boolean return is ignored. For a standard underlying this is fine, and the zero-then-max ordering already handles USDT-style "reset to zero first" tokens. But the contract imports `SafeERC20` and uses it elsewhere — inconsistent. **Recommendation:** use `forceApprove` for both calls for defense-in-depth.

### 4. Business Logic — infinite approval to redemption (Low / accepted pattern)
`Vault.sol:94` grants `type(uint).max` to the redemption contract. Standard for a pull-based redemption flow, and the old redemption is revoked to `0` first (`Vault.sol:90-92`). Residual risk is centralization: a malicious/compromised redemption contract could drain the entire underlying balance. Acceptable given `setRedemption` is `onlyOwner`, but worth a comment. No unbounded-approval bug beyond the trusted-role exposure.

### 5. Input Validation — minor gaps, mostly self-guarding (Informational)
- `addAllowableAsset` (`Vault.sol:140`): no explicit zero/duplicate check, but `IERC20Metadata(_asset).decimals()` reverts on a non-contract, and `_allowableAssets.add` returns `false` on duplicate → `revert Failed()`. The inline concerns are already covered by existing logic.
- `isAllowableAsset` (`Vault.sol:109`): a `view` that `revert`s on `address(0)` is a code smell (view getters should not revert) but has no security impact.
- `withdraw` with `_amount == 0`: harmless no-op; `safeTransfer` handles failure by reverting.

### 6. Rescuable — privileged full-drain capability (Informational / centralization)
`Rescuable.sol:57` `rescueERC20` lets the `rescuer` transfer *any* ERC20 (including all user deposits and the underlying) to an arbitrary address. This is a deliberate escape hatch, but it is a single-key full-drain path. **Recommendation:** rescuer should be a timelock/multisig, and ideally excluded from rescuing the core underlying/TAsset. This is the highest real-world risk surface on the contract.

---

## Vectors checked and cleared

| Vector | Result |
|---|---|
| Reentrancy | `withdraw` holds no state and makes no callback before/after external calls; no CEI violation, no guard needed. Safe. |
| Arithmetic / Overflow-Underflow | Solidity 0.8.24 checked math; no `unchecked` blocks in this contract. Not affected. |
| Price Oracle Manipulation / Flash Loan | Vault does no pricing or share math; `RATE_PROVIDER_REGISTRY` is stored but unused here. Not applicable in this file. |
| Proxy / Upgradeability | Non-upgradeable; immutables set in constructor. No delegatecall in Vault itself. Not affected. |
| Delegatecall to untrusted callee | None in `Vault.sol`. (The arbitrary delegatecall lives in `Strategy.sol:57`, gated to `strategyExecutor` — out of this file's scope but flagged for its own review.) |
| Signature Replay | No signatures in Vault. Not applicable. |
| Insecure Randomness / Timestamp | No randomness, no `block.timestamp` dependence. Not applicable. |
| Uninitialized Storage Pointer | No struct-in-memory/storage pointer usage. Not affected. |
| Front-Running / TOD | Only owner config changes (`setRedemption`, add/remove asset); no user-value ordering dependence. Negligible. |
| DoS | `getAllowableAssets()` returns the full set — unbounded array growth is owner-controlled and view-only. No user-facing DoS. |
| Short Address / Multisig / Private Key / Supply Chain / Drainer / CEX-Web2 | Off-chain or client-side vectors, not properties of this contract. The relevant on-chain exposure is the single-key `owner`/`rescuer` centralization noted in #6. |

---

## Summary

No high/critical on-chain vulnerabilities in `Vault.sol` under its trust model. The contract is small and defensive. Priorities:

1. **#6 (rescuer full-drain)** — put `rescuer` behind a timelock/multisig; strongest real risk.
2. **#3** — switch `approve` → `forceApprove`.
3. **Correct the inline `@audit` note at `Vault.sol:164`** — adding `onlyOwner` to `_transferOwnership` would be a bug, not a fix.

---

## Adjacent observation (out of file scope)

While tracing `withdraw`, `StrategyStorage.isActiveStrategy` (`StrategyStorage.sol:216-217`) appears to be **missing its closing brace** before the `isAssetWhitelisted` doc comment. If that reflects the actual source, the file would not compile — and `Vault.withdraw` depends entirely on that function for access control. Recommend confirming against the real source and, if genuine, reviewing `StrategyStorage.sol` and `Strategy.sol` in full.

