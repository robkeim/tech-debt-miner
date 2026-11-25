# Run artifacts are one table, and RunDir reads, writes and appends over it

Accepted 2026-11-24. Decided in #103. Refines the "One `RunDir` class" rule in [ADR 0009](0009-code-layout-and-core-types.md); everything else in ADR 0009 stands.

## Decision

- **One table.** `run/artifacts.py` defines each Run file once as an `Artifact[T, K]`: its name, relative path (a function of the key `K`), encoder, explicit decoder and write policy. Adding an artifact is one entry plus its decoder in `run/store.py`.
- **Ownership is unchanged.** `RunDir` still owns every artifact path and does the atomic writes. Only the shape of its interface changes, from about 25 typed forwarding methods to `read`, `write`, `append`, `read_all`, `exists` and `keys`, plus `create`, `is_done` and `state`.
- **Write policy is data.** `Policy.REPLACE`, `CREATE_ONCE` (manifest and scores never overwrite) and `APPEND` (the JSONL logs). Calling an operation the policy does not allow raises `TypeError`.
- **Keys.** Singletons use `None`. Ranking is keyed by `(ranker, repeat)` and derived from the value on `write`, so a ranking cannot be written under the wrong name. Scores are keyed by scoring date, passed explicitly. `keys` enumerates files via the artifact's glob and `parse_key`.
- **Decoding stays explicit per type**, as ADR 0009 requires. The table points at the decoders and adds no generic or reflective decoding.
- **No `*_path` properties.** Callers use `exists`. This lands before #102, which builds the Run state type on the smaller interface.

## Why

- File name, codec and policy sit in one entry, so the four places a new artifact touched become two.
- Round-trip and policy tests iterate the table once.

## Known limits

- `key` is `K | None` rather than an overload per artifact, so a missing key on a keyed artifact is a runtime `TypeError`, not a type error.
- `cost` and `responses` keep identity codecs. Giving them core types would change the on-disk contract and is a separate decision.

## Amendments

- 2026-11-25: `cost` now has the `Cost` core type and its own codec, and its on-disk shape is `{"attempts": [...]}` (#84, see the 2026-11-25 note in [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md)). The identity-codec line above no longer holds for `cost`.
