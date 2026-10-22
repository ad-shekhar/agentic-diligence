"""
Canonical Diligence Report Engine (Phase 4).

Generates schema-validated canonical JSON and audit-grade Markdown diligence reports
from the Claim Verification Matrix, deterministic metrics, and evidence bundles.
Conforms strictly to docs/phase-4/data-contracts.md (v1.0 schema).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import json

from app.evidence.claim_matrix import ClaimVerificationMatrix, ClaimVerificationMatrixEntry
from app.reporting.manifest import canonicalize_json, compute_canonical_sha256


class DiligenceVerdict(str, Enum):
    PASS = "PASS"
    PASS_WITH_CONDITIONS = "PASS_WITH_CONDITIONS"
    CAUTION = "CAUTION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EpistemicConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"


def build_canonical_diligence_report(
    company_id: str,
    company_name: str,
    scope: Dict[str, Any],
    signals: Dict[str, Any],
    claim_matrix: ClaimVerificationMatrix,
    trace_payload_digests: List[str],
    manifest_sha256: Optional[str] = None,
    is_synthetic: bool = False,
    known_limitations: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Constructs the canonical structured diligence report model.
    Conforms to the CanonicalDiligenceReport schema in docs/phase-4/data-contracts.md.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    report_id = f"REP-{company_id.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    # Analyze claims to derive executive verdict and headline findings
    entries = claim_matrix.entries
    verified_count = sum(1 for e in entries if e.verification_verdict.value == "VERIFIED")
    partially_count = sum(1 for e in entries if e.verification_verdict.value == "PARTIALLY_VERIFIED")
    contradicted_count = sum(1 for e in entries if e.verification_verdict.value == "CONTRADICTED")
    insufficient_count = sum(1 for e in entries if e.verification_verdict.value == "INSUFFICIENT_EVIDENCE")

    headline_findings: List[str] = []
    
    # Check overall verdict
    if contradicted_count > 0:
        overall_verdict = DiligenceVerdict.CAUTION.value
        headline_findings.append(f"{contradicted_count} vendor claim(s) directly contradicted by observed runtime evidence.")
    elif insufficient_count > len(entries) / 2 and len(entries) > 0:
        overall_verdict = DiligenceVerdict.INSUFFICIENT_EVIDENCE.value
        headline_findings.append(f"Majority of claims ({insufficient_count}/{len(entries)}) lack sufficient telemetry coverage to verify.")
    elif verified_count > 0 and contradicted_count == 0:
        overall_verdict = DiligenceVerdict.PASS_WITH_CONDITIONS.value
        headline_findings.append(f"{verified_count} claim(s) verified against telemetry within pre-declared tolerance.")
    else:
        overall_verdict = DiligenceVerdict.PASS_WITH_CONDITIONS.value
        headline_findings.append("Telemetry evaluated with conditional findings across primary signals.")

    # Check signal headlines (support direct or nested signals dictionary)
    sig_map = signals.get("signals", signals) if isinstance(signals, dict) else {}
    auto_sig = sig_map.get("autonomy_rate") or sig_map.get("autonomy")
    if auto_sig and isinstance(auto_sig, dict):
        bounds = auto_sig.get("bounds", {}) or {}
        headline_findings.append(
            f"Observed autonomy bounded at [{bounds.get('lower', 0):.1f}%, {bounds.get('upper', 0):.1f}%] "
            f"with unknown fraction {auto_sig.get('unknown_fraction', 0)*100:.1f}%."
        )

    conc_sig = sig_map.get("model_concentration") or sig_map.get("provider_concentration")
    if conc_sig and isinstance(conc_sig, dict):
        hhi_val = conc_sig.get("value")
        if hhi_val is not None:
            headline_findings.append(
                f"Provider concentration HHI measured at {hhi_val:.0f}/10000 across active LLM backends."
            )

    # Determine confidence level based on trust summary and sample size
    trust_summary = scope.get("evidence_trust_summary", {})
    t0_count = trust_summary.get("T0", 0)
    t1_count = trust_summary.get("T1", 0)
    t2_count = trust_summary.get("T2", 0)
    t3_count = trust_summary.get("T3", 0)
    
    total_spans = scope.get("total_spans_analyzed", 0)
    if total_spans == 0 or (t0_count > 0 and t1_count == 0 and t2_count == 0 and t3_count == 0):
        confidence = EpistemicConfidence.UNVERIFIED.value
    elif (t2_count + t3_count) > total_spans / 2:
        confidence = EpistemicConfidence.HIGH.value
    elif t1_count > 0 and scope.get("unobserved_intervals_count", 0) == 0:
        confidence = EpistemicConfidence.HIGH.value
    elif scope.get("unobserved_intervals_count", 0) > 0:
        confidence = EpistemicConfidence.MEDIUM.value
    else:
        confidence = EpistemicConfidence.MEDIUM.value

    # Manifest hash placeholder if None
    m_hash = manifest_sha256 or "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    return {
        "schema_version": "1.0.0",
        "report_id": report_id,
        "generated_at_utc": timestamp,
        "is_synthetic": is_synthetic,
        "subject_company": {
            "company_id": company_id,
            "company_name": company_name
        },
        "evaluation_scope": {
            "total_traces_analyzed": scope.get("total_traces_analyzed", 0),
            "total_spans_analyzed": scope.get("total_spans_analyzed", 0),
            "total_tasks_segmented": scope.get("total_tasks_segmented", 0),
            "evidence_trust_summary": trust_summary,
            "unobserved_intervals_count": scope.get("unobserved_intervals_count", 0)
        },
        "executive_summary": {
            "overall_verdict": overall_verdict,
            "headline_findings": headline_findings,
            "epistemic_confidence_level": confidence
        },
        "signals": signals,
        "claim_matrix": [e.to_dict() for e in entries],
        "provenance_trail": {
            "manifest_sha256": m_hash,
            "trace_payload_digests": trace_payload_digests
        },
        "known_limitations_and_assumptions": list(known_limitations or [
            "All telemetry evaluated under local execution context.",
            "L-001 Security Notice: Tenant authentication is NOT enabled. Not ready for shared or production deployment."
        ])
    }


def render_markdown_diligence_report(report_json: Dict[str, Any]) -> str:
    """
    Renders an audit-grade Markdown diligence report directly from the canonical report model.
    """
    lines: List[str] = []
    
    # 1. Header & Synthetic Labeling
    company = report_json.get("subject_company", {})
    comp_name = company.get("company_name", "Target AI Company")
    comp_id = company.get("company_id", "unknown")
    rep_id = report_json.get("report_id", "REP-UNKNOWN")
    gen_time = report_json.get("generated_at_utc", "")
    is_synth = report_json.get("is_synthetic", False)

    lines.append(f"# Technical Due Diligence Report: {comp_name}")
    lines.append("")
    lines.append(f"**Report ID:** `{rep_id}`  ")
    lines.append(f"**Company ID:** `{comp_id}`  ")
    lines.append(f"**Generated:** {gen_time} UTC  ")
    lines.append(f"**Schema Version:** `{report_json.get('schema_version', '1.0.0')}`  ")
    lines.append("")

    if is_synth:
        lines.append("> [!WARNING]")
        lines.append("> **SYNTHETIC DATASET — BENCHMARK DEMONSTRATION**")
        lines.append("> This report was compiled from synthetic or seeded benchmark test fixtures. It does NOT represent empirical evidence from a live production runtime.")
        lines.append("")

    # Security Alert (L-001)
    lines.append("> [!CAUTION]")
    lines.append("> **PRE-PRODUCTION SECURITY STATUS — NOT READY FOR SHARED DEPLOYMENT**")
    lines.append("> Multi-tenant authentication and token authorization (Finding L-001) are not currently enforced. This system is approved for isolated single-tenant testbed analysis only.")
    lines.append("")

    # 2. Executive Summary
    exec_sum = report_json.get("executive_summary", {})
    verdict = exec_sum.get("overall_verdict", "INSUFFICIENT_EVIDENCE")
    confidence = exec_sum.get("epistemic_confidence_level", "UNVERIFIED")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Overall Diligence Verdict:** **`{verdict}`**  ")
    lines.append(f"**Epistemic Confidence Level:** `{confidence}`  ")
    lines.append("")
    lines.append("### Key Findings")
    for h in exec_sum.get("headline_findings", []):
        lines.append(f"- {h}")
    lines.append("")

    # 3. Evaluation Scope
    scope = report_json.get("evaluation_scope", {})
    lines.append("## Evaluation Scope & Evidence Trust Ladder")
    lines.append("")
    lines.append(f"- **Total Traces Analyzed:** {scope.get('total_traces_analyzed', 0)}")
    lines.append(f"- **Total Spans Ingested:** {scope.get('total_spans_analyzed', 0)}")
    lines.append(f"- **Segmented Tasks:** {scope.get('total_tasks_segmented', 0)}")
    lines.append(f"- **Unobserved Interval Dark Zones:** {scope.get('unobserved_intervals_count', 0)}")
    
    trust_sum = scope.get("evidence_trust_summary", {})
    lines.append(f"- **Trust Ladder Distribution:** T0 (Self-Report): {trust_sum.get('T0', 0)} | T1 (In-Process SDK): {trust_sum.get('T1', 0)} | T2 (Proxy): {trust_sum.get('T2', 0)} | T3 (Billing): {trust_sum.get('T3', 0)}")
    lines.append("")

    # 4. Claim Verification Matrix
    claims = report_json.get("claim_matrix", [])
    lines.append("## Claim Verification Matrix")
    lines.append("")
    lines.append("| Claim ID | Stated Claim Text | Target | Observed Bounds | Trust | Verdict | Evidence Reason |")
    lines.append("|---|---|---|---|---|---|---|")
    
    for c in claims:
        cid = c.get("claim_id", "")
        txt = c.get("verbatim_claim_text", "")
        op = c.get("target_operator", "")
        target = c.get("target_threshold", "")
        unit = c.get("target_units", "")
        
        obs_obj = c.get("observed_epistemic_value", {})
        bounds = obs_obj.get("bounds")
        tag = obs_obj.get("tag", "")
        if bounds:
            obs_str = f"[{bounds.get('lower', 0):.2f}, {bounds.get('upper', 0):.2f}] {unit} {tag}"
        elif obs_obj.get("value") is not None:
            obs_str = f"{obs_obj.get('value'):.2f} {unit} {tag}"
        else:
            obs_str = f"N/A {tag}"

        trust = obs_obj.get("trust_level", "T0")
        c_verdict = c.get("verification_verdict", "UNVERIFIED")
        reason = c.get("verdict_reason", "").replace("|", "/")
        
        lines.append(f"| `{cid}` | {txt} | {op} {target} {unit} | {obs_str} | `{trust}` | **{c_verdict}** | {reason} |")
    lines.append("")

    signals = report_json.get("signals", {})
    sig_items = signals.get("signals", signals) if isinstance(signals, dict) else {}
    lines.append("## Deterministic Signals Deep-Dive")
    lines.append("")
    lines.append("| Signal Dimension | Metric Name | Point Value | Uncertainty Bounds | Epistemic Tag | Trust | Notes / Disclosures |")
    lines.append("|---|---|---|---|---|---|---|")

    for dim_name, sig in sig_items.items():
        if not isinstance(sig, dict) or dim_name in ("computation_notes",):
            continue
        val = sig.get("value")
        val_str = f"{val:.4f}" if isinstance(val, (int, float)) else str(val or "None")
        bounds = sig.get("bounds", {})
        if bounds and isinstance(bounds, dict):
            b_str = f"[{bounds.get('lower', 0):.2f}, {bounds.get('upper', 0):.2f}]"
        else:
            b_str = "None"
        tag = sig.get("tag", "[UNKNOWN]")
        trust = sig.get("trust_level", "T1")
        notes = (sig.get("notes") or "").replace("|", "/")
        lines.append(f"| {dim_name} | {sig.get('metric_name', dim_name)} | {val_str} | {b_str} | `{tag}` | `{trust}` | {notes} |")
    lines.append("")

    # 6. Provenance & Cryptographic Traceability
    prov = report_json.get("provenance_trail", {})
    lines.append("## Provenance & Cryptographic Traceability")
    lines.append("")
    lines.append(f"- **Artifact Manifest Digest (SHA-256):** `{prov.get('manifest_sha256', '')}`")
    lines.append(f"- **Telemetry Ingestion Payloads (`payload_sha256`):** {len(prov.get('trace_payload_digests', []))} payloads anchored")
    for d in prov.get("trace_payload_digests", [])[:5]:
        lines.append(f"  - `{d}`")
    if len(prov.get("trace_payload_digests", [])) > 5:
        lines.append(f"  - ... and {len(prov.get('trace_payload_digests', [])) - 5} more digests")
    lines.append("")

    # 7. Limitations & Epistemic Boundaries
    lines.append("## Known Limitations & Evaluation Boundaries")
    lines.append("")
    for lim in report_json.get("known_limitations_and_assumptions", []):
        lines.append(f"- {lim}")
    lines.append("")

    return "\n".join(lines)
