"""
Task Segmentation Engine — Phase 3 of Agentic Diligence.

Segments a normalized trace into discrete, atomic tasks and classifies each one
with an explicit epistemic status:

    AUTONOMOUS           — agent completed the task end-to-end with no observed human signal
    HUMAN_EXPLICIT       — human intervention was directly recorded in telemetry spans
    HUMAN_INFERRED       — human involvement inferred via reaction-latency heuristic (labeled, never isolated)
    UNKNOWN              — uninstrumented gap or missing telemetry; never silently assumed either way

Core invariant (from Phase 1): absence of evidence ≠ evidence of absence.
Unknown tasks widen the autonomy confidence interval; they are never collapsed into
an autonomous count.

Deterministic Autonomy Rate formula
------------------------------------
   lower_pct  = autonomous / total * 100
   upper_pct  = (autonomous + unknown) / total * 100
   point_est  = lower_pct   # honest pessimistic baseline

Trust annotations are carried forward from the ingested spans (T0..T3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from app.epistemic.tags import (
    ConfidenceBounds,
    EpistemicTag,
    EpistemicValue,
    TrustLevel,
    compute_autonomy_bounds,
)
from app.ingestion.schema import NormalizedSpan


# ---------------------------------------------------------------------------
# Task-level classification
# ---------------------------------------------------------------------------

class TaskOutcome(str, Enum):
    AUTONOMOUS       = "AUTONOMOUS"
    HUMAN_EXPLICIT   = "HUMAN_EXPLICIT"
    HUMAN_INFERRED   = "HUMAN_INFERRED"
    UNKNOWN          = "UNKNOWN"


class InterventionKind(str, Enum):
    """What triggered a human-involved classification."""
    OBSERVED_SPAN    = "observed_span"          # explicit human span in telemetry
    LATENCY_HEURISTIC = "latency_heuristic"    # inferred from anomalous inter-span gap
    MISSING_DATA     = "missing_data"           # no spans present for interval → UNKNOWN


# Heuristic threshold: gaps longer than this between consecutive spans are flagged
# as a possible human checkpoint.  This is INFERRED, never OBSERVED.
_DEFAULT_GAP_HEURISTIC_MS: float = 30_000.0   # 30 seconds


@dataclass
class SegmentedTask:
    """
    A single atomic task extracted from a trace, with epistemic attribution.
    """
    task_id: str
    trace_id: str
    name: str                               # Derived from root/anchor span name
    start_time: datetime
    end_time: datetime
    duration_ms: float

    outcome: TaskOutcome
    epistemic_tag: EpistemicTag             # OBSERVED / INFERRED / UNKNOWN for outcome
    trust_level: TrustLevel

    # Spans that constitute this task (may be empty for UNKNOWN gaps)
    span_ids: List[str] = field(default_factory=list)

    # Intervention details (set for HUMAN_EXPLICIT / HUMAN_INFERRED)
    intervention_kind: Optional[InterventionKind] = None
    intervention_detail: Optional[str] = None

    # Gap metadata (set for UNKNOWN gaps)
    gap_before_ms: Optional[float] = None    # uninstrumented interval preceding this task

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "outcome": self.outcome.value,
            "epistemic_tag": self.epistemic_tag.value,
            "trust_level": self.trust_level.value,
            "span_ids": self.span_ids,
            "intervention_kind": self.intervention_kind.value if self.intervention_kind else None,
            "intervention_detail": self.intervention_detail,
            "gap_before_ms": round(self.gap_before_ms, 2) if self.gap_before_ms is not None else None,
        }


@dataclass
class TraceSegmentationResult:
    """
    Full segmentation analysis for a single trace, including epistemically-tagged
    autonomy bounds.
    """
    trace_id: str
    workflow_name: str
    total_tasks: int
    tasks: List[SegmentedTask]

    # Autonomy metric (epistemically bounded)
    autonomy: EpistemicValue

    # Counts by outcome
    autonomous_count: int = 0
    human_explicit_count: int = 0
    human_inferred_count: int = 0
    unknown_count: int = 0

    # Trust level of the overall trace (minimum across constituent spans)
    min_trust_level: TrustLevel = TrustLevel.T1

    # Analysis notes
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_name": self.workflow_name,
            "total_tasks": self.total_tasks,
            "autonomous_count": self.autonomous_count,
            "human_explicit_count": self.human_explicit_count,
            "human_inferred_count": self.human_inferred_count,
            "unknown_count": self.unknown_count,
            "min_trust_level": self.min_trust_level.value,
            "autonomy": self.autonomy.to_dict(),
            "notes": self.notes,
            "tasks": [t.to_dict() for t in self.tasks],
        }


# ---------------------------------------------------------------------------
# Segmentation Logic
# ---------------------------------------------------------------------------

def segment_trace(
    spans: Sequence[NormalizedSpan],
    trace_id: str,
    workflow_name: str = "unknown_workflow",
    gap_heuristic_ms: float = _DEFAULT_GAP_HEURISTIC_MS,
) -> TraceSegmentationResult:
    """
    Segments a list of NormalizedSpans from a single trace into atomic tasks
    and returns epistemically-tagged autonomy bounds.

    Algorithm
    ---------
    1. Sort spans by start_time.
    2. Merge overlapping/adjacent spans into contiguous task windows
       (a task = a continuous cluster of spans with no gap > gap_heuristic_ms).
    3. Classify each task window:
       a. If any span within the window has is_human_intervention=True and
          intervention_detection_method indicates OBSERVED_TELEMETRY → HUMAN_EXPLICIT.
       b. If any span has is_human_intervention=True via INFERRED method → HUMAN_INFERRED.
       c. If a gap exceeds gap_heuristic_ms and no span bridges it → UNKNOWN.
       d. Otherwise → AUTONOMOUS.
    4. Compute autonomy bounds using the Phase 1 `compute_autonomy_bounds` formula.
    """
    if not spans:
        bounds, unknown_frac = compute_autonomy_bounds(0, 0, 0, 0)
        return TraceSegmentationResult(
            trace_id=trace_id,
            workflow_name=workflow_name,
            total_tasks=0,
            tasks=[],
            autonomy=EpistemicValue(
                value=None,
                tag=EpistemicTag.UNKNOWN,
                trust_level=TrustLevel.T1,
                bounds=bounds,
                sample_size=0,
                unknown_fraction=unknown_frac,
                notes="No spans available; autonomy is entirely unknown.",
            ),
            notes=["No instrumented spans provided — trace may be entirely uninstrumented."],
        )

    # Filter out epoch-sentinel spans (1970-01-01T00:00:00) — these indicate missing timestamps,
    # not genuine observations. Including them would generate false 50-year gaps against real spans.
    _EPOCH_SENTINEL = datetime(1970, 1, 1, 0, 0, 0)
    epoch_spans = [s for s in spans if s.start_time == _EPOCH_SENTINEL]
    real_spans = [s for s in spans if s.start_time != _EPOCH_SENTINEL]

    sentinel_notes: list = []
    if epoch_spans:
        sentinel_notes.append(
            f"{len(epoch_spans)} span(s) had missing timestamps (epoch sentinel 1970-01-01) "
            "and were excluded from gap analysis to prevent spurious UNKNOWN classification. "
            "These spans are counted in total span metrics but not task segmentation."
        )

    if not real_spans:
        # All spans had missing timestamps; cannot segment
        bounds, unknown_frac = compute_autonomy_bounds(0, 0, 0, 0)
        return TraceSegmentationResult(
            trace_id=trace_id,
            workflow_name=workflow_name,
            total_tasks=0,
            tasks=[],
            autonomy=EpistemicValue(
                value=None,
                tag=EpistemicTag.UNKNOWN,
                trust_level=TrustLevel.T1,
                bounds=bounds,
                sample_size=0,
                unknown_fraction=unknown_frac,
                notes="All spans had missing timestamps (epoch sentinel); autonomy is entirely unknown.",
            ),
            notes=sentinel_notes or ["All spans had missing timestamps; cannot segment."],
        )

    # Sort real spans chronologically
    sorted_spans = sorted(real_spans, key=lambda s: s.start_time)

    # Determine minimum trust level across all spans
    trust_ranks = {TrustLevel.T0: 0, TrustLevel.T1: 1, TrustLevel.T2: 2, TrustLevel.T3: 3}
    min_trust = min(sorted_spans, key=lambda s: trust_ranks.get(s.trust_level, 1)).trust_level

    tasks: List[SegmentedTask] = []
    notes: List[str] = list(sentinel_notes)  # Carry forward any epoch-sentinel warnings

    # --- Step 1: Cluster spans into contiguous task windows ---
    clusters: List[List[NormalizedSpan]] = []
    current_cluster: List[NormalizedSpan] = [sorted_spans[0]]

    for prev_span, curr_span in zip(sorted_spans, sorted_spans[1:]):
        gap_ms = (curr_span.start_time - prev_span.end_time).total_seconds() * 1000.0
        if gap_ms > gap_heuristic_ms:
            clusters.append(current_cluster)
            current_cluster = [curr_span]
            # Record an UNKNOWN gap task between clusters
            gap_task = _make_unknown_gap_task(
                task_index=len(clusters),
                trace_id=trace_id,
                gap_start=prev_span.end_time,
                gap_end=curr_span.start_time,
                gap_ms=gap_ms,
                trust_level=min_trust,
            )
            tasks.append(gap_task)
            notes.append(
                f"Uninstrumented gap of {gap_ms:.0f} ms detected between "
                f"span '{prev_span.name}' and '{curr_span.name}'. Classified as UNKNOWN."
            )
        else:
            current_cluster.append(curr_span)

    clusters.append(current_cluster)

    # --- Step 2: Classify each cluster as a task ---
    for cluster_idx, cluster in enumerate(clusters):
        task = _classify_cluster(
            cluster=cluster,
            task_index=len(tasks),
            trace_id=trace_id,
        )
        tasks.append(task)

    # Sort tasks by start_time for canonical ordering
    tasks.sort(key=lambda t: t.start_time)

    # Re-index task_ids after sort
    for i, task in enumerate(tasks):
        task.task_id = f"{trace_id}::task-{i + 1:03d}"

    # --- Step 3: Count outcomes ---
    auto_count = sum(1 for t in tasks if t.outcome == TaskOutcome.AUTONOMOUS)
    human_exp  = sum(1 for t in tasks if t.outcome == TaskOutcome.HUMAN_EXPLICIT)
    human_inf  = sum(1 for t in tasks if t.outcome == TaskOutcome.HUMAN_INFERRED)
    unk_count  = sum(1 for t in tasks if t.outcome == TaskOutcome.UNKNOWN)
    total      = len(tasks)

    # --- Step 4: Compute autonomy bounds ---
    bounds, unknown_frac = compute_autonomy_bounds(
        autonomous_count=auto_count,
        human_explicit_count=human_exp,
        human_inferred_count=human_inf,
        unknown_count=unk_count,
    )

    # Determine epistemic tag for autonomy value
    if unk_count > 0 and auto_count == 0:
        tag = EpistemicTag.UNKNOWN
    elif unk_count > 0:
        tag = EpistemicTag.INFERRED   # Partial unknown; point estimate is inferred
    else:
        tag = EpistemicTag.CALCULATED

    autonomy_value = EpistemicValue(
        value=round(bounds.point_estimate, 2),
        tag=tag,
        trust_level=min_trust,
        bounds=bounds,
        sample_size=total,
        unknown_fraction=unknown_frac,
        notes=(
            f"Autonomy bounds [{bounds.lower:.1f}%, {bounds.upper:.1f}%] "
            f"over {total} segmented tasks ({auto_count} autonomous, "
            f"{human_exp} explicit human, {human_inf} inferred human, "
            f"{unk_count} unknown/uninstrumented)."
        ),
        metadata={
            "gap_heuristic_ms": gap_heuristic_ms,
            "min_trust_level": min_trust.value,
        },
    )

    return TraceSegmentationResult(
        trace_id=trace_id,
        workflow_name=workflow_name,
        total_tasks=total,
        tasks=tasks,
        autonomy=autonomy_value,
        autonomous_count=auto_count,
        human_explicit_count=human_exp,
        human_inferred_count=human_inf,
        unknown_count=unk_count,
        min_trust_level=min_trust,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_cluster(
    cluster: List[NormalizedSpan],
    task_index: int,
    trace_id: str,
) -> SegmentedTask:
    """Classify a cluster of spans into a single SegmentedTask."""
    start = min(s.start_time for s in cluster)
    end   = max(s.end_time   for s in cluster)
    duration_ms = max(0.0, (end - start).total_seconds() * 1000.0)

    # Trust: use minimum (most conservative) trust level within cluster
    trust_ranks = {TrustLevel.T0: 0, TrustLevel.T1: 1, TrustLevel.T2: 2, TrustLevel.T3: 3}
    trust = min(cluster, key=lambda s: trust_ranks.get(s.trust_level, 1)).trust_level

    # Collect human-intervention spans
    explicit_spans = [
        s for s in cluster
        if s.is_human_intervention
        and s.intervention_detection_method in (
            None,                    # default → treat as observed
            "OBSERVED_TELEMETRY",
            "WORKFLOW_STATE",
            "APPLICATION_EVENT",
        )
    ]
    inferred_spans = [
        s for s in cluster
        if s.is_human_intervention
        and s.intervention_detection_method == "INFERRED_HEURISTIC_LATENCY"
    ]

    span_ids = [s.span_id for s in cluster]
    anchor_name = cluster[0].name  # root span name as task name

    if explicit_spans:
        return SegmentedTask(
            task_id=f"{trace_id}::task-{task_index + 1:03d}",
            trace_id=trace_id,
            name=anchor_name,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            outcome=TaskOutcome.HUMAN_EXPLICIT,
            epistemic_tag=EpistemicTag.OBSERVED,
            trust_level=trust,
            span_ids=span_ids,
            intervention_kind=InterventionKind.OBSERVED_SPAN,
            intervention_detail=(
                f"Explicit human intervention observed in {len(explicit_spans)} span(s): "
                + ", ".join(s.human_action_type or s.name for s in explicit_spans)
            ),
        )

    if inferred_spans:
        return SegmentedTask(
            task_id=f"{trace_id}::task-{task_index + 1:03d}",
            trace_id=trace_id,
            name=anchor_name,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            outcome=TaskOutcome.HUMAN_INFERRED,
            epistemic_tag=EpistemicTag.INFERRED,
            trust_level=trust,
            span_ids=span_ids,
            intervention_kind=InterventionKind.LATENCY_HEURISTIC,
            intervention_detail=(
                f"Human involvement inferred from latency heuristic in "
                f"{len(inferred_spans)} span(s). Not independently verified."
            ),
        )

    # No intervention signals → autonomous
    return SegmentedTask(
        task_id=f"{trace_id}::task-{task_index + 1:03d}",
        trace_id=trace_id,
        name=anchor_name,
        start_time=start,
        end_time=end,
        duration_ms=duration_ms,
        outcome=TaskOutcome.AUTONOMOUS,
        epistemic_tag=EpistemicTag.OBSERVED,
        trust_level=trust,
        span_ids=span_ids,
    )


def _make_unknown_gap_task(
    task_index: int,
    trace_id: str,
    gap_start: datetime,
    gap_end: datetime,
    gap_ms: float,
    trust_level: TrustLevel,
) -> SegmentedTask:
    """Creates an UNKNOWN task representing an uninstrumented gap between spans."""
    return SegmentedTask(
        task_id=f"{trace_id}::gap-{task_index:03d}",
        trace_id=trace_id,
        name="[uninstrumented_gap]",
        start_time=gap_start,
        end_time=gap_end,
        duration_ms=gap_ms,
        outcome=TaskOutcome.UNKNOWN,
        epistemic_tag=EpistemicTag.UNKNOWN,
        trust_level=trust_level,
        span_ids=[],
        intervention_kind=InterventionKind.MISSING_DATA,
        intervention_detail=(
            f"Uninstrumented interval of {gap_ms:.0f} ms. "
            "Cannot determine whether human or autonomous. Treated as UNKNOWN."
        ),
        gap_before_ms=gap_ms,
    )


# ---------------------------------------------------------------------------
# Aggregate across multiple traces
# ---------------------------------------------------------------------------

def aggregate_autonomy_across_traces(
    results: Sequence[TraceSegmentationResult],
) -> EpistemicValue:
    """
    Aggregates per-trace segmentation results into a portfolio-level autonomy metric.

    Uses the same Phase 1 formula: pools all task counts across traces and recomputes
    bounds. Unknown tasks from uninstrumented intervals are never dropped.
    """
    if not results:
        bounds, _ = compute_autonomy_bounds(0, 0, 0, 0)
        return EpistemicValue(
            value=None,
            tag=EpistemicTag.UNKNOWN,
            trust_level=TrustLevel.T1,
            bounds=bounds,
            sample_size=0,
            unknown_fraction=1.0,
            notes="No trace results provided.",
        )

    total_auto  = sum(r.autonomous_count for r in results)
    total_hexp  = sum(r.human_explicit_count for r in results)
    total_hinf  = sum(r.human_inferred_count for r in results)
    total_unk   = sum(r.unknown_count for r in results)
    total_tasks = sum(r.total_tasks for r in results)

    trust_ranks = {TrustLevel.T0: 0, TrustLevel.T1: 1, TrustLevel.T2: 2, TrustLevel.T3: 3}
    min_trust = min(results, key=lambda r: trust_ranks.get(r.min_trust_level, 1)).min_trust_level

    bounds, unknown_frac = compute_autonomy_bounds(total_auto, total_hexp, total_hinf, total_unk)

    if total_unk > 0 and total_auto == 0:
        tag = EpistemicTag.UNKNOWN
    elif total_unk > 0:
        tag = EpistemicTag.INFERRED
    else:
        tag = EpistemicTag.CALCULATED

    return EpistemicValue(
        value=round(bounds.point_estimate, 2),
        tag=tag,
        trust_level=min_trust,
        bounds=bounds,
        sample_size=total_tasks,
        unknown_fraction=unknown_frac,
        notes=(
            f"Portfolio autonomy bounds [{bounds.lower:.1f}%, {bounds.upper:.1f}%] "
            f"across {len(results)} traces / {total_tasks} total tasks "
            f"({total_auto} autonomous, {total_hexp} explicit human, "
            f"{total_hinf} inferred human, {total_unk} unknown)."
        ),
        metadata={
            "trace_count": len(results),
            "total_tasks": total_tasks,
            "min_trust_level": min_trust.value,
        },
    )
