"""The behavioral canary probe: name the buggy file from a Fix commit message alone.

Memorization check from ADR 0006, reported beside results and never in the verdict. The prompt
holds one post-Cutoff Fix commit message and nothing else: no repo name, no paths, no code. That
is the one deliberate exception to "nothing after the Cutoff date reaches a prompt", and it is
safe because the probe is a separate stage that no ranker prompt or feature reads. Everything here
is pure: it takes commits already read from the Target repo.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import cast

from tech_debt_miner.labels import is_keyword_fix
from tech_debt_miner.repo.eligibility import is_eligible
from tech_debt_miner.repo.history import CommitChange
from tech_debt_miner.types import Probe, Request

PROBE_RANKER = "probe"  # the `ranker` field of the probe's Request and log record
MAX_TOKENS = 200
MAX_MESSAGE_CHARS = 2000
SYSTEM = "You answer with JSON only."
SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}


def select_commit(commits: Sequence[CommitChange]) -> tuple[CommitChange, str] | None:
    """Return the earliest usable Fix commit and the one file it changed, or None.

    `commits` are the non-merge commits of the Label window. A commit is usable when it is a
    keyword Fix commit (ADR 0004) that touches exactly one eligible file, and its message does
    not name that file, since the answer would then be in the question. Earliest wins, with
    equal times in git order, so the choice is the same on every run.
    """
    oldest_first = list(reversed(commits))
    oldest_first.sort(key=lambda commit: commit.committed_at)  # stable: ties keep git order
    for commit in oldest_first:
        if not is_keyword_fix(commit):
            continue
        eligible = [change for change in commit.files if is_eligible(change.path)]
        if len(eligible) != 1 or eligible[0].deleted:
            continue
        path = eligible[0].path
        if PurePosixPath(path).name.lower() in commit.message.lower():
            continue
        return commit, path
    return None


def build_request(message: str, model: str) -> Request:
    """Return the probe's one call: the commit message with no repo context."""
    prompt = (
        "Here is the message of a bug-fix commit from a Python repository:\n\n"
        f"{message[:MAX_MESSAGE_CHARS]}\n\n"
        "Name the one source file this commit most likely changed, as a path relative to the "
        'repository root. Reply with JSON: {"path": "<path>"}.'
    )
    return Request(
        ranker=PROBE_RANKER,
        repeat=0,
        attempt=0,
        model=model,
        system=SYSTEM,
        prompt=prompt,
        max_tokens=MAX_TOKENS,
    )


def parse_answer(text: str) -> str:
    """Return the path the model named, or an empty string when the reply is not usable."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    answer = cast("dict[str, object]", data).get("path")
    return answer.strip().strip("`").removeprefix("./") if isinstance(answer, str) else ""


def grade(commit: str, expected_path: str, answer: str) -> Probe:
    """Return the result: a hit is the exact path, so a guess of just the right name is a miss."""
    return Probe(
        commit=commit, expected_path=expected_path, answer=answer, hit=answer == expected_path
    )
