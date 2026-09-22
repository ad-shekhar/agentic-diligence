import os
import sys
import json
import click

from app.db.session import init_db, SessionLocal
from app.ingestion.synthetic import generate_synthetic_scenario
from app.reporting.builder import build_due_diligence_report

@click.group()
def cli():
    """Agentic Diligence CLI - Evidence-First AI Technical Due Diligence Platform."""
    pass

@cli.command()
@click.option("--scenario", default="scenario_a", help="Scenario preset (scenario_a to scenario_j)")
@click.option("--output-pdf", default=None, help="Output PDF report path")
@click.option("--output-json", default=None, help="Output JSON evidence package path")
@click.option("--sample-size", default=500, help="Number of synthetic traces to generate")
@click.option("--seed", default=42, help="Random seed for reproducible benchmark generation")
def generate_demo_report(scenario, output_pdf, output_json, sample_size, seed):
    """
    Generates synthetic telemetry for a benchmark scenario and outputs an evidence-backed due diligence report.
    """
    sc_name = scenario.lower()
    if not output_pdf:
        output_pdf = f"diligence_report_{sc_name}.pdf"
    if not output_json:
        output_json = f"diligence_report_{sc_name}.json"
        
    click.echo("Initializing database schema...")
    init_db()
    
    db = SessionLocal()
    try:
        click.echo(f"Generating synthetic telemetry data for scenario '{sc_name}' ({sample_size} traces, seed={seed})...")
        synth_res = generate_synthetic_scenario(db, scenario_name=sc_name, sample_size=sample_size, seed=seed)
        company_id = synth_res["company_id"]
        
        click.echo(f"Synthetic benchmark generated successfully.")
        click.echo("Running deterministic analysis engines and evidence synthesis...")
        
        report_data = build_due_diligence_report(db, company_id, pdf_output_path=output_pdf)
        
        # Save JSON evidence package
        with open(output_json, "w") as f:
            json.dump(report_data, f, indent=2)
            
        click.echo("\n========================================================")
        click.echo(f"  AGENTIC DILIGENCE REPORT GENERATED ({sc_name.upper()})")
        click.echo("========================================================")
        click.echo(f"  Target Company : {report_data['company']['name']}")
        click.echo(f"  Total Traces   : {report_data['interventions']['total_traces']}")
        click.echo(f"  Autonomous Rate: {report_data['interventions']['autonomous_rate_pct']}%")
        click.echo(f"  Human Interv.  : {report_data['interventions']['human_intervention_rate_pct']}% HIR")
        click.echo(f"  Cost Per Task  : ${report_data['economics']['telemetry_attributable_cost_per_task_usd']:.4f} (Status: {report_data['economics']['overall_cost_status']})")
        click.echo(f"  Provider HHI   : {report_data['dependencies']['hhi_score']} ({report_data['dependencies']['concentration_level']})")
        click.echo(f"  Claim Statuses : {[(c['category'], c['verification_status']) for c in report_data['claims']]}")
        click.echo(f"  PDF Report     : {os.path.abspath(output_pdf)}")
        click.echo(f"  JSON Package   : {os.path.abspath(output_json)}")
        click.echo("========================================================\n")
        
    finally:
        db.close()

if __name__ == "__main__":
    cli()
