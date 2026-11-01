"""
Phase 9: Telemetry and Evidence Ingestion Service.

Provides secure file ingestion, drag-and-drop batch processing,
duplicate payload detection, and persistent IngestionJob history.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import Project, Company, IngestionJob, PayloadProvenance, Trace, Span
from app.ingestion.otlp_handler import process_otlp_http_bytes, IngestionError
from app.projects.service import log_project_activity, get_project_by_id_or_company

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB max batch upload


def sanitize_filename(filename: str) -> str:
    """Removes path traversal components and normalizes filename."""
    base = os.path.basename(filename or "telemetry.json")
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    return clean[:128]


def ingest_project_telemetry(
    db: Session,
    project_identifier: str,
    raw_bytes: bytes,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingests telemetry payload file or bytes into a diligence project scope.
    Computes pre-parsing SHA-256 fingerprint, performs duplicate detection,
    normalizes spans against GenAI conventions, and logs IngestionJob record.
    """
    project = get_project_by_id_or_company(db, project_identifier)
    if not project:
        raise ValueError(f"Project '{project_identifier}' not found.")

    company_id = project.company_id
    clean_filename = sanitize_filename(filename or "telemetry_payload.json")
    file_size = len(raw_bytes)

    if file_size == 0:
        raise ValueError("Cannot ingest empty payload.")

    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Payload exceeds maximum allowable size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.")

    # 1. Pre-parsing SHA-256 Provenance Fingerprint
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()

    # 2. Check for duplicate payload within company scope
    existing_prov = (
        db.query(PayloadProvenance)
        .filter(PayloadProvenance.payload_hash == payload_hash, PayloadProvenance.company_id == company_id)
        .first()
    )
    if existing_prov:
        job = IngestionJob(
            project_id=project.id,
            company_id=company_id,
            filename=clean_filename,
            file_size_bytes=file_size,
            format="otlp_json",
            payload_hash=payload_hash,
            status="DUPLICATE",
            traces_count=existing_prov.trace_count or 0,
            spans_count=existing_prov.span_count or 0,
            error_message="Payload previously ingested. Duplicate detection prevented re-insertion.",
        )
        db.add(job)
        db.commit()
        return {
            "job_id": job.id,
            "status": "DUPLICATE",
            "message": "Payload previously ingested. Duplicate spans preserved.",
            "payload_hash": payload_hash,
            "traces_count": job.traces_count,
            "spans_count": job.spans_count,
        }

    # 3. Parse JSON / JSONL
    try:
        decoded_str = raw_bytes.decode("utf-8")
        if clean_filename.endswith(".jsonl") or ("\n" in decoded_str and not decoded_str.strip().startswith("{") and not decoded_str.strip().startswith("[")):
            # Line-delimited JSON
            spans_list = []
            for line in decoded_str.splitlines():
                line = line.strip()
                if line:
                    spans_list.append(json.loads(line))
            payload_dict = {"spans": spans_list}
        else:
            payload_dict = json.loads(decoded_str)
            if isinstance(payload_dict, list):
                payload_dict = {"spans": payload_dict}
    except Exception as e:
        job = IngestionJob(
            project_id=project.id,
            company_id=company_id,
            filename=clean_filename,
            file_size_bytes=file_size,
            format="unknown",
            payload_hash=payload_hash,
            status="FAILED",
            error_message=f"JSON deserialization failed: {str(e)}",
        )
        db.add(job)
        db.commit()
        raise ValueError(f"Malformed JSON telemetry file: {str(e)}")

    # 4. Ingest spans into database
    try:
        ingest_bytes = raw_bytes if (isinstance(payload_dict, dict) and not clean_filename.endswith(".jsonl")) else json.dumps(payload_dict).encode("utf-8")
        result = process_otlp_http_bytes(
            db=db,
            raw_bytes=ingest_bytes,
            content_type="application/json",
            company_id=company_id
        )

        # Record IngestionJob
        job = IngestionJob(
            project_id=project.id,
            company_id=company_id,
            filename=clean_filename,
            file_size_bytes=file_size,
            format="otlp_json",
            payload_hash=payload_hash,
            status=result.status,
            traces_count=result.traces_count,
            spans_count=result.spans_count,
            error_message="; ".join(result.errors) if result.errors else None
        )
        db.add(job)

        # Log Activity on project
        log_project_activity(
            db,
            project.id,
            activity_type="TELEMETRY_INGESTED",
            description=f"Ingested {result.spans_count} spans across {result.traces_count} traces from '{clean_filename}' (SHA-256: {payload_hash[:8]}...).",
            metadata_json={"payload_hash": payload_hash, "spans_count": result.spans_count, "traces_count": result.traces_count}
        )
        db.commit()

        return {
            "job_id": job.id,
            "status": result.status,
            "payload_hash": payload_hash,
            "traces_count": result.traces_count,
            "spans_count": result.spans_count,
            "trace_ids": result.trace_ids,
        }
    except Exception as e:
        db.rollback()
        job = IngestionJob(
            project_id=project.id,
            company_id=company_id,
            filename=clean_filename,
            file_size_bytes=file_size,
            format="otlp_json",
            payload_hash=payload_hash,
            status="FAILED",
            error_message=str(e),
        )
        db.add(job)
        db.commit()
        raise ValueError(f"Telemetry normalization failed: {str(e)}")


def list_project_ingestion_jobs(db: Session, project_identifier: str) -> List[Dict[str, Any]]:
    """Retrieves ingestion job history for a project."""
    project = get_project_by_id_or_company(db, project_identifier)
    if not project:
        return []

    jobs = (
        db.query(IngestionJob)
        .filter(IngestionJob.company_id == project.company_id)
        .order_by(desc(IngestionJob.created_at))
        .all()
    )
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "file_size_bytes": j.file_size_bytes,
            "payload_hash": j.payload_hash,
            "status": j.status,
            "traces_count": j.traces_count,
            "spans_count": j.spans_count,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


def list_project_evidence_records(db: Session, project_identifier: str) -> Dict[str, Any]:
    """Retrieves evidence records and provenance digests for a project."""
    project = get_project_by_id_or_company(db, project_identifier)
    if not project:
        return {"total_spans": 0, "total_traces": 0, "provenance_digests": [], "evidence_records": []}

    comp = project.company
    traces = comp.traces if comp else []
    total_spans = sum(len(t.spans) for t in traces)

    provs = (
        db.query(PayloadProvenance)
        .filter(PayloadProvenance.company_id == project.company_id)
        .order_by(desc(PayloadProvenance.received_at))
        .all()
    )
    return {
        "project_id": project.id,
        "company_id": project.company_id,
        "total_traces": len(traces),
        "total_spans": total_spans,
        "provenance_digests": [
            {
                "hash": p.payload_hash,
                "byte_size": p.byte_size,
                "spans_count": p.span_count,
                "received_at": p.received_at.isoformat() if p.received_at else None,
            }
            for p in provs
        ]
    }
