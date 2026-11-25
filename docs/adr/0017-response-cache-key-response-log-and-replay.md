# The Response cache key, the responses log and Replay

Accepted. Decided in #83. It fills in the cache layers of [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md) and the reproducibility rule of [ADR 0001](0001-reproducibility-means-replay.md), on top of the Run artifact table of [ADR 0015](0015-run-artifacts-are-a-codec-table.md) and the client from [ADR 0014](0014-provider-neutral-response-and-the-anthropic-dependency.md).

## Decision

- **Key.** The hex SHA-256 of the canonical JSON of `model`, `system`, `prompt`, `max_tokens`, the output `schema`, `repeat` and `attempt`. `ranker` is a log label that the API never sees, so it is not in the key; two rankers that send the same call share one entry. The repeat and attempt are in the key but never sent ([ADR 0008](0008-pipeline-stages-artifacts-and-resume.md)).
- **Store.** `llm/cache.py` holds `cache_key` and `ResponseCache`: one atomically written JSON file per entry at `<root>/<first 2 hex>/<key>.json`, holding a `Response`. The root is chosen by the caller; ADR 0008 names `.cache/responses/`, which `.gitignore` already covers. An unreadable entry is a miss and the next put replaces it. There is no eviction.
- **Hits are free and come first.** `LLMClient.complete` checks the cache before the price lookup and the cap, so a hit costs $0 and is never refused for lack of budget. A miss that succeeds is stored. Failed attempts are never stored. The per-attempt log marks each record `cache_hit`; a hit has `try_number` 0.
- **`responses.jsonl` row.** Every returned Response, hit or miss, goes to an injected `on_response` callback, which a caller wires to `run_dir.append(RESPONSES, row)`, as one row: `ranker`, `repeat`, `attempt`, `cache_hit` and the Response fields. The text is redacted like the per-attempt log. A resume that finds its replies in the cache logs them again, so the file may hold the same (ranker, repeat, attempt) more than once; the rows are identical apart from `cache_hit`.
- **Unparsable output.** `LLMClient.complete_parsed(request, parse, schema, amend=...)` calls `parse` on the text and, if it raises `ValueError`, sends the request once more with `attempt + 1` (after an optional `amend` rewrite, for example to append the validation error as [ADR 0010](0010-llm-ranker-design.md) says). Both replies are logged raw. A second failure raises `UnparsableOutputError`, so `rank` fails loudly and stays resumable.
- **Replay.** `run/replay.py` reads only the Run directory: `logged_responses` decodes the log, `final_responses` takes the highest attempt for each (ranker, repeat), and `replay_rankings(run_dir, parse)` rebuilds each `Ranking` with a ranker-supplied parser. Replay imports no client, cache or repo code. A final reply that does not parse raises; it is never replayed as an empty ranking.
- **`RESPONSES` gets a codec.** ADR 0015 left `responses` with an identity codec and called a core type a separate decision. This is that decision: the artifact holds a `LoggedResponse` (`types.py`) encoded by `store.logged_response_to_json`, so the client and Replay never handle raw dicts.
- **Layering.** `llm/cache.py` imports `run/store.py` for atomic JSON IO and the `Response` codec. `store.py` imports only `types`, so no cycle forms, but this is outside the leaf rule of [ADR 0009](0009-code-layout-and-core-types.md) even as [ADR 0016](0016-leaf-imports-and-clone-updates-by-label.md) relaxed it, which allows only the pure `repo` modules. Neither amends the rule here. The ways out are to move the JSON helpers into a pure module the rule then names, to inline a small atomic writer and codec in the cache (about 15 duplicated lines), or to inject the read and write functions. None was clearly better, so the import stays and Rob decides.

## Why

- **The schema is in the key** because it changes what the API returns for the same text. **The ranker is not**, so the cache never pays twice for a call it already has.
- **Hits before the cap** because the cap exists to limit spend, and a hit spends nothing. A resumed Run should never fail on budget for replies it already has.
- **Parsing is the client's retry trigger, not the cache's.** A cached bad reply would be returned forever, so the retry changes the key.
- **Replay takes the parser as an argument** so `run/` does not import the rankers, and so the parse used at rank time and at replay time is one function.

## Known limits

- **Transport settings are not in the key.** Thinking mode and effort ([ADR 0010](0010-llm-ranker-design.md)) are set when the transport is built, so changing them returns older replies for identical requests. Clear the cache directory when they change. Adding a settings fingerprint to the key is a possible follow-up.
- **The key is not versioned.** Changing which fields it covers orphans old entries, which is harmless but wastes disk.
- **Replay rebuilds rankings only.** Re-scoring them needs `labels.json` and the scoring code, which Replay leaves to the `score` stage.

## Alternatives rejected

- **Including `ranker` in the key.** It splits entries for identical API calls and gives up free hits for nothing.
- **A single JSON or SQLite cache file.** One file per entry needs no locking, survives a crash with at most one lost entry, and can be inspected with `ls`.
- **Replay served through a fake transport.** It would still need a client and would hide a log that is missing a reply behind a transport error.

## Amendments

- 2026-11-25: The key now also covers the transport's thinking and effort settings ([#119](https://github.com/robkeim/tech-debt-miner/issues/119)), which closes the first "Known limits" item. `AnthropicTransport.settings` supplies them, `ResponseCache(root, settings)` holds them, and `cache_key` hashes them under `settings`. `ranker` stays out. Entries written before this change are orphaned, as the "key is not versioned" limit already says.
