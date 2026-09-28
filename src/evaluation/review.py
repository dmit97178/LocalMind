"""Anonymous G1/G2 review artifacts derived solely from archived evaluation data."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from src.evaluation.records import append_record


def generate_pair_reviews(runs: list[dict[str, object]], evals_dir: Path) -> list[Path]:
    """Write anonymous pair sheets, score sidecars, and separate variant keys."""

    review_dir = evals_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for scenario_id in sorted({str(run.get("scenario_id", "")) for run in runs}):
        candidates = [run for run in runs if run.get("scenario_id") == scenario_id]
        variants = {str(run.get("variant")) for run in candidates}
        expected = (
            ("round1", "round4") if {"round1", "round4"}.issubset(variants)
            else ("local_only", "cloud_assisted") if {"local_only", "cloud_assisted"}.issubset(variants)
            else None
        )
        if expected is None:
            continue
        generations = sorted(
            {(run.get("repeat"), _cloud_provider(run)) for run in candidates},
            key=lambda item: (str(item[0]), item[1]),
        )
        for repeat, provider in generations:
            pair = {
                str(run.get("variant")): run
                for run in candidates
                if run.get("repeat") == repeat and _cloud_provider(run) == provider
            }
            if not all(variant in pair for variant in expected):
                continue
            pair_id = f"{scenario_id}_{repeat}_{uuid4().hex[:6]}"
            left, right = pair[expected[0]], pair[expected[1]]
            sheet = review_dir / f"pair_{pair_id}.md"
            sheet.write_text(
                "\n".join((
                    f"# 场景 {scenario_id} · 评审对 {repeat}", "", "## 回答 A", _transcript(evals_dir, left),
                    "", "## 回答 B", _transcript(evals_dir, right), "",
                )), encoding="utf-8", newline="\n"
            )
            key = review_dir / f"pair_{pair_id}.key.json"
            key.write_text(json.dumps({"A": {"run_id": left["run_id"], "variant": left["variant"]}, "B": {"run_id": right["run_id"], "variant": right["variant"]}}, ensure_ascii=False), encoding="utf-8")
            scores = (
                {"intent_correctness": None, "followup_quality": None, "constraint_completeness": None, "misexecution": None}
                if expected == ("round1", "round4")
                else {"completeness": None, "reasoning_quality": None, "constraint_compliance": None, "cloud_worth_it": None}
            )
            append_record(review_dir / f"pair_{pair_id}.scores.jsonl", {
                "pair_id": pair_id, "scenario_id": scenario_id,
                "run_id_a": left["run_id"], "run_id_b": right["run_id"], "kind": "pair",
                "scores": scores,
                "notes": "", "scored_at": None,
            })
            created.append(sheet)
    return created


def _cloud_provider(run: dict[str, object]) -> str:
    snapshot = run.get("config_snapshot")
    if isinstance(snapshot, dict):
        provider = snapshot.get("cloud_provider")
        if isinstance(provider, str):
            return provider
    return ""


def _transcript(evals_dir: Path, run: dict[str, object]) -> str:
    path = evals_dir / "transcripts" / f"run_{run['run_id']}.md"
    return path.read_text(encoding="utf-8") if path.exists() else "（未生成转录）"
