"""
Reproducible Ingestion & Normalization Performance Benchmark for Agentic Diligence Phase 2.
Measures local P50, P95, P99 latency and throughput (spans/second).
"""

import time
import json
import statistics
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.db.models import Company, Tenant
from app.ingestion.otlp_handler import process_otlp_http_bytes

def run_benchmark(iterations: int = 200, spans_per_batch: int = 5):
    # In-memory SQLite for high-fidelity engine isolation
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    tenant = Tenant(name="Bench Tenant")
    session.add(tenant)
    session.flush()
    company = Company(tenant_id=tenant.id, name="Bench Company")
    session.add(company)
    session.commit()

    # Create sample multi-span OTLP batch
    spans = []
    for i in range(spans_per_batch):
        spans.append({
            "traceId": f"bench_trace_{i:04d}",
            "spanId": f"bench_span_{i:04d}",
            "name": f"step_{i}",
            "kind": 3,
            "startTimeUnixNano": "1726999200000000000",
            "endTimeUnixNano": "1726999200500000000",
            "attributes": [
                {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 400}},
                {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 100}}
            ],
            "status": {"code": 1}
        })

    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "benchmark_agent"}}]
                },
                "scopeSpans": [{"spans": spans}]
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    byte_size = len(raw_bytes)

    # Warmup
    for _ in range(10):
        process_otlp_http_bytes(session, raw_bytes, company_id=company.id)

    durations_ms = []
    errors = 0

    print(f"Running benchmark: {iterations} iterations, {spans_per_batch} spans/batch ({byte_size} bytes/payload)...")
    t0 = time.time()

    for idx in range(iterations):
        # Unique trace ID per run to avoid collision
        unique_spans = []
        for i in range(spans_per_batch):
            unique_spans.append({
                "traceId": f"bench_trace_{idx}_{i:04d}",
                "spanId": f"bench_span_{idx}_{i:04d}",
                "name": f"step_{i}",
                "kind": 3,
                "startTimeUnixNano": "1726999200000000000",
                "endTimeUnixNano": "1726999200500000000",
                "attributes": [
                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 400}},
                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 100}}
                ]
            })
        unique_payload = {"resourceSpans": [{"scopeSpans": [{"spans": unique_spans}]}]}
        u_bytes = json.dumps(unique_payload).encode("utf-8")

        start = time.perf_counter()
        try:
            res = process_otlp_http_bytes(session, u_bytes, company_id=company.id)
            if res.status != "SUCCESS":
                errors += 1
        except Exception:
            errors += 1
        dur = (time.perf_counter() - start) * 1000.0
        durations_ms.append(dur)

    total_wall_sec = time.time() - t0
    total_spans = iterations * spans_per_batch
    spans_per_sec = total_spans / total_wall_sec
    batches_per_sec = iterations / total_wall_sec

    durations_sorted = sorted(durations_ms)
    p50 = statistics.median(durations_sorted)
    p90 = durations_sorted[int(0.90 * len(durations_sorted))]
    p95 = durations_sorted[int(0.95 * len(durations_sorted))]
    p99 = durations_sorted[int(0.99 * len(durations_sorted))]
    mean = statistics.mean(durations_sorted)

    print("\n=======================================================")
    print("  AGENTIC DILIGENCE PHASE 2 INGESTION BENCHMARK RESULTS")
    print("=======================================================")
    print(f"  Total Iterations : {iterations}")
    print(f"  Total Spans      : {total_spans}")
    print(f"  Payload Size     : {byte_size} bytes/batch")
    print(f"  Throughput       : {spans_per_sec:.1f} spans/sec ({batches_per_sec:.1f} batches/sec)")
    print(f"  Error Rate       : {errors / iterations * 100:.2f}% ({errors} errors)")
    print("-------------------------------------------------------")
    print(f"  P50 Latency      : {p50:.2f} ms")
    print(f"  Mean Latency     : {mean:.2f} ms")
    print(f"  P90 Latency      : {p90:.2f} ms")
    print(f"  P95 Latency      : {p95:.2f} ms")
    print(f"  P99 Latency      : {p99:.2f} ms")
    print("=======================================================\n")

if __name__ == "__main__":
    run_benchmark(iterations=200, spans_per_batch=5)
