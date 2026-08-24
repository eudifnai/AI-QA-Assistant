# ruff: noqa: RUF001
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from backend.app.domain.reports import ReportArtifact, ReportFormat, ReportSnapshot

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|token|api[_-]?key|secret|password)\b(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def _redact(value: str) -> str:
    value = _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    value = _BEARER.sub("Bearer ***", value)
    value = _EMAIL.sub("***", value)
    return _PHONE.sub("***", value)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _markdown(value: object | None) -> str:
    if value is None:
        return "-"
    return html.escape(_redact(str(value)), quote=False).replace("|", "\\|").replace("\n", " ")


def _duration(value: int | None) -> str:
    return "-" if value is None else f"{value} ms"


class SafeReportRenderer:
    def render(self, snapshot: ReportSnapshot, format_name: ReportFormat) -> ReportArtifact:
        if format_name not in {"json", "markdown", "html"}:
            raise ValueError("unsupported report format")
        suffix = {"json": "json", "markdown": "md", "html": "html"}[format_name]
        media_type = {
            "json": "application/json",
            "markdown": "text/markdown",
            "html": "text/html",
        }[format_name]
        stem = self._safe_name(snapshot.workspace_name)
        timestamp = f"{snapshot.generated_at:%Y%m%d-%H%M%S}"
        file_name = f"{stem}-qa-report-{timestamp}.{suffix}"
        content = {
            "json": self._json(snapshot),
            "markdown": self._markdown_report(snapshot),
            "html": self._html_report(snapshot),
        }[format_name]
        return ReportArtifact(format_name, file_name, media_type, content, snapshot.generated_at)

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-.")
        return safe[:60] or "workspace"

    @staticmethod
    def _json(snapshot: ReportSnapshot) -> str:
        return (
            json.dumps(
                _json_value(asdict(snapshot)),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )

    @staticmethod
    def _markdown_report(snapshot: ReportSnapshot) -> str:
        summary = snapshot.execution_summary
        summary_row = " | ".join(
            (
                str(summary.total),
                str(summary.passed),
                str(summary.failed),
                str(summary.error),
                str(summary.cancelled),
                str(summary.timeout),
                str(summary.active),
                str(summary.evaluated),
                f"{summary.pass_rate:.2f}%",
                _duration(summary.average_duration_ms),
            )
        )
        analysis = snapshot.analysis_summary
        design = snapshot.design_summary
        lines = [
            f"# {_markdown(snapshot.workspace_name)} QA 报告",
            "",
            f"生成时间：{snapshot.generated_at.isoformat()}",
            "",
            "## 执行摘要",
            "",
            "| 总数 | 通过 | 失败 | 错误 | 取消 | 超时 | 进行中 | 有效终态 | 通过率 | 平均时长 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| {summary_row} |",
            "",
            "## 最近 14 日趋势",
            "",
            "| 日期 (UTC) | 有效终态 | 通过 | 失败 | 错误 | 取消 | 超时 | 通过率 | 平均时长 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for point in snapshot.trend:
            trend_cells = (
                point.date.isoformat(),
                str(point.evaluated),
                str(point.passed),
                str(point.failed),
                str(point.error),
                str(point.cancelled),
                str(point.timeout),
                f"{point.pass_rate:.2f}%",
                _duration(point.average_duration_ms),
            )
            lines.append(f"| {' | '.join(trend_cells)} |")
        attribution = snapshot.failure_attribution_summary
        lines.extend(
            [
                "",
                "## 失败归因（本地确定性规则）",
                "",
                "该归因不调用模型，仅根据稳定状态和错误码给出可审计的初步分类，未知项需要人工复核。",
                "",
                (
                    f"产品 {attribution.product}，环境 {attribution.environment}，"
                    f"数据 {attribution.data}，脚本 {attribution.script}，"
                    f"未知 {attribution.unknown}。"
                ),
                "",
                "| 类型 | 执行 | 状态 | 错误码 | 分类 | 规则 | 原因 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for attribution_item in snapshot.failure_attributions:
            attribution_cells = (
                _markdown(attribution_item.execution_type),
                _markdown(attribution_item.execution_name),
                _markdown(attribution_item.status),
                _markdown(attribution_item.error_code),
                _markdown(attribution_item.category),
                _markdown(attribution_item.rule_id),
                _markdown(attribution_item.reason),
            )
            lines.append(f"| {' | '.join(attribution_cells)} |")
        lines.extend(
            [
                "",
                "## 分析与测试设计",
                "",
                (
                    f"- 分析运行：{analysis.total}，通过 {analysis.passed}，"
                    f"失败/错误 {analysis.failed_or_error}"
                ),
                f"- 最新总体评分：{_markdown(analysis.latest_overall_score)}",
                f"- 分析问题：{analysis.issue_count}",
                f"- 测试点：{design.test_point_total}，已确认 {design.test_point_confirmed}",
                f"- 测试用例：{design.test_case_total}，已确认 {design.test_case_confirmed}",
                "",
                "## 执行明细",
                "",
                "| 类型 | 名称 | 状态 | 时长 | 请求摘要 | 响应摘要 | 失败原因 |",
                "| --- | --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for execution_item in snapshot.executions:
            error = (
                None
                if execution_item.error_code is None
                else f"{execution_item.error_code}: {execution_item.error_message or ''}"
            )
            execution_cells = (
                _markdown(execution_item.execution_type),
                _markdown(execution_item.name),
                _markdown(execution_item.status),
                _duration(execution_item.duration_ms),
                _markdown(execution_item.request_summary),
                _markdown(execution_item.response_summary),
                _markdown(error),
            )
            lines.append(f"| {' | '.join(execution_cells)} |")
        lines.extend(["", "## 安全事件", ""])
        if not any(item.events for item in snapshot.executions):
            lines.append("无。")
        for execution_item in snapshot.executions:
            for event in execution_item.events:
                prefix = f"- `{event.created_at.isoformat()}` {_markdown(execution_item.name)}"
                detail = (
                    f"[{_markdown(event.level)}] `{_markdown(event.code)}` "
                    f"{_markdown(event.message)}"
                )
                lines.append(f"{prefix} {detail}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _html_report(snapshot: ReportSnapshot) -> str:
        summary = snapshot.execution_summary
        analysis = snapshot.analysis_summary
        design = snapshot.design_summary
        rows: list[str] = []
        for execution_item in snapshot.executions:
            error = execution_item.error_code or ""
            if execution_item.error_message:
                error = f"{error}: {execution_item.error_message}"
            execution_values = (
                execution_item.execution_type,
                execution_item.name,
                execution_item.status,
                _duration(execution_item.duration_ms),
                execution_item.request_summary,
                execution_item.response_summary or "-",
                error or "-",
            )
            cells = "".join(f"<td>{html.escape(_redact(value))}</td>" for value in execution_values)
            rows.append(f"<tr>{cells}</tr>")
        events = (
            "".join(
                f"<li><code>{event.created_at.isoformat()}</code> "
                f"{html.escape(_redact(execution_item.name))} "
                f"[{html.escape(event.level)}] <code>{html.escape(_redact(event.code))}</code> "
                f"{html.escape(_redact(event.message))}</li>"
                for execution_item in snapshot.executions
                for event in execution_item.events
            )
            or "<li>无。</li>"
        )
        trend_rows = []
        for point in snapshot.trend:
            trend_values = (
                point.date.isoformat(),
                str(point.evaluated),
                str(point.passed),
                str(point.failed),
                str(point.error),
                str(point.cancelled),
                str(point.timeout),
                f"{point.pass_rate:.2f}%",
                _duration(point.average_duration_ms),
            )
            trend_rows.append(
                "<tr>"
                + "".join(f"<td>{html.escape(value)}</td>" for value in trend_values)
                + "</tr>"
            )
        attribution_rows = []
        for attribution_item in snapshot.failure_attributions:
            attribution_values = (
                attribution_item.execution_type,
                attribution_item.execution_name,
                attribution_item.status,
                attribution_item.error_code or "-",
                attribution_item.category,
                attribution_item.rule_id,
                attribution_item.reason,
            )
            attribution_rows.append(
                "<tr>"
                + "".join(f"<td>{html.escape(_redact(value))}</td>" for value in attribution_values)
                + "</tr>"
            )
        title = html.escape(_redact(snapshot.workspace_name))
        styles = (
            "body{font:14px/1.6 system-ui,sans-serif;max-width:1200px;"
            "margin:32px auto;padding:0 20px;color:#1f2937}"
            "table{width:100%;border-collapse:collapse}"
            "th,td{border:1px solid #d1d5db;padding:8px;text-align:left;vertical-align:top}"
            "th{background:#f3f4f6}code{overflow-wrap:anywhere}"
            ".summary{display:flex;flex-wrap:wrap;gap:12px}"
            ".summary span{padding:8px 12px;background:#f3f4f6;border-radius:6px}"
        )
        summary_values = (
            ("总数", summary.total),
            ("通过", summary.passed),
            ("失败", summary.failed),
            ("错误", summary.error),
            ("取消", summary.cancelled),
            ("超时", summary.timeout),
            ("进行中", summary.active),
            ("有效终态", summary.evaluated),
            ("通过率", f"{summary.pass_rate:.2f}%"),
            ("平均时长", _duration(summary.average_duration_ms)),
        )
        summary_html = "".join(
            f"<span>{label} {html.escape(str(value))}</span>" for label, value in summary_values
        )
        design_html = (
            f"<li>分析运行 {analysis.total}，通过 {analysis.passed}，"
            f"失败/错误 {analysis.failed_or_error}</li>"
            f"<li>最新总体评分 {_markdown(analysis.latest_overall_score)}</li>"
            f"<li>分析问题 {analysis.issue_count}</li>"
            f"<li>测试点 {design.test_point_total}，已确认 {design.test_point_confirmed}</li>"
            f"<li>测试用例 {design.test_case_total}，已确认 {design.test_case_confirmed}</li>"
        )
        header_cells = "".join(
            f"<th>{label}</th>"
            for label in ("类型", "名称", "状态", "时长", "请求摘要", "响应摘要", "失败原因")
        )
        trend_header = "".join(
            f"<th>{label}</th>"
            for label in (
                "日期 (UTC)",
                "有效终态",
                "通过",
                "失败",
                "错误",
                "取消",
                "超时",
                "通过率",
                "平均时长",
            )
        )
        attribution = snapshot.failure_attribution_summary
        attribution_summary = (
            f"产品 {attribution.product}，环境 {attribution.environment}，"
            f"数据 {attribution.data}，脚本 {attribution.script}，未知 {attribution.unknown}。"
        )
        attribution_header = "".join(
            f"<th>{label}</th>"
            for label in ("类型", "执行", "状态", "错误码", "分类", "规则", "原因")
        )
        return "\n".join(
            (
                "<!doctype html>",
                '<html lang="zh-CN"><head><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width,initial-scale=1">',
                f"<title>{title} QA 报告</title><style>{styles}</style></head>",
                f"<body><h1>{title} QA 报告</h1>",
                f"<p>生成时间：{snapshot.generated_at.isoformat()}</p>",
                f'<h2>执行摘要</h2><div class="summary">{summary_html}</div>',
                f"<h2>最近 14 日趋势</h2><table><thead><tr>{trend_header}</tr></thead>",
                f"<tbody>{''.join(trend_rows)}</tbody></table>",
                "<h2>失败归因（本地确定性规则）</h2>",
                "<p>该归因不调用模型，仅根据稳定状态和错误码给出可审计的初步分类，"
                "未知项需要人工复核。</p>",
                f"<p>{attribution_summary}</p>",
                f"<table><thead><tr>{attribution_header}</tr></thead>",
                f"<tbody>{''.join(attribution_rows)}</tbody></table>",
                f"<h2>分析与测试设计</h2><ul>{design_html}</ul>",
                f"<h2>执行明细</h2><table><thead><tr>{header_cells}</tr></thead>",
                f"<tbody>{''.join(rows)}</tbody></table>",
                f"<h2>安全事件</h2><ul>{events}</ul></body></html>",
                "",
            )
        )
