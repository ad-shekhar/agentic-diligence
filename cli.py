import os
import sys
import json
import click
import uvicorn

from app.db.session import init_db, SessionLocal
from app.ingestion.synthetic import generate_synthetic_scenario
from app.reporting.builder import build_due_diligence_report
from app.reporting.bundle import verify_diligence_bundle
from app.analysis.comparison import compare_diligence_targets
from app.analysis.defensibility import analyze_defensibility_and_moat
from app.analysis.stress_test import simulate_stress_test_economics
from app.analysis.memo import generate_investment_committee_memo

@click.group()
def cli():
    """Agentic Diligence CLI - Standardized Technical Diligence Package Platform."""
    pass

@cli.command()
@click.option("--scenario", default="scenario_a", help="Scenario preset (scenario_a to scenario_j)")
@click.option("--output-pdf", default=None, help="Output PDF report path")
@click.option("--output-json", default=None, help="Output JSON package path")
@click.option("--output-dir", default=".", help="Directory to save package artifacts")
@click.option("--sample-size", default=500, help="Number of synthetic traces to generate")
@click.option("--seed", default=42, help="Random seed for reproducible benchmark generation")
def generate_demo_report(scenario, output_pdf, output_json, output_dir, sample_size, seed):
    """
    Generates synthetic telemetry for a benchmark scenario and outputs a standardized technical diligence package and .zip bundle.
    """
    sc_name = scenario.lower()
    if not output_pdf:
        output_pdf = os.path.join(output_dir, f"diligence_report_{sc_name}.pdf")
    if not output_json:
        output_json = os.path.join(output_dir, f"diligence_package_{sc_name}.json")
        
    click.echo("Initializing database schema...")
    init_db()
    
    db = SessionLocal()
    try:
        click.echo(f"Generating synthetic telemetry data for scenario '{sc_name}' ({sample_size} traces, seed={seed})...")
        synth_res = generate_synthetic_scenario(db, scenario_name=sc_name, sample_size=sample_size, seed=seed)
        company_id = synth_res["company_id"]
        
        click.echo("Running deterministic analysis engines, tool privilege analyzer, AIBOM, and cryptographic synthesis...")
        report_data = build_due_diligence_report(db, company_id, pdf_output_path=output_pdf, output_dir=output_dir)
        
        manifest = report_data.get("audit_manifest", {})
        aibom = report_data.get("aibom", {})
        casc = report_data.get("cascades", {})
        tool_risk = report_data.get("tool_risk", {})
        pkg_files = report_data.get("package_files", {})
        
        click.echo("\n=========================================================================")
        click.echo(f"  AGENTIC DILIGENCE STANDARDIZED PACKAGE GENERATED ({sc_name.upper()})")
        click.echo("=========================================================================")
        click.echo(f"  Target Company  : {report_data['company']['name']}")
        click.echo(f"  Total Traces    : {report_data['interventions']['total_traces']}")
        click.echo(f"  Autonomous Rate : {report_data['interventions']['autonomous_rate_pct']}%")
        click.echo(f"  Human Interv.   : {report_data['interventions']['human_intervention_rate_pct']}% HIR")
        click.echo(f"  Cost Per Task   : ${report_data['economics']['telemetry_attributable_cost_per_task_usd']:.4f} (Status: {report_data['economics']['overall_cost_status']})")
        click.echo(f"  Cascade Impact  : {casc.get('cascade_frequency_pct', 0)}% traces cascaded ({casc.get('avg_cost_multiplier_on_failure', 1.0)}x cost overrun)")
        click.echo(f"  Tool Risk Score : {tool_risk.get('tool_risk_score', 0)} / 100 ({tool_risk.get('risk_level', 'LOW')} risk, {tool_risk.get('total_tool_calls', 0)} tool calls)")
        click.echo(f"  AIBOM ID        : {aibom.get('bom_id')} ({aibom.get('unique_model_count')} models, {aibom.get('unique_tool_count')} tools)")
        click.echo(f"  Provider HHI    : {report_data['dependencies']['hhi_score']} ({report_data['dependencies']['concentration_level']})")
        click.echo(f"  Claim Statuses  : {[(c['category'], c['verification_status']) for c in report_data['claims']]}")
        click.echo(f"  Manifest Seal   : {manifest.get('chain_of_custody_seal', {}).get('digest', 'N/A')[:32]}...")
        click.echo(f"  PDF Report      : {pkg_files.get('pdf_report')}")
        click.echo(f"  JSON Package    : {pkg_files.get('package_json')}")
        click.echo(f"  Verifiable ZIP  : {pkg_files.get('diligence_bundle_zip')}")
        click.echo("=========================================================================\n")
        
    finally:
        db.close()

@cli.command()
@click.option("--bundle", required=True, help="Path to .zip diligence bundle file to verify")
def verify_bundle(bundle):
    """
    Verifies the cryptographic integrity and chain-of-custody seal of a diligence bundle archive.
    """
    click.echo(f"Verifying diligence bundle: {bundle}...")
    res = verify_diligence_bundle(bundle)
    
    click.echo("\n=========================================================================")
    click.echo("  CRYPTOGRAPHIC DILIGENCE BUNDLE VERIFICATION REPORT")
    click.echo("=========================================================================")
    click.echo(f"  Bundle File : {res.get('bundle_path', bundle)}")
    click.echo(f"  Verdict     : {'[PASSED] VERIFIED' if res['is_valid'] else '[FAILED] ' + res.get('status', 'ERROR')}")
    click.echo(f"  Files Tested: {res.get('total_files_checked', 0)}")
    click.echo("-------------------------------------------------------------------------")
    
    for f in res.get("checked_files", []):
        icon = "[OK]" if f.get("status") == "VERIFIED" else "[FAIL]"
        click.echo(f"  {icon} {f['file']:<26} SHA-256: {f.get('digest', f.get('actual', ''))[:24]}...")
        
    if res.get("errors"):
        click.echo("\n  Verification Discrepancies:")
        for err in res["errors"]:
            click.echo(f"  - [X] {err}")
    click.echo("=========================================================================\n")
    
    if not res["is_valid"]:
        sys.exit(1)

@cli.command()
@click.option("--target-a", default="scenario_a", help="Scenario or Company ID for Target A")
@click.option("--target-b", default="scenario_c", help="Scenario or Company ID for Target B")
@click.option("--sample-size", default=300, help="Sample size if generating scenarios")
def compare_targets(target_a, target_b, sample_size):
    """
    Executes a side-by-side comparative technical diligence audit between two AI agent targets.
    """
    init_db()
    db = SessionLocal()
    try:
        click.echo(f"Preparing diligence analysis for Target A: {target_a} and Target B: {target_b}...")
        
        # Check if scenario names or company IDs
        res_a = generate_synthetic_scenario(db, scenario_name=target_a.lower(), sample_size=sample_size, seed=42)
        res_b = generate_synthetic_scenario(db, scenario_name=target_b.lower(), sample_size=sample_size, seed=99)
        
        comp_res = compare_diligence_targets(db, res_a["company_id"], res_b["company_id"])
        
        click.echo("\n=========================================================================")
        click.echo(f"  {comp_res['comparison_title'].upper()}")
        click.echo("=========================================================================")
        winners = comp_res["dimension_winners"]
        click.echo(f"  Dimension Winners:")
        click.echo(f"    * True Autonomy      : {winners['autonomy']}")
        click.echo(f"    * Unit Economics     : {winners['economics']}")
        click.echo(f"    * Resilience & Arch  : {winners['resilience']}")
        click.echo(f"    * Governance & Verif : {winners['governance_and_safety']}")
        click.echo("-------------------------------------------------------------------------")
        click.echo(f"  {'DIMENSION':<22} | {'TARGET A':<14} | {'TARGET B':<14} | {'ADVANTAGE'}")
        click.echo("  " + "-" * 69)
        
        for row in comp_res["matrix"]:
            click.echo(f"  {row['dimension']:<22} | {row['target_a_value']:<14} | {row['target_b_value']:<14} | {row['advantage']}")
            
        click.echo("=========================================================================\n")
    finally:
        db.close()

@cli.command()
@click.option("--scenario", default="scenario_a", help="Benchmark scenario name (scenario_a to scenario_j)")
@click.option("--sample-size", default=300, help="Number of traces to generate")
def analyze_defensibility(scenario, sample_size):
    """
    Evaluates proprietary scaffolding, model sovereignty, domain tool assets, and moat defensibility.
    """
    init_db()
    db = SessionLocal()
    try:
        click.echo(f"Running Defensibility & Moat Analysis for {scenario.upper()}...")
        synth = generate_synthetic_scenario(db, scenario_name=scenario.lower(), sample_size=sample_size, seed=42)
        moat = analyze_defensibility_and_moat(db, synth["company_id"])
        
        click.echo("\n=========================================================================")
        click.echo(f"  AI DEFENSIBILITY & MOAT AUDIT ({scenario.upper()})")
        click.echo("=========================================================================")
        click.echo(f"  Moat Score        : {moat['moat_score']} / 100")
        click.echo(f"  Classification    : {moat['moat_classification']}")
        click.echo(f"  Scaffolding Index : {moat['scaffolding_complexity_score']} / 25 pts")
        click.echo(f"  Weight Sovereignty: {moat['weight_sovereignty_score']} / 25 pts")
        click.echo(f"  Tool Integration  : {moat['tool_integration_score']} / 25 pts")
        click.echo(f"  Data Flywheel     : {moat['data_flywheel_score']} / 25 pts")
        click.echo(f"  Replication Barrier: ~{moat['estimated_replication_months']} months (${moat['estimated_replication_cost_usd']:,} USD)")
        click.echo("-------------------------------------------------------------------------")
        click.echo(f"  Architecture Assessment:")
        click.echo(f"  {moat['verdict_summary']}")
        click.echo("=========================================================================\n")
    finally:
        db.close()

@cli.command()
@click.option("--scenario", default="scenario_a", help="Benchmark scenario name")
@click.option("--volume-mult", default=1.0, type=float, help="Volume multiplier (e.g. 1.0, 5.0, 10.0)")
@click.option("--price-shock", default=0.0, type=float, help="Provider price shock % (e.g. +25.0, -20.0)")
@click.option("--labor-rate", default=28.0, type=float, help="Human operator hourly wage in USD")
@click.option("--task-price", default=0.05, type=float, help="Target customer price per task in USD")
def stress_test(scenario, volume_mult, price_shock, labor_rate, task_price):
    """
    Executes What-If Economic Stress-Testing, Token Price Shocks, and Fully-Loaded Labor Economics.
    """
    init_db()
    db = SessionLocal()
    try:
        click.echo(f"Running Operational & Economic Stress Test for {scenario.upper()}...")
        synth = generate_synthetic_scenario(db, scenario_name=scenario.lower(), sample_size=300, seed=42)
        res = simulate_stress_test_economics(
            db, synth["company_id"],
            volume_multiplier=volume_mult,
            provider_price_shock_pct=price_shock,
            human_hourly_wage_usd=labor_rate,
            target_customer_price_per_task_usd=task_price
        )
        base = res["baseline_economics"]
        strsd = res["stressed_economics"]
        verdict = res["vulnerability_verdict"]
        
        click.echo("\n=========================================================================")
        click.echo(f"  WHAT-IF ECONOMIC STRESS TEST ({scenario.upper()})")
        click.echo("=========================================================================")
        click.echo(f"  Parameters: Volume={volume_mult}x | Price Shock={price_shock:+0.1f}% | Labor Rate=${labor_rate}/hr | Customer Price=${task_price}/task")
        click.echo("-------------------------------------------------------------------------")
        click.echo(f"  {'METRIC':<28} | {'BASELINE':<18} | {'STRESSED':<18}")
        click.echo("  " + "-" * 69)
        click.echo(f"  {'Telemetry LLM Cost/Task':<28} | ${base['llm_cost_per_task_usd']:<17.4f} | ${strsd['llm_cost_per_task_usd']:<17.4f}")
        click.echo(f"  {'Human Labor Cost/Task':<28} | ${base['human_labor_cost_per_task_usd']:<17.4f} | ${strsd['human_labor_cost_per_task_usd']:<17.4f}")
        click.echo(f"  {'Fully-Loaded Unit Cost':<28} | ${base['fully_loaded_cost_per_task_usd']:<17.4f} | ${strsd['fully_loaded_cost_per_task_usd']:<17.4f}")
        click.echo(f"  {'Monthly Tasks':<28} | {base['monthly_tasks']:<18,d} | {strsd['monthly_tasks']:<18,d}")
        click.echo(f"  {'Monthly Total Run-Rate':<28} | ${base['monthly_total_cost_usd']:<17,.2f} | ${strsd['monthly_total_cost_usd']:<17,.2f}")
        click.echo(f"  {'Gross Margin %':<28} | {base['gross_margin_pct']:<17.1f}% | {strsd['gross_margin_pct']:<17.1f}%")
        click.echo(f"  {'Target 70% Margin Price':<28} | ${base['fully_loaded_cost_per_task_usd']/0.30:<17.4f} | ${strsd['price_for_70pct_margin_usd']:<17.4f}")
        click.echo("-------------------------------------------------------------------------")
        click.echo(f"  Stress Verdict: {verdict['status']}")
        click.echo(f"  {verdict['statement']}")
        click.echo("=========================================================================\n")
    finally:
        db.close()

@cli.command()
@click.option("--scenario", default="scenario_a", help="Benchmark scenario name")
def diligence_memo(scenario):
    """
    Generates Investment Committee (IC) Executive Diligence Memo, Red/Yellow/Green Flags, and Remediation Playbook.
    """
    init_db()
    db = SessionLocal()
    try:
        click.echo(f"Synthesizing Investment Committee Diligence Memo for {scenario.upper()}...")
        synth = generate_synthetic_scenario(db, scenario_name=scenario.lower(), sample_size=300, seed=42)
        memo = generate_investment_committee_memo(db, synth["company_id"])
        
        click.echo("\n=========================================================================")
        click.echo(f"  EXECUTIVE INVESTMENT COMMITTEE DILIGENCE MEMO ({scenario.upper()})")
        click.echo("=========================================================================")
        click.echo(f"  Target Company      : {memo['company_name']}")
        click.echo(f"  Diligence Risk Score: {memo['diligence_risk_score']} / 100 ({memo['risk_classification']} RISK)")
        click.echo(f"  Deal Recommendation : {memo['deal_verdict']}")
        click.echo("-------------------------------------------------------------------------")
        click.echo(f"  Executive Assessment:")
        click.echo(f"  {memo['executive_verdict_summary']}")
        click.echo("-------------------------------------------------------------------------")
        flags = memo["flags_summary"]
        click.echo(f"  Flag Summary: {flags['red_flags_count']} RED | {flags['yellow_flags_count']} YELLOW | {flags['green_flags_count']} GREEN")
        
        if memo["red_flags"]:
            click.echo("\n  [!] CRITICAL RED FLAGS:")
            for rf in memo["red_flags"]:
                click.echo(f"    * [{rf['category']}] {rf['title']}")
                click.echo(f"      {rf['detail']}")
                
        if memo["yellow_flags"]:
            click.echo("\n  [?] OPERATIONAL YELLOW FLAGS:")
            for yf in memo["yellow_flags"]:
                click.echo(f"    * [{yf['category']}] {yf['title']}")
                
        if memo["green_flags"]:
            click.echo("\n  [+] GREEN FLAGS / ARCHITECTURAL STRENGTHS:")
            for gf in memo["green_flags"]:
                click.echo(f"    * [{gf['category']}] {gf['title']}")
                
        click.echo("\n  100-Day Technical Remediation Playbook:")
        for step in memo["remediation_playbook"]:
            click.echo(f"    [{step['priority']}] {step['initiative']}: {step['kpi_target']}")
        click.echo("=========================================================================\n")
    finally:
        db.close()

@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.option("--reload", is_flag=True, default=False, help="Enable live code reloading")
def serve(host, port, reload):
    """
    Starts the Agentic Diligence FastAPI application and Interactive Cockpit server.
    """
    click.echo(f"Starting Agentic Diligence Server on http://{host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# Phase 3: Task Segmentation & Deterministic Metrics Engine
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--scenario", default="scenario_a",
              help="Scenario preset (scenario_a to scenario_j)")
@click.option("--sample-size", default=200,
              help="Number of synthetic traces to segment")
@click.option("--seed", default=42, help="Random seed")
@click.option("--gap-ms", default=30000.0,
              help="Gap heuristic threshold in milliseconds (default 30 000 ms = 30 s)")
@click.option("--output-json", default=None,
              help="Write full metrics JSON to this path")
def compute_metrics(scenario, sample_size, seed, gap_ms, output_json):
    """
    Phase 3 — Runs task segmentation and computes all 8 epistemically-tagged
    diligence signals (Autonomy Rate, HIR, TCR, Error Rate, Token Efficiency,
    Cost Per Task, Model Concentration / HHI, Telemetry Coverage).

    Absence of evidence is never silently assumed to be autonomy.
    Unknown intervals widen the confidence interval; they are never collapsed.
    """
    from app.db.session import init_db, SessionLocal
    from app.ingestion.synthetic import generate_synthetic_scenario
    from app.db.models import Trace, Span
    from app.ingestion.schema import NormalizedSpan as SchemaSpan
    from app.epistemic.tags import TrustLevel
    from app.analysis.task_segmentation import segment_trace
    from app.analysis.metrics_engine import compute_diligence_metrics

    click.echo("Initializing database...")
    init_db()
    db = SessionLocal()
    try:
        click.echo(f"Generating synthetic scenario '{scenario}' ({sample_size} traces, seed={seed})...")
        synth_res = generate_synthetic_scenario(db, scenario_name=scenario.lower(),
                                                sample_size=sample_size, seed=seed)
        company_id = synth_res["company_id"]

        click.echo("Loading spans from database and running task segmentation...")
        traces = db.query(Trace).filter(Trace.company_id == company_id).all()

        all_seg_results = []
        all_norm_spans = []

        for trace in traces:
            norm_spans = []
            for sp in trace.spans:
                ns = SchemaSpan(
                    span_id=sp.id,
                    trace_id=trace.id,
                    name=sp.name,
                    span_kind=sp.span_kind,
                    start_time=sp.start_time,
                    end_time=sp.end_time,
                    duration_ms=sp.duration_ms,
                    status_code="OK",
                    provider_name=sp.gen_ai_system,
                    requested_model=sp.gen_ai_model,
                    input_tokens=sp.gen_ai_prompt_tokens,
                    output_tokens=sp.gen_ai_completion_tokens,
                    has_token_data=(sp.gen_ai_prompt_tokens or 0) + (sp.gen_ai_completion_tokens or 0) > 0,
                    tool_name=sp.tool_name,
                    is_human_intervention=sp.is_human_intervention,
                    human_action_type=sp.human_action_type,
                    intervention_detection_method=(
                        sp.detection_method.value if sp.detection_method else None
                    ),
                    cost_usd=sp.cost or 0.0,
                    cost_status=sp.cost_status.value if sp.cost_status else "MEASURED",
                    trust_level=TrustLevel.T1,
                )
                norm_spans.append(ns)
                all_norm_spans.append(ns)

            seg = segment_trace(norm_spans, trace_id=trace.id,
                                workflow_name=trace.name, gap_heuristic_ms=gap_ms)
            all_seg_results.append(seg)

        click.echo("Computing 8 diligence signals...")
        metrics = compute_diligence_metrics(all_seg_results, all_norm_spans)
        d = metrics.to_dict()

        ar = d["signals"]["autonomy_rate"]
        hir = d["signals"]["human_intervention_rate"]
        tcr = d["signals"]["task_completion_rate"]
        er  = d["signals"]["error_rate"]
        te  = d["signals"]["token_efficiency"]
        cpt = d["signals"]["cost_per_task"]
        mc  = d["signals"]["model_concentration"]
        tc  = d["signals"]["telemetry_coverage"]

        click.echo("\n=======================================================================")
        click.echo(f"  AGENTIC DILIGENCE — PHASE 3 METRICS  [{scenario.upper()}]")
        click.echo("=======================================================================")
        click.echo(f"  Traces Analyzed   : {d['total_traces']}")
        click.echo(f"  Total Tasks       : {d['total_tasks']}  (spans: {d['total_spans']})")
        click.echo(f"  Total Cost        : ${d['total_cost_usd']:.4f} USD")
        click.echo("-----------------------------------------------------------------------")
        _print_signal("1. Autonomy Rate (AR)",        ar,  "%")
        _print_signal("2. Human Intervention Rate",   hir, "%")
        _print_signal("3. Task Completion Rate",      tcr, "%")
        _print_signal("4. Error Rate",                er,  "%")
        _print_signal("5. Token Efficiency (TE)",     te,  "")
        _print_signal("6. Cost Per Task (CPT)",       cpt, "USD")
        _print_signal("7. Model Concentration (HHI)", mc,  "")
        _print_signal("8. Telemetry Coverage",        tc,  "%")
        click.echo("=======================================================================\n")

        if output_json:
            with open(output_json, "w") as f:
                import json
                json.dump(d, f, indent=2, default=str)
            click.echo(f"Full metrics JSON written to: {output_json}")
    finally:
        db.close()


def _print_signal(label: str, sig: dict, unit: str):
    """Helper to pretty-print a single diligence signal."""
    val = sig.get("value")
    tag = sig.get("epistemic_tag", "?")
    trust = sig.get("trust_level", "?")
    bounds = sig.get("bounds") or {}
    lo  = bounds.get("lower", "?")
    hi  = bounds.get("upper", "?")
    n   = sig.get("sample_size", 0)
    if val is not None:
        val_str = f"{val:.2f} {unit}  [bounds: {lo:.1f}–{hi:.1f}]" if isinstance(val, float) else f"{val} {unit}"
    else:
        val_str = "UNKNOWN"
    click.echo(f"  {label:<35} {val_str:<30} {tag} / {trust}  (n={n})")


# --- Phase 4 CLI Commands ---

@cli.command("claim-matrix")
@click.option("--company", required=True, help="Target company ID")
@click.option("--output", default=None, help="Output JSON path")
def cmd_claim_matrix(company, output):
    """Generates and displays the formal Phase 4 Claim Verification Matrix."""
    init_db()
    db = SessionLocal()
    try:
        from app.reporting.service import assemble_canonical_diligence_report_package
        _, _, matrix = assemble_canonical_diligence_report_package(db, company)
        d = matrix.to_dict()
        click.echo("\n=======================================================================")
        click.echo(f"  AGENTIC DILIGENCE — CLAIM VERIFICATION MATRIX [{company.upper()}]")
        click.echo("=======================================================================")
        click.echo(f"  Matrix ID       : {d['matrix_id']}")
        click.echo(f"  Total Claims    : {d['summary']['total_claims']}")
        click.echo(f"  Verified        : {d['summary']['verified_count']}")
        click.echo(f"  Partially Verif : {d['summary']['partially_verified_count']}")
        click.echo(f"  Contradicted    : {d['summary']['contradicted_count']}")
        click.echo(f"  Insufficient Ev : {d['summary']['insufficient_evidence_count']}")
        click.echo("-----------------------------------------------------------------------")
        for e in d["entries"]:
            click.echo(f"  [{e['verification_verdict']:<21}] {e['claim_id']}: {e['verbatim_claim_text']}")
            click.echo(f"    Reason: {e['verdict_reason']}")
        click.echo("=======================================================================\n")
        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            click.echo(f"Saved Claim Matrix to: {output}")
    finally:
        db.close()


@cli.command("report")
@click.option("--company", required=True, help="Target company ID")
@click.option("--format", "report_format", type=click.Choice(["json", "markdown"]), default="markdown", help="Report format (markdown or json)")
@click.option("--output", default=None, help="Output file path")
@click.option("--synthetic/--no-synthetic", default=False, help="Flag dataset as synthetic benchmark demonstration")
def cmd_report(company, report_format, output, synthetic):
    """Generates a canonical diligence report in Markdown or JSON format."""
    init_db()
    db = SessionLocal()
    try:
        from app.reporting.service import assemble_canonical_diligence_report_package
        rep_json, rep_md, _ = assemble_canonical_diligence_report_package(db, company, is_synthetic=synthetic)
        content = rep_md if report_format == "markdown" else json.dumps(rep_json, indent=2)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(content)
            click.echo(f"Diligence report ({report_format}) written to: {output}")
        else:
            click.echo(content)
    finally:
        db.close()


@cli.group("bundle")
def bundle_group():
    """Manage and verify cryptographic evidence bundles."""
    pass


@bundle_group.command("create")
@click.option("--company", required=True, help="Target company ID")
@click.option("--output-dir", required=True, help="Directory to save the evidence bundle")
@click.option("--synthetic/--no-synthetic", default=False, help="Flag dataset as synthetic benchmark")
def cmd_bundle_create(company, output_dir, synthetic):
    """Compiles all diligence artifacts and generates manifest.json."""
    init_db()
    db = SessionLocal()
    try:
        from app.reporting.service import compile_diligence_bundle_on_disk
        click.echo(f"Compiling diligence bundle for company '{company}' in '{output_dir}'...")
        res = compile_diligence_bundle_on_disk(db, company, output_dir, is_synthetic=synthetic)
        click.echo("\n=======================================================================")
        click.echo(f"  EVIDENCE BUNDLE COMPILED SUCCESSFULLY")
        click.echo("=======================================================================")
        click.echo(f"  Bundle ID     : {res['bundle_id']}")
        click.echo(f"  Manifest Path : {res['manifest_path']}")
        click.echo(f"  Artifacts     : {res['artifacts_compiled']} files anchored")
        click.echo("=======================================================================\n")
    finally:
        db.close()


@bundle_group.command("verify")
@click.option("--dir", "bundle_dir", required=True, help="Path to evidence bundle directory")
def cmd_bundle_verify(bundle_dir):
    """Cryptographically verifies an evidence bundle against its manifest.json."""
    from app.reporting.manifest import verify_bundle_integrity
    click.echo(f"Verifying evidence bundle at: {bundle_dir}...")
    res = verify_bundle_integrity(bundle_dir)
    d = res.to_dict()
    click.echo("\n=======================================================================")
    click.echo(f"  BUNDLE INTEGRITY VERIFICATION RESULT: [{d['status']}]")
    click.echo("=======================================================================")
    click.echo(f"  Status        : {d['status']}")
    click.echo(f"  Is Valid      : {d['is_valid']}")
    click.echo(f"  Declared Files: {d['total_files_declared']}")
    click.echo(f"  Verified Files: {d['files_verified']}")
    if d["missing_files"]:
        click.echo(f"  Missing Files : {d['missing_files']}")
    if d["altered_files"]:
        click.echo(f"  Altered Files : {d['altered_files']}")
    if d["untracked_files"]:
        click.echo(f"  Untracked     : {d['untracked_files']}")
    if d["error_message"]:
        click.echo(f"  Error Message : {d['error_message']}")
    click.echo("=======================================================================\n")


@cli.command("aibom")
@click.option("--company", required=True, help="Target company ID")
@click.option("--spec-version", type=click.Choice(["1.5", "1.6"]), default="1.6", help="CycloneDX specVersion")
@click.option("--validate/--no-validate", default=True, help="Validate against official OWASP JSON schema")
@click.option("--output", default=None, help="Output JSON path")
def cmd_aibom(company, spec_version, validate, output):
    """Exports CycloneDX AI-BOM and validates against official schema."""
    init_db()
    db = SessionLocal()
    try:
        from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom, validate_cyclonedx_schema
        native = generate_native_aibom(db, company)
        cdx = export_cyclonedx_aibom(native, spec_version=spec_version)
        validation_status = "NOT_CHECKED"
        if validate:
            is_valid, errors = validate_cyclonedx_schema(cdx, spec_version=spec_version)
            validation_status = "PASSED" if is_valid else f"FAILED: {'; '.join(errors)}"

        click.echo("\n=======================================================================")
        click.echo(f"  CYCLONEDX AI-BOM EXPORT [{company.upper()}]")
        click.echo("=======================================================================")
        click.echo(f"  Spec Version     : {spec_version}")
        click.echo(f"  Components       : {len(cdx.get('components', []))}")
        click.echo(f"  Schema Validation: {validation_status}")
        click.echo("=======================================================================\n")

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(cdx, f, indent=2)
            click.echo(f"Saved AI-BOM to: {output}")
        else:
            click.echo(json.dumps(cdx, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    cli()

