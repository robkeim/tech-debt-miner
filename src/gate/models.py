"""The values that flow through the gate: steps to run and the results they produce."""

from dataclasses import dataclass
from typing import Literal

Status = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class Step:
    """One command in the gate.

    `argv[0]` is looked up with `resolve_tool`. `needs_ref` names a git ref that must
    exist locally; a missing ref fails the step instead of skipping it. `stdin` is piped
    to the command when set. `requires` lists helper tools the command shells out to
    (actionlint skips shell linting without shellcheck), so a missing one fails loudly
    instead of weakening the step.
    """

    name: str
    argv: tuple[str, ...]
    needs_ref: str | None = None
    requires: tuple[str, ...] = ()
    stdin: str | None = None


@dataclass(frozen=True)
class Skipped:
    """A step that does not apply, with the reason shown in the summary."""

    name: str
    reason: str


@dataclass(frozen=True)
class Result:
    name: str
    status: Status
    detail: str = ""
