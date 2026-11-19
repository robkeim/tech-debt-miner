"""Entry point for `uv run gate`."""

import argparse
import os
import sys
from collections.abc import Sequence
from enum import Enum
from pathlib import Path

from gate import repo
from gate.commit_message import strip_comments, validate_message, validate_title
from gate.models import Step
from gate.runner import Environment, exit_code, run_steps
from gate.steps import FIX_STEPS, INSTALL_STEPS, WorkflowLint, fast_steps, full_steps

PR_TITLE_ENV = "PR_TITLE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gate", description="The single definition of green.")
    parser.add_argument("--fast", action="store_true", help="the pre-commit subset")
    parser.add_argument("--fix", action="store_true", help="apply ruff format and ruff check --fix")
    commands = parser.add_subparsers(dest="command")
    commit_msg = commands.add_parser("commit-msg", help="validate a commit message file")
    commit_msg.add_argument("file", type=Path)
    commands.add_parser("pr-title", help=f"validate the title in ${PR_TITLE_ENV}")
    commands.add_parser("install", help="install the git hooks")
    return parser


def _report(errors: Sequence[str], subject: str) -> int:
    if not errors:
        return 0
    print(f"{subject} is invalid:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def _spellcheck(message: str, root: Path) -> int:
    """Spellcheck the message without git's comment lines, using the repo's cspell config.

    The text goes in on stdin: cspell skips files outside the repo, so a temp file
    would report "no files found" and check nothing.
    """
    step = Step(
        "cspell (commit message)",
        ("cspell", "--no-progress", "--config", str(root / "cspell.json"), "stdin"),
        stdin=strip_comments(message) + "\n",
    )
    return exit_code(run_steps([step], Environment(root)))


def _commit_msg(file: Path) -> int:
    message = file.read_text(encoding="utf-8")
    rules = _report(validate_message(message), "commit message")
    return max(rules, _spellcheck(message, Path.cwd()))


def _pr_title() -> int:
    title = os.environ.get(PR_TITLE_ENV)
    if title is None:
        print(f"{PR_TITLE_ENV} is not set", file=sys.stderr)
        return 1
    return _report(validate_title(title), "PR title")


class Mode(Enum):
    """What one invocation does, decided once from the parsed arguments."""

    FULL = "full"
    FAST = "fast"
    FIX = "fix"
    INSTALL = "install"
    COMMIT_MSG = "commit-msg"
    PR_TITLE = "pr-title"


def _mode(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Mode:
    if args.command and (args.fast or args.fix):
        parser.error("--fast and --fix cannot be combined with a subcommand")
    if args.fast and args.fix:
        parser.error("--fast and --fix cannot be combined")
    if args.command:
        return Mode(args.command)
    if args.fix:
        return Mode.FIX
    return Mode.FAST if args.fast else Mode.FULL


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    match _mode(parser, args):
        case Mode.COMMIT_MSG:
            return _commit_msg(args.file)
        case Mode.PR_TITLE:
            return _pr_title()
        case Mode.INSTALL:
            steps = INSTALL_STEPS
        case Mode.FIX:
            steps = FIX_STEPS
        case Mode.FAST:
            steps = fast_steps(repo.staged_files(root), root)
        case Mode.FULL:
            steps = full_steps(
                WorkflowLint.when(
                    bool(os.environ.get("CI")) or repo.workflows_changed_since(repo.MAIN_REF, root)
                )
            )
    return exit_code(run_steps(steps, Environment(root)))


if __name__ == "__main__":
    sys.exit(main())
