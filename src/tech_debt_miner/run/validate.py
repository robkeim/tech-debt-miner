"""The `validate` command: the ADR 0004 pre-run checks, written once per Run.

It computes the fix-size cap N, reports the Label at N and at 5, 10, 20 and uncapped, and
samples the Fix commits for the review sheet. It reads the same closed window as `label`, so
N comes from the commits the Label will count. The human review is not part of this stage.
"""

from tech_debt_miner import labels
from tech_debt_miner.repo import git
from tech_debt_miner.run.artifacts import VALIDATION
from tech_debt_miner.run.label import LabelDeps, read_window
from tech_debt_miner.run.run_dir import RunDir
from tech_debt_miner.types import Manifest, ReviewItem, Validation


def validate(run_dir: RunDir, deps: LabelDeps) -> Validation:
    """Write `validation.json`, or raise `FileExistsError` if N was already computed.

    N is fixed before any scored Run, so the file is create-once: a different N needs a new
    Run. Pass the printed N to `label --max-files`. `deps.max_files` is not used.
    """
    if run_dir.exists(VALIDATION):
        msg = f"{VALIDATION.path(None)} already exists; N is fixed before any scored Run"
        raise FileExistsError(msg)
    window = read_window(run_dir, deps)
    sizes = labels.fix_sizes(window.commits)
    cap_n = labels.percentile_cap(sizes)
    caps = [*([] if cap_n is None else [cap_n]), *labels.CAP_GRID]
    sample = [] if cap_n is None else labels.sample_fixes(window.commits, cap_n)
    result = Validation(
        cap_n=cap_n,
        fix_commits_sized=len(sizes),
        cap_report=labels.cap_report(window.commits, window.cutoff_files, caps),
        sample_seed=labels.SAMPLE_SEED,
        sample=tuple(
            ReviewItem(
                sha=commit.sha,
                message=commit.message,
                issue_references=labels.issue_references(commit),
                files=labels.eligible_files(commit),
                diff_stat=git.diff_stat(window.clone, commit.sha),
            )
            for commit in sample
        ),
        clone_head=git.head_sha(window.clone),
        fetched=deps.update_clone is not None,
    )
    run_dir.write(VALIDATION, result)
    return result


def render(manifest: Manifest, validation: Validation) -> str:
    """Return the cap report and the review sheet as Markdown, for the reviewer."""
    cap = (
        "none, no Fix commit touches an Eligible file"
        if validation.cap_n is None
        else str(validation.cap_n)
    )
    lines = [
        f"# Validation for {manifest.target_repo} at {manifest.cutoff_date}",
        "",
        f"- Fix-size cap N (90th percentile of {validation.fix_commits_sized} fix sizes): {cap}",
        f"- Clone HEAD: {validation.clone_head} (fast-forwarded: {validation.fetched})",
        "",
        "## Label by cap",
        "",
        "| Cap | Fix commits dropped | Files with a Label | Label total |",
        "| --- | --- | --- | --- |",
    ]
    for index, row in enumerate(validation.cap_report):
        name = "uncapped" if row.max_files is None else str(row.max_files)
        if index == 0 and validation.cap_n is not None:
            name = f"N = {name}"
        lines.append(
            f"| {name} | {row.fix_commits_dropped} | {row.files_labeled} | {row.label_total} |"
        )
    lines += [
        "",
        f"## Review sheet ({len(validation.sample)} Fix commits, seed {validation.sample_seed})",
        "",
        "The rule fails if more than 20% are not real fixes (ADR 0004).",
    ]
    for number, item in enumerate(validation.sample, start=1):
        references = ", ".join(item.issue_references) or "none"
        lines += [
            "",
            f"### {number}. {item.sha}",
            "",
            f"- Issue references: {references}",
            f"- Filtered files: {', '.join(item.files)}",
            "- Real fix: yes / no",
            "",
            "```text",
            item.message,
            "```",
            "",
            "```text",
            item.diff_stat,
            "```",
        ]
    return "\n".join(lines) + "\n"
