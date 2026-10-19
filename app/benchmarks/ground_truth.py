"""
Seeded-Failure Ground-Truth Benchmark Test Harness.
Generates deterministic runtime telemetry scenarios with known mathematical ground truth
to validate epistemic tagging, bounds calculation, and claim verification.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum

from app.epistemic.tags import (
    EpistemicTag, TrustLevel, VerificationVerdict,
    ConfidenceBounds, EpistemicValue, compute_autonomy_bounds
)
from app.epistemic.claims import (
    ClaimSchema, ClaimDimension, ComparisonOperator,
    verify_claim_against_evidence, ClaimVerificationResult
)

class BenchmarkType(str, Enum):
    ALPHA_SILENT_ESCALATION = "benchmark_alpha_silent_escalation"
    BETA_RETRY_CASCADE = "benchmark_beta_retry_cascade"
    GAMMA_DARK_INTERVALS = "benchmark_gamma_dark_intervals"
    DELTA_PROVIDER_CONCENTRATION = "benchmark_delta_provider_concentration"

@dataclass
class GroundTruthTask:
    task_id: str
    workflow_id: str
    status: str  # OK, FAILED, TIMEOUT
    is_autonomous: bool
    has_explicit_hitl: bool
    has_inferred_hitl: bool
    is_dark_interval: bool
    retry_count: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_ms: float
    provider: str
    model: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class GroundTruthResult:
    benchmark_type: BenchmarkType
    total_tasks: int
    autonomous_tasks: int
    explicit_hitl_tasks: int
    inferred_hitl_tasks: int
    dark_interval_tasks: int
    expected_autonomy_lower: float
    expected_autonomy_upper: float
    expected_unknown_fraction: float
    expected_cost_per_task: float
    expected_retry_multiplier: float
    expected_hhi: float
    tasks: List[GroundTruthTask]
    claims: List[ClaimSchema]

def generate_ground_truth_benchmark(
    benchmark_type: BenchmarkType,
    sample_size: int = 500,
    seed: int = 42
) -> GroundTruthResult:
    """
    Generates synthetic traces with mathematically provable ground truth.
    """
    rng = random.Random(seed)
    tasks: List[GroundTruthTask] = []

    if benchmark_type == BenchmarkType.ALPHA_SILENT_ESCALATION:
        # Known ground truth: exactly 72% autonomous, 28% explicit HITL escalation
        target_autonomous = int(sample_size * 0.72)
        total_tasks = sample_size
        autonomous_count = target_autonomous
        explicit_hitl_count = total_tasks - autonomous_count
        inferred_hitl_count = 0
        dark_interval_count = 0

        claims = [
            ClaimSchema(
                claim_id="CLM-ALPHA-01",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="95% Autonomous operations without human intervention",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=95.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1
            )
        ]

        total_cost = 0.0
        for i in range(total_tasks):
            is_auto = i < autonomous_count
            cost = rng.uniform(0.0008, 0.0012)
            total_cost += cost
            tasks.append(GroundTruthTask(
                task_id=f"alpha-task-{i:04d}",
                workflow_id="support_orchestrator",
                status="OK",
                is_autonomous=is_auto,
                has_explicit_hitl=not is_auto,
                has_inferred_hitl=False,
                is_dark_interval=False,
                retry_count=0,
                prompt_tokens=400,
                completion_tokens=120,
                cost_usd=cost,
                duration_ms=rng.uniform(800, 1500) if is_auto else rng.uniform(25000, 65000),
                provider="openai",
                model="gpt-4o-mini"
            ))

        lower_bound = (autonomous_count / float(total_tasks)) * 100.0
        upper_bound = lower_bound

        return GroundTruthResult(
            benchmark_type=benchmark_type,
            total_tasks=total_tasks,
            autonomous_tasks=autonomous_count,
            explicit_hitl_tasks=explicit_hitl_count,
            inferred_hitl_tasks=inferred_hitl_count,
            dark_interval_tasks=dark_interval_count,
            expected_autonomy_lower=round(lower_bound, 2),
            expected_autonomy_upper=round(upper_bound, 2),
            expected_unknown_fraction=0.0,
            expected_cost_per_task=round(total_cost / total_tasks, 6),
            expected_retry_multiplier=1.0,
            expected_hhi=1.0,
            tasks=tasks,
            claims=claims
        )

    elif benchmark_type == BenchmarkType.BETA_RETRY_CASCADE:
        # Known ground truth: downstream tool fails on 20% of tasks, triggering 3-5 retries
        claims = [
            ClaimSchema(
                claim_id="CLM-BETA-01",
                dimension=ClaimDimension.UNIT_COST,
                stated_claim_text="$0.0010 per resolved customer task",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=0.0010,
                unit="USD",
                evidence_trust_minimum=TrustLevel.T1
            )
        ]

        clean_costs = []
        retry_costs = []
        for i in range(sample_size):
            has_error = rng.random() < 0.20
            if not has_error:
                cost = 0.0009
                clean_costs.append(cost)
                retries = 0
            else:
                retries = rng.randint(3, 5)
                cost = 0.0009 + (retries * 0.00085)
                retry_costs.append(cost)

            tasks.append(GroundTruthTask(
                task_id=f"beta-task-{i:04d}",
                workflow_id="order_resolver",
                status="OK",
                is_autonomous=True,
                has_explicit_hitl=False,
                has_inferred_hitl=False,
                is_dark_interval=False,
                retry_count=retries,
                prompt_tokens=400 + (retries * 350),
                completion_tokens=100 + (retries * 90),
                cost_usd=cost,
                duration_ms=1200 + (retries * 1800),
                provider="openai",
                model="gpt-4o"
            ))

        avg_clean = sum(clean_costs) / len(clean_costs)
        avg_retry = sum(retry_costs) / len(retry_costs)
        total_avg_cost = sum(t.cost_usd for t in tasks) / len(tasks)
        retry_mult = avg_retry / avg_clean

        return GroundTruthResult(
            benchmark_type=benchmark_type,
            total_tasks=sample_size,
            autonomous_tasks=sample_size,
            explicit_hitl_tasks=0,
            inferred_hitl_tasks=0,
            dark_interval_tasks=0,
            expected_autonomy_lower=100.0,
            expected_autonomy_upper=100.0,
            expected_unknown_fraction=0.0,
            expected_cost_per_task=round(total_avg_cost, 6),
            expected_retry_multiplier=round(retry_mult, 2),
            expected_hhi=1.0,
            tasks=tasks,
            claims=claims
        )

    elif benchmark_type == BenchmarkType.GAMMA_DARK_INTERVALS:
        # Known ground truth: 75% autonomous observed, 10% explicit HITL, 15% dark uninstrumented intervals
        dark_count = int(sample_size * 0.15)
        hitl_count = int(sample_size * 0.10)
        auto_count = sample_size - dark_count - hitl_count

        claims = [
            ClaimSchema(
                claim_id="CLM-GAMMA-01",
                dimension=ClaimDimension.AUTONOMY,
                stated_claim_text="90% Autonomous ticket completion",
                target_operator=ComparisonOperator.GREATER_EQUAL,
                target_value=90.0,
                unit="%",
                evidence_trust_minimum=TrustLevel.T1
            )
        ]

        for i in range(sample_size):
            if i < auto_count:
                is_auto = True
                is_hitl = False
                is_dark = False
            elif i < auto_count + hitl_count:
                is_auto = False
                is_hitl = True
                is_dark = False
            else:
                is_auto = False
                is_hitl = False
                is_dark = True

            tasks.append(GroundTruthTask(
                task_id=f"gamma-task-{i:04d}",
                workflow_id="data_pipeline",
                status="OK" if not is_dark else "INCOMPLETE_DARK_INTERVAL",
                is_autonomous=is_auto,
                has_explicit_hitl=is_hitl,
                has_inferred_hitl=False,
                is_dark_interval=is_dark,
                retry_count=0,
                prompt_tokens=300 if not is_dark else 0,
                completion_tokens=80 if not is_dark else 0,
                cost_usd=0.0006 if not is_dark else 0.0,
                duration_ms=1000 if not is_dark else 15000,
                provider="anthropic" if not is_dark else "unknown",
                model="claude-3-5-sonnet" if not is_dark else "unknown"
            ))

        bounds, unknown_frac = compute_autonomy_bounds(auto_count, hitl_count, 0, dark_count)

        return GroundTruthResult(
            benchmark_type=benchmark_type,
            total_tasks=sample_size,
            autonomous_tasks=auto_count,
            explicit_hitl_tasks=hitl_count,
            inferred_hitl_tasks=0,
            dark_interval_tasks=dark_count,
            expected_autonomy_lower=round(bounds.lower, 2),
            expected_autonomy_upper=round(bounds.upper, 2),
            expected_unknown_fraction=round(unknown_frac, 4),
            expected_cost_per_task=0.00051,
            expected_retry_multiplier=1.0,
            expected_hhi=1.0,
            tasks=tasks,
            claims=claims
        )

    elif benchmark_type == BenchmarkType.DELTA_PROVIDER_CONCENTRATION:
        # Known ground truth: 90% primary provider (OpenAI), 10% secondary (Anthropic), 0 failover observed
        claims = [
            ClaimSchema(
                claim_id="CLM-DELTA-01",
                dimension=ClaimDimension.PROVIDER_SPREAD,
                stated_claim_text="Multi-cloud resilient provider architecture with automated failover",
                target_operator=ComparisonOperator.LESS_EQUAL,
                target_value=0.50, # HHI <= 0.50 indicates balanced
                unit="HHI",
                evidence_trust_minimum=TrustLevel.T1
            )
        ]

        openai_count = int(sample_size * 0.90)
        for i in range(sample_size):
            prov = "openai" if i < openai_count else "anthropic"
            model = "gpt-4o" if prov == "openai" else "claude-3-5-sonnet"
            cost = 0.0020 if prov == "openai" else 0.0020

            tasks.append(GroundTruthTask(
                task_id=f"delta-task-{i:04d}",
                workflow_id="triage_agent",
                status="OK",
                is_autonomous=True,
                has_explicit_hitl=False,
                has_inferred_hitl=False,
                is_dark_interval=False,
                retry_count=0,
                prompt_tokens=600,
                completion_tokens=200,
                cost_usd=cost,
                duration_ms=1800,
                provider=prov,
                model=model
            ))

        s1 = 0.90
        s2 = 0.10
        hhi = (s1**2) + (s2**2) # 0.81 + 0.01 = 0.82

        return GroundTruthResult(
            benchmark_type=benchmark_type,
            total_tasks=sample_size,
            autonomous_tasks=sample_size,
            explicit_hitl_tasks=0,
            inferred_hitl_tasks=0,
            dark_interval_tasks=0,
            expected_autonomy_lower=100.0,
            expected_autonomy_upper=100.0,
            expected_unknown_fraction=0.0,
            expected_cost_per_task=0.0020,
            expected_retry_multiplier=1.0,
            expected_hhi=round(hhi, 4),
            tasks=tasks,
            claims=claims
        )

    raise ValueError(f"Unknown benchmark type: {benchmark_type}")
