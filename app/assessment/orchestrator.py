"""
Phase 9: Unified Assessment Orchestration Engine.

Coordinates the 10 core diligence analytical engines in dependency-respecting
order with complete error isolation, duration tracking, finding extraction,
and auditable execution persistence.
"""

import time
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import (
    Project,
    Company,
    Assessment,
    AssessmentEngineExecution,
    Finding,
    Claim,
)
from app.projects.service import get_project_by_id_or_company, log_project_activity
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.evaluation import analyze_evaluation_overhead
from app.analysis.dependency import analyze_provider_dependencies
from app.analysis.cascade import analyze_failure_cascades
from app.analysis.tool_risk import analyze_tool_execution_risk
from app.analysis.defensibility import analyze_defensibility_and_moat
from app.analysis.stress_test import simulate_stress_test_economics
from app.analysis.memo import generate_investment_committee_memo
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom
from app.evidence.engine import generate_evidence_package


ALL_ENGINE_KEYS = [
    "autonomy",
    "economics",
    "evaluation",
    "dependencies",
    "cascades",
    "tool_risk",
    "aibom",
    "evidence",
    "defensibility",
    "stress_test",
    "memo",
]


def count_evidence_data(result: Any) -> int:
    """Estimates the count of evidence data points referenced in an engine output."""
    if not isinstance(result, dict):
        return 0
    count = 0
    if "total_traces" in result:
        count += int(result["total_traces"] or 0)
    if "sample_size" in result:
        count += int(result["sample_size"] or 0)
    if "traces_count" in result:
        count += int(result["traces_count"] or 0)
    if "spans_count" in result:
        count += int(result["spans_count"] or 0)
    if "components" in result and isinstance(result["components"], list):
        count += len(result["components"])
    return max(count, 1 if result else 0)


def extract_findings_for_engine(
    engine_key: str,
    result: Dict[str, Any],
    assessment_id: str,
    project_id: str,
) -> List[Finding]:
    """
    Extracts standardized, actionable Finding records from engine result dictionary.
    """
    findings: List[Finding] = []
    if not isinstance(result, dict):
        return findings

    if engine_key == "autonomy":
        hir = result.get("human_intervention_rate", 0.0)
        if hir > 0.15:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="autonomy",
                title="Elevated Human Intervention Rate",
                description=f"Human intervention rate is {hir * 100:.1f}%, exceeding the diligence threshold of 15%. Indicates persistent reliance on operator correction.",
                severity="HIGH" if hir > 0.30 else "MEDIUM",
                confidence="Calculated",
                recommendation="Investigate high-intervention workflow stages and evaluate supervisory loop automation.",
            ))
        if result.get("untracked_interventions_detected"):
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="autonomy",
                title="Unlogged Human Overrides Detected",
                description="Latency heuristics detected gaps indicating manual out-of-band operator intervention not tagged in telemetry.",
                severity="MEDIUM",
                confidence="Heuristic",
                recommendation="Require client application to instrument human interaction spans using GenAI semantic conventions.",
            ))

    elif engine_key == "economics":
        if result.get("overall_cost_status") == "UNKNOWN" or result.get("has_unpriced_model"):
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="economics",
                title="Unpriced Model Telemetry Detected",
                description="Execution spans reference model identifiers without pinned public pricing rates. Economic viability is partially unestablished.",
                severity="HIGH",
                confidence="Calculated",
                recommendation="Supply verified enterprise contract pricing rates for unlisted models.",
            ))
        cpt = result.get("mean_cost_per_task", 0.0)
        if cpt > 1.0:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="economics",
                title="High Mean Task Inference Cost",
                description=f"Average task cost is ${cpt:.2f}, indicating risk of unit economic degradation at scale.",
                severity="MEDIUM",
                confidence="Calculated",
                recommendation="Optimize prompt templates and evaluate small language model routing for tier-1 classification steps.",
            ))

    elif engine_key == "evaluation":
        if result.get("insufficient_coverage_flag") or result.get("eval_coverage_pct", 100.0) < 20.0:
            cov = result.get("eval_coverage_pct", 0.0)
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="evaluation",
                title="Insufficient Automated Evaluation Coverage",
                description=f"Evaluation coverage is {cov:.1f}% (threshold: 20%). Quality control effectiveness cannot be reliably demonstrated from traces.",
                severity="HIGH",
                confidence="Calculated",
                recommendation="Expand automated LLM-as-a-judge or deterministic rule-based evaluation spans across all production workflows.",
            ))

    elif engine_key == "dependencies":
        hhi = result.get("hhi_index", 0)
        spof_list = result.get("potential_spof", [])
        if hhi > 2500 or len(spof_list) > 0:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="dependencies",
                title="Critical Single Point of Failure (Provider SPOF)",
                description=f"Provider concentration HHI is {hhi} (Concentrated > 2500). System has single-vendor critical dependencies on: {', '.join(spof_list) if spof_list else 'primary provider'}.",
                severity="HIGH",
                confidence="Calculated",
                recommendation="Implement multi-provider fallback routing and abstract proprietary vendor SDK primitives.",
            ))

    elif engine_key == "cascades":
        multiplier = result.get("failure_multiplier", 1.0)
        cascade_score = result.get("cascade_risk_score", 0)
        if multiplier > 2.0 or cascade_score > 40:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="cascades",
                title="High Cascade Failure Blast Radius",
                description=f"Downstream failure multiplier is {multiplier:.1f}x with cascade risk score of {cascade_score}/100. Upstream tool failures rapidly induce workflow-wide halts.",
                severity="HIGH" if multiplier > 3.0 else "MEDIUM",
                confidence="Calculated",
                recommendation="Implement circuit breakers and exponential backoff jitter on external tool integrations.",
            ))

    elif engine_key == "tool_risk":
        score = result.get("tool_risk_score", 0)
        if score > 40:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="tool_risk",
                title="Excessive Tool Execution Privileges",
                description=f"Tool safety risk score is {score}/100. Agent possesses write permissions or unconstrained execution capabilities without confirmation boundaries.",
                severity="CRITICAL" if score > 70 else "HIGH",
                confidence="Calculated",
                recommendation="Enforce human-in-the-loop approvals on write operations and restrict tool invocation scopes with fine-grained RBAC.",
            ))

    elif engine_key == "defensibility":
        def_score = result.get("defensibility_score", 0)
        if def_score < 40:
            findings.append(Finding(
                assessment_id=assessment_id,
                project_id=project_id,
                engine_key="defensibility",
                title="Low Architectural Defensibility (Wrapper Risk)",
                description=f"Defensibility score is {def_score}/100. System relies heavily on generic commodity foundation models with minimal proprietary data flywheel or tool complexity.",
                severity="MEDIUM",
                confidence="Calculated",
                recommendation="Develop proprietary domain fine-tuning and compound multi-step agentic workflows to increase moat.",
            ))

    elif engine_key == "memo":
        flags = result.get("flags", [])
        for f in flags:
            if isinstance(f, dict):
                sev = "CRITICAL" if f.get("severity") == "RED" else "HIGH" if f.get("severity") == "YELLOW" else "MEDIUM"
                findings.append(Finding(
                    assessment_id=assessment_id,
                    project_id=project_id,
                    engine_key="memo",
                    title=f.get("title", "Investment Committee Flag"),
                    description=f.get("detail", f.get("description", "Identified by committee review engine.")),
                    severity=sev,
                    confidence="Calculated",
                    recommendation=f.get("mitigation", "Review in Investment Committee diligence session."),
                ))

    return findings


class AssessmentOrchestrator:
    """
    Coordinates end-to-end execution of the 10 diligence engines.
    Guarantees strict error isolation so no single engine crash terminates the entire audit.
    """

    @classmethod
    def execute_assessment(
        cls,
        db: Session,
        project_identifier: str,
        selected_engines: Optional[List[str]] = None,
        trigger_type: str = "MANUAL",
        config: Optional[Dict[str, Any]] = None,
    ) -> Assessment:
        project = get_project_by_id_or_company(db, project_identifier)
        if not project:
            raise ValueError(f"Project '{project_identifier}' not found.")

        company_id = project.company_id
        active_engine_keys = [k for k in (selected_engines or ALL_ENGINE_KEYS) if k in ALL_ENGINE_KEYS]
        if not active_engine_keys:
            active_engine_keys = ALL_ENGINE_KEYS

        # 1. Initialize Assessment in RUNNING state
        assessment = Assessment(
            project_id=project.id,
            company_id=company_id,
            name=f"Assessment - {datetime.now(timezone.utc).strftime('%b %d, %Y %H:%M')}",
            status="RUNNING",
            trigger_type=trigger_type,
            selected_engines=active_engine_keys,
            engines_executed=active_engine_keys,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(assessment)
        db.commit()

        completed_count = 0
        failed_count = 0
        all_findings: List[Finding] = []
        engine_results: Dict[str, Any] = {}

        # 2. Sequential Execution with Error Isolation
        # Phase 1: Foundational Engines
        intervention_res: Dict[str, Any] = {}
        economics_res: Dict[str, Any] = {}
        evaluation_res: Dict[str, Any] = {}
        dependency_res: Dict[str, Any] = {}

        for key in active_engine_keys:
            start_time = time.time()
            engine_name = key.replace("_", " ").title()

            try:
                if key == "autonomy":
                    res = analyze_human_intervention(db, company_id)
                    intervention_res = res
                elif key == "economics":
                    res = analyze_unit_economics(db, company_id)
                    economics_res = res
                elif key == "evaluation":
                    res = analyze_evaluation_overhead(db, company_id)
                    evaluation_res = res
                elif key == "dependencies":
                    res = analyze_provider_dependencies(db, company_id)
                    dependency_res = res
                elif key == "cascades":
                    res = analyze_failure_cascades(db, company_id)
                elif key == "tool_risk":
                    res = analyze_tool_execution_risk(db, company_id)
                elif key == "aibom":
                    aibom_obj = generate_native_aibom(db, company_id)
                    res = aibom_obj.model_dump() if hasattr(aibom_obj, "model_dump") else aibom_obj.dict()
                elif key == "evidence":
                    ev_records = generate_evidence_package(
                        db, company_id, intervention_res, economics_res, evaluation_res, dependency_res
                    )
                    res = {
                        "evidence_records_count": len(ev_records),
                        "records": [
                            {
                                "code": e.evidence_code,
                                "type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
                                "status": e.verification_status.value if (e.verification_status and hasattr(e.verification_status, "value")) else str(e.verification_status),
                                "claim": e.claim_summary,
                                "fact": e.observed_fact,
                            }
                            for e in ev_records
                        ]
                    }
                elif key == "defensibility":
                    res = analyze_defensibility_and_moat(db, company_id)
                elif key == "stress_test":
                    res = simulate_stress_test_economics(db, company_id)
                elif key == "memo":
                    res = generate_investment_committee_memo(db, company_id)
                else:
                    raise ValueError(f"Unknown engine key: {key}")

                duration_ms = (time.time() - start_time) * 1000.0
                engine_results[key] = res

                exec_record = AssessmentEngineExecution(
                    assessment_id=assessment.id,
                    engine_key=key,
                    engine_name=engine_name,
                    status="COMPLETED",
                    duration_ms=round(duration_ms, 2),
                    result_json=res,
                    evidence_count=count_evidence_data(res),
                )
                db.add(exec_record)
                completed_count += 1

                # Extract findings
                extracted = extract_findings_for_engine(key, res, assessment.id, project.id)
                for f in extracted:
                    db.add(f)
                    all_findings.append(f)

            except Exception as e:
                db.rollback()
                duration_ms = (time.time() - start_time) * 1000.0
                err_msg = f"{type(e).__name__}: {str(e)}"
                exec_record = AssessmentEngineExecution(
                    assessment_id=assessment.id,
                    engine_key=key,
                    engine_name=engine_name,
                    status="FAILED",
                    duration_ms=round(duration_ms, 2),
                    error_details=f"{err_msg}\n{traceback.format_exc()}",
                )
                db.add(exec_record)
                failed_count += 1

            db.commit()

        # 3. Calculate Overall Scores & Verdict
        autonomy_score = None
        if "autonomy" in engine_results:
            hir = engine_results["autonomy"].get("human_intervention_rate", 0.0)
            autonomy_score = round(max(0.0, min(100.0, (1.0 - hir) * 100.0)), 1)

        # Composite risk score
        risk_components: List[float] = []
        if "tool_risk" in engine_results:
            risk_components.append(float(engine_results["tool_risk"].get("tool_risk_score", 0.0)))
        if "cascades" in engine_results:
            risk_components.append(float(engine_results["cascades"].get("cascade_risk_score", 0.0)))
        if "dependencies" in engine_results:
            hhi = float(engine_results["dependencies"].get("hhi_index", 0.0))
            risk_components.append(min(100.0, hhi / 50.0))
        if "autonomy" in engine_results:
            hir = float(engine_results["autonomy"].get("human_intervention_rate", 0.0))
            risk_components.append(hir * 100.0)

        overall_risk_score = round(sum(risk_components) / len(risk_components), 1) if risk_components else 20.0

        # Verdict
        critical_count = sum(1 for f in all_findings if f.severity == "CRITICAL")
        high_count = sum(1 for f in all_findings if f.severity == "HIGH")
        if critical_count > 0:
            summary_verdict = "HIGH_RISK"
        elif high_count > 0 or overall_risk_score > 50.0:
            summary_verdict = "CONDITIONAL"
        else:
            summary_verdict = "VERIFIED"

        # Final Status
        if completed_count == len(active_engine_keys):
            final_status = "COMPLETED"
        elif completed_count > 0:
            final_status = "PARTIALLY_COMPLETED"
        else:
            final_status = "FAILED"

        assessment.status = final_status
        assessment.autonomy_score = autonomy_score
        assessment.overall_risk_score = overall_risk_score
        assessment.summary_verdict = summary_verdict
        assessment.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(assessment)

        # Log Activity on project
        log_project_activity(
            db,
            project.id,
            activity_type="ASSESSMENT_RUN",
            description=f"Assessment finished with status {final_status}: {completed_count}/{len(active_engine_keys)} engines executed ({len(all_findings)} findings, verdict: {summary_verdict}).",
            metadata_json={
                "assessment_id": assessment.id,
                "status": final_status,
                "completed_engines": completed_count,
                "failed_engines": failed_count,
                "findings_count": len(all_findings),
            }
        )
        db.commit()
        return assessment


def list_project_assessments(db: Session, project_identifier: str) -> List[Dict[str, Any]]:
    """Lists assessment execution runs for a project in reverse chronological order."""
    project = get_project_by_id_or_company(db, project_identifier)
    if not project:
        return []

    assessments = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id)
        .order_by(desc(Assessment.created_at))
        .all()
    )

    return [
        {
            "id": a.id,
            "project_id": a.project_id,
            "status": a.status,
            "trigger_type": a.trigger_type,
            "overall_risk_score": a.overall_risk_score,
            "autonomy_score": a.autonomy_score,
            "summary_verdict": a.summary_verdict,
            "engines_executed": a.engines_executed or [],
            "engine_executions_count": len(a.engine_executions),
            "findings_count": len(a.findings),
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assessments
    ]


def get_assessment_details(db: Session, assessment_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full assessment execution details, engine records, and findings."""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        return None

    executions = (
        db.query(AssessmentEngineExecution)
        .filter(AssessmentEngineExecution.assessment_id == assessment_id)
        .order_by(AssessmentEngineExecution.executed_at)
        .all()
    )

    findings = (
        db.query(Finding)
        .filter(Finding.assessment_id == assessment_id)
        .order_by(Finding.severity)
        .all()
    )

    return {
        "id": assessment.id,
        "project_id": assessment.project_id,
        "status": assessment.status,
        "trigger_type": assessment.trigger_type,
        "overall_risk_score": assessment.overall_risk_score,
        "autonomy_score": assessment.autonomy_score,
        "summary_verdict": assessment.summary_verdict,
        "engines_executed": assessment.engines_executed or [],
        "started_at": assessment.started_at.isoformat() if assessment.started_at else None,
        "completed_at": assessment.completed_at.isoformat() if assessment.completed_at else None,
        "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
        "engine_executions": [
            {
                "id": e.id,
                "engine_key": e.engine_key,
                "engine_name": e.engine_name,
                "status": e.status,
                "duration_ms": e.duration_ms,
                "evidence_count": e.evidence_count,
                "error_details": e.error_details,
                "result_json": e.result_json,
                "executed_at": e.executed_at.isoformat() if e.executed_at else None,
            }
            for e in executions
        ],
        "findings": [
            {
                "id": f.id,
                "engine_key": f.engine_key,
                "title": f.title,
                "description": f.description,
                "severity": f.severity,
                "confidence": f.confidence,
                "recommendation": f.recommendation,
                "evidence_references": f.evidence_references,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in findings
        ]
    }


def list_project_findings(
    db: Session,
    project_identifier: str,
    severity: Optional[str] = None,
    engine_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lists findings across all assessments for a project with severity/engine filters."""
    project = get_project_by_id_or_company(db, project_identifier)
    if not project:
        return []

    query = db.query(Finding).filter(Finding.project_id == project.id)
    if severity and severity.upper() != "ALL":
        query = query.filter(Finding.severity == severity.upper())
    if engine_key and engine_key.lower() != "all":
        query = query.filter(Finding.engine_key == engine_key.lower())

    findings = query.order_by(desc(Finding.created_at)).all()
    return [
        {
            "id": f.id,
            "assessment_id": f.assessment_id,
            "project_id": f.project_id,
            "engine_key": f.engine_key,
            "title": f.title,
            "description": f.description,
            "severity": f.severity,
            "confidence": f.confidence,
            "recommendation": f.recommendation,
            "evidence_references": f.evidence_references,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in findings
    ]
