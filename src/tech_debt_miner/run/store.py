"""The (de)serialization of the core types beside `RunDir`.

The types stay pure data; everything about the on-disk format lives here. The generic JSON and
JSONL file IO lives in `jsonio`.
"""

from collections.abc import Mapping
from typing import Any

from tech_debt_miner.jsonio import response_from_json, to_json
from tech_debt_miner.types import (
    CapResult,
    CommitSubject,
    Cost,
    CostAttempt,
    FileFacts,
    Issue,
    Labels,
    LateLabels,
    LoggedResponse,
    Manifest,
    OutlineEntry,
    Probe,
    Ranking,
    Request,
    ReviewItem,
    RunScores,
    Scores,
    Snapshot,
    Validation,
)


def manifest_from_json(data: Mapping[str, Any]) -> Manifest:
    return Manifest(
        target_repo=data["target_repo"],
        pinned_sha=data["pinned_sha"],
        cutoff_date=data["cutoff_date"],
        model=data["model"],
        model_training_cutoff=data["model_training_cutoff"],
        cutoff_minus_training_days=data["cutoff_minus_training_days"],
        repeats=data["repeats"],
        prompt_hashes=dict(data["prompt_hashes"]),
        lizard_version=data["lizard_version"],
        adr_shas=dict(data["adr_shas"]),
        tool_sha=data["tool_sha"],
    )


def _file_facts_from_json(data: Mapping[str, Any]) -> FileFacts:
    return FileFacts(
        **{k: v for k, v in data.items() if k not in {"outline", "recent_commits"}},
        outline=tuple(OutlineEntry(**entry) for entry in data["outline"]),
        recent_commits=tuple(CommitSubject(**commit) for commit in data["recent_commits"]),
    )


def snapshot_from_json(data: Mapping[str, Any]) -> Snapshot:
    return Snapshot(
        files=tuple(_file_facts_from_json(file) for file in data["files"]),
        issues=tuple(Issue(**issue) for issue in data["issues"]),
        zero_complexity_files=data["zero_complexity_files"],
        excluded_issues=data.get("excluded_issues", 0),
        issues_collected=data.get("issues_collected", False),
    )


def request_from_json(data: Mapping[str, Any]) -> Request:
    return Request(**data)


def ranking_from_json(data: Mapping[str, Any]) -> Ranking:
    return Ranking(
        ranker=data["ranker"],
        repeat=data["repeat"],
        groups=tuple(tuple(group) for group in data["groups"]),
    )


def labels_from_json(data: Mapping[str, Any]) -> Labels:
    return Labels(
        counts=dict(data["counts"]),
        keyword_counts=dict(data.get("keyword_counts", {})),
        stats=dict(data.get("stats", {})),
        clone_head=data.get("clone_head", ""),
        clone_newest_commit=data.get("clone_newest_commit", ""),
        fetched=data.get("fetched", False),
        linked_closed_bugs=tuple(data.get("linked_closed_bugs", ())),
        issues_read_at=data.get("issues_read_at", ""),
        variants={name: dict(counts) for name, counts in data.get("variants", {}).items()},
    )


def late_labels_from_json(data: Mapping[str, Any]) -> LateLabels:
    return LateLabels(
        counts=dict(data["counts"]),
        max_files=data["max_files"],
        issues_read_at=data["issues_read_at"],
        clone_head=data["clone_head"],
        clone_newest_commit=data["clone_newest_commit"],
        fetched=data["fetched"],
    )


def scores_from_json(data: Mapping[str, Any]) -> RunScores:
    return RunScores(
        labeled_files=data["labeled_files"],
        min_labeled_files=data["min_labeled_files"],
        excluded=data["excluded"],
        rankings={
            name: Scores(metrics=dict(scores["metrics"]))
            for name, scores in data["rankings"].items()
        },
    )


def validation_from_json(data: Mapping[str, Any]) -> Validation:
    return Validation(
        cap_n=data["cap_n"],
        fix_commits_sized=data["fix_commits_sized"],
        cap_report=tuple(CapResult(**row) for row in data["cap_report"]),
        sample_seed=data["sample_seed"],
        sample=tuple(
            ReviewItem(
                sha=item["sha"],
                message=item["message"],
                issue_references=tuple(item["issue_references"]),
                files=tuple(item["files"]),
                diff_stat=item["diff_stat"],
            )
            for item in data["sample"]
        ),
        clone_head=data["clone_head"],
        fetched=data["fetched"],
    )


def cost_from_json(data: Mapping[str, Any]) -> Cost:
    return Cost(attempts=tuple(CostAttempt(**attempt) for attempt in data["attempts"]))


def probe_from_json(data: Mapping[str, Any]) -> Probe:
    return Probe(**data)


def logged_response_to_json(logged: LoggedResponse) -> dict[str, Any]:
    """Flatten to one `responses.jsonl` row: the request identity beside the Response fields."""
    return {
        "ranker": logged.ranker,
        "repeat": logged.repeat,
        "attempt": logged.attempt,
        "cache_hit": logged.cache_hit,
        **to_json(logged.response),
    }


def logged_response_from_json(data: Mapping[str, Any]) -> LoggedResponse:
    return LoggedResponse(
        ranker=data["ranker"],
        repeat=data["repeat"],
        attempt=data["attempt"],
        cache_hit=data["cache_hit"],
        response=response_from_json(data),
    )
