"""The command line: `resolve` and `status` so far (ADR 0009)."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path

from tech_debt_miner.run.resolve import ResolveDeps, ResolveInputs, resolve
from tech_debt_miner.run.run_dir import RunDir

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_TRAINING_CUTOFF = date(2026, 6, 30)  # K, June 30 2026 (ADR 0006)
DEFAULT_REPEATS = 3  # ADR 0005
TOOL_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdm")
    commands = parser.add_subparsers(dest="command", required=True)

    resolve_cmd = commands.add_parser("resolve", help="pin the SHA and create a Run directory")
    resolve_cmd.add_argument("--repo", required=True, help="Target repo as owner/name")
    resolve_cmd.add_argument("--cutoff", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    resolve_cmd.add_argument("--model", default=DEFAULT_MODEL)
    resolve_cmd.add_argument(
        "--training-cutoff", type=date.fromisoformat, default=DEFAULT_TRAINING_CUTOFF
    )
    resolve_cmd.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    resolve_cmd.add_argument("--repos-dir", type=Path, default=Path("repos"))
    resolve_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))

    status_cmd = commands.add_parser("status", help="print a Run's state")
    status_cmd.add_argument("run_id")
    status_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "resolve":
        return _resolve(args)
    return _status(args)


def _resolve(args: argparse.Namespace) -> int:
    inputs = ResolveInputs(
        repo=args.repo,
        cutoff=args.cutoff,
        model=args.model,
        training_cutoff=args.training_cutoff,
        repeats=args.repeats,
    )
    deps = ResolveDeps(
        repos_dir=args.repos_dir,
        runs_dir=args.runs_dir,
        tool_root=TOOL_ROOT,
        lizard_version=version("lizard"),
        clock=lambda: datetime.now(UTC),
    )
    print(resolve(inputs, deps).id)  # noqa: T201 - the CLI's job is to print
    return 0


def _status(args: argparse.Namespace) -> int:
    run_dir = RunDir(args.runs_dir / args.run_id)
    if not run_dir.manifest_path.exists():
        print(f"no such Run: {args.run_id}", file=sys.stderr)  # noqa: T201 - the CLI's job is to print
        return 2
    state = run_dir.state()
    print(state.value if state else "resolved")  # noqa: T201 - the CLI's job is to print
    return 0


if __name__ == "__main__":
    sys.exit(main())
