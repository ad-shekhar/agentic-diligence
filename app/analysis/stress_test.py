from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.analysis.economics import analyze_unit_economics
from app.analysis.intervention import analyze_human_intervention
from app.analysis.cascade import analyze_failure_cascades

def simulate_stress_test_economics(
    db: Session,
    company_id: str,
    volume_multiplier: float = 1.0,
    provider_price_shock_pct: float = 0.0,
    human_hourly_wage_usd: float = 28.0,
    target_customer_price_per_task_usd: float = 0.05,
    baseline_monthly_tasks: int = 50000
) -> Dict[str, Any]:
    """
    Simulates operational stress testing, token inflation, provider price shocks,
    and fully-loaded human-in-the-loop labor costs for venture/PE technical diligence.
    """
    econ = analyze_unit_economics(db, company_id)
    interv = analyze_human_intervention(db, company_id)
    casc = analyze_failure_cascades(db, company_id)
    
    # 1. Base telemetry parameters
    base_llm_cost_per_task = econ.get("telemetry_attributable_cost_per_task_usd", 0.0)
    hir_pct = interv.get("human_intervention_rate_pct", 0.0)
    hir_ratio = hir_pct / 100.0
    
    # Estimate average human review duration in minutes (from P95 latency or minimum 3.0 min standard)
    p95_sec = econ.get("latency_ms", {}).get("p95", 3000) / 1000.0
    # Operational review heuristic: human review typically takes 2.5 to 5 minutes per intervention
    avg_review_minutes = max(2.5, min(10.0, p95_sec / 30.0 + 2.0))
    
    # 2. Fully-Loaded Baseline Economics
    base_labor_cost_per_task = hir_ratio * (avg_review_minutes / 60.0) * human_hourly_wage_usd
    base_fully_loaded_cost_per_task = base_llm_cost_per_task + base_labor_cost_per_task
    
    base_tasks_month = int(baseline_monthly_tasks)
    base_monthly_llm_spend = base_llm_cost_per_task * base_tasks_month
    base_monthly_labor_spend = base_labor_cost_per_task * base_tasks_month
    base_monthly_total_cost = base_monthly_llm_spend + base_monthly_labor_spend
    base_monthly_revenue = target_customer_price_per_task_usd * base_tasks_month
    base_gross_margin_pct = (
        round(((base_monthly_revenue - base_monthly_total_cost) / base_monthly_revenue) * 100.0, 1)
        if base_monthly_revenue > 0 else 0.0
    )
    
    # 3. Stressed Economics Calculation
    price_shock_factor = 1.0 + (provider_price_shock_pct / 100.0)
    stressed_llm_cost_per_task = base_llm_cost_per_task * price_shock_factor
    
    # Under volume stress, human review efficiency might degrade slightly (+10% time per review at high scale)
    stressed_review_minutes = avg_review_minutes * (1.10 if volume_multiplier >= 5.0 else 1.0)
    stressed_labor_cost_per_task = hir_ratio * (stressed_review_minutes / 60.0) * human_hourly_wage_usd
    stressed_fully_loaded_cost_per_task = stressed_llm_cost_per_task + stressed_labor_cost_per_task
    
    stressed_tasks_month = int(base_tasks_month * volume_multiplier)
    stressed_monthly_llm_spend = stressed_llm_cost_per_task * stressed_tasks_month
    stressed_monthly_labor_spend = stressed_labor_cost_per_task * stressed_tasks_month
    stressed_monthly_total_cost = stressed_monthly_llm_spend + stressed_monthly_labor_spend
    stressed_monthly_revenue = target_customer_price_per_task_usd * stressed_tasks_month
    
    stressed_gross_margin_pct = (
        round(((stressed_monthly_revenue - stressed_monthly_total_cost) / stressed_monthly_revenue) * 100.0, 1)
        if stressed_monthly_revenue > 0 else 0.0
    )
    
    # Breakeven & Target Pricing Analysis
    # Target 70% software gross margin price: cost / (1 - 0.70)
    price_for_70pct_margin = stressed_fully_loaded_cost_per_task / 0.30
    price_for_80pct_margin = stressed_fully_loaded_cost_per_task / 0.20
    
    # 4. Sensitivity Grids
    # Grid 1: Price Shock vs Volume Multiplier
    shock_levels = [-20.0, 0.0, 25.0, 50.0]
    volume_levels = [1.0, 3.0, 10.0]
    volume_shock_grid = []
    
    for vol in volume_levels:
        row = {"volume_multiple": f"{vol}x", "monthly_tasks": int(base_tasks_month * vol)}
        for shock in shock_levels:
            shock_llm = base_llm_cost_per_task * (1.0 + shock / 100.0)
            tot_cost = shock_llm + base_labor_cost_per_task
            rev = target_customer_price_per_task_usd
            margin = round(((rev - tot_cost) / rev) * 100.0, 1) if rev > 0 else 0.0
            row[f"shock_{int(shock)}pct"] = margin
        volume_shock_grid.append(row)
        
    # Grid 2: Human Hourly Wage vs HIR Sensitivity
    wage_levels = [20.0, 30.0, 45.0]
    hir_variations = [max(0.0, hir_pct - 10.0), hir_pct, min(100.0, hir_pct + 15.0)]
    labor_sensitivity_grid = []
    
    for h_var in hir_variations:
        row = {"hir_rate_pct": f"{h_var:.1f}%"}
        for wage in wage_levels:
            l_cost = (h_var / 100.0) * (avg_review_minutes / 60.0) * wage
            full_c = base_llm_cost_per_task + l_cost
            rev = target_customer_price_per_task_usd
            m = round(((rev - full_c) / rev) * 100.0, 1) if rev > 0 else 0.0
            row[f"wage_${int(wage)}"] = m
        labor_sensitivity_grid.append(row)
        
    # 5. Margin Vulnerability Verdict
    if stressed_gross_margin_pct < 0.0:
        verdict = "NEGATIVE_UNIT_MARGIN_HAZARD"
        verdict_text = (
            f"CRITICAL RISK: Negative gross margin ({stressed_gross_margin_pct}%). "
            f"Human operational review labor (${stressed_labor_cost_per_task:.4f}/task) exceeds target pricing (${target_customer_price_per_task_usd:.4f}). "
            "Company loses money on every incremental resolved task without immediate pricing adjustment or autonomy gains."
        )
    elif stressed_gross_margin_pct < 50.0:
        verdict = "MARGIN_COMPRESSION_RISK"
        verdict_text = (
            f"ELEVATED RISK: Stressed gross margin is {stressed_gross_margin_pct}%, well below standard 70-80% SaaS benchmarks. "
            "High human intervention rate or API provider price increases will severely impair software multiples."
        )
    elif stressed_gross_margin_pct < 75.0:
        verdict = "SUSTAINABLE_SOFTWARE_MARGINS"
        verdict_text = (
            f"HEALTHY: Stressed gross margin is {stressed_gross_margin_pct}%. Unit economics remain resilient under tested "
            "token price and volume stress, supporting viable software margins."
        )
    else:
        verdict = "HIGH_MARGIN_EXPANSION_CAPABLE"
        verdict_text = (
            f"EXEMPLARY: Stressed gross margin is {stressed_gross_margin_pct}%. Highly autonomous execution produces strong "
            "operating leverage and robust insulation against foundation model price increases."
        )
        
    return {
        "parameters": {
            "volume_multiplier": volume_multiplier,
            "provider_price_shock_pct": provider_price_shock_pct,
            "human_hourly_wage_usd": human_hourly_wage_usd,
            "target_customer_price_per_task_usd": target_customer_price_per_task_usd,
            "baseline_monthly_tasks": base_tasks_month,
            "avg_review_duration_minutes": round(avg_review_minutes, 1)
        },
        "baseline_economics": {
            "llm_cost_per_task_usd": round(base_llm_cost_per_task, 4),
            "human_labor_cost_per_task_usd": round(base_labor_cost_per_task, 4),
            "fully_loaded_cost_per_task_usd": round(base_fully_loaded_cost_per_task, 4),
            "monthly_tasks": base_tasks_month,
            "monthly_llm_spend_usd": round(base_monthly_llm_spend, 2),
            "monthly_labor_spend_usd": round(base_monthly_labor_spend, 2),
            "monthly_total_cost_usd": round(base_monthly_total_cost, 2),
            "monthly_revenue_usd": round(base_monthly_revenue, 2),
            "gross_margin_pct": base_gross_margin_pct,
            "labor_share_of_total_cost_pct": round((base_labor_cost_per_task / max(0.0001, base_fully_loaded_cost_per_task)) * 100.0, 1)
        },
        "stressed_economics": {
            "llm_cost_per_task_usd": round(stressed_llm_cost_per_task, 4),
            "human_labor_cost_per_task_usd": round(stressed_labor_cost_per_task, 4),
            "fully_loaded_cost_per_task_usd": round(stressed_fully_loaded_cost_per_task, 4),
            "monthly_tasks": stressed_tasks_month,
            "monthly_llm_spend_usd": round(stressed_monthly_llm_spend, 2),
            "monthly_labor_spend_usd": round(stressed_monthly_labor_spend, 2),
            "monthly_total_cost_usd": round(stressed_monthly_total_cost, 2),
            "monthly_revenue_usd": round(stressed_monthly_revenue, 2),
            "gross_margin_pct": stressed_gross_margin_pct,
            "price_for_70pct_margin_usd": round(price_for_70pct_margin, 4),
            "price_for_80pct_margin_usd": round(price_for_80pct_margin, 4)
        },
        "sensitivity_grids": {
            "volume_and_price_shock_margins": volume_shock_grid,
            "hir_and_wage_margins": labor_sensitivity_grid
        },
        "vulnerability_verdict": {
            "status": verdict,
            "statement": verdict_text
        }
    }
