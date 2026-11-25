# A Ranking holds ordered tie groups, not ordered paths

Accepted 2026-11-25. Decided in #71. Changes the `Ranking` core type described in [ADR 0009](0009-code-layout-and-core-types.md).

## Decision

`Ranking.groups` is a tuple of tuples of paths, most risky group first. Files in one inner tuple are tied with each other. A ranking with no ties (every LLM ranking) is all singleton groups. The Baseline writes its real ties ([ADR 0007](0007-heuristic-baseline-definition.md)), and the scorer hands the groups straight to its tie averaging ([ADR 0005](0005-scoring-pre-registration.md)).

Members of a group are stored sorted by path, only so the artifact bytes are deterministic. That order carries no meaning: the scorer averages over every ordering of the group, so it is not a tie-break.

## Why

ADR 0005 forbids a path-name tie-break and requires averaging over tied orderings, and the Baseline produces ties. A flat ordered tuple loses them, and any reader would silently apply the stored order. Putting the groups in the artifact keeps `rankings/baseline.json` self-describing, so Replay and scoring can read ties from the artifact alone, without the Snapshot or the ranker module (the scorer already takes groups).

## Known limits

- Every reader of `Ranking` handles groups, even where ties never occur.
- Sorting members by path looks like a tie-break. It is not, only because the scorer ignores member order; a scorer that did not would break ADR 0005.

## Alternatives rejected

- **An optional `ties` field beside `paths`.** Two fields that must agree, and a reader can ignore the second.
- **Recompute groups from `snapshot.json` when scoring.** Scoring would depend on the ranker module, and the artifact alone could not be replayed.
