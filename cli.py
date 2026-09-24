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
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.option("--reload", is_flag=True, default=False, help="Enable live code reloading")
def serve(host, port, reload):
    """
    Starts the Agentic Diligence FastAPI application and Interactive Cockpit server.
    """
    click.echo(f"Starting Agentic Diligence Server on http://{host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    cli()
