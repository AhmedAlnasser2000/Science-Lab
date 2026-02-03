from __future__ import annotations

import time
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from ..badges import Badge, sort_by_priority
from ..diff import NodeChange
from ..expectations import EVACheck
from ..graph_model import ArchitectureGraph, Node
from ..runtime.events import CodeSeeEvent, SpanRecord


def _span_is_stuck(span: SpanRecord, now: float, threshold: int) -> bool:
    if threshold <= 0:
        return False
    updated = span.updated_ts or span.started_ts
    if not updated:
        return False
    return (now - updated) > threshold


class CodeSeeInspectorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        node: Node,
        graph: ArchitectureGraph,
        selected_badge: Optional[Badge],
        diff_state: Optional[str],
        diff_change: Optional[NodeChange],
        events: list[CodeSeeEvent],
        crash_record: Optional[dict],
        build_info: Optional[dict],
        crash_build_info: Optional[dict],
        span_stuck_seconds: int,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Code See Inspector")
        self.setMinimumWidth(480)

        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(node.title)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        meta = QtWidgets.QLabel(f"ID: {node.node_id} | Type: {node.node_type}")
        meta.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)

        meta_label = QtWidgets.QLabel("Extensions & Metadata")
        meta_label.setStyleSheet("color: #444;")
        layout.addWidget(meta_label)
        meta_text = QtWidgets.QPlainTextEdit()
        meta_text.setReadOnly(True)
        meta_text.setPlainText(_format_metadata(node.metadata))
        layout.addWidget(meta_text)

        build_label = QtWidgets.QLabel("Build")
        build_label.setStyleSheet("color: #444;")
        layout.addWidget(build_label)
        build_text = QtWidgets.QPlainTextEdit()
        build_text.setReadOnly(True)
        build_text.setPlainText(_format_build_info(build_info, crash_build_info))
        layout.addWidget(build_text)

        if selected_badge:
            selected = QtWidgets.QLabel(f"Selected badge: {_format_badge_line(selected_badge)}")
            selected.setWordWrap(True)
            layout.addWidget(selected)

        if diff_state:
            diff_label = QtWidgets.QLabel(f"Diff status: {diff_state}")
            diff_label.setStyleSheet("color: #555;")
            layout.addWidget(diff_label)
            if diff_change:
                diff_details = QtWidgets.QPlainTextEdit()
                diff_details.setReadOnly(True)
                diff_details.setPlainText(_format_diff_change(diff_change))
                layout.addWidget(diff_details)

        badges_label = QtWidgets.QLabel("Badges")
        badges_label.setStyleSheet("color: #444;")
        layout.addWidget(badges_label)
        badges_text = QtWidgets.QPlainTextEdit()
        badges_text.setReadOnly(True)
        badges_text.setPlainText(_format_badges(node.badges))
        layout.addWidget(badges_text)

        activity_label = QtWidgets.QLabel("Activity")
        activity_label.setStyleSheet("color: #444;")
        layout.addWidget(activity_label)
        activity_text = QtWidgets.QPlainTextEdit()
        activity_text.setReadOnly(True)
        activity_text.setPlainText(_format_spans(node.spans, span_stuck_seconds))
        layout.addWidget(activity_text)

        edges_label = QtWidgets.QLabel("Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_edges(graph, node))
        layout.addWidget(edges_text)

        events_label = QtWidgets.QLabel("Recent events")
        events_label.setStyleSheet("color: #444;")
        layout.addWidget(events_label)
        events_text = QtWidgets.QPlainTextEdit()
        events_text.setReadOnly(True)
        events_text.setPlainText(_format_events(events))
        layout.addWidget(events_text)

        if crash_record:
            crash_label = QtWidgets.QLabel("Crash")
            crash_label.setStyleSheet("color: #444;")
            layout.addWidget(crash_label)
            crash_text = QtWidgets.QPlainTextEdit()
            crash_text.setReadOnly(True)
            crash_text.setPlainText(_format_crash_record(crash_record))
            layout.addWidget(crash_text)

        checks_label = QtWidgets.QLabel("Expected vs Actual")
        checks_label.setStyleSheet("color: #444;")
        layout.addWidget(checks_label)
        checks_text = QtWidgets.QPlainTextEdit()
        checks_text.setReadOnly(True)
        checks_text.setPlainText(_format_checks(node.checks))
        layout.addWidget(checks_text)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


def _format_badges(badges: list[Badge]) -> str:
    if not badges:
        return "No badges."
    lines = []
    for badge in sort_by_priority(badges):
        lines.append(_format_badge_line(badge))
        if badge.detail:
            lines.append(f"  detail: {badge.detail}")
        if badge.timestamp:
            lines.append(f"  timestamp: {badge.timestamp}")
    return "\n".join(lines)


def _format_badge_line(badge: Badge) -> str:
    line = f"{badge.key} ({badge.rail}) - {badge.title}: {badge.summary}"
    return line.strip()


def _format_edges(graph: ArchitectureGraph, node: Node) -> str:
    node_map = graph.node_map()
    outgoing = []
    incoming = []
    for edge in graph.edges:
        if edge.src_node_id == node.node_id:
            dst = node_map.get(edge.dst_node_id)
            dst_label = dst.title if dst else edge.dst_node_id
            outgoing.append(f"{edge.kind} -> {dst_label} ({edge.dst_node_id})")
        if edge.dst_node_id == node.node_id:
            src = node_map.get(edge.src_node_id)
            src_label = src.title if src else edge.src_node_id
            incoming.append(f"{edge.kind} <- {src_label} ({edge.src_node_id})")
    if not outgoing and not incoming:
        return "No edges."
    lines = []
    if outgoing:
        lines.append("Outgoing:")
        lines.extend(f"- {line}" for line in outgoing)
    if incoming:
        lines.append("Incoming:")
        lines.extend(f"- {line}" for line in incoming)
    return "\n".join(lines)


def _format_diff_change(change: NodeChange) -> str:
    lines = ["Before:", f"  title: {change.before.title}", f"  type: {change.before.node_type}"]
    lines.append(f"  severity: {change.severity_before}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_before)
    lines.append("After:")
    lines.append(f"  title: {change.after.title}")
    lines.append(f"  type: {change.after.node_type}")
    lines.append(f"  severity: {change.severity_after}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_after)
    lines.append(f"Changed fields: {', '.join(change.fields_changed)}")
    return "\n".join(lines)


def _format_events(events: list[CodeSeeEvent]) -> str:
    if not events:
        return "No recent events."
    lines = []
    for event in events:
        line = f"{event.ts} | {event.kind} | {event.severity}: {event.message}"
        if event.detail:
            line = f"{line}\n  {event.detail}"
        lines.append(line)
    return "\n".join(lines)


def _format_metadata(metadata: dict) -> str:
    if not metadata:
        return "No metadata."
    lines = []
    for key in sorted(metadata.keys()):
        value = metadata.get(key)
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key in sorted(value.keys()):
                lines.append(f"  {sub_key}: {value.get(sub_key)}")
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _format_spans(spans: list[SpanRecord], stuck_threshold_s: int, limit: int = 6) -> str:
    if not spans:
        return "No activity spans."
    now = time.time()
    sorted_spans = sorted(
        spans,
        key=lambda s: s.updated_ts or s.started_ts or 0.0,
        reverse=True,
    )[:limit]
    lines = []
    for span in sorted_spans:
        status = span.status or "active"
        if _span_is_stuck(span, now, stuck_threshold_s):
            status = "stuck"
        ts = span.updated_ts or span.started_ts
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "n/a"
        progress = ""
        if span.progress is not None:
            if 0.0 <= span.progress <= 1.0:
                progress = f" ({int(span.progress * 100)}%)"
            else:
                progress = f" ({span.progress})"
        message = f" - {span.message}" if span.message else ""
        lines.append(f"{stamp} | {status.upper()} | {span.label}{progress}{message}")
    return "\n".join(lines)


def _format_build_info(build: Optional[dict], crash_build: Optional[dict]) -> str:
    build = build if isinstance(build, dict) else {}
    crash_build = crash_build if isinstance(crash_build, dict) else {}
    app_version = build.get("app_version") or "unknown"
    build_id = build.get("build_id") or "unknown"
    lines = [f"Current: {app_version} ({build_id})"]
    if crash_build:
        crash_version = crash_build.get("app_version") or "unknown"
        crash_id = crash_build.get("build_id") or "unknown"
        if crash_version != app_version or crash_id != build_id:
            lines.append(f"Crash: {crash_version} ({crash_id})")
    return "\n".join(lines)


def _format_checks(checks: list[EVACheck], limit: int = 5) -> str:
    if not checks:
        return "No expectation checks."
    recent = sorted(checks, key=lambda c: c.ts or 0.0, reverse=True)[:limit]
    lines = []
    for check in recent:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(check.ts)) if check.ts else "n/a"
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"{stamp} | {status} | {check.message}")
        lines.append(f"  expected: {check.expected}")
        lines.append(f"  actual: {check.actual}")
        lines.append(f"  mode: {check.mode}")
        if check.tolerance is not None:
            lines.append(f"  tolerance: {check.tolerance}")
        if check.context:
            lines.append(f"  context: {check.context}")
    return "\n".join(lines)


def _format_crash_record(record: dict, limit_lines: int = 12) -> str:
    ts = record.get("ts")
    stamp = "n/a"
    if isinstance(ts, (int, float)):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    exc_type = record.get("exception_type") or "Crash"
    message = record.get("message") or ""
    where = record.get("where") or "startup"
    traceback_text = record.get("traceback") or ""
    lines = traceback_text.splitlines()
    if limit_lines and len(lines) > limit_lines:
        lines = lines[-limit_lines:]
    excerpt = "\n".join(lines).strip() or "(traceback unavailable)"
    return (
        f"Time: {stamp}\n"
        f"Where: {where}\n"
        f"Type: {exc_type}\n"
        f"Message: {message}\n"
        f"Traceback:\n{excerpt}"
    )

