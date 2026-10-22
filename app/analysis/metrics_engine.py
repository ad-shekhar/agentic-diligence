"""
Deterministic Metrics Engine — Phase 3 of Agentic Diligence.

Computes the canonical 8 diligence signals from a collection of
TraceSegmentationResults and NormalizedSpans/Traces.

All metrics carry:
  - EpistemicTag  (OBSERVED | CALCULATED | INFERRED | UNKNOWN)
  - TrustLevel    (T0..T3)
  - ConfidenceBounds (lower, point_estimate, upper)

Formulas are published deterministically so any external party can reproduce
results given the same evidence. No heuristic is silently baked in.

Signal definitions
------------------
1. Autonomy Rate (AR)          — bounded [lower, upper] over task-segmented traces
2. Human Intervention Rate (HIR) — observed / inferred breakdown
3. Task Completion Rate (TCR)  — fraction of tasks that reached terminal OK status
4. Error Rate (ER)             — fraction of tasks/spans with ERROR status code
5. Token Efficiency (TE)       — mean output_tokens / (input_tokens + output_tokens)
6. Cost Per Task (CPT)         — mean USD cost per atomic task
7. Model Concentration (MC)    — Herfindahl-Hirschman Index over provider distribution
8. Telemetry Coverage (TC)     — fraction of tasks with T1+ evidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.epistemic.tags import (
    ConfidenceBounds,
    EpistemicTag,
    EpistemicValue,
    TrustLevel,
    compute_autonomy_bounds,
)
from app.ingestion.schema import NormalizedSpan, NormalizedTrace
from app.analysis.task_segmentation import (
    SegmentedTask,
    TaskOutcome,
    TraceSegmentationResult,
    aggregate_autonomy_across_traces,
)


# ---------------------------------------------------------------------------
# Per-signal computed results
# ---------------------------------------------------------------------------

@dataclass
class DiligenceMetrics:
    """
    The 8 canonical diligence signals computed from segmented trace data.
    Each signal is an EpistemicValue carrying explicit trust attribution.
    """
    autonomy_rate: EpistemicValue               # AR  [%]
    human_intervention_rate: EpistemicValue     # HIR [%]
    task_completion_rate: EpistemicValue        # TCR [%]
    error_rate: EpistemicValue                  # ER  [%]
    token_efficiency: EpistemicValue            # TE  [0–1]
    cost_per_task: EpistemicValue               # CPT [USD]
    model_concentration: EpistemicValue         # MC  [HHI 0–10000]
    telemetry_coverage: EpistemicValue          # TC  [%]

    # Summary stats
    total_tasks: int = 0
    total_spans: int = 0
    total_traces: int = 0
    total_cost_usd: float = 0.0
    computation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "total_spans": self.total_spans,
            "total_traces": self.total_traces,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "signals": {
                "autonomy_rate": self.autonomy_rate.to_dict(),
                "human_intervention_rate": self.human_intervention_rate.to_dict(),
                "task_completion_rate": self.task_completion_rate.to_dict(),
                "error_rate": self.error_rate.to_dict(),
                "token_efficiency": self.token_efficiency.to_dict(),
                "cost_per_task": self.cost_per_task.to_dict(),
                "model_concentration": self.model_concentration.to_dict(),
                "telemetry_coverage": self.telemetry_coverage.to_dict(),
            },
            "computation_notes": self.computation_notes,
        }


# ---------------------------------------------------------------------------
# Metrics Engine
# ---------------------------------------------------------------------------

def compute_diligence_metrics(
    segmentation_results: Sequence[TraceSegmentationResult],
    all_spans: Sequence[NormalizedSpan],
) -> DiligenceMetrics:
    """
    Computes all 8 diligence signals from segmented task results and raw spans.

    Parameters
    ----------
    segmentation_results : Sequence[TraceSegmentationResult]
        One result per ingested trace, produced by segment_trace().
    all_spans : Sequence[NormalizedSpan]
        All normalized spans across those traces (used for token / cost signals).

    Returns
    -------
    DiligenceMetrics
        Fully populated, epistemically-tagged metrics object.
    """
    notes: List[str] = []
    total_traces = len(segmentation_results)
    total_spans  = len(all_spans)

    # -------------------------------------------------------------------------
    # 1. Autonomy Rate (AR) — delegate to Phase 1 aggregate formula
    # -------------------------------------------------------------------------
    ar = aggregate_autonomy_across_traces(segmentation_results)
    all_tasks: List[SegmentedTask] = [t for r in segmentation_results for t in r.tasks]
    total_tasks = len(all_tasks)

    # -------------------------------------------------------------------------
    # 2. Human Intervention Rate (HIR)
    # -------------------------------------------------------------------------
    explicit_human = sum(r.human_explicit_count for r in segmentation_results)
    inferred_human = sum(r.human_inferred_count for r in segmentation_results)
    # Also check raw spans: even if a cluster is classified EXPLICIT (because an
    # observed span has higher priority), there may still be INFERRED spans within it.
    # HIR tag must be INFERRED whenever any span was classified via heuristic.
    has_inferred_spans = any(
        s.is_human_intervention and s.intervention_detection_method == "INFERRED_HEURISTIC_LATENCY"
        for s in all_spans
    )
    total_human = explicit_human + inferred_human
    hir_pct = (total_human / total_tasks * 100.0) if total_tasks > 0 else 0.0
    hir_tag = EpistemicTag.INFERRED if (inferred_human > 0 or has_inferred_spans) else EpistemicTag.OBSERVED

    hir = EpistemicValue(
        value=round(hir_pct, 2),
        tag=hir_tag,
        trust_level=_min_trust(segmentation_results),
        bounds=ConfidenceBounds(
            lower=round(explicit_human / total_tasks * 100.0, 4) if total_tasks else 0.0,
            point_estimate=round(hir_pct, 4),
            upper=round(hir_pct, 4),
        ),
        sample_size=total_tasks,
        notes=(
            f"{total_human} human-involved tasks "
            f"({explicit_human} observed in telemetry, {inferred_human} inferred via latency heuristic) "
            f"out of {total_tasks} total."
            + (" Note: inferred spans present — tag is INFERRED." if has_inferred_spans else "")
        ),
    )

    # -------------------------------------------------------------------------
    # 3. Task Completion Rate (TCR)
    # -------------------------------------------------------------------------
    # A task is complete if it has at least one span with status_code == "OK"
    # and is not an UNKNOWN gap.
    completed = 0
    incomplete = 0
    unknown_outcome = 0
    for task in all_tasks:
        if task.outcome == TaskOutcome.UNKNOWN:
            unknown_outcome += 1
        elif _task_is_completed(task, all_spans):
            completed += 1
        else:
            incomplete += 1

    tcr_lower = (completed / total_tasks * 100.0) if total_tasks > 0 else 0.0
    tcr_upper = ((completed + unknown_outcome) / total_tasks * 100.0) if total_tasks > 0 else 0.0
    tcr_point = tcr_lower
    tcr_tag = EpistemicTag.UNKNOWN if unknown_outcome > 0 and completed == 0 else (
        EpistemicTag.INFERRED if unknown_outcome > 0 else EpistemicTag.CALCULATED
    )

    tcr = EpistemicValue(
        value=round(tcr_point, 2),
        tag=tcr_tag,
        trust_level=_min_trust(segmentation_results),
        bounds=ConfidenceBounds(lower=tcr_lower, point_estimate=tcr_point, upper=tcr_upper),
        sample_size=total_tasks,
        notes=(
            f"{completed} completed, {incomplete} incomplete, "
            f"{unknown_outcome} unknown-outcome tasks. "
            "Unknown tasks widen the upper bound."
        ),
    )

    # -------------------------------------------------------------------------
    # 4. Error Rate (ER) — over all instrumented spans
    # -------------------------------------------------------------------------
    error_spans = [s for s in all_spans if s.status_code == "ERROR"]
    er_pct = (len(error_spans) / total_spans * 100.0) if total_spans > 0 else 0.0

    er = EpistemicValue(
        value=round(er_pct, 2),
        tag=EpistemicTag.OBSERVED if total_spans > 0 else EpistemicTag.UNKNOWN,
        trust_level=_min_trust_spans(all_spans),
        bounds=ConfidenceBounds(
            lower=round(er_pct, 4),
            point_estimate=round(er_pct, 4),
            upper=round(er_pct, 4),
        ),
        sample_size=total_spans,
        notes=f"{len(error_spans)} ERROR spans out of {total_spans} total spans.",
    )

    # -------------------------------------------------------------------------
    # 5. Token Efficiency (TE) — output / (input + output)
    # -------------------------------------------------------------------------
    te_value, te_tag, te_n, te_note = _compute_token_efficiency(all_spans)

    te = EpistemicValue(
        value=te_value,
        tag=te_tag,
        trust_level=_min_trust_spans(all_spans),
        bounds=ConfidenceBounds(
            lower=te_value if te_value is not None else 0.0,
            point_estimate=te_value if te_value is not None else 0.0,
            upper=te_value if te_value is not None else 0.0,
        ),
        sample_size=te_n,
        notes=te_note,
    )

    # -------------------------------------------------------------------------
    # 6. Cost Per Task (CPT)
    # -------------------------------------------------------------------------
    total_cost = sum(s.cost_usd for s in all_spans)
    cpt_value  = round(total_cost / total_tasks, 6) if total_tasks > 0 else 0.0
    unpriced   = sum(1 for s in all_spans if s.cost_status != "MEASURED")
    cpt_tag    = EpistemicTag.CALCULATED if unpriced == 0 else EpistemicTag.INFERRED

    cpt = EpistemicValue(
        value=cpt_value,
        tag=cpt_tag,
        trust_level=_min_trust_spans(all_spans),
        bounds=ConfidenceBounds(
            lower=cpt_value,
            point_estimate=cpt_value,
            upper=cpt_value,
        ),
        sample_size=total_tasks,
        notes=(
            f"Total cost ${total_cost:.4f} across {total_tasks} tasks. "
            f"{unpriced} spans have unresolved cost (ESTIMATED or UNKNOWN)."
            if unpriced else
            f"Total cost ${total_cost:.4f} across {total_tasks} tasks. "
            "All spans have measured costs."
        ),
    )

    # -------------------------------------------------------------------------
    # 7. Model Concentration (MC) — HHI over provider traffic share
    # -------------------------------------------------------------------------
    hhi, provider_shares, mc_note = _compute_hhi(all_spans)
    mc_tag = EpistemicTag.CALCULATED if total_spans > 0 else EpistemicTag.UNKNOWN

    mc = EpistemicValue(
        value=round(hhi, 1),
        tag=mc_tag,
        trust_level=_min_trust_spans(all_spans),
        bounds=ConfidenceBounds(
            lower=round(hhi, 1),
            point_estimate=round(hhi, 1),
            upper=round(hhi, 1),
        ),
        sample_size=total_spans,
        notes=mc_note,
        metadata={"provider_shares": provider_shares},
    )

    # -------------------------------------------------------------------------
    # 8. Telemetry Coverage (TC)
    # -------------------------------------------------------------------------
    t1_plus_tasks = sum(
        1 for t in all_tasks
        if t.trust_level.value in ("T1", "T2", "T3")
        and t.outcome != TaskOutcome.UNKNOWN
    )
    tc_pct = (t1_plus_tasks / total_tasks * 100.0) if total_tasks > 0 else 0.0

    tc = EpistemicValue(
        value=round(tc_pct, 2),
        tag=EpistemicTag.CALCULATED if total_tasks > 0 else EpistemicTag.UNKNOWN,
        trust_level=_min_trust(segmentation_results),
        bounds=ConfidenceBounds(
            lower=round(tc_pct, 4),
            point_estimate=round(tc_pct, 4),
            upper=round(tc_pct, 4),
        ),
        sample_size=total_tasks,
        notes=(
            f"{t1_plus_tasks} tasks with T1+ telemetry coverage "
            f"out of {total_tasks} total tasks ({total_tasks - t1_plus_tasks} uninstrumented/unknown)."
        ),
    )

    return DiligenceMetrics(
        autonomy_rate=ar,
        human_intervention_rate=hir,
        task_completion_rate=tcr,
        error_rate=er,
        token_efficiency=te,
        cost_per_task=cpt,
        model_concentration=mc,
        telemetry_coverage=tc,
        total_tasks=total_tasks,
        total_spans=total_spans,
        total_traces=total_traces,
        total_cost_usd=round(total_cost, 6),
        computation_notes=notes,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _min_trust(results: Sequence[TraceSegmentationResult]) -> TrustLevel:
    if not results:
        return TrustLevel.T1
    trust_ranks = {TrustLevel.T0: 0, TrustLevel.T1: 1, TrustLevel.T2: 2, TrustLevel.T3: 3}
    return min(results, key=lambda r: trust_ranks.get(r.min_trust_level, 1)).min_trust_level


def _min_trust_spans(spans: Sequence[NormalizedSpan]) -> TrustLevel:
    if not spans:
        return TrustLevel.T1
    trust_ranks = {TrustLevel.T0: 0, TrustLevel.T1: 1, TrustLevel.T2: 2, TrustLevel.T3: 3}
    return min(spans, key=lambda s: trust_ranks.get(s.trust_level, 1)).trust_level


def _task_is_completed(task: SegmentedTask, all_spans: Sequence[NormalizedSpan]) -> bool:
    """
    Returns True only if at least one span belonging to this task has status_code == 'OK'.

    Epistemic note: If no matching spans are found in the provided span set (e.g., when spans
    are loaded from DB separately from segmentation), we return False rather than assuming
    completion. Absence of observed completion evidence is not evidence of completion.
    """
    span_set = set(task.span_ids)
    if not span_set:
        # UNKNOWN gap tasks have no span_ids — never mark as completed
        return False
    matched_any = False
    for s in all_spans:
        if s.span_id in span_set:
            matched_any = True
            if s.status_code == "OK":
                return True
    # If we found matching spans but none were OK, task is not completed
    # If we found no matching spans at all, we cannot assert completion
    return False


def _compute_token_efficiency(
    spans: Sequence[NormalizedSpan],
) -> Tuple[Optional[float], EpistemicTag, int, str]:
    """
    Computes mean token efficiency = output / (input + output) across spans
    that have complete token data.
    Returns (value, tag, sample_n, note).
    """
    valid_spans = [
        s for s in spans
        if s.has_token_data
        and s.input_tokens is not None
        and s.output_tokens is not None
        and (s.input_tokens + s.output_tokens) > 0
    ]
    if not valid_spans:
        return None, EpistemicTag.UNKNOWN, 0, "No spans with complete token data available."

    ratios = [
        s.output_tokens / (s.input_tokens + s.output_tokens)
        for s in valid_spans
    ]
    mean_te = round(sum(ratios) / len(ratios), 4)
    no_token_count = sum(1 for s in spans if not s.has_token_data)
    tag = EpistemicTag.CALCULATED if no_token_count == 0 else EpistemicTag.INFERRED
    note = (
        f"Token efficiency computed over {len(valid_spans)} spans with full token data. "
        f"{no_token_count} spans had no token data (excluded from calculation)."
    )
    return mean_te, tag, len(valid_spans), note


def _compute_hhi(
    spans: Sequence[NormalizedSpan],
) -> Tuple[float, Dict[str, float], str]:
    """
    Computes the Herfindahl-Hirschman Index (HHI) over LLM provider traffic share.
    HHI = sum(share_i^2) * 10000 where share_i is provider's fraction of total spans.

    Returns (hhi, {provider: share_pct}, note).
    """
    provider_counts: Dict[str, int] = {}
    total_provider_spans = 0
    for s in spans:
        if s.provider_name:
            provider_counts[s.provider_name] = provider_counts.get(s.provider_name, 0) + 1
            total_provider_spans += 1

    if total_provider_spans == 0:
        return 0.0, {}, "No provider-attributed spans available to compute HHI."

    shares = {p: cnt / total_provider_spans for p, cnt in provider_counts.items()}
    hhi = sum(v ** 2 for v in shares.values()) * 10_000.0

    share_pcts = {p: round(v * 100.0, 2) for p, v in shares.items()}

    if hhi >= 2500:
        concentration_label = "HIGH concentration (HHI ≥ 2500) — single-provider dependency risk"
    elif hhi >= 1500:
        concentration_label = "MODERATE concentration (HHI 1500–2499)"
    else:
        concentration_label = "LOW concentration (HHI < 1500) — diversified"

    note = (
        f"HHI = {hhi:.0f} over {len(provider_counts)} providers. {concentration_label}. "
        f"Shares: {share_pcts}"
    )
    return hhi, share_pcts, note
