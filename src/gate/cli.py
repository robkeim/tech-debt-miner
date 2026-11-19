"""Entry point for `uv run gate`."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from gate import repo
from gate.commit_message import strip_comments, validate_message, validate_title
from gate.runner import Result, Step, exit_code, run_steps
from gate.steps import FIX_STEPS, INSTALL_STEPS, fast_steps, full_steps

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
    return exit_code(run_steps([step], ref_exists=lambda ref: repo.ref_exists(ref, root)))


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


def _steps(args: argparse.Namespace, root: Path) -> list[Result]:
    def ref_exists(ref: str) -> bool:
        return repo.ref_exists(ref, root)

    if args.command == "install":
        return run_steps(INSTALL_STEPS, ref_exists=ref_exists)
    if args.fix:
        return run_steps(FIX_STEPS, ref_exists=ref_exists)
    if args.fast:
        return run_steps(fast_steps(repo.staged_files(root), root), ref_exists=ref_exists)
    steps = full_steps(
        workflows_changed=repo.workflows_changed_since(repo.MAIN_REF, root),
        in_ci=bool(os.environ.get("CI")),
    )
    return run_steps(steps, ref_exists=ref_exists)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command and (args.fast or args.fix):
        parser.error("--fast and --fix cannot be combined with a subcommand")
    if args.fast and args.fix:
        parser.error("--fast and --fix cannot be combined")
    if args.command == "commit-msg":
        return _commit_msg(args.file)
    if args.command == "pr-title":
        return _pr_title()
    return exit_code(_steps(args, Path.cwd()))


if __name__ == "__main__":
    sys.exit(main())
