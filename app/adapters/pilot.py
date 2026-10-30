"""
Ground-Truth Controlled Pilot Engine (Phase 5 — Milestone C).

Executes a controlled local agent harness across 7 deterministic runtime scenarios:
1. Autonomous Tool Completion
2. Human Intervention
3. Tool Failure and Retry
4. Complete Failure
5. Suppressed Telemetry (Dark Zone)
6. Duplicate Events
7. Provider Fallback

Calculates the False-Positive Verification Rate (FPVR) and False-Negative
Verification Rate (FNVR) by comparing pipeline verification outcomes against
empirically certified ground-truth reality.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.adapters.otlp import OtlpEvidenceAdapter
from app.analysis.metrics_engine import DiligenceMetrics, compute_diligence_metrics
from app.analysis.task_segmentation import (
    TraceSegmentationResult,
    segment_trace,
)
from app.epistemic.claims import (
    ClaimDimension,
    ClaimSchema,
    ComparisonOperator,
)
from app.epistemic.tags import (
    EpistemicTag,
    EpistemicValue,
    TrustLevel,
    VerificationVerdict,
)
from app.evidence.claim_matrix import (
    ClaimVerificationMatrixEntry,
    evaluate_single_claim,
)


class PilotScenarioType(str, Enum):
    AUTONOMOUS_TOOL_COMPLETION = "autonomous_tool_completion"
    HUMAN_INTERVENTION = "human_intervention"
    TOOL_FAILURE_AND_RETRY = "tool_failure_and_retry"
    COMPLETE_FAILURE = "complete_failure"
    SUPPRESSED_TELEMETRY = "suppressed_telemetry"
    DUPLICATE_EVENTS = "duplicate_events"
    PROVIDER_FALLBACK = "provider_fallback"


@dataclass
class GroundTruthScenario:
    """Specification of a controlled test scenario with ground-truth facts."""
    scenario_type: PilotScenarioType
    title: str
    description: str
    raw_payload: Dict[str, Any]
    claims_to_test: List[Tuple[ClaimSchema, bool]]  # (ClaimSchema, ground_truth_holds_true)
    expected_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioEvaluationResult:
    """Evaluation output for a single pilot scenario."""
    scenario_type: PilotScenarioType
    title: str
    total_traces: int
    total_spans: int
    metrics: DiligenceMetrics
    claim_verdicts: List[Dict[str, Any]]
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int


@dataclass
class PilotEvaluationReport:
    """
    Consolidated audit report across all 7 pilot scenarios.
    Computes empirical FPVR, FNVR, and epistemic verification accuracy.
    """
    total_scenarios: int
    total_traces_analyzed: int
    total_spans_analyzed: int
    total_claims_evaluated: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    false_positive_verification_rate: float
    false_negative_verification_rate: float
    verification_accuracy: float
    passed_audit: bool
    scenario_evaluations: List[ScenarioEvaluationResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "total_traces_analyzed": self.total_traces_analyzed,
            "total_spans_analyzed": self.total_spans_analyzed,
            "total_claims_evaluated": self.total_claims_evaluated,
            "confusion_matrix": {
                "true_positives": self.true_positives,
                "true_negatives": self.true_negatives,
                "false_positives": self.false_positives,
                "false_negatives": self.false_negatives,
            },
            "false_positive_verification_rate_pct": round(self.false_positive_verification_rate * 100.0, 2),
            "false_negative_verification_rate_pct": round(self.false_negative_verification_rate * 100.0, 2),
            "verification_accuracy_pct": round(self.verification_accuracy * 100.0, 2),
            "passed_audit": self.passed_audit,
            "scenarios": [
                {
                    "scenario_type": s.scenario_type.value,
                    "title": s.title,
                    "total_traces": s.total_traces,
                    "total_spans": s.total_spans,
                    "claims": s.claim_verdicts,
                }
                for s in self.scenario_evaluations
            ],
        }


# ==============================================================================
# Deterministic Scenario Payload Generators (N = 20 Traces per Scenario)
# ==============================================================================

def _generate_autonomous_scenario() -> GroundTruthScenario:
    """Scenario 1: Agent executes end-to-end with tool calls and zero human intervention."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-auto-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=400)
        t2 = t1 + timedelta(milliseconds=600)
        t3 = t2 + timedelta(milliseconds=500)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-auto-p-{i:03d}",
                "name": "agent_plan",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 120,
                    "gen_ai.usage.completion_tokens": 60,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-auto-t-{i:03d}",
                "name": "tool_execute_calculator",
                "kind": "CLIENT",
                "start_time": t1.isoformat(),
                "end_time": t2.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "tool.name": "shipping_calculator",
                    "gen_ai.tool.status": "OK"
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-auto-s-{i:03d}",
                "name": "agent_synthesize",
                "kind": "INTERNAL",
                "start_time": t2.isoformat(),
                "end_time": t3.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 150,
                    "gen_ai.usage.completion_tokens": 80,
                }
            }
        ])

    claims = [
        # Claim 1: 95% Autonomy -> True in reality (100% observed) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-AUT-01",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="95% Autonomous Customer Workflows",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=95.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
        # Claim 2: <= 50% Autonomy -> False in reality -> Expect CONTRADICTED
        (
            ClaimSchema(
                claim_id="CLM-AUT-02",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="Low Autonomy Workflow <= 50%",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=50.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
        # Claim 3: <= 5% Error Rate -> True in reality (0% observed) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-AUT-03",
                dimension=ClaimDimension.RELIABILITY,
                stated_claim_text="Tool Error Rate <= 5%",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=5.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.AUTONOMOUS_TOOL_COMPLETION,
        title="Autonomous Tool Completion Pilot",
        description="20 traces executing planning, tool invocation, and synthesis with 0 human interventions.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"autonomy": 100.0, "error_rate": 0.0},
    )


def _generate_human_intervention_scenario() -> GroundTruthScenario:
    """Scenario 2: Agent escalates to human operator via explicit HITL approval."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 11, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-hitl-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=300)
        t2 = t1 + timedelta(milliseconds=1200)
        t3 = t2 + timedelta(milliseconds=400)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-hitl-p-{i:03d}",
                "name": "agent_evaluate_risk",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 40,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-hitl-h-{i:03d}",
                "name": "human_operator_approval",
                "kind": "INTERNAL",
                "start_time": t1.isoformat(),
                "end_time": t2.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "human_in_the_loop": True,
                    "human_action_type": "manual_review_approval",
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-hitl-e-{i:03d}",
                "name": "agent_dispatch_decision",
                "kind": "INTERNAL",
                "start_time": t2.isoformat(),
                "end_time": t3.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 80,
                    "gen_ai.usage.completion_tokens": 30,
                }
            }
        ])

    claims = [
        # Claim 1: >= 90% Autonomy -> False in reality (0% autonomous) -> Expect CONTRADICTED
        (
            ClaimSchema(
                claim_id="CLM-HITL-01",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="90% Autonomous Operations",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=90.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
        # Claim 2: <= 10% Autonomy -> True in reality (0% autonomous) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-HITL-02",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="Predominantly Human Supervised Autonomy <= 10%",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=10.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.HUMAN_INTERVENTION,
        title="Human Intervention Pilot",
        description="20 traces containing explicit human approval checkpoints (100% intervention).",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"autonomy": 0.0, "hir": 100.0},
    )


def _generate_retry_scenario() -> GroundTruthScenario:
    """Scenario 3: Initial tool call fails, agent retries and completes."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-retry-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=200)
        t2 = t1 + timedelta(milliseconds=400)
        t3 = t2 + timedelta(milliseconds=350)
        t4 = t3 + timedelta(milliseconds=300)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-ret-p-{i:03d}",
                "name": "agent_plan",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 40,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-ret-fail-{i:03d}",
                "name": "tool_query_crm",
                "kind": "CLIENT",
                "start_time": t1.isoformat(),
                "end_time": t2.isoformat(),
                "status": {"code": 2, "message": "504 Gateway Timeout"},
                "attributes": {
                    "tool.name": "crm_lookup",
                    "gen_ai.tool.status": "ERROR",
                    "error": True,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-ret-ok-{i:03d}",
                "name": "tool_query_crm_retry",
                "kind": "CLIENT",
                "start_time": t2.isoformat(),
                "end_time": t3.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "tool.name": "crm_lookup",
                    "gen_ai.tool.status": "OK",
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-ret-done-{i:03d}",
                "name": "agent_synthesize",
                "kind": "INTERNAL",
                "start_time": t3.isoformat(),
                "end_time": t4.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 110,
                    "gen_ai.usage.completion_tokens": 50,
                }
            }
        ])

    claims = [
        # Claim 1: Error rate <= 5% -> False in reality (1 failure out of 4 spans = 25%) -> Expect CONTRADICTED
        (
            ClaimSchema(
                claim_id="CLM-RET-01",
                dimension=ClaimDimension.RELIABILITY,
                stated_claim_text="Zero Tool Failure Error Rate <= 5%",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=5.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
        # Claim 2: Error rate >= 15% -> True in reality (25% error rate) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-RET-02",
                dimension=ClaimDimension.RELIABILITY,
                stated_claim_text="Transient Failure Observed >= 15%",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=15.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.TOOL_FAILURE_AND_RETRY,
        title="Tool Failure & Retry Pilot",
        description="20 traces with transient tool 504 timeouts recovering on secondary retry.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"error_rate": 25.0},
    )


def _generate_complete_failure_scenario() -> GroundTruthScenario:
    """Scenario 4: Agent crashes on unrecoverable tool error."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 13, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-fail-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=200)
        t2 = t1 + timedelta(milliseconds=500)
        t3 = t2 + timedelta(milliseconds=200)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-cfl-p-{i:03d}",
                "name": "agent_plan",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 30,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-cfl-err-{i:03d}",
                "name": "tool_database_lock",
                "kind": "CLIENT",
                "start_time": t1.isoformat(),
                "end_time": t2.isoformat(),
                "status": {"code": 2, "message": "Deadlock detected"},
                "attributes": {
                    "tool.name": "db_transaction",
                    "gen_ai.tool.status": "ERROR",
                    "error": True,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-cfl-abort-{i:03d}",
                "name": "agent_abort",
                "kind": "INTERNAL",
                "start_time": t2.isoformat(),
                "end_time": t3.isoformat(),
                "status": {"code": 2, "message": "Workflow aborted"},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "error": True,
                }
            }
        ])

    claims = [
        # Claim 1: Error rate <= 10% -> False in reality (66.7% error rate) -> Expect CONTRADICTED
        (
            ClaimSchema(
                claim_id="CLM-CFL-01",
                dimension=ClaimDimension.RELIABILITY,
                stated_claim_text="Reliable System Error Rate <= 10%",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=10.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
        # Claim 2: Error rate >= 50% -> True in reality (66.7% error rate) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-CFL-02",
                dimension=ClaimDimension.RELIABILITY,
                stated_claim_text="High Failure Cascade Error Rate >= 50%",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=50.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.COMPLETE_FAILURE,
        title="Complete Failure Pilot",
        description="20 traces that terminate with unhandled error status and aborted execution.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"error_rate": 66.67},
    )


def _generate_suppressed_telemetry_scenario() -> GroundTruthScenario:
    """Scenario 5: Excessive dark zones (> 35% unknown intervals)."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 14, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-dark-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 300)
        t1 = t0 + timedelta(milliseconds=500)
        # First 90-second dark zone (gap 1 > 30s heuristic)
        t2 = t1 + timedelta(seconds=90)
        t3 = t2 + timedelta(milliseconds=500)
        # Second 90-second dark zone (gap 2 > 30s heuristic)
        t4 = t3 + timedelta(seconds=90)
        t5 = t4 + timedelta(milliseconds=500)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-dark-1-{i:03d}",
                "name": "initial_dispatch",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 50,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-dark-2-{i:03d}",
                "name": "intermediate_step",
                "kind": "INTERNAL",
                "start_time": t2.isoformat(),
                "end_time": t3.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 50,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-dark-3-{i:03d}",
                "name": "final_completion",
                "kind": "INTERNAL",
                "start_time": t4.isoformat(),
                "end_time": t5.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 120,
                    "gen_ai.usage.completion_tokens": 60,
                }
            }
        ])

    claims = [
        # Claim 1: 95% Autonomy -> Epistemic rule: >35% dark zone MUST result in INSUFFICIENT_EVIDENCE
        # Ground truth is unprovable -> False positive prevention requires rejection -> Expect INSUFFICIENT_EVIDENCE
        (
            ClaimSchema(
                claim_id="CLM-DRK-01",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="95% Autonomous Customer Service (Uninstrumented)",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=95.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.SUPPRESSED_TELEMETRY,
        title="Suppressed Telemetry Dark Zone Pilot",
        description="20 traces with two 90-second unobserved gaps creating > 35% unknown tasks.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"has_dark_zone": True},
    )


def _generate_duplicate_events_scenario() -> GroundTruthScenario:
    """Scenario 6: Transport exporter re-emits duplicate spans."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 15, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-dup-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=400)
        t2 = t1 + timedelta(milliseconds=500)

        span_a = {
            "trace_id": tid,
            "span_id": f"span-dup-a-{i:03d}",
            "name": "agent_plan",
            "kind": "INTERNAL",
            "start_time": t0.isoformat(),
            "end_time": t1.isoformat(),
            "status": {"code": 1},
            "attributes": {
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o-mini",
                "gen_ai.usage.prompt_tokens": 100,
                "gen_ai.usage.completion_tokens": 50,
            }
        }
        span_b = {
            "trace_id": tid,
            "span_id": f"span-dup-b-{i:03d}",
            "name": "agent_synthesize",
            "kind": "INTERNAL",
            "start_time": t1.isoformat(),
            "end_time": t2.isoformat(),
            "status": {"code": 1},
            "attributes": {
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o-mini",
                "gen_ai.usage.prompt_tokens": 150,
                "gen_ai.usage.completion_tokens": 75,
            }
        }

        # Intentionally inject duplicates into raw stream
        traces_spans.extend([span_a, span_a, span_b, span_b])

    claims = [
        # Claim 1: Cost per task <= $0.0050 -> True in reality with deduplication -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-DUP-01",
                dimension=ClaimDimension.UNIT_COST,
                stated_claim_text="Cheap Mini Task Cost <= $0.0050",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=0.0050,
                unit="USD",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.DUPLICATE_EVENTS,
        title="Duplicate Events Deduplication Pilot",
        description="20 traces with duplicated spans injected by simulated network retries.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"has_duplicates": True},
    )


def _generate_provider_fallback_scenario() -> GroundTruthScenario:
    """Scenario 7: Primary provider (OpenAI) fails; agent succeeds on fallback provider (Anthropic)."""
    traces_spans = []
    base_time = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)

    for i in range(20):
        tid = f"trace-fbk-{i:03d}"
        t0 = base_time + timedelta(seconds=i * 10)
        t1 = t0 + timedelta(milliseconds=250)
        t2 = t1 + timedelta(milliseconds=600)

        traces_spans.extend([
            {
                "trace_id": tid,
                "span_id": f"span-fbk-oai-{i:03d}",
                "name": "openai_rate_limited",
                "kind": "INTERNAL",
                "start_time": t0.isoformat(),
                "end_time": t1.isoformat(),
                "status": {"code": 2, "message": "429 Rate Limit Exceeded"},
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "error": True,
                }
            },
            {
                "trace_id": tid,
                "span_id": f"span-fbk-ant-{i:03d}",
                "name": "anthropic_fallback_success",
                "kind": "INTERNAL",
                "start_time": t1.isoformat(),
                "end_time": t2.isoformat(),
                "status": {"code": 1},
                "attributes": {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": "claude-3-5-sonnet",
                    "gen_ai.usage.prompt_tokens": 200,
                    "gen_ai.usage.completion_tokens": 100,
                }
            }
        ])

    claims = [
        # Claim 1: Multi-cloud diversification HHI <= 6000 -> True in reality (HHI ~5000) -> Expect VERIFIED
        (
            ClaimSchema(
                claim_id="CLM-FBK-01",
                dimension=ClaimDimension.PROVIDER_SPREAD,
                stated_claim_text="Multi-Cloud Vendor HHI Concentration <= 6000",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=6000.0,
                unit="HHI",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            True,
        ),
        # Claim 2: Monoculture vendor HHI >= 9500 -> False in reality -> Expect CONTRADICTED
        (
            ClaimSchema(
                claim_id="CLM-FBK-02",
                dimension=ClaimDimension.PROVIDER_SPREAD,
                stated_claim_text="Monoculture Cloud Dependency HHI >= 9500",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=9500.0,
                unit="HHI",
                evidence_trust_minimum=TrustLevel.T1,
            ),
            False,
        ),
    ]

    return GroundTruthScenario(
        scenario_type=PilotScenarioType.PROVIDER_FALLBACK,
        title="Provider Fallback Diversification Pilot",
        description="20 traces with OpenAI 429 rate limit triggers fallback to Anthropic Claude.",
        raw_payload={"spans": traces_spans},
        claims_to_test=claims,
        expected_attributes={"hhi": 5000.0},
    )


# ==============================================================================
# Pilot Execution & Verification Engine
# ==============================================================================

def execute_scenario(
    scenario: GroundTruthScenario,
    adapter: Optional[OtlpEvidenceAdapter] = None
) -> ScenarioEvaluationResult:
    """Executes a single scenario through the adapter, segmentation, metrics, and claim matrix."""
    import json
    adapter = adapter or OtlpEvidenceAdapter()
    raw_bytes = json.dumps(scenario.raw_payload).encode("utf-8")

    envelope, normalized_spans = adapter.parse_and_normalize(
        raw_bytes=raw_bytes,
        content_type="application/json",
        company_id=f"target-{scenario.scenario_type.value}"
    )

    # Group spans by trace_id
    trace_groups: Dict[str, List[Any]] = {}
    for s in normalized_spans:
        trace_groups.setdefault(s.trace_id, []).append(s)

    segmentation_results: List[TraceSegmentationResult] = []
    for tid, spans in trace_groups.items():
        res = segment_trace(spans, trace_id=tid)
        segmentation_results.append(res)

    metrics = compute_diligence_metrics(segmentation_results, normalized_spans)

    # Map signals to dimension names
    dim_evidence: Dict[ClaimDimension, EpistemicValue] = {
        ClaimDimension.AUTONOMY: metrics.autonomy_rate,
        ClaimDimension.UNIT_COST: metrics.cost_per_task,
        ClaimDimension.PROVIDER_SPREAD: metrics.model_concentration,
        ClaimDimension.RELIABILITY: metrics.error_rate,
    }

    claim_verdicts: List[Dict[str, Any]] = []
    tp = tn = fp = fn = 0

    for claim, ground_truth_is_true in scenario.claims_to_test:
        evidence = dim_evidence.get(claim.dimension)
        entry = evaluate_single_claim(claim, evidence, min_sample_size=15)
        verdict = entry.verification_verdict

        is_verified = verdict in (VerificationVerdict.VERIFIED, VerificationVerdict.PARTIALLY_VERIFIED)

        # Confusion Matrix Categorization
        if ground_truth_is_true and is_verified:
            tp += 1
            classification = "TP"
        elif not ground_truth_is_true and not is_verified:
            tn += 1
            classification = "TN"
        elif not ground_truth_is_true and is_verified:
            fp += 1
            classification = "FP"
        else:
            fn += 1
            classification = "FN"

        claim_verdicts.append({
            "claim_id": claim.claim_id,
            "verbatim_claim": claim.stated_claim_text,
            "dimension": claim.dimension.value,
            "target": claim.target_value,
            "ground_truth_is_true": ground_truth_is_true,
            "pipeline_verdict": verdict.value,
            "classification": classification,
            "verdict_reason": entry.verdict_reason,
        })

    return ScenarioEvaluationResult(
        scenario_type=scenario.scenario_type,
        title=scenario.title,
        total_traces=len(trace_groups),
        total_spans=len(normalized_spans),
        metrics=metrics,
        claim_verdicts=claim_verdicts,
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
    )


def run_ground_truth_pilot() -> PilotEvaluationReport:
    """
    Executes the complete Phase 5 Milestone C Ground-Truth Pilot across all 7 scenarios.
    Returns consolidated audit report with FPVR and FNVR calculations.
    """
    scenarios = [
        _generate_autonomous_scenario(),
        _generate_human_intervention_scenario(),
        _generate_retry_scenario(),
        _generate_complete_failure_scenario(),
        _generate_suppressed_telemetry_scenario(),
        _generate_duplicate_events_scenario(),
        _generate_provider_fallback_scenario(),
    ]

    adapter = OtlpEvidenceAdapter()
    evaluations: List[ScenarioEvaluationResult] = []

    total_traces = 0
    total_spans = 0
    total_claims = 0
    total_tp = 0
    total_tn = 0
    total_fp = 0
    total_fn = 0

    for sc in scenarios:
        res = execute_scenario(sc, adapter=adapter)
        evaluations.append(res)
        total_traces += res.total_traces
        total_spans += res.total_spans
        total_claims += len(res.claim_verdicts)
        total_tp += res.true_positives
        total_tn += res.true_negatives
        total_fp += res.false_positives
        total_fn += res.false_negatives

    fp_denom = total_fp + total_tn
    fpvr = (total_fp / fp_denom) if fp_denom > 0 else 0.0

    fn_denom = total_fn + total_tp
    fnvr = (total_fn / fn_denom) if fn_denom > 0 else 0.0

    accuracy = ((total_tp + total_tn) / total_claims) if total_claims > 0 else 0.0
    passed_audit = (fpvr == 0.0) and (fnvr <= 0.05)

    return PilotEvaluationReport(
        total_scenarios=len(scenarios),
        total_traces_analyzed=total_traces,
        total_spans_analyzed=total_spans,
        total_claims_evaluated=total_claims,
        true_positives=total_tp,
        true_negatives=total_tn,
        false_positives=total_fp,
        false_negatives=total_fn,
        false_positive_verification_rate=fpvr,
        false_negative_verification_rate=fnvr,
        verification_accuracy=accuracy,
        passed_audit=passed_audit,
        scenario_evaluations=evaluations,
    )
