# Phase 9 Implementation Plan & Milestone Roadmap
**Document:** `docs/phase-09/implementation-plan.md`  
**Phase:** 9 — Complete Product Workflows  
**Branch:** `feat/phase-09-full-product-workflows`  

---

## Milestone Breakdown & Execution Strategy

### Milestone 9.1 — Project Lifecycle Management
- **Backend Models:** Add `Project` and `ProjectActivity` to `app/db/models.py`.
- **API Endpoints:**
  - `POST /api/v1/projects`: Create diligence project (with target system, target type, framework, description, scope).
  - `GET /api/v1/projects`: List projects with status filter, search, and pagination.
  - `GET /api/v1/projects/{id}`: Get project details, target company, latest assessment, trace count.
  - `PATCH /api/v1/projects/{id}`: Rename, update description, target system, or assessment scope.
  - `POST /api/v1/projects/{id}/archive`: Soft-archive a project.
  - `GET /api/v1/projects/{id}/activity`: Retrieve timeline of project activity events.
- **Frontend Views:**
  - Update `/app/projects` catalog table with real project metadata, status tags, search, and action menus.
  - Update `/app/projects/{id}` project dashboard with overview, assessment status, available evidence, risk summary, and quick navigation.
- **Automated Tests:** `tests/test_phase9_project_lifecycle.py`.

---

### Milestone 9.2 — Complete Onboarding
- **Public & App Wizards:**
  - `/get-started` (Public Onboarding)
  - `/app/projects/new` (In-App Creation)
- **Path A (Benchmark Evaluation):**
  - Explicitly states data is synthetic sample data.
  - Explains scenario parameters and runs benchmark scenario.
  - Associates created benchmark company with a persisted `Project`.
- **Path B (Custom Target Evaluation):**
  - Form collects Target Name, Target Description, Target Type (Autonomous Agent, Multi-Agent Swarm, RAG Pipeline, Custom Model), Primary Framework (LangGraph, CrewAI, MCP, OTel In-House), and Assessment Scope.
  - Validates inputs server-side.
  - Creates a genuine `Company` and `Project` in the database without running synthetic scenarios.
  - Redirects to `/app/projects/{id}` showing an empty state with an invitation to upload telemetry.
- **Automated Tests:** `tests/test_phase9_onboarding.py`.

---

### Milestone 9.3 — Telemetry and Evidence Ingestion
- **Backend Models & Endpoints:**
  - Add `IngestionJob` to `app/db/models.py`.
  - `POST /api/v1/projects/{id}/ingest`: Accepts file uploads (multipart) or JSON bodies.
  - Validates file format (.json, .jsonl), file size (up to 25MB), and OTel/native schema.
  - Calculates pre-parsing SHA-256 fingerprint.
  - Prevents path traversal and checks for duplicates.
  - Associates ingested traces with the project's company and logs an `IngestionJob` and `ProjectActivity`.
  - `GET /api/v1/projects/{id}/ingestion-jobs`: Ingestion history and status logs.
  - `GET /api/v1/projects/{id}/evidence`: Lists durable evidence records and source references.
- **Frontend Upload Experience:**
  - Modern drag-and-drop file upload zone in `app.html` modal and `/app/projects/{id}/evidence`.
  - Client-side format/size validation and upload progress bar.
  - Ingestion confirmation toast and real-time refresh of traces count.
- **Automated Tests:** `tests/test_phase9_ingestion.py`.

---

### Milestone 9.4 — Unified Assessment Orchestration
- **Backend Service:**
  - Create `app/assessment/orchestrator.py`: `AssessmentOrchestrator`.
  - Coordinates all 10 analytical engines: Claims, Autonomy, Economics, Dependencies, AI BOM, Evidence, Security, Defensibility, Stress Test, Comparison.
  - Lifecycle: `create_assessment()` $\to$ `validate_inputs()` $\to$ `execute_engines()` $\to$ `persist_results()`.
  - Per-engine execution with timing (`duration_ms`), error isolation (engine failure doesn't crash the assessment), and result persistence in `AssessmentEngineExecution`.
  - Distinguishes statuses: PENDING, RUNNING, COMPLETED, PARTIALLY_COMPLETED, FAILED.
  - Extracts structured `Finding` records (CRITICAL, HIGH, MEDIUM, LOW) with evidence references.
- **API Endpoints:**
  - `POST /api/v1/projects/{id}/assessments`: Run a new assessment (optional engine selection).
  - `GET /api/v1/projects/{id}/assessments`: List historical assessments.
  - `GET /api/v1/assessments/{assessment_id}`: Get assessment details, engine execution states, and findings.
- **Automated Tests:** `tests/test_phase9_assessment_orchestration.py`.

---

### Milestone 9.5 — Results and Findings Experience
- **Frontend View Controllers:**
  - Update all 10 analytical views in `app-router.js` to render directly from persisted assessment results or fall back cleanly to empty states with clear calls to action.
  - Standardized component templates: Result summaries, findings table, severity indicators, evidence links.
  - Findings view: Consolidated register of red/yellow/green findings with filtering by severity and engine.
- **Automated Tests:** Frontend route verification tests.

---

### Milestone 9.6 — Report Generation
- **Reporting Workflow:**
  - `POST /api/v1/assessments/{id}/report`: Generates and persists canonical Markdown, JSON package, and PDF report.
  - `GET /api/v1/projects/{id}/reports`: List all historical reports.
  - `GET /api/v1/reports/{id}/download`: Download report by format (`?format=pdf`, `?format=json`, `?format=zip`).
  - Ensures no cross-project report leaks.
- **Automated Tests:** `tests/test_phase9_reporting.py`.

---

### Milestone 9.7 — Frontend Product Integration
- Seamless navigation flow across Company Workspace $\to$ Project List $\to$ New Project $\to$ Ingestion $\to$ Assessment $\to$ Engine Dashboards $\to$ Findings $\to$ Reports $\to$ Historical Archive.
- Unified empty, loading, error, and success states using the dark enterprise design system.

---

### Milestone 9.8 — End-to-End QA and Acceptance
- Acceptance scenario: complete user journey from project creation to report download.
- Full regression suite execution: preserve 280 baseline tests + all new Phase 9 tests.
- Author final implementation report in `docs/phase-09/phase-9-implementation-report.md`.
