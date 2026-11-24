"""The Response cache: a global store of replies keyed by the exact request (ADR 0008, ADR 0016).

Never pay twice for an identical request. The key covers everything the API sees plus the repeat
and attempt indexes, which the API does not see: the 3 repeats send identical requests, and a key
without the repeat would return one reply three times.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path

from tech_debt_miner.run import store
from tech_debt_miner.types import Request, Response


def cache_key(request: Request, schema: Mapping[str, object] | None = None) -> str:
    """Return the hex SHA-256 of the request, schema, repeat and attempt.

    `ranker` is a label for logs, not part of the call, so it is not in the key.
    """
    identity = {
        "model": request.model,
        "system": request.system,
        "prompt": request.prompt,
        "max_tokens": request.max_tokens,
        "schema": schema,
        "repeat": request.repeat,
        "attempt": request.attempt,
    }
    return hashlib.sha256(store.canonical_json(identity).encode("utf-8")).hexdigest()


class ResponseCache:
    """One JSON file per entry under `root`, written atomically."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, request: Request, schema: Mapping[str, object] | None = None) -> Response | None:
        path = self._path(cache_key(request, schema))
        try:
            return store.response_from_json(store.read_json(path))
        except FileNotFoundError:
            return None
        except ValueError, KeyError, TypeError:
            return None  # an unreadable entry is a miss; the next put replaces it

    def put(
        self,
        request: Request,
        response: Response,
        schema: Mapping[str, object] | None = None,
    ) -> None:
        store.write_json(self._path(cache_key(request, schema)), store.to_json(response))

    def _path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.json"
