"""The command line: the five stages, `validate`, `probe`, `report`, `resume` and `status`.

`status` prints a Run's state. See ADR 0009.
"""

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from functools import partial
from importlib.metadata import version
from pathlib import Path

from tech_debt_miner.jsonio import write_atomic
from tech_debt_miner.llm.client import (
    DEFAULT_MAX_USD,
    AnthropicTransport,
    DryRunError,
    DryRunTransport,
    LLMClient,
    LLMError,
    load_api_key,
)
from tech_debt_miner.repo import git, github
from tech_debt_miner.report import DuplicateWindowError, build_report
from tech_debt_miner.report import render as render_report
from tech_debt_miner.run.artifacts import MANIFEST, RESPONSES, SNAPSHOT
from tech_debt_miner.run.cost import open_client
from tech_debt_miner.run.label import (
    CapMismatchError,
    CloneUpdateError,
    LabelDeps,
    WindowOpenError,
    label,
)
from tech_debt_miner.run.probe import NoProbeCommitError, ProbeDeps, run_probe
from tech_debt_miner.run.rank import rank
from tech_debt_miner.run.report import load_runs
from tech_debt_miner.run.resolve import ResolveDeps, ResolveInputs, resolve
from tech_debt_miner.run.run_dir import RunDir, RunNotFoundError, Stage
from tech_debt_miner.run.score import LabelMissingError, NoRankingsError, ScoreDeps, score
from tech_debt_miner.run.snapshot import SnapshotDeps, snapshot
from tech_debt_miner.run.stages import StageDeps, resume
from tech_debt_miner.run.validate import render, validate

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_TRAINING_CUTOFF = date(2026, 6, 30)  # K, June 30 2026 (ADR 0006)
DEFAULT_REPEATS = 3  # ADR 0005
DEFAULT_REPOS_DIR = Path("repos")
TOOL_ROOT = Path(__file__).resolve().parents[2]

Handler = Callable[[argparse.Namespace], int]
RunHandler = Callable[[argparse.Namespace, RunDir], int]


def _add_report(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    report_cmd = add_parser("report", help="aggregate many Runs into a verdict")
    report_cmd.add_argument(
        "--treatment",
        default="llm",
        help="ranker compared with the Baseline; `baseline` runs the Baseline against itself",
    )
    report_cmd.add_argument("--out", type=Path, default=None, help="also write the report here")
    report_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))


def _stage_flags() -> argparse.ArgumentParser:
    """Return the flags `_stage_deps` reads, so every command that builds stage deps has them."""
    flags = argparse.ArgumentParser(add_help=False)
    flags.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    flags.add_argument("--runs-dir", type=Path, default=Path("runs"))
    flags.add_argument(
        "--no-fetch", action="store_true", help="skip fast-forwarding the clone (offline use)"
    )
    flags.add_argument(
        "--no-issues", action="store_true", help="skip fetching issues from GitHub (offline use)"
    )
    flags.add_argument(
        "--max-files", type=int, default=None, help="fix-size cap N; omit for uncapped"
    )
    return flags


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdm")
    commands = parser.add_subparsers(dest="command", required=True)
    stage_flags = _stage_flags()

    resolve_cmd = commands.add_parser("resolve", help="pin the SHA and create a Run directory")
    resolve_cmd.add_argument("--repo", required=True, help="Target repo as owner/name")
    resolve_cmd.add_argument("--cutoff", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    resolve_cmd.add_argument("--model", default=DEFAULT_MODEL)
    resolve_cmd.add_argument(
        "--training-cutoff", type=date.fromisoformat, default=DEFAULT_TRAINING_CUTOFF
    )
    resolve_cmd.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    resolve_cmd.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    resolve_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))

    label_cmd = commands.add_parser(
        "label", help="count Fix commits once the window has closed", parents=[stage_flags]
    )
    label_cmd.add_argument("run_id")

    _add_report(commands.add_parser)

    score_cmd = commands.add_parser(
        "score", help="write scores-<today>.json for a Run", parents=[stage_flags]
    )
    score_cmd.add_argument("run_id")

    validate_cmd = commands.add_parser(
        "validate",
        help="compute the fix-size cap N and print the review sheet",
        parents=[stage_flags],
    )
    validate_cmd.add_argument("run_id")

    snapshot_cmd = commands.add_parser(
        "snapshot", help="write snapshot.json for a Run", parents=[stage_flags]
    )
    snapshot_cmd.add_argument("run_id")

    probe_cmd = commands.add_parser(
        "probe", help="ask the model to name a buggy file from a post-Cutoff Fix commit message"
    )
    probe_cmd.add_argument("run_id")
    probe_cmd.add_argument("--run", action="store_true", help="send the call; default is Dry-run")
    probe_cmd.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    probe_cmd.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    probe_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))
    rank_cmd = commands.add_parser("rank", help="write the Baseline ranking for a Run")
    rank_cmd.add_argument("run_id")
    rank_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))

    resume_cmd = commands.add_parser(
        "resume",
        help="run the stages a Run has not finished; skips the done ones",
        parents=[stage_flags],
    )
    resume_cmd.add_argument("run_id")
    resume_cmd.add_argument(
        "--run", action="store_true", help="continue past planning; default stops at a Dry-run"
    )

    status_cmd = commands.add_parser("status", help="print a Run's state")
    status_cmd.add_argument("run_id")
    status_cmd.add_argument("--runs-dir", type=Path, default=Path("runs"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return _COMMANDS[args.command](args)


def _with_run(handler: RunHandler) -> Handler:
    """Open the Run named by the arguments, or print the error and exit 2, then call `handler`."""

    def run_handler(args: argparse.Namespace) -> int:
        try:
            run_dir = RunDir.open(args.runs_dir, args.run_id)
        except RunNotFoundError as error:
            print(error, file=sys.stderr)
            return 2
        return handler(args, run_dir)

    return run_handler


def _now() -> datetime:
    """Return the one clock the CLI hands to every stage that stamps a date."""
    return datetime.now(UTC)


def _stage_deps(args: argparse.Namespace) -> StageDeps:
    """Build the deps for every stage from the arguments; the CLI is their composition root."""
    return StageDeps(
        snapshot=SnapshotDeps(
            repos_dir=args.repos_dir,
            issues=None if args.no_issues else github.fetch_issues,
        ),
        label=LabelDeps(
            repos_dir=args.repos_dir,
            clock=_now,
            update_clone=None if args.no_fetch else git.fast_forward,
            max_files=args.max_files,
        ),
        closed_bugs=github.fetch_closed_bugs,
        score=ScoreDeps(clock=_now),
    )


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
        clock=_now,
    )
    print(resolve(inputs, deps).id)
    return 0


def _snapshot(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        snapshot(run_dir, _stage_deps(args).snapshot)
    except github.GitHubError as error:
        print(f"{error} (pass --no-issues to skip issues)", file=sys.stderr)
        return 1
    return 0


def _rank(args: argparse.Namespace, run_dir: RunDir) -> int:
    if not run_dir.exists(SNAPSHOT):
        print(f"run {args.run_id} has no snapshot; run `snapshot` first", file=sys.stderr)
        return 2
    rank(run_dir)
    return 0


def _label(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        deps = _stage_deps(args)
        label(run_dir, deps.label, deps.closed_bugs)
    except (WindowOpenError, CloneUpdateError, CapMismatchError, github.GitHubError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def _validate(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        result = validate(run_dir, _stage_deps(args).label)
    except (WindowOpenError, CloneUpdateError, FileExistsError) as error:
        print(error, file=sys.stderr)
        return 1
    print(render(run_dir.read(MANIFEST), result), end="")
    return 0


def _score(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        result = score(run_dir, _stage_deps(args).score)
    except (LabelMissingError, NoRankingsError, FileExistsError) as error:
        print(error, file=sys.stderr)
        return 1
    if result.excluded:
        print(f"excluded: {result.excluded}")
    return 0


def _report(args: argparse.Namespace) -> int:
    try:
        text = render_report(build_report(load_runs(args.runs_dir), treatment=args.treatment))
    except DuplicateWindowError as error:
        print(error, file=sys.stderr)
        return 1
    print(text, end="")
    if args.out is not None:
        write_atomic(args.out, text)
    return 0


def _probe(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        # Dry-run logs nothing: its raiser would otherwise leave an error row in the log.
        client = (
            open_client(
                run_dir,
                AnthropicTransport(load_api_key(os.environ, Path(".env"))),
                max_usd=args.max_usd,
                on_response=partial(run_dir.append, RESPONSES),
            )
            if args.run
            else LLMClient(DryRunTransport(), max_usd=args.max_usd)
        )
        deps = ProbeDeps(repos_dir=args.repos_dir, client=client, today=_now().date())
        result = run_probe(run_dir, deps)
    except DryRunError:
        print("Dry-run: no call was made; pass --run to send it")
        return 0
    except (WindowOpenError, NoProbeCommitError, FileExistsError, LLMError) as error:
        print(error, file=sys.stderr)
        return 1
    print("hit" if result.hit else "miss")
    return 0


def _resume(args: argparse.Namespace, run_dir: RunDir) -> int:
    try:
        ran = resume(run_dir, _stage_deps(args), run=args.run)
    except github.GitHubError as error:
        # Only `snapshot` can be told to skip GitHub; a failure after it has no such flag.
        hint = "" if run_dir.is_done(Stage.SNAPSHOT) else " (pass --no-issues to skip issues)"
        print(f"{error}{hint}", file=sys.stderr)
        return 1
    except (WindowOpenError, CloneUpdateError, CapMismatchError, FileExistsError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"ran: {', '.join(ran) or 'nothing'}; state: {run_dir.state().value}")
    return 0


def _status(_args: argparse.Namespace, run_dir: RunDir) -> int:
    print(run_dir.state().value)
    return 0


_COMMANDS: dict[str, Handler] = {
    "resolve": _resolve,
    "snapshot": _with_run(_snapshot),
    "rank": _with_run(_rank),
    "label": _with_run(_label),
    "validate": _with_run(_validate),
    "score": _with_run(_score),
    "report": _report,
    "probe": _with_run(_probe),
    "resume": _with_run(_resume),
    "status": _with_run(_status),
}


if __name__ == "__main__":
    sys.exit(main())
