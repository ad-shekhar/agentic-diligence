# Phase 9 API Contracts & Endpoint Specification
**Document:** `docs/phase-09/api-contracts.md`  
**Phase:** 9 — Complete Product Workflows  

---

## 1. Project Lifecycle Endpoints

### 1.1 `POST /api/v1/projects`
Creates a genuine diligence project and underlying target company.
- **Request Body:**
```json
{
  "name": "NexusFlow Autonomous Agent Diligence",
  "target_name": "NexusFlow AI",
  "target_system": "Autonomous Tier-1 Support Agent",
  "target_type": "autonomous_agent",
  "framework": "LangGraph / LangChain",
  "description": "Pre-acquisition diligence evaluating claims of 95% autonomy and <$0.05 CPT.",
  "assessment_scope": "OTel runtime traces for customer support workflows",
  "evaluation_objective": "Verify autonomous completion and check for single-provider lock-in."
}
```
- **Response (201 Created):**
```json
{
  "id": "proj-uuid",
  "company_id": "comp-uuid",
  "name": "NexusFlow Autonomous Agent Diligence",
  "target_system": "Autonomous Tier-1 Support Agent",
  "status": "ACTIVE",
  "created_at": "2026-11-02T00:00:00Z"
}
```

### 1.2 `GET /api/v1/projects`
Lists all diligence projects with summary statistics.
- **Query Parameters:** `status` (optional: ACTIVE, ARCHIVED), `search` (optional)
- **Response (200 OK):**
```json
[
  {
    "id": "proj-uuid",
    "company_id": "comp-uuid",
    "name": "NexusFlow Autonomous Agent Diligence",
    "target_name": "NexusFlow AI",
    "target_system": "Autonomous Tier-1 Support Agent",
    "status": "ACTIVE",
    "trace_count": 0,
    "assessment_count": 0,
    "last_assessment_at": null,
    "created_at": "2026-11-02T00:00:00Z"
  }
]
```

### 1.3 `GET /api/v1/projects/{id}`
Returns complete project overview including target system, latest assessment verdict, and evidence stats.

### 1.4 `PATCH /api/v1/projects/{id}`
Updates project metadata (name, description, target_system, assessment_scope, evaluation_objective).

### 1.5 `POST /api/v1/projects/{id}/archive`
Soft-archives a project (`status = "ARCHIVED"`).

### 1.6 `GET /api/v1/projects/{id}/activity`
Returns the chronological activity audit log for the project.

---

## 2. Ingestion Endpoints

### 2.1 `POST /api/v1/projects/{id}/ingest`
Accepts file upload (multipart form data) or direct JSON body containing OpenTelemetry or native trace records.
- **Form Data / Body:**
  - `file`: .json or .jsonl payload (up to 25MB).
  - or `payload`: raw JSON body.
- **Processing:**
  1. Computes SHA-256 pre-parsing hash.
  2. Checks for duplicate payload hashes.
  3. Deserializes and parses spans.
  4. Stores spans in database linked to `project.company_id`.
  5. Logs `IngestionJob` and `ProjectActivity`.
- **Response (200 OK):**
```json
{
  "job_id": "job-uuid",
  "status": "SUCCESS",
  "payload_hash": "a1b2c3...",
  "traces_count": 12,
  "spans_count": 48,
  "errors": []
}
```

### 2.2 `GET /api/v1/projects/{id}/ingestion-jobs`
Returns history of file ingestion batches with status, file size, trace count, and error logs.

---

## 3. Assessment Orchestration Endpoints

### 3.1 `POST /api/v1/projects/{id}/assessments`
Initiates a new assessment run across the project's evidence base.
- **Request Body (optional):**
```json
{
  "name": "Q4 Technical Diligence Audit",
  "engines": ["claims", "autonomy", "economics", "dependencies", "aibom", "evidence", "security", "defensibility", "stress_test", "comparison"]
}
```
- **Processing:**
  1. Validates that project has telemetry traces. If empty, records `INSUFFICIENT_EVIDENCE` status.
  2. Executes selected analytical engines with error isolation and runtime stopwatch.
  3. Extracts red/yellow flags and synthesized deal recommendation.
  4. Persists `Assessment`, `AssessmentEngineExecution`, and `Finding` records.
  5. Logs `ProjectActivity`.
- **Response (200 OK):** Complete assessment record with engine statuses and synthesized findings.

### 3.2 `GET /api/v1/projects/{id}/assessments`
Lists all historical assessments executed for this project.

### 3.3 `GET /api/v1/assessments/{assessment_id}`
Retrieves detailed assessment execution results, individual engine outputs, and findings.

### 3.4 `GET /api/v1/projects/{id}/findings`
Returns the consolidated findings register for the project, queryable by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) or `engine_key`.

---

## 4. Report Generation Endpoints

### 4.1 `POST /api/v1/assessments/{assessment_id}/report`
Generates board-ready IC Memo, PDF report, and RFC 8785 signed evidence bundle from a persisted assessment.

### 4.2 `GET /api/v1/reports/{report_id}/download`
Downloads report in requested format:
- `?format=pdf`: PDF report file.
- `?format=json`: Standardized diligence package JSON.
- `?format=zip`: Verifiable diligence bundle with `manifest.json`.
