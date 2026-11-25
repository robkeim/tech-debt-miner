"""The two stage prompts of the LLM ranker, built from a Snapshot (ADR 0010). Pure.

Dry-run and real Runs share these builders, so the Leakage test inspects the prompts that are
sent. They read only what a Snapshot carries, so nothing after the Cutoff date can reach them,
and they never show a churn count, a complexity number or a Baseline ranking.
"""

import hashlib
from collections.abc import Collection, Sequence
from importlib import resources
from math import ceil
from string import Template

from tech_debt_miner.repo.source import HEAD_LINES
from tech_debt_miner.types import FileFacts, OutlineEntry, Snapshot

TRIAGE_TEMPLATE = "triage"
RANK_TEMPLATE = "rank"
TRIAGE_SET_SIZE = 100  # the Triage set holds `min(TRIAGE_SET_SIZE, eligible files)`
RANKING_SIZE = 50  # the most files stage 2 returns
DIGEST_MAX_SUBJECTS = 5
# Conservative: real code averages nearer 4 characters a token (ADR 0022).
CHARS_PER_TOKEN = 3
# What the stage 1 digest may use. Sonnet 5.5 reads 1M tokens; the rest is for the template, the
# output and slack in the estimate. A convention, not a tuned value.
DIGEST_TOKEN_BUDGET = 800_000


class DigestOverflowError(Exception):
    """The digest does not fit even with path and LOC alone, so the Dry-run fails (ADR 0010)."""


def estimate_tokens(text: str) -> int:
    """Return a conservative token count for `text`: more than a real tokenizer would say."""
    return ceil(len(text) / CHARS_PER_TOKEN)


def _template_bytes(name: str) -> bytes:
    return (resources.files("tech_debt_miner") / "prompts" / f"{name}.txt").read_bytes()


def load_template(name: str) -> str:
    return _template_bytes(name).decode("utf-8")


def template_hashes() -> dict[str, str]:
    """Return each template's SHA-256, for the Manifest."""
    return {
        name: hashlib.sha256(_template_bytes(name)).hexdigest()
        for name in (TRIAGE_TEMPLATE, RANK_TEMPLATE)
    }


def triage_set_size(eligible_files: int) -> int:
    return min(TRIAGE_SET_SIZE, eligible_files)


def _entry_lines(file: FileFacts, *, subjects: int, names: bool) -> list[str]:
    header = f"{file.path} ({file.loc} lines)"
    if names and file.top_level_names:
        header += f": {', '.join(file.top_level_names)}"
    return [header] + [f"  {c.date} {c.subject}" for c in file.recent_commits[:subjects]]


def build_digest(files: Sequence[FileFacts], *, max_tokens: int = DIGEST_TOKEN_BUDGET) -> str:
    """Return the stage 1 digest: every file, in path order, with the most detail that fits.

    Detail shrinks uniformly for all files: first fewer commit subjects, then no names. A file is
    never dropped. Raises `DigestOverflowError` when path and LOC alone exceed `max_tokens`.
    """
    ordered = sorted(files, key=lambda file: file.path)
    levels = [(count, True) for count in range(DIGEST_MAX_SUBJECTS, -1, -1)] + [(0, False)]
    for subjects, names in levels:
        digest = "\n".join(
            line for file in ordered for line in _entry_lines(file, subjects=subjects, names=names)
        )
        if estimate_tokens(digest) <= max_tokens:
            return digest
    msg = f"the digest of {len(ordered)} files exceeds {max_tokens} tokens with path and LOC only"
    raise DigestOverflowError(msg)


def build_triage_prompt(snapshot: Snapshot, *, max_tokens: int = DIGEST_TOKEN_BUDGET) -> str:
    """Return the stage 1 prompt: the digest of every eligible file."""
    digest = build_digest(snapshot.files, max_tokens=max_tokens)
    return Template(load_template(TRIAGE_TEMPLATE)).substitute(
        count=triage_set_size(len(snapshot.files)), digest=digest
    )


def _outline_lines(outline: Sequence[OutlineEntry]) -> list[str]:
    return [
        f"{'  ' * entry.depth}{entry.kind} {entry.name} (line {entry.line})"
        for entry in outline
        if entry.line > HEAD_LINES
    ]


def _code_block(file: FileFacts) -> str:
    lines = [f"=== {file.path} ==="]
    if file.recent_commits:
        lines += ["Recent commits:", *(f"{c.date} {c.subject}" for c in file.recent_commits)]
    lines += ["Code:", file.head]
    if file.truncated_lines:
        outline = _outline_lines(file.outline)
        lines += ["Outline of the rest:", *outline] if outline else []
        lines.append(f"[truncated {file.truncated_lines} lines]")
    return "\n".join(lines)


def build_rank_prompt(snapshot: Snapshot, triage_set: Collection[str]) -> str:
    """Return the stage 2 prompt: code, outline and history for the Triage set, in path order.

    Raises `ValueError` for a path that is not in the Snapshot.
    """
    chosen = set(triage_set)
    unknown = chosen - {file.path for file in snapshot.files}
    if unknown:
        msg = f"not in the Snapshot: {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    files = sorted((file for file in snapshot.files if file.path in chosen), key=lambda f: f.path)
    return Template(load_template(RANK_TEMPLATE)).substitute(
        count=len(files),
        head_lines=HEAD_LINES,
        limit=RANKING_SIZE,
        files="\n\n".join(_code_block(file) for file in files),
    )
