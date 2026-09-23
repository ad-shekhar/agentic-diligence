import os
from typing import Dict, Any, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_pdf_report(report_data: Dict[str, Any], output_path: str) -> str:
    """
    Generates an evidence-backed PDF Due-Diligence Report using ReportLab,
    featuring AIBOM summary, PSPOF analysis, cascade economic impact, and chain-of-custody seal.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0284C7'),
        spaceAfter=10
    )
    
    heading2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=5
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155'),
        spaceAfter=5
    )
    
    limitation_style = ParagraphStyle(
        'LimitationText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#475569')
    )
    
    seal_style = ParagraphStyle(
        'SealText',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#0F766E')
    )
    
    story = []
    
    company_name = report_data.get("company", {}).get("name", "Target AI Company")
    
    # Header
    story.append(Paragraph("AGENTIC DILIGENCE | Standardized AI Technical Due Diligence Package", subtitle_style))
    story.append(Paragraph(f"Target Assessment: {company_name}", title_style))
    story.append(Paragraph(
        f"Observation Window: <b>{report_data.get('observation_window', 'Last 30 Days')}</b> | "
        f"Telemetry Sample: <b>{report_data['interventions']['total_traces']} Traces</b> | "
        f"Pricing Version: <b>{report_data['report_metadata']['pricing_version']}</b>",
        body_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284C7'), spaceAfter=8))
    
    # 1. Executive Claim Verification Summary
    story.append(Paragraph("1. Pitch Deck Claim Verification Audit", heading2_style))
    
    claim_table_data = [
        [
            Paragraph("<b>Category</b>", body_style),
            Paragraph("<b>Stated Claim</b>", body_style),
            Paragraph("<b>Observed Telemetry Fact</b>", body_style),
            Paragraph("<b>Status</b>", body_style),
            Paragraph("<b>Conf.</b>", body_style)
        ]
    ]
    
    for c in report_data.get("claims", []):
        status_str = c.get("verification_status", "INSUFFICIENT_EVIDENCE")
        if status_str == "VERIFIED":
            status_html = "<font color='#16A34A'><b>VERIFIED</b></font>"
        elif status_str == "PARTIALLY_VERIFIED":
            status_html = "<font color='#D97706'><b>PARTIAL</b></font>"
        elif status_str == "CONTRADICTED":
            status_html = "<font color='#DC2626'><b>CONTRADICTED</b></font>"
        else:
            status_html = "<font color='#64748B'><b>UNVERIFIED</b></font>"
            
        claim_table_data.append([
            Paragraph(c.get("category", "").title(), body_style),
            Paragraph(c.get("claim_text", ""), body_style),
            Paragraph(f"{c.get('observed_value', '')}<br/><font color='#64748B'>{c.get('verification_reason', '')}</font>", body_style),
            Paragraph(status_html, body_style),
            Paragraph(c.get("confidence", "High"), body_style)
        ])
        
    t_claims = Table(claim_table_data, colWidths=[0.9*inch, 1.8*inch, 2.8*inch, 1.0*inch, 0.6*inch])
    t_claims.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_claims)
    story.append(Spacer(1, 8))
    
    # 2. Autonomy Profile & Human Intervention Rate (HIR)
    story.append(Paragraph("2. Autonomy Profile & Human Intervention Rate (HIR)", heading2_style))
    int_res = report_data["interventions"]
    story.append(Paragraph(
        f"Analyzed <b>{int_res['total_traces']}</b> workflow traces. "
        f"Autonomous completion rate is <b>{int_res['autonomous_rate_pct']}%</b> ({int_res['autonomous_traces']} traces). "
        f"Human Intervention Rate (HIR) is <b>{int_res['human_intervention_rate_pct']}%</b> ({int_res['human_traces']} traces). "
        f"<i>Detection Breakdown:</i> {int_res['explicitly_observed_human_traces']} explicitly observed in telemetry spans, "
        f"{int_res['inferred_heuristic_human_traces']} inferred via reaction latency heuristics (>300s).",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    # 3. Unit Economics & Trust Tax
    story.append(Paragraph("3. Unit Economics & Trust Tax (Evaluation Overhead)", heading2_style))
    econ = report_data["economics"]
    eval_res = report_data["evaluation"]
    story.append(Paragraph(
        f"Measured Telemetry Cost: <b>${econ['total_measured_cost_usd']:.2f}</b> across {econ['total_tasks']} tasks. "
        f"Telemetry-Attributable Cost Per Task: <b>${econ['telemetry_attributable_cost_per_task_usd']:.4f}</b> (Status: <b>{econ['overall_cost_status']}</b>). "
        f"Latency: P50 = <b>{econ['latency_ms']['p50']}ms</b> | P95 = <b>{econ['latency_ms']['p95']}ms</b> | P99 = <b>{econ['latency_ms']['p99']}ms</b>.<br/>"
        f"Trust Tax (Evaluation Overhead): <b>{eval_res['trust_tax_rate_pct']}%</b> of primary inference. "
        f"Evaluation Coverage: <b>{eval_res['eval_coverage_pct']}%</b> of workflow traces (Status: <b>{eval_res['evaluation_status']}</b>).",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    # 4. Failure Cascades & Cost Amplification
    if "cascades" in report_data:
        casc = report_data["cascades"]
        story.append(Paragraph("4. Failure Cascades & Retry Cost Amplification", heading2_style))
        story.append(Paragraph(
            f"<b>Economic Impact:</b> {casc['economic_impact_statement']}<br/>"
            f"Cascade Frequency: <b>{casc['cascade_frequency_pct']}%</b> ({casc['cascading_traces_count']}/{casc['total_traces_analyzed']} traces). "
            f"Average Cost Multiplier on Error: <b>{casc['avg_cost_multiplier_on_failure']}x</b>. "
            f"Added Execution Latency: <b>+{casc['avg_latency_added_ms']}ms</b>.",
            body_style
        ))
        story.append(Spacer(1, 6))
        
    # 5. AIBOM & Potential Single Point of Failure (PSPOF)
    story.append(Paragraph("5. AI Bill of Materials (AIBOM) & Potential Single Point of Failure (PSPOF)", heading2_style))
    if "aibom" in report_data:
        bom = report_data["aibom"]
        story.append(Paragraph(
            f"AIBOM ID: <b>{bom.get('bom_id')}</b> | Models: <b>{bom.get('unique_model_count')}</b> | "
            f"Tools: <b>{bom.get('unique_tool_count')}</b> | Self-Hosted Weights: <b>{'Yes' if bom.get('has_self_hosted_models') else 'None (100% Cloud API)'}</b> | "
            f"Human Checkpoints: <b>{'Active' if bom.get('has_human_checkpoints') else 'None'}</b>",
            body_style
        ))
        
    dep = report_data["dependencies"]
    spofs = dep.get("potential_spofs", [])
    if spofs:
        spof_data = [
            [
                Paragraph("<b>Component</b>", body_style),
                Paragraph("<b>Type</b>", body_style),
                Paragraph("<b>Share</b>", body_style),
                Paragraph("<b>Fallback Observed?</b>", body_style),
                Paragraph("<b>Evidence & Risk Status</b>", body_style)
            ]
        ]
        for s in spofs:
            risk_badge = f"<font color='#D97706'><b>{s['risk_status']}</b></font>" if "MITIGATED" in s['risk_status'] else f"<font color='#DC2626'><b>{s['risk_status']}</b></font>"
            spof_data.append([
                Paragraph(s["component_name"], body_style),
                Paragraph(s["component_type"], body_style),
                Paragraph(f"{s['dependency_share_pct']}%", body_style),
                Paragraph("Yes (Observed)" if s["fallback_observed"] else "No Fallback", body_style),
                Paragraph(f"{risk_badge}<br/><font color='#64748B'>{'; '.join(s['failure_evidence'][:2])}</font>", body_style)
            ])
            
        t_spof = Table(spof_data, colWidths=[1.4*inch, 1.4*inch, 0.7*inch, 1.2*inch, 2.4*inch])
        t_spof.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(t_spof)
    story.append(Spacer(1, 6))
    
    # 6. Data Coverage & Scope Limitations
    story.append(Paragraph("6. Data Coverage & Technical Limitations", heading2_style))
    lim_data = [[Paragraph(f"• {lim}", limitation_style)] for lim in report_data.get("limitations", [])]
    t_lim = Table(lim_data, colWidths=[7.1*inch])
    t_lim.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_lim)
    story.append(Spacer(1, 8))
    
    # 7. Appendix: Evidence Audit Trail
    story.append(Paragraph("7. Appendix: Auditable Evidence Graph", heading2_style))
    evd_table_data = [
        [
            Paragraph("<b>Code</b>", body_style),
            Paragraph("<b>Type</b>", body_style),
            Paragraph("<b>Conf.</b>", body_style),
            Paragraph("<b>Observed Fact & Derived Metric</b>", body_style)
        ]
    ]
    for evd in report_data.get("evidence_records", []):
        evd_table_data.append([
            Paragraph(f"<b>{evd['evidence_code']}</b>", body_style),
            Paragraph(f"<font color='#0284C7'><b>{evd['evidence_type']}</b></font>", body_style),
            Paragraph(evd['confidence'], body_style),
            Paragraph(f"<b>Observed Fact:</b> {evd['observed_fact']}<br/><b>Derived Metric:</b> {evd.get('derived_metric_summary', '')}<br/><b>Inference:</b> {evd.get('inference_summary', '')}", body_style)
        ])
    t_evd = Table(evd_table_data, colWidths=[0.8*inch, 0.7*inch, 0.7*inch, 4.9*inch])
    t_evd.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_evd)
    story.append(Spacer(1, 8))
    
    # 8. Cryptographic Chain-of-Custody Seal
    if "audit_manifest" in report_data:
        m = report_data["audit_manifest"]
        seal = m.get("chain_of_custody_seal", {})
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0F766E'), spaceAfter=5))
        story.append(Paragraph(
            f"<b>CRYPTOGRAPHIC CHAIN-OF-CUSTODY MANIFEST SEAL</b> | Manifest ID: <b>{m.get('manifest_id')}</b><br/>"
            f"Input Telemetry SHA-256: <code>{m['pipeline_stages']['1_telemetry_input']['aggregate_telemetry_sha256'][:32]}...</code><br/>"
            f"Master Verification Digest ({seal.get('algorithm', 'SHA-256')}): <code>{seal.get('digest')}</code> [{seal.get('verification_status', 'VERIFIED')}]",
            seal_style
        ))
    
    doc.build(story)
    return output_path
