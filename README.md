# Agentic Diligence (`agd`)
## An Evidence-First Framework for Verifying AI Agent Runtime Claims

> **"Don't trust the claim. Verify what the available runtime evidence supports."**  
> *"Absence of evidence ≠ evidence of absence."*

Agentic Diligence is a deterministic, evidence-backed technical due diligence platform for AI agents. Rather than relying on subjective LLM-as-judge scoring or vendor pitch-deck self-reports, `agd` directly inspects runtime telemetry, normalizes traces against OpenTelemetry GenAI semantic conventions, attributes unit economics, bounds autonomy, and cryptographically signs verification packages.

---

## SaaS Platform & Multi-Page Architecture (Phase 8)

Agentic Diligence features a modern multi-page architecture with two distinct experiences powered by a unified dark enterprise design system:

### Experience A — Public Product Website
- **Landing Page (`/`)**: Value proposition ("Don't Trust the Claim. Verify the Reality."), core problems, 10 engines overview, live benchmark preview.
- **Product Architecture (`/product`)**: End-to-end telemetry pipeline, task segmentation, 10 diligence engines, and deliverables.
- **Analytical Capabilities (`/capabilities`)**: Deep dive into all 10 specialized intelligence modules across 4 pillars.
- **Methodology & Pipeline (`/how-it-works`)**: 4-stage pipeline (Connect → Analyze → Verify → Decide).
- **Trust & Epistemic Governance (`/trust`)**: Epistemic trust ladder (T0–T3), 35% dark-zone threshold, automated credential sanitization.
- **Documentation Hub (`/docs`)**: Auditor & developer guide, CLI cheat sheet, REST endpoints, and OpenAPI Swagger UI (`/api/docs`).
- **Onboarding Wizard (`/get-started`)**: Guided launchpad for benchmark presets (AcmeAI Scenario A, Scenarios B–J) or custom evaluations.

### Experience B — Authenticated / Managed SaaS Application Workspace
- **Workspace Hub (`/app`)**: Interactive multi-page SaaS shell with collapsible sidebar, dynamic breadcrumbs, and live company selector.
- **Project Catalog (`/app/projects`)**: Catalog of all evaluated target companies, statuses, and trace counts.
- **Audit Initializer (`/app/projects/new`)**: Configure new target evaluations.
- **Deep-Dive Engine Controllers**: Dedicated view controllers for all 10 analytical engines:
  - `/app/projects/{id}/claims`: Claim Verification Matrix
  - `/app/projects/{id}/autonomy`: Autonomy & Human Intervention Rate
  - `/app/projects/{id}/economics`: Unit Economics & Cost Per Task
  - `/app/projects/{id}/dependencies`: SPOF & Failure Cascades
  - `/app/projects/{id}/aibom`: CycloneDX 1.6 AI Bill of Materials
  - `/app/projects/{id}/evidence`: Cryptographic Evidence Log & SHA-256 Hashes
  - `/app/projects/{id}/security`: Tool Risk & Blast Radius
  - `/app/projects/{id}/defensibility`: Moat & Scaffolding Analysis
  - `/app/projects/{id}/stress-test`: Economic Stress Simulator
  - `/app/projects/{id}/comparison`: Multi-Target Diligence Matrix
  - `/app/projects/{id}/reports`: IC Deal Memo & Bundle Download
- **Integrations & Settings**:
  - `/app/integrations`: OpenTelemetry collector status & MCP proxy config
  - `/app/settings`: Workspace settings & API key administration
- **Legacy Cockpit Fallback**: Accessible anytime at `/cockpit`.

---

## OpenTelemetry OTLP Ingestion (`POST /v1/traces`)

Agentic Diligence exposes a standards-compliant OpenTelemetry Protocol (OTLP) HTTP/JSON trace ingestion endpoint at `POST /v1/traces`.

### 1. Starting the Ingestion Receiver

```bash
# Start the local server
python cli.py serve --port 8000
# Or directly with uvicorn
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The receiver will listen on `http://127.0.0.1:8000/v1/traces`.

---

### 2. Exporting Traces from Agent Frameworks

#### Option A: Using curl / Direct HTTP
```bash
curl -X POST http://127.0.0.1:8000/v1/traces \
  -H "Content-Type: application/json" \
  -d '{
    "resourceSpans": [
      {
        "resource": {
          "attributes": [{"key": "service.name", "value": {"stringValue": "my-agent"}}]
        },
        "scopeSpans": [
          {
            "spans": [
              {
                "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
                "spanId": "00f067aa0ba902b7",
                "name": "ChatOpenAI.generate",
                "kind": 3,
                "startTimeUnixNano": "1726999200000000000",
                "endTimeUnixNano": "1726999201500000000",
                "attributes": [
                  {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                  {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                  {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 450}},
                  {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 120}}
                ],
                "status": {"code": 1}
              }
            ]
          }
        ]
      }
    ]
  }'
```

#### Option B: Standard OpenTelemetry Python SDK Exporter
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://127.0.0.1:8000/v1/traces"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
```

---

### 3. Ingestion Response & Cryptographic Provenance

Every ingested payload produces an immutable cryptographic record:

```json
{
  "status": "SUCCESS",
  "payload_hash": "8c691b87d84531201caa167b2f9a287e86ab0c76e1aacbdeef52a5d2d23272f6",
  "byte_size": 1024,
  "content_type": "application/json",
  "normalization_version": "v1.28.0",
  "traces_count": 1,
  "spans_count": 4,
  "trace_ids": ["4bf92f3577b34da6a3ce929d0e0e4736"],
  "errors": [],
  "duration_ms": 7.4
}
```

#### Verifying a Payload Digest
The `payload_hash` is the exact SHA-256 digest of the raw incoming request bytes:
```bash
python -c "import hashlib; print(hashlib.sha256(open('trace.json', 'rb').read()).hexdigest())"
```

---

### 4. Integration Compatibility Matrix

Query the live matrix via `GET http://127.0.0.1:8000/v1/compatibility` or inspect `app/ingestion/compatibility.py`:

| Framework / Exporter | Tested Version | Supported Format | Attributes Observed | Trust Level |
| :--- | :--- | :--- | :--- | :---: |
| **LangChain / LangGraph** | `0.2.x / 0.1.x` | `resourceSpans` JSON | `gen_ai.system`, `gen_ai.request.model`, `prompt_tokens`, `completion_tokens` | `T1` |
| **Claude Desktop / MCP** | Protocol `2024-11-05` | Standard OTLP JSON | `gen_ai.provider.name`, `gen_ai.tool.name`, `tool.call_id`, `tool.status` | `T2` |
| **CrewAI** | `0.30.x+` | `resourceSpans` JSON | `model_name`, `prompt_tokens`, `completion_tokens`, `agent.role` | `T1` |
| **Standard OTel Collector**| `v0.98.0+` | Full Protobuf-JSON | `gen_ai.provider.name`, `gen_ai.usage.input_tokens`, `output_tokens` | `T1` |

---

### 5. Running Tests & Benchmarks

```bash
# Run complete test suite (280 passed)
pytest

# Run Phase 8 multi-page & SaaS UI route tests
pytest tests/test_phase8_ui_routes.py -v

# Run local ingestion performance benchmark
python scripts/benchmark_ingest.py
```

---

### 6. Known Limitations & Deferred Capabilities

- **Protobuf Binary Format:** Currently deferred. `application/x-protobuf` returns `415 Unsupported Media Type` with an explicit notice to export as OTLP HTTP/JSON.
- **Max Batch Size:** Enforces a strict 10 MB per-request limit to prevent denial-of-service or unbounded memory consumption.
- **Local-First Privacy:** `agd` does not log raw user prompts or confidential model parameters by default. Token metadata, latency, and tool statuses are preserved while sensitive content strings are redacted.
