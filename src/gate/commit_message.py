"""Commit message and PR title rules from CONTRIBUTING.md#commits-and-prs.

The commit-msg hook and the CI title check both call `validate_message`, so a
title that passes CI is exactly a message the hook would accept.
"""

import re

TYPES = (
    "feat",
    "fix",
    "docs",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)
MAX_SUBJECT = 72
MAX_BODY_LINE = 72

_HEADER = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?: (?P<subject>.*)$",
)
_SCOPE = re.compile(r"^[a-z][a-z0-9-]*$")
_TRAILER = re.compile(r"^(?:[A-Za-z][A-Za-z-]*|BREAKING CHANGE): \S")
_SCISSORS = "# ------------------------ >8 ------------------------"


def strip_comments(message: str) -> str:
    """Drop git's comment lines and everything after the scissors line."""
    kept: list[str] = []
    for line in message.splitlines():
        if line == _SCISSORS:
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept).strip("\n")


def validate_title(title: str) -> list[str]:
    """Return the rule violations in a one-line header (empty when valid)."""
    if "\n" in title:
        return ["title must be a single line"]
    match = _HEADER.match(title)
    if match is None:
        return ["header must look like `<type>(<scope>)<!>: <subject>`"]

    errors: list[str] = []
    if match["type"] not in TYPES:
        errors.append(f"type `{match['type']}` is not one of: {', '.join(TYPES)}")
    scope = match["scope"]
    if scope is not None and not _SCOPE.match(scope):
        errors.append(f"scope `{scope}` must be a short lowercase noun")

    subject = match["subject"]
    if not subject.strip():
        errors.append("subject must not be empty")
        return errors
    if subject != subject.strip():
        errors.append("subject must not have leading or trailing whitespace")
    if subject[0].isupper():
        errors.append("subject must be lowercase after the prefix")
    if subject.endswith("."):
        errors.append("subject must not end with a period")
    if len(subject) > MAX_SUBJECT:
        errors.append(f"subject is {len(subject)} characters; the limit is {MAX_SUBJECT}")
    return errors


def validate_message(message: str) -> list[str]:
    """Return the rule violations in a full commit message (empty when valid)."""
    lines = strip_comments(message).splitlines()
    if not lines:
        return ["message is empty"]

    errors = validate_title(lines[0])
    body = lines[1:]
    if body and body[0].strip():
        errors.append("leave a blank line between the header and the body")
    errors.extend(
        f"body line {number} is {len(line)} characters; wrap at {MAX_BODY_LINE}"
        for number, line in enumerate(body, start=2)
        if len(line) > MAX_BODY_LINE and not _TRAILER.match(line)
    )
    return errors
