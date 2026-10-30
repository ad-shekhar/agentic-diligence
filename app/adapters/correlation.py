"""
Evidence Correlation Engine (Phase 6 — Milestone B).

Correlates observations across heterogeneous telemetry adapters (OTLP, MCP, Browser)
using deterministic identifiers (Trace ID, Span ID, Session ID, Run ID, Tool-call ID, Parent-Child).

Epistemic Invariants:
1. Never fabricate relationships where correlation identifiers are insufficient.
   Spans lacking common trace or session IDs are quarantined in unlinked traces.
2. Contradiction Resolution: Out-of-band proxy (T2) observers take precedence over
   in-process client (T1) self-reports. Human intervention signals cannot be erased.
3. Incomplete tool calls remain UNKNOWN; absence of evidence is never converted to success.
4. Out-of-order events are causally sorted; clock skew and missing parents are logged as anomalies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.adapters.base import ProvenanceEnvelope
from app.adapters.registry import EvidenceRecord, EvidenceStatus, SourceType
from app.epistemic.tags import EpistemicTag, TrustLevel
from app.ingestion.schema import NormalizedSpan


class AnomalyType(str, Enum):
    OUT_OF_ORDER_EVENTS = "out_of_order_events"
    MISSING_PARENT_SPAN = "missing_parent_span"
    CLOCK_SKEW = "clock_skew"
    CONTRADICTORY_OBSERVATION = "contradictory_observation"
    INCOMPLETE_TOOL_EXECUTION = "incomplete_tool_execution"
    DUPLICATE_EVENT = "duplicate_event"
    DARK_ZONE_GAP = "dark_zone_gap"
    UNLINKED_OBSERVATION = "unlinked_observation"


@dataclass
class CorrelationAnomaly:
    """Detailed record of an evidentiary anomaly discovered during correlation."""
    anomaly_type: AnomalyType
    trace_id: str
    span_id: Optional[str]
    description: str
    severity: str  # "INFO", "WARNING", "ERROR"
    conflicting_values: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type.value,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "description": self.description,
            "severity": self.severity,
            "conflicting_values": self.conflicting_values or {},
        }


@dataclass
class CorrelatedToolCall:
    """
    Cross-adapter correlated tool execution observation.
    Reconciles OTLP spans, MCP JSON-RPC messages, and Browser telemetry for a single tool call.
    """
    tool_call_id: str
    tool_name: str
    trace_id: str
    session_id: Optional[str]
    reconciled_status: str  # "SUCCESS", "ERROR", "UNKNOWN", "REJECTED"
    is_human_intervention: bool
    epistemic_tag: EpistemicTag
    trust_level: TrustLevel
    sources: List[SourceType]
    otlp_span: Optional[NormalizedSpan] = None
    mcp_span: Optional[NormalizedSpan] = None
    browser_span: Optional[NormalizedSpan] = None
    contradiction_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "reconciled_status": self.reconciled_status,
            "is_human_intervention": self.is_human_intervention,
            "epistemic_tag": self.epistemic_tag.value,
            "trust_level": self.trust_level.value,
            "sources": [s.value for s in self.sources],
            "contradiction_notes": self.contradiction_notes,
        }


@dataclass
class CorrelatedTrace:
    """
    Unified trace object synthesized across multiple evidence sources.
    Contains causally ordered normalized spans, reconciled tool calls, and detected anomalies.
    """
    trace_id: str
    company_id: str
    session_id: Optional[str]
    run_id: Optional[str]
    start_time: datetime
    end_time: datetime
    duration_ms: float
    spans: List[NormalizedSpan]
    tool_calls: Dict[str, CorrelatedToolCall]
    sources: Set[SourceType]
    anomalies: List[CorrelationAnomaly]
    has_contradictions: bool
    has_incomplete_tools: bool
    dark_zones: List[Dict[str, Any]]
    evidence_record_ids: List[str]
    provenance_hashes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "company_id": self.company_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "spans_count": len(self.spans),
            "tool_calls_count": len(self.tool_calls),
            "sources": sorted([s.value for s in self.sources]),
            "anomalies_count": len(self.anomalies),
            "has_contradictions": self.has_contradictions,
            "has_incomplete_tools": self.has_incomplete_tools,
            "dark_zones": self.dark_zones,
            "evidence_record_ids": self.evidence_record_ids,
            "provenance_hashes": self.provenance_hashes,
        }


class EvidenceCorrelationEngine:
    """
    Core engine responsible for unifying, cross-validating, ordering, and reconciling
    evidence records across heterogeneous telemetry sources.
    """

    DEFAULT_GAP_THRESHOLD_MS: float = 30000.0  # 30 seconds threshold for dark zones

    def __init__(self, gap_threshold_ms: float = DEFAULT_GAP_THRESHOLD_MS):
        self.gap_threshold_ms = gap_threshold_ms

    def correlate_records(
        self,
        records: Sequence[EvidenceRecord],
        filter_duplicates: bool = True
    ) -> List[CorrelatedTrace]:
        """
        Correlates a collection of evidence records into coherent multi-source CorrelatedTraces.
        """
        if not records:
            return []

        # 1. Group records by trace_id (preserving unlinked records explicitly)
        grouped_by_trace: Dict[str, List[EvidenceRecord]] = {}
        for r in records:
            tid = r.trace_id
            if not tid or tid == "unknown_trace":
                # Strict invariant: never fabricate link to existing trace
                tid = f"unlinked-{r.evidence_id}"
            grouped_by_trace.setdefault(tid, []).append(r)

        correlated_traces: List[CorrelatedTrace] = []

        for trace_id, trace_records in grouped_by_trace.items():
            ct = self._correlate_single_trace(trace_id, trace_records, filter_duplicates)
            correlated_traces.append(ct)

        # Sort traces deterministically by start_time
        correlated_traces.sort(key=lambda t: t.start_time)
        return correlated_traces

    def _correlate_single_trace(
        self,
        trace_id: str,
        records: List[EvidenceRecord],
        filter_duplicates: bool
    ) -> CorrelatedTrace:
        """Processes and reconciles all records for a specific trace identifier."""
        anomalies: List[CorrelationAnomaly] = []
        sources: Set[SourceType] = set()
        evidence_ids: List[str] = []
        prov_hashes: Set[str] = set()
        spans_to_process: List[NormalizedSpan] = []

        company_id = records[0].company_id if records else "default_target"
        session_id: Optional[str] = None
        run_id: Optional[str] = None

        if trace_id.startswith("unlinked-"):
            anomalies.append(CorrelationAnomaly(
                anomaly_type=AnomalyType.UNLINKED_OBSERVATION,
                trace_id=trace_id,
                span_id=None,
                description="Evidence record lacked a trace identifier; quarantined in unlinked trace.",
                severity="WARNING"
            ))

        # 1. Separate duplicates and collect valid records
        for r in records:
            sources.add(r.source_type)
            evidence_ids.append(r.evidence_id)
            prov_hashes.add(r.provenance_hash)

            if r.status == EvidenceStatus.DUPLICATE:
                anomalies.append(CorrelationAnomaly(
                    anomaly_type=AnomalyType.DUPLICATE_EVENT,
                    trace_id=trace_id,
                    span_id=r.span_id,
                    description=f"Duplicate observation detected from source {r.source_type.value}.",
                    severity="INFO"
                ))
                if filter_duplicates:
                    continue

            span = r.span
            spans_to_process.append(span)

            # Extract session and run IDs from span attributes if not yet set
            if not session_id:
                session_id = (
                    span.raw_attributes.get("session.id")
                    or span.raw_attributes.get("session_id")
                    or span.unmapped_attributes.get("session_id")
                )
            if not run_id:
                run_id = (
                    span.raw_attributes.get("run.id")
                    or span.raw_attributes.get("run_id")
                    or span.unmapped_attributes.get("run_id")
                )

        if not spans_to_process:
            # All spans were duplicates or empty
            now = datetime.now(timezone.utc)
            return CorrelatedTrace(
                trace_id=trace_id,
                company_id=company_id,
                session_id=session_id,
                run_id=run_id,
                start_time=now,
                end_time=now,
                duration_ms=0.0,
                spans=[],
                tool_calls={},
                sources=sources,
                anomalies=anomalies,
                has_contradictions=False,
                has_incomplete_tools=False,
                dark_zones=[],
                evidence_record_ids=evidence_ids,
                provenance_hashes=sorted(list(prov_hashes)),
            )

        # 2. Check Parent-Child relationships and detect missing parents
        span_ids = {s.span_id for s in spans_to_process}
        for s in spans_to_process:
            if s.parent_span_id and s.parent_span_id not in span_ids:
                anomalies.append(CorrelationAnomaly(
                    anomaly_type=AnomalyType.MISSING_PARENT_SPAN,
                    trace_id=trace_id,
                    span_id=s.span_id,
                    description=(
                        f"Span {s.span_id} references parent {s.parent_span_id} which was not "
                        "found in trace telemetry. Retained as top-level root without fabricating parent."
                    ),
                    severity="WARNING",
                    conflicting_values={"declared_parent": s.parent_span_id}
                ))

        # 3. Detect clock skew and out-of-order events
        was_out_of_order = False
        for i in range(len(spans_to_process)):
            s = spans_to_process[i]
            if s.end_time < s.start_time:
                anomalies.append(CorrelationAnomaly(
                    anomaly_type=AnomalyType.CLOCK_SKEW,
                    trace_id=trace_id,
                    span_id=s.span_id,
                    description=f"Negative duration detected on span {s.span_id}: start={s.start_time}, end={s.end_time}",
                    severity="WARNING",
                    conflicting_values={"start": s.start_time.isoformat(), "end": s.end_time.isoformat()}
                ))
            if i > 0 and s.start_time < spans_to_process[i - 1].start_time:
                was_out_of_order = True

        if was_out_of_order:
            anomalies.append(CorrelationAnomaly(
                anomaly_type=AnomalyType.OUT_OF_ORDER_EVENTS,
                trace_id=trace_id,
                span_id=None,
                description="Spans arrived out of chronological order. Causally reordering.",
                severity="INFO"
            ))

        # Reorder spans causally: by start_time, then parent before child
        sorted_spans = self._causal_sort_spans(spans_to_process)

        # 4. Check for Dark Zones / Uninstrumented gaps between consecutive spans
        dark_zones: List[Dict[str, Any]] = []
        for i in range(1, len(sorted_spans)):
            prev = sorted_spans[i - 1]
            curr = sorted_spans[i]
            gap_ms = (curr.start_time - prev.end_time).total_seconds() * 1000.0
            if gap_ms > self.gap_threshold_ms:
                dz = {
                    "start_time": prev.end_time.isoformat(),
                    "end_time": curr.start_time.isoformat(),
                    "gap_duration_ms": round(gap_ms, 2),
                    "previous_span_id": prev.span_id,
                    "next_span_id": curr.span_id,
                }
                dark_zones.append(dz)
                anomalies.append(CorrelationAnomaly(
                    anomaly_type=AnomalyType.DARK_ZONE_GAP,
                    trace_id=trace_id,
                    span_id=curr.span_id,
                    description=f"Dark zone detected: {round(gap_ms / 1000.0, 1)}s telemetry gap between spans.",
                    severity="WARNING",
                    conflicting_values=dz
                ))

        # 5. Correlate and reconcile tool calls across sources
        correlated_tool_calls, tool_anomalies = self._reconcile_tool_calls(
            trace_id, session_id, sorted_spans, records
        )
        anomalies.extend(tool_anomalies)

        has_contradictions = any(
            a.anomaly_type == AnomalyType.CONTRADICTORY_OBSERVATION for a in anomalies
        )
        has_incomplete = any(
            tc.reconciled_status == "UNKNOWN" or tc.epistemic_tag == EpistemicTag.UNKNOWN
            for tc in correlated_tool_calls.values()
        ) or any(
            s.tool_status == "UNKNOWN" or s.epistemic_tag == EpistemicTag.UNKNOWN
            for s in sorted_spans if s.tool_call_id or s.tool_name
        )

        trace_start = sorted_spans[0].start_time
        trace_end = max(s.end_time for s in sorted_spans)
        trace_duration_ms = max(0.0, (trace_end - trace_start).total_seconds() * 1000.0)

        return CorrelatedTrace(
            trace_id=trace_id,
            company_id=company_id,
            session_id=session_id,
            run_id=run_id,
            start_time=trace_start,
            end_time=trace_end,
            duration_ms=trace_duration_ms,
            spans=sorted_spans,
            tool_calls=correlated_tool_calls,
            sources=sources,
            anomalies=anomalies,
            has_contradictions=has_contradictions,
            has_incomplete_tools=has_incomplete,
            dark_zones=dark_zones,
            evidence_record_ids=evidence_ids,
            provenance_hashes=sorted(list(prov_hashes)),
        )

    def _causal_sort_spans(self, spans: List[NormalizedSpan]) -> List[NormalizedSpan]:
        """
        Sorts spans primarily by start_time.
        When timestamps are equal, ensures parent spans precede child spans.
        """
        # Graph parent -> children
        span_by_id = {s.span_id: s for s in spans}

        def sort_key(s: NormalizedSpan) -> Tuple[datetime, int, str]:
            depth = 0
            curr = s
            seen = set()
            while curr.parent_span_id and curr.parent_span_id in span_by_id:
                if curr.parent_span_id in seen:
                    break
                seen.add(curr.parent_span_id)
                depth += 1
                curr = span_by_id[curr.parent_span_id]
            return (s.start_time, depth, s.span_id)

        return sorted(spans, key=sort_key)

    def _reconcile_tool_calls(
        self,
        trace_id: str,
        session_id: Optional[str],
        spans: List[NormalizedSpan],
        records: List[EvidenceRecord]
    ) -> Tuple[Dict[str, CorrelatedToolCall], List[CorrelationAnomaly]]:
        """
        Reconciles multi-adapter observations of tool calls.
        Detects conflicts between in-process (T1) and out-of-band proxy (T2) observers.
        """
        tool_groups: Dict[str, Dict[str, Any]] = {}
        anomalies: List[CorrelationAnomaly] = []

        # Map span_id to record source_type
        record_source_map = {r.span_id: r.source_type for r in records}

        for span in spans:
            call_id = span.tool_call_id or (
                f"tool-call:{span.tool_name}:{span.span_id}" if span.tool_name else None
            )
            if not call_id:
                continue

            src = record_source_map.get(span.span_id, SourceType.UNKNOWN)
            group = tool_groups.setdefault(call_id, {
                "tool_name": span.tool_name or "unknown_tool",
                "otlp_span": None,
                "mcp_span": None,
                "browser_span": None,
                "spans": [],
                "sources": set(),
            })
            group["spans"].append(span)
            group["sources"].add(src)

            if src == SourceType.OTLP:
                group["otlp_span"] = span
            elif src == SourceType.MCP:
                group["mcp_span"] = span
            elif src == SourceType.BROWSER:
                group["browser_span"] = span

        reconciled_calls: Dict[str, CorrelatedToolCall] = {}

        for call_id, g in tool_groups.items():
            otlp_s: Optional[NormalizedSpan] = g["otlp_span"]
            mcp_s: Optional[NormalizedSpan] = g["mcp_span"]
            browser_s: Optional[NormalizedSpan] = g["browser_span"]
            sources_list = sorted(list(g["sources"]), key=lambda s: s.value)

            tool_name = g["tool_name"]
            statuses: Dict[SourceType, str] = {}
            if otlp_s and otlp_s.tool_status:
                statuses[SourceType.OTLP] = otlp_s.tool_status
            if mcp_s and mcp_s.tool_status:
                statuses[SourceType.MCP] = mcp_s.tool_status
            if browser_s and browser_s.tool_status:
                statuses[SourceType.BROWSER] = browser_s.tool_status

            # Reconcile status:
            # 1. If any observer records UNKNOWN / incomplete -> status is UNKNOWN
            # 2. If T2 MCP disagrees with T1 OTLP (e.g. OTLP says SUCCESS, MCP says ERROR),
            #    T2 takes precedence and a CONTRADICTION is logged.
            # 3. If Browser records modal rejection -> status is REJECTED
            reconciled_status = "UNKNOWN"
            contradiction_note: Optional[str] = None
            epistemic_tag = EpistemicTag.OBSERVED
            trust_level = TrustLevel.T1

            # Check human intervention first: cannot be erased
            is_human = any(s.is_human_intervention for s in g["spans"])
            if browser_s and browser_s.is_human_intervention:
                is_human = True
                if otlp_s and not otlp_s.is_human_intervention:
                    msg = (
                        f"Contradiction on tool call {call_id}: OTLP reported autonomous execution, "
                        "but Browser adapter recorded explicit human intervention/approval modal."
                    )
                    anomalies.append(CorrelationAnomaly(
                        anomaly_type=AnomalyType.CONTRADICTORY_OBSERVATION,
                        trace_id=trace_id,
                        span_id=otlp_s.span_id,
                        description=msg,
                        severity="ERROR",
                        conflicting_values={
                            "otlp_is_human_intervention": False,
                            "browser_is_human_intervention": True,
                        }
                    ))
                    contradiction_note = msg
                    epistemic_tag = EpistemicTag.INFERRED

            # Check for incomplete executions
            has_unknown_status = any(st.upper() == "UNKNOWN" for st in statuses.values())
            if has_unknown_status or not statuses:
                reconciled_status = "UNKNOWN"
                epistemic_tag = EpistemicTag.UNKNOWN
                anomalies.append(CorrelationAnomaly(
                    anomaly_type=AnomalyType.INCOMPLETE_TOOL_EXECUTION,
                    trace_id=trace_id,
                    span_id=g["spans"][0].span_id,
                    description=f"Tool call {call_id} was unresolved or missing confirmation.",
                    severity="WARNING",
                    conflicting_values={"observed_statuses": {s.value: v for s, v in statuses.items()}}
                ))
            elif SourceType.MCP in statuses and SourceType.OTLP in statuses:
                mcp_st = statuses[SourceType.MCP].upper()
                otlp_st = statuses[SourceType.OTLP].upper()

                if mcp_st == "ERROR" and otlp_st in ("SUCCESS", "OK"):
                    # T2 observer precedence
                    reconciled_status = "ERROR"
                    trust_level = TrustLevel.T2
                    msg = (
                        f"Contradiction on tool call {call_id}: T1 OTLP reported SUCCESS, "
                        "but T2 MCP proxy observed JSON-RPC execution ERROR. Downgrading to ERROR."
                    )
                    anomalies.append(CorrelationAnomaly(
                        anomaly_type=AnomalyType.CONTRADICTORY_OBSERVATION,
                        trace_id=trace_id,
                        span_id=otlp_s.span_id if otlp_s else None,
                        description=msg,
                        severity="ERROR",
                        conflicting_values={"otlp_status": otlp_st, "mcp_status": mcp_st}
                    ))
                    contradiction_note = msg
                elif mcp_st == otlp_st:
                    reconciled_status = mcp_st
                    trust_level = TrustLevel.T2
                else:
                    reconciled_status = mcp_st
                    trust_level = TrustLevel.T2
            elif SourceType.BROWSER in statuses and statuses[SourceType.BROWSER].upper() == "REJECTED":
                reconciled_status = "REJECTED"
                trust_level = TrustLevel.T2
            else:
                # Single source or concurring sources
                first_st = list(statuses.values())[0].upper()
                reconciled_status = first_st
                # Highest trust level present
                for s in g["spans"]:
                    if s.trust_level.rank > trust_level.rank:
                        trust_level = s.trust_level

            # Propagate reconciled values back into spans so downstream stages see reconciled truth
            for s in g["spans"]:
                s.tool_status = reconciled_status
                if is_human:
                    s.is_human_intervention = True
                if epistemic_tag == EpistemicTag.UNKNOWN:
                    s.epistemic_tag = EpistemicTag.UNKNOWN

            reconciled_calls[call_id] = CorrelatedToolCall(
                tool_call_id=call_id,
                tool_name=tool_name,
                trace_id=trace_id,
                session_id=session_id,
                reconciled_status=reconciled_status,
                is_human_intervention=is_human,
                epistemic_tag=epistemic_tag,
                trust_level=trust_level,
                sources=sources_list,
                otlp_span=otlp_s,
                mcp_span=mcp_s,
                browser_span=browser_s,
                contradiction_notes=contradiction_note,
            )

        return reconciled_calls, anomalies


# Singleton instance
default_correlation_engine = EvidenceCorrelationEngine()

