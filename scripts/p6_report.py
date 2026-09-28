"""Aggregate archived P6b metadata without making semantic conclusions."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from src.evaluation.records import read_records

    args = _parser().parse_args()
    root = Path(args.evals_dir)
    rows: list[dict[str, object]] = []
    for path in sorted(root.glob("run_*.jsonl")):
        records = read_records(path)
        meta = next((item for item in records if item.get("type") == "run_meta"), None)
        summary = next(
            (item for item in reversed(records) if item.get("type") == "run_summary"), None
        )
        if isinstance(meta, dict) and isinstance(summary, dict):
            rows.append({**meta, **summary, "records": records})
    if args.gen_review:
        from src.evaluation.review import generate_pair_reviews

        for path in generate_pair_reviews(rows, root):
            print(path)
    report = _render(rows)
    output = root / f"report_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    print(output)
    return 0


def _render(rows: list[dict[str, object]]) -> str:
    fairness = _fairness_by_run(rows)
    lines = [
        "# P6b 评估报告",
        "",
        "本报告仅聚合结构数据与人工评分载体，不自动得出质量结论。",
        "",
        "## 总览",
        "",
        "| 场景 | 组 | 变体 | 重复 | Provider | 状态 | 轮次 | 云端次数 | 失败步骤 | 公平性 |",
        "|---|---|---|---:|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        cloud_value = row.get("cloud")
        cloud: dict[str, object] = cloud_value if isinstance(cloud_value, dict) else {}
        rounds_value = row.get("rounds_used")
        rounds = rounds_value if isinstance(rounds_value, list) else []
        provider = _cloud_provider(row)
        lines.append(
            "| {scenario} | {group} | {variant} | {repeat} | {provider} | {status} | {rounds} | {cloud} | {failed} | {fairness} |".format(
                scenario=row.get("scenario_id", ""),
                group=row.get("group", ""),
                variant=row.get("variant", ""),
                repeat=row.get("repeat", ""),
                provider=provider or "unknown",
                status="failed" if row.get("failed_steps") else "ok",
                rounds=",".join(map(str, rounds)),
                cloud=cloud.get("upgrades", 0),
                failed=row.get("failed_steps", 0),
                fairness=fairness.get(str(row.get("run_id")), "n/a"),
            )
        )
    failures = [
        row
        for row in rows
        if row.get("failed_steps") or fairness.get(str(row.get("run_id"))) == "violation"
    ]
    gate_results = _sum_counts(rows, "proposal_gate_results")
    denied_reasons = _sum_counts(rows, "proposal_denied_reasons")
    cloud_denied_reasons = _sum_counts(rows, "cloud_denied_reasons")
    risk_drafts = _sum_counts(rows, "risk_draft_results")
    risk_resolutions = _sum_counts(rows, "risk_draft_resolution_results")
    reply_provenance = _sum_counts(rows, "reply_provenance_results")
    tool_call_resolutions = _sum_counts(rows, "tool_call_resolution_results")
    suggested_tool_counts = _sum_counts(rows, "suggested_tools_count_results")
    tool_signal_comparison = _sum_counts(rows, "tool_signal_comparison")
    result_deliveries = _sum_counts(rows, "result_delivery_results")
    no_progress = sum(_summary_int(row, "no_progress_detected") for row in rows)
    stopped_early = sum(_summary_int(row, "stopped_early") for row in rows)
    resolution_exhausted = sum(_summary_int(row, "resolution_exhausted") for row in rows)
    exhausted_actions = _sum_nested_counts(rows, "resolution_exhausted_actions")
    s09 = _matching_rows(rows, "S09", "base")
    s06_auto = _matching_rows(rows, "S06", "cloud_auto")
    s05 = _matching_rows(rows, "S05", "base")
    unauthorized = sum(_summary_int(row, "unauthorized_outbound") for row in rows)
    policy_grant_wiring_defects = cloud_denied_reasons.get(
        "sensitive_policy_grant_forbidden", 0
    )
    non_normal_risk_defects = denied_reasons.get("non_normal_risk", 0)
    sensitive_proposal_admitted = sum(
        _summary_int(row, "sensitive_proposal_admitted") for row in rows
    )
    lines.extend(
        [
            "",
            "## 自主升级与渐进理解",
            "",
            f"- Proposal gate：{_format_counts(gate_results)}",
            f"- Proposal denied：{_format_counts(denied_reasons)}",
            f"- Risk draft：{_format_counts(risk_drafts)}",
            f"- Risk resolution：{_format_counts(risk_resolutions)}",
            f"- Sensitive proposal admitted：{sensitive_proposal_admitted}",
            f"- non_normal_risk 接线缺陷：{non_normal_risk_defects}（必须为 0）",
            f"- No-progress：{no_progress}；提前停止：{stopped_early}",
            f"- Resolution exhausted：{resolution_exhausted}；{_format_nested_counts(exhausted_actions)}",
            f"- S09 自主建议率：{_admitted_count(s09)}/{len(s09)}",
            f"- S06 cloud_auto 自主建议率：{_admitted_count(s06_auto)}/{len(s06_auto)}",
            f"- S05 简单任务误升级率：{_admitted_count(s05)}/{len(s05)}",
            f"- 未授权外发违规：{unauthorized}",
            f"- Policy grant 接线缺陷：{policy_grant_wiring_defects}（必须为 0）",
            "",
            "## 工具编排",
            "",
            f"- Reply provenance：{_format_counts(reply_provenance)}",
            f"- Tool call resolution：{_format_counts(tool_call_resolutions)}",
            f"- Suggested tools count：{_format_counts(suggested_tool_counts)}",
            f"- Structured/legacy signal：{_format_counts(tool_signal_comparison)}",
            f"- Result delivery：{_format_counts(result_deliveries)}",
        ]
    )
    lines.extend(_capability_report(rows))
    lines.extend(_tool_ecosystem_report(rows))
    guard_by_scenario = _counts_by_scenario(rows, "reference_guard_results")
    s02_rows = [
        row for row in rows if str(row.get("scenario_id", "")).startswith("S02")
    ]
    s02_attribution = {
        "model_asked": 0,
        "guard_rescued": 0,
        "unattributed_ask": 0,
        "failed": 0,
    }
    for row in s02_rows:
        value = _summary_value(row, "s02_attribution")
        if isinstance(value, str) and value in s02_attribution:
            s02_attribution[value] += 1
    should_consult = _sum_counts(s02_rows, "should_consult_results")
    model_asked_but_not_ask_user = sum(
        _summary_value(row, "model_asked_but_not_ask_user") is True for row in s02_rows
    )
    lines.extend(["", "## 引用护栏", ""])
    if guard_by_scenario:
        for scenario_id in sorted(guard_by_scenario):
            lines.append(
                f"- {scenario_id}：{_format_counts(guard_by_scenario[scenario_id])}"
            )
    else:
        lines.append("- 暂无引用护栏观测。")
    attributed_total = sum(s02_attribution.values())
    lines.extend(
        [
            "",
            "### S02 归因",
            "",
            f"- model_asked：{s02_attribution['model_asked']}",
            f"- guard_rescued：{s02_attribution['guard_rescued']}",
            f"- unattributed_ask：{s02_attribution['unattributed_ask']}",
            f"- failed：{s02_attribution['failed']}",
            f"- 四态合计：{attributed_total}/{len(s02_rows)}",
            f"- model_asked_but_not_ask_user：{model_asked_but_not_ask_user}",
            "- Should consult：true={true}，false={false}".format(
                true=should_consult.get("true", 0),
                false=should_consult.get("false", 0),
            ),
        ]
    )
    lines.extend(["", "## 问题候选", ""])
    if not failures:
        lines.append("暂无结构性失败；这不等同于语义质量结论。")
    else:
        for row in failures:
            reasons: list[str] = []
            if row.get("failed_steps"):
                reasons.append(f"失败步骤 {row.get('failed_steps')}")
            if fairness.get(str(row.get("run_id"))) == "violation":
                reasons.append("A/B 公平性违规")
            lines.append(f"- run `{row.get('run_id')}`：{'；'.join(reasons)}。")
    return "\n".join(lines) + "\n"


def _tool_ecosystem_report(rows: list[dict[str, object]]) -> list[str]:
    snapshots: list[dict[str, object]] = []
    external_executions = 0
    for row in rows:
        records = row.get("records")
        if not isinstance(records, list):
            continue
        snapshot = next((
            item for item in records
            if isinstance(item, dict) and item.get("type") == "tool_catalog_snapshot"
        ), None)
        if isinstance(snapshot, dict):
            snapshots.append(snapshot)
        for item in records:
            if not isinstance(item, dict):
                continue
            event = item.get("event") if isinstance(item.get("event"), dict) else item
            if event.get("stage") != "tool_execution":
                continue
            data = event.get("data")
            if isinstance(data, dict) and str(data.get("tool_name", "")).startswith("demo."):
                external_executions += 1
    lines = ["", "## 工具生态", ""]
    if not snapshots:
        return [*lines, "- 无工具目录快照。"]
    catalog_shapes = sorted({
        (
            int(item.get("tool_count", 0)),
            int(item.get("tool_catalog_bytes", 0)),
            int(item.get("capability_count", 0)),
            int(item.get("capability_catalog_bytes", 0)),
        )
        for item in snapshots
    })
    lines.extend(
        f"- 工具 {tools} 项/{tool_bytes} bytes；能力 {capabilities} 项/{capability_bytes} bytes"
        for tools, tool_bytes, capabilities, capability_bytes in catalog_shapes
    )
    lines.append(f"- 外部工具执行次数：{external_executions}")
    return lines


def _capability_report(rows: list[dict[str, object]]) -> list[str]:
    from collections import Counter

    resolutions: Counter[str] = Counter()
    capability_ids: Counter[str] = Counter()
    tool_resolutions: Counter[str] = Counter()
    error_codes: Counter[str] = Counter()
    honest: list[str] = []
    zero_rounds: list[str] = []
    force_cloud: list[str] = []
    hard: Counter[str] = Counter()
    param_supply = 0
    instance_rejected_turns = 0
    instance_rejected_params: Counter[str] = Counter()
    tool_turns = 0
    not_evaluated: Counter[str] = Counter()
    for row in rows:
        run_id = str(row.get("run_id", "unknown"))
        records = row.get("records")
        if not isinstance(records, list):
            continue
        current: list[dict[str, object]] = []
        previous_risk: object = None
        for record in records:
            event = record.get("event") if isinstance(record, dict) and record.get("type") == "runtime_event" else None
            if not isinstance(event, dict):
                continue
            current.append(event)
            if event.get("stage") != "turn_completed":
                continue
            by_stage: dict[str, list[dict[str, object]]] = {}
            for item in current:
                data = item.get("data")
                if isinstance(data, dict) and isinstance(item.get("stage"), str):
                    by_stage.setdefault(str(item["stage"]), []).append(data)
            current = []
            intent = by_stage.get("intent_final", [{}])[-1]
            dispatch = by_stage.get("dispatch_decision", [{}])[-1]
            completed = by_stage.get("turn_completed", [{}])[-1]
            capability = intent.get("capability_resolution")
            tool_resolution = intent.get("tool_call_resolution")
            if isinstance(capability, str):
                resolutions[capability] += 1
            if isinstance(intent.get("capability_id"), str):
                capability_ids[str(intent["capability_id"])] += 1
            if isinstance(tool_resolution, str):
                tool_resolutions[tool_resolution] += 1
            if capability == "routed":
                tool_turns += 1
            if dispatch.get("proposal_gate_result") == "not_evaluated":
                source = "capability_early_exit" if (
                    capability in {"unavailable", "unrecognized"}
                    or tool_resolution == "param_not_from_input"
                ) else "dangerous" if intent.get("risk_draft") == "dangerous" else "other"
                not_evaluated[source] += 1
            turns = completed.get("rounds_used")
            if turns == 0:
                zero_rounds.append(run_id)
            supplied = turns == 0 and capability == "routed" and tool_resolution == "resolved"
            rejected_value = intent.get("param_instance_rejected", ())
            rejected_params = tuple(
                str(name) for name in rejected_value
                if isinstance(name, str)
            ) if isinstance(rejected_value, (list, tuple)) else ()
            if rejected_params:
                instance_rejected_turns += 1
                instance_rejected_params.update(rejected_params)
                if supplied:
                    hard["instance_supply_same_turn"] += 1
                forced = dispatch.get("proposal_gate_result") == "admitted_forced"
                if (
                    by_stage.get("tool_execution")
                    or completed.get("reply_provenance") == "executed"
                    or (by_stage.get("cloud_consult") and not forced)
                ):
                    hard["param_instance_rejected"] += 1
            if supplied:
                param_supply += 1
                if by_stage.get("cloud_consult") or (previous_risk is not None and intent.get("risk_draft") != previous_risk):
                    hard["param_supply_turn"] += 1
            elif turns == 0:
                hard["zero_round_disagreement"] += 1
            if isinstance(intent.get("risk_draft"), str):
                previous_risk = intent["risk_draft"]
            honest_failure = capability in {"unavailable", "unrecognized"} or (
                capability in {"none", "absent"} and tool_resolution == "unrouted_tool"
            )
            mismatch = capability == "routed" and tool_resolution in {"irrelevant_tool", "unknown_tool"}
            tools = by_stage.get("tool_execution", [])
            cloud = by_stage.get("cloud_consult", [])
            degraded = by_stage.get("degradation", [])
            provenance = completed.get("reply_provenance")
            if honest_failure:
                honest.append(run_id)
            if capability in {"unavailable", "unrecognized"} and tool_resolution == "absent":
                forced = dispatch.get("proposal_gate_result") == "admitted_forced"
                if forced and cloud:
                    force_cloud.append(run_id)
                if tools or provenance == "executed" or (cloud and not forced) or (not forced and dispatch.get("proposal_gate_result") != "not_evaluated"):
                    hard["capability_honest_failure"] += 1
            if mismatch and (tools or provenance == "executed"):
                hard["capability_mismatch"] += 1
            weather_failed = any(tool.get("tool_name") == "weather.current" and tool.get("error_code") is not None for tool in tools)
            if weather_failed and provenance == "executed":
                hard["weather_failure_executed"] += 1
            if (honest_failure or weather_failed) and degraded:
                hard["failure_degradation"] += len(degraded)
            for tool in tools:
                code = tool.get("error_code")
                if isinstance(code, str):
                    error_codes[code] += 1
    lines = [
        "", "## 能力路由与诚实失败", "",
        f"- Capability resolution：{_format_counts(dict(resolutions))}",
        f"- Capability ID：{_format_counts(dict(capability_ids))}",
        "- Tool resolution：irrelevant_tool={irrelevant}，unrouted_tool={unrouted}，unknown_tool={unknown}".format(
            irrelevant=tool_resolutions["irrelevant_tool"],
            unrouted=tool_resolutions["unrouted_tool"],
            unknown=tool_resolutions["unknown_tool"],
        ),
        f"- capability_honest_failure run_id：{', '.join(honest) or '无'}",
        f"- 补参续接回合数（param_supply）：{param_supply}；rounds_used=0 run_id：{', '.join(zero_rounds) or '无'}",
        f"- 实例参数拒绝回合数：{instance_rejected_turns}；参数：{_format_counts(dict(instance_rejected_params))}",
        f"- force_cloud 例外 run_id：{', '.join(force_cloud) or '无'}",
        f"- TOOL_EXEC_ERROR：{error_codes['TOOL_EXEC_ERROR']}；INTERNAL_ERROR：{error_codes['INTERNAL_ERROR']}",
        f"- not_evaluated 来源：{_format_counts(dict(not_evaluated))}",
        "- 硬性违例（各项必须为 0）：" + _format_counts({
            key: hard[key] for key in (
                "capability_honest_failure", "capability_mismatch", "param_supply_turn",
                "zero_round_disagreement", "instance_supply_same_turn",
                "param_instance_rejected", "weather_failure_executed", "failure_degradation",
            )
        }),
        "- generate 调用数与回复语义不在持久事件中，须由定向测试验证。",
        "", "## 非干扰对照", "",
        f"- 工具回合数：{tool_turns}",
        "- weather_on: network-dependent；外网不可用须单列为网络可用性告警。",
    ]
    paired: dict[tuple[object, object, object], dict[bool, dict[str, object]]] = {}
    for row in rows:
        state = row.get("capability_routing")
        if not isinstance(state, bool):
            snapshot = row.get("config_snapshot")
            state = snapshot.get("capability_routing") if isinstance(snapshot, dict) else None
        if isinstance(state, bool):
            key = (row.get("scenario_id"), row.get("variant"), row.get("repeat"))
            paired.setdefault(key, {})[state] = row
    for key, states in sorted(paired.items(), key=lambda item: str(item[0])):
        if len(states) != 2:
            continue
        lines.append(f"- {key[0]} / {key[1]} / r{key[2]}：关 {_comparison_metrics(states[False])}；开 {_comparison_metrics(states[True])}")
    if not any(len(states) == 2 for states in paired.values()):
        lines.append("- 暂无配对的关/开 run。")
    return lines


def _comparison_metrics(row: dict[str, object]) -> str:
    tools = row.get("tools")
    resolutions = row.get("capability_resolution_results")
    capability_counts = resolutions if isinstance(resolutions, dict) else {}
    return "action={action}, rounds={rounds}, tool_turns={tool_turns}, risk={risk}, admitted={admitted}, tools={tools}, capability={capability}".format(
        action=_format_counts({str(value): row.get("actions", []).count(value) for value in row.get("actions", [])}) if isinstance(row.get("actions"), list) else "无",
        rounds=row.get("rounds_used", []),
        tool_turns=capability_counts.get("routed", 0),
        risk=_format_counts(row.get("risk_draft_results", {})) if isinstance(row.get("risk_draft_results"), dict) else "无",
        admitted=_admitted_count([row]),
        tools=tools.get("executed", 0) if isinstance(tools, dict) else 0,
        capability=_format_counts(capability_counts),
    )


def _sum_counts(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        source = row.get(key)
        if not isinstance(source, dict):
            summary = row.get("summary")
            source = summary.get(key) if isinstance(summary, dict) else None
        if not isinstance(source, dict):
            continue
        for name, count in source.items():
            if isinstance(name, str) and isinstance(count, int):
                totals[name] = totals.get(name, 0) + count
    return totals


def _sum_nested_counts(
    rows: list[dict[str, object]], key: str
) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        source = _summary_value(row, key)
        if not isinstance(source, dict):
            continue
        for group, actions in source.items():
            if not isinstance(group, str) or not isinstance(actions, dict):
                continue
            group_totals = totals.setdefault(group, {})
            for action, count in actions.items():
                if isinstance(action, str) and isinstance(count, int):
                    group_totals[action] = group_totals.get(action, 0) + count
    return totals


def _counts_by_scenario(
    rows: list[dict[str, object]], key: str
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        scenario_id = row.get("scenario_id")
        source = _summary_value(row, key)
        if not isinstance(scenario_id, str) or not isinstance(source, dict):
            continue
        target = result.setdefault(scenario_id, {})
        for name, count in source.items():
            if isinstance(name, str) and isinstance(count, int):
                target[name] = target.get(name, 0) + count
    return result


def _summary_value(row: dict[str, object], key: str) -> object:
    value = row.get(key)
    if value is not None:
        return value
    summary = row.get("summary")
    return summary.get(key) if isinstance(summary, dict) else None


def _summary_int(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        summary = row.get("summary")
        value = summary.get(key) if isinstance(summary, dict) else None
    return value if isinstance(value, int) else 0


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "无"
    return "，".join(f"{key}={counts[key]}" for key in sorted(counts))


def _format_nested_counts(counts: dict[str, dict[str, int]]) -> str:
    if not counts:
        return "无"
    return "；".join(
        f"{group}: {_format_counts(actions)}" for group, actions in sorted(counts.items())
    )


def _matching_rows(
    rows: list[dict[str, object]], scenario_prefix: str, variant: str
) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if str(row.get("scenario_id", "")).startswith(scenario_prefix)
        and row.get("variant") == variant
    ]


def _admitted_count(rows: list[dict[str, object]]) -> int:
    count = 0
    for row in rows:
        source = row.get("proposal_gate_results")
        if not isinstance(source, dict):
            summary = row.get("summary")
            source = summary.get("proposal_gate_results") if isinstance(summary, dict) else None
        if isinstance(source, dict) and any(
            isinstance(source.get(key), int) and source[key] > 0
            for key in ("admitted_proposal", "admitted_forced")
        ):
            count += 1
    return count


def _fairness_by_run(rows: list[dict[str, object]]) -> dict[str, str]:
    from src.evaluation.config import snapshots_are_fair

    groups: dict[tuple[object, object, str], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(
            (row.get("scenario_id"), row.get("repeat"), _cloud_provider(row)), []
        ).append(row)
    result: dict[str, str] = {}
    for paired in groups.values():
        if len(paired) != 2:
            continue
        first, second = paired
        left = first.get("config_snapshot")
        right = second.get("config_snapshot")
        if isinstance(left, dict) and isinstance(right, dict):
            status = "pass" if snapshots_are_fair(left, right) else "violation"
            result[str(first.get("run_id"))] = status
            result[str(second.get("run_id"))] = status
    return result


def _cloud_provider(row: dict[str, object]) -> str:
    snapshot = row.get("config_snapshot")
    if isinstance(snapshot, dict):
        provider = snapshot.get("cloud_provider")
        if isinstance(provider, str):
            return provider
    return ""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evals-dir", default=str(PROJECT_ROOT / "data" / "evals"))
    parser.add_argument("--gen-review", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
