import uuid
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models import Company, Tenant, Trace, Span, CostEvent, HumanIntervention, Claim, VerificationStatus, InterventionDetectionMethod, CostStatus
from app.config import settings

def generate_synthetic_scenario(
    db: Session,
    scenario_name: str = "scenario_a",
    sample_size: int = 500,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Generates synthetic telemetry data for 10 distinct benchmark scenarios with reproducible random seeds.
    """
    random.seed(seed)
    
    tenant = Tenant(name=f"Tenant for {scenario_name}")
    db.add(tenant)
    db.flush()
    
    company = Company(
        tenant_id=tenant.id,
        name=f"AcmeAI Target ({scenario_name.upper()})",
        domain="acmeai.example.com"
    )
    db.add(company)
    db.flush()
    
    # Configure Scenario Parameters
    sc = scenario_name.lower()
    
    if sc == "scenario_b": # Fully Verified
        claimed_autonomy = "95.0% Fully Autonomous Workflows"
        claimed_cost = "$0.0010 per resolved customer task"
        target_auto_rate = 0.96
        target_cost_per_task = 0.0009
        eval_coverage_rate = 0.80
        provider_dist = [("openai", "gpt-4o-mini", 0.50), ("anthropic", "claude-3-5-sonnet", 0.50)]
        has_unpriced = False
    elif sc == "scenario_c": # Contradicted
        claimed_autonomy = "95.0% Fully Autonomous Workflows"
        claimed_cost = "$0.0010 per resolved customer task"
        target_auto_rate = 0.20
        target_cost_per_task = 0.0085
        eval_coverage_rate = 0.15
        provider_dist = [("openai", "gpt-4o", 0.90), ("anthropic", "claude-3-5-sonnet", 0.10)]
        has_unpriced = False
    elif sc == "scenario_d": # Insufficient Telemetry
        claimed_autonomy = "95.0% Fully Autonomous Workflows"
        claimed_cost = "$0.0010 per task"
        sample_size = 5
        target_auto_rate = 0.80
        target_cost_per_task = 0.0040
        eval_coverage_rate = 0.00
        provider_dist = [("openai", "gpt-4o", 1.0)]
        has_unpriced = False
    elif sc == "scenario_f": # High Provider Concentration
        claimed_autonomy = "95.0% Autonomous"
        claimed_cost = "$0.0010 per task"
        target_auto_rate = 0.75
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.40
        provider_dist = [("openai", "gpt-4o", 0.98), ("anthropic", "claude-3-5-sonnet", 0.02)]
        has_unpriced = False
    elif sc == "scenario_g": # Low Evaluation Coverage
        claimed_autonomy = "95.0% Autonomous"
        claimed_cost = "$0.0010 per task"
        target_auto_rate = 0.75
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.00 # 0% eval spans
        provider_dist = [("openai", "gpt-4o", 0.68), ("anthropic", "claude-3-5-sonnet", 0.23), ("self_hosted", "llama-3-70b", 0.09)]
        has_unpriced = False
    elif sc == "scenario_h": # Unknown Pricing
        claimed_autonomy = "95.0% Autonomous"
        claimed_cost = "$0.0010 per task"
        target_auto_rate = 0.75
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.40
        provider_dist = [("custom_vendor", "unpriced-custom-model-v1", 1.0)]
        has_unpriced = True
    elif sc == "scenario_i": # Multi-Provider Balanced
        claimed_autonomy = "95.0% Autonomous"
        claimed_cost = "$0.0010 per task"
        target_auto_rate = 0.75
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.50
        provider_dist = [("openai", "gpt-4o", 0.34), ("anthropic", "claude-3-5-sonnet", 0.33), ("self_hosted", "llama-3-70b", 0.33)]
        has_unpriced = False
    elif sc == "scenario_j": # Self-Hosted Heavy
        claimed_autonomy = "95.0% Autonomous"
        claimed_cost = "$0.0010 per task"
        target_auto_rate = 0.75
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.40
        provider_dist = [("self_hosted", "llama-3-70b", 0.90), ("openai", "gpt-4o", 0.10)]
        has_unpriced = False
    else: # Default: Scenario A (AcmeAI Benchmark)
        claimed_autonomy = "95.0% Fully Autonomous Customer Support Agent Workflows"
        claimed_cost = "Unit economics of $0.0010 per resolved customer task"
        target_auto_rate = 0.756
        target_cost_per_task = 0.0041
        eval_coverage_rate = 0.42
        provider_dist = [("openai", "gpt-4o", 0.68), ("anthropic", "claude-3-5-sonnet", 0.23), ("self_hosted", "llama-3-70b", 0.09)]
        has_unpriced = False
        
    # Add Pitch Deck Claims
    claim1 = Claim(
        company_id=company.id,
        category="autonomy",
        claim_text=claimed_autonomy,
        source="Series A Pitch Deck (Slide 8)",
        target_value="95.0%"
    )
    claim2 = Claim(
        company_id=company.id,
        category="economics",
        claim_text=claimed_cost,
        source="Series A Pitch Deck (Slide 12)",
        target_value="$0.0010"
    )
    claim3 = Claim(
        company_id=company.id,
        category="dependency",
        claim_text="Multi-cloud resilient model orchestration with zero vendor lock-in",
        source="Technical Due Diligence Q&A",
        target_value="Multi-Cloud Resilient"
    )
    db.add_all([claim1, claim2, claim3])
    db.flush()
    
    count_auto = int(sample_size * target_auto_rate)
    count_human = sample_size - count_auto
    
    base_time = datetime.utcnow() - timedelta(days=30)
    
    def pick_provider_tuple():
        r = random.random()
        cumulative = 0.0
        for prov, mod, share in provider_dist:
            cumulative += share
            if r <= cumulative:
                if prov == "openai" and mod == "gpt-4o":
                    return prov, mod, settings.OPENAI_GPT4O_PROMPT_COST, settings.OPENAI_GPT4O_COMPLETION_COST
                elif prov == "openai" and mod == "gpt-4o-mini":
                    return prov, mod, settings.OPENAI_GPT4O_MINI_PROMPT_COST, settings.OPENAI_GPT4O_MINI_COMPLETION_COST
                elif prov == "anthropic":
                    return prov, mod, settings.ANTHROPIC_CLAUDE_SONNET_PROMPT_COST, settings.ANTHROPIC_CLAUDE_SONNET_COMPLETION_COST
                elif prov == "self_hosted":
                    return prov, mod, settings.LOCAL_LLAMA3_PROMPT_COST, settings.LOCAL_LLAMA3_COMPLETION_COST
                else:
                    return prov, mod, 0.0, 0.0 # Unpriced
        return provider_dist[0][0], provider_dist[0][1], 0.0, 0.0

    trace_types = [("auto", False)] * count_auto + [("human", True)] * count_human
    random.shuffle(trace_types)
    
    for i, (cat_type, is_human) in enumerate(trace_types):
        trace_id = str(uuid.uuid4())
        trace_time = base_time + timedelta(seconds=i * (30 * 86400 / sample_size))
        
        latency_ms = max(400, random.gauss(1420, 300)) if not is_human else max(2000, random.gauss(4823, 1000))
        
        provider, model, p_rate, c_rate = pick_provider_tuple()
        
        prompt_tokens = max(100, int(random.gauss(650, 100)))
        comp_tokens = max(30, int(random.gauss(220, 40)))
        
        if p_rate > 0 or c_rate > 0:
            inf_cost = (prompt_tokens / 1000.0 * p_rate) + (comp_tokens / 1000.0 * c_rate)
            cost_st = CostStatus.MEASURED
        else:
            inf_cost = 0.0
            cost_st = CostStatus.UNKNOWN if has_unpriced else CostStatus.MEASURED
            
        has_eval = random.random() < eval_coverage_rate
        eval_cost = inf_cost * 0.25 if has_eval else 0.0
        total_trace_cost = inf_cost + eval_cost
        
        trace = Trace(
            id=trace_id,
            company_id=company.id,
            name="customer_support_workflow",
            start_time=trace_time,
            end_time=trace_time + timedelta(milliseconds=latency_ms),
            duration_ms=latency_ms,
            status_code="OK" if random.random() > 0.02 else "ERROR",
            has_human_intervention=is_human,
            total_cost=total_trace_cost,
            has_unpriced_model=(cost_st == CostStatus.UNKNOWN)
        )
        db.add(trace)
        
        # 1. Agent Span
        span_orch = Span(
            id=str(uuid.uuid4()),
            trace_id=trace_id,
            name="orchestrator_agent",
            span_kind="agent",
            start_time=trace_time,
            end_time=trace_time + timedelta(milliseconds=latency_ms),
            duration_ms=latency_ms,
            is_human_intervention=False,
            cost=0.0
        )
        db.add(span_orch)
        
        # 2. LLM Span
        span_llm_id = str(uuid.uuid4())
        span_llm = Span(
            id=span_llm_id,
            trace_id=trace_id,
            parent_span_id=span_orch.id,
            name="llm_inference",
            span_kind="llm",
            start_time=trace_time + timedelta(milliseconds=50),
            end_time=trace_time + timedelta(milliseconds=1200),
            duration_ms=1150,
            gen_ai_system=provider,
            gen_ai_model=model,
            gen_ai_prompt_tokens=prompt_tokens,
            gen_ai_completion_tokens=comp_tokens,
            is_human_intervention=False,
            cost=inf_cost,
            cost_status=cost_st
        )
        db.add(span_llm)
        
        db.add(CostEvent(
            trace_id=trace_id,
            span_id=span_llm_id,
            cost_category="inference",
            provider_name=provider,
            model_name=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            cost_usd=inf_cost,
            cost_status=cost_st
        ))
        
        # 3. Human Intervention Span if human
        if is_human:
            det_method = InterventionDetectionMethod.OBSERVED_TELEMETRY if random.random() < 0.80 else InterventionDetectionMethod.INFERRED_HEURISTIC_LATENCY
            int_type = "human_review" if det_method == InterventionDetectionMethod.OBSERVED_TELEMETRY else "human_reaction_gap"
            
            span_human = Span(
                id=str(uuid.uuid4()),
                trace_id=trace_id,
                parent_span_id=span_orch.id,
                name=int_type,
                span_kind="human" if det_method == InterventionDetectionMethod.OBSERVED_TELEMETRY else "agent",
                start_time=trace_time + timedelta(milliseconds=1300),
                end_time=trace_time + timedelta(milliseconds=latency_ms),
                duration_ms=latency_ms - 1300,
                is_human_intervention=True,
                human_action_type=int_type,
                detection_method=det_method,
                cost=0.0
            )
            db.add(span_human)
            
            db.add(HumanIntervention(
                trace_id=trace_id,
                span_id=span_human.id,
                intervention_type=int_type,
                reaction_time_seconds=(latency_ms - 1300) / 1000.0,
                detected_via=det_method,
                details=f"Intervention detected via {det_method.value}"
            ))
            
        # 4. Evaluation Span
        if has_eval:
            span_eval_id = str(uuid.uuid4())
            span_eval = Span(
                id=span_eval_id,
                trace_id=trace_id,
                parent_span_id=span_orch.id,
                name="eval_guardrail_check",
                span_kind="evaluation",
                start_time=trace_time + timedelta(milliseconds=1220),
                end_time=trace_time + timedelta(milliseconds=1400),
                duration_ms=180,
                gen_ai_system="openai",
                gen_ai_model="gpt-4o-mini",
                gen_ai_prompt_tokens=300,
                gen_ai_completion_tokens=50,
                is_human_intervention=False,
                cost=eval_cost,
                cost_status=CostStatus.MEASURED
            )
            db.add(span_eval)
            
            db.add(CostEvent(
                trace_id=trace_id,
                span_id=span_eval_id,
                cost_category="evaluation",
                provider_name="openai",
                model_name="gpt-4o-mini",
                prompt_tokens=300,
                completion_tokens=50,
                cost_usd=eval_cost,
                cost_status=CostStatus.MEASURED
            ))
            
    db.commit()
    
    return {
        "scenario": scenario_name,
        "tenant_id": tenant.id,
        "company_id": company.id,
        "total_traces": sample_size,
        "autonomous_traces": count_auto,
        "human_traces": count_human,
        "claims_created": 3
    }
