# Phase 8 — Architecture & Implementation Plan
## Enterprise SaaS Transformation, Multi-Page Architecture & Complete Product Experience Modernization

**Project:** Agentic Diligence (`agentic-diligence` / `agd`)  
**Phase:** 8  
**Document Version:** 1.0.0  
**Classification:** Major Product Experience & Frontend Architecture Upgrade  
**Branch:** `feat/phase-08-enterprise-saas-experience`  
**Test Baseline:** 268 passing tests, 0 failures, 3 non-blocking warnings  
**Author:** Principal Product Architect & Senior Full-Stack Engineer  

---

## 1. Executive Summary & Vision

Agentic Diligence has established an evidence-first technical diligence engine covering ten analytical dimensions, OTel ingestion, MCP and browser adapters, cryptographic manifests, CycloneDX AI-BOMs, and claim verification.

Phase 8 elevates this functional core into a mature, enterprise-grade SaaS product with two distinct product experiences:

1. **Experience A — Public Product Website:**
   A premium, multi-page public marketing and discovery website that communicates the platform's core thesis ("Don't Trust the Claim. Verify the Reality."), explains its runtime methodology, showcases the 10 analytical engines, proves security/trust, and drives visitor conversion into onboarding.
2. **Experience B — Authenticated / Managed Application Workspace:**
   A structured, multi-page SaaS application with an enterprise sidebar shell, breadcrumbs, project management, evaluation lifecycle tracking, and dedicated deep-dive pages for all ten analytical modules.

### Quality Benchmarks
The product aesthetic and ergonomics are inspired by modern software platforms (Linear, Stripe, Vercel, Ramp, Notion):
- Editorial clarity with generous whitespace and precise typography.
- Information-dense, calm enterprise data tables and KPI cards.
- Restrained color palette (no gratuitous neon borders or random gradients).
- Zero fake functionality: every stat, claim, and chart binds directly to real backend telemetry.

---

## 2. Baseline Status & Repository Inventory

- **Baseline Test Suite:** `python -m pytest tests/ -q --tb=short` -> **268 passed, 3 warnings in 13.45s**.
- **Database Models (`app/db/models.py`):**
  - `Company`: Represents target entities under diligence.
  - `Tenant`: Multi-tenant boundary.
  - `Trace`, `Span`, `CostEvent`: Runtime telemetry.
  - `Claim`: Founder pitch statements and SLA targets.
  - `Report`: Stored diligence report packages.
  - `PayloadProvenance`: Raw SHA-256 evidence records.
  - `TenantApiKey`, `DurableEvidenceRecord`: Phase 7.1 security and persistence foundation.
- **Backend API Surface (`app/api/routes.py`):**
  - 35+ fully tested REST endpoints spanning scenarios, metrics, claim matrices, AI-BOMs, PDF/ZIP bundles, stress simulations, IC memos, and comparisons.
  - OTLP HTTP/JSON trace ingestion at `/v1/traces`.

---

## 3. Frontend Architecture Decision: Modern FastAPI Multi-Page + Hybrid Workspace Shell

In strict accordance with Section 3.4 of the Phase 8 specification, we evaluated whether to migrate to React/Next.js versus modernizing the existing native frontend stack:

### Evaluation Matrix

| Criterion | React / Next.js Migration | FastAPI-Native Multi-Page + Hybrid Workspace Shell |
|---|---|---|
| **Architectural Coupling** | High: Requires separate Node.js build pipeline, dual-port dev servers, CORS management, SSR server or static export. | Low: Zero coupling overhead; runs directly inside FastAPI with zero extra build tools. |
| **Deployment Complexity** | High: Requires Node runtime or multi-stage Docker build; increased attack surface. | Minimal: Single `uvicorn app.main:app` command serves backend APIs and UI instantly. |
| **Load Performance** | Moderate: Large JS bundles, hydration latency, layout shift. | Extremely Fast: Native HTML5 + scoped CSS tokens load in <50ms with 0ms hydration lag. |
| **Deep Linking & URLs** | Handled via Next.js router. | Handled via FastAPI route templates + HTML5 History API for seamless in-app transitions. |
| **Regression Risk** | Severe: Complete rewrite of UI logic, event handlers, and data binding risks breaking 268 existing test baselines. | Very Low: Preserves working endpoints, encapsulates pages into clean reusable modules. |
| **Maintainability** | High maintenance: npm dependency updates, bundler drift, version mismatch. | Excellent: Clean vanilla ES6 modules, standards-compliant Web APIs, predictable lifecycles. |

### Architectural Verdict
**Retain and modernize the FastAPI-native architecture.** We will implement:
1. **Public Marketing Site:** Clean, distinct multi-page templates (`landing.html`, `product.html`, `capabilities.html`, `how_it_works.html`, `trust.html`, `docs.html`, `get_started.html`).
2. **Application Workspace:** An enterprise application shell (`app.html`) with an interactive sidebar, breadcrumb system, and a lightweight client-side router (`app-router.js`) that supports direct URL deep-linking, browser Back/Forward navigation, and page refreshes for all `/app/...` routes.
3. **Unified Design System:** Shared CSS tokens (`design-system.css`) providing typography, dark surface elevation layers, semantic status badges, and responsive grids.

---

## 4. Design System Tokens (`design-system.css`)

### Color Palette
- **Background Root:** `#0B1020` (Deep midnight navy)
- **Secondary Background:** `#111827` (Card and panel slate)
- **Elevated Surfaces:** `#172033` (Dropdowns, modals, floating headers)
- **Surface Hover:** `#1E293B`
- **Border Default:** `#263249`
- **Border Focus:** `#6385F5`
- **Primary Text:** `#F3F5FA`
- **Secondary Text:** `#9AA7BC`
- **Muted Text:** `#64748B`

### Brand Accents
- **Primary Accent:** `#6385F5` (Electric indigo)
- **Secondary Accent:** `#39B9A5` (Verifiable teal)

### Semantic Colors
- **Success / Verified:** `#10B981` (Emerald)
- **Warning / Partial:** `#F59E0B` (Amber)
- **Critical / Contradicted:** `#EF4444` (Ruby red)
- **Information / Processing:** `#3B82F6` (Sky blue)

### Typography
- **Primary Font Family:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Monospace Code/Hash Font:** `'JetBrains Mono', 'Fira Code', monospace`

---

## 5. Route Architecture & Page Specifications

### Experience A: Public Website

| Route | Template | Key Sections & Content |
|---|---|---|
| `/` | `landing.html` | Sticky navigation, Hero ("Don't Trust the Claim. Verify the Reality."), 3 Problems, 3 Pillars, 10 Capabilities summary, 4-step How It Works, Interactive product preview, Final CTA, Footer. |
| `/product` | `product.html` | Comprehensive platform tour, Architecture overview, Ingestion layers, Evidence-to-decision pipeline, Enterprise readiness. |
| `/capabilities` | `capabilities.html` | Deep dive into all 10 analytical engines organized into 4 pillars (Autonomy, Architecture, Trust, Investment Intelligence). |
| `/how-it-works` | `how_it_works.html` | In-depth technical methodology: OTel GenAI normalization, gap analysis heuristic, deterministic metrics formulas, claim matrix evaluation, cryptographic sealing. |
| `/trust` | `trust.html` | Evidence provenance, SHA-256 custody, CycloneDX 1.6 compliance, dark-zone limits (35% rule), data redaction, tenant isolation posture. |
| `/docs` | `docs.html` | Documentation hub, Quickstart guides, REST API endpoints reference, CLI guide, data contracts. |
| `/get-started` | `get_started.html` | 4-step onboarding journey: Welcome -> Choose Path (Sample vs Custom) -> Target Configuration -> Launch Workspace. |

### Experience B: Application Workspace (`/app/...`)

The application workspace uses a master shell with sidebar, top breadcrumbs, and modular view controllers:

| Route | View Component | Core Functionality |
|---|---|---|
| `/app` | `OverviewView` | Live workspace metrics (Total Targets, Active Audits, Verified Claims, Avg Autonomy), recent target list, quick evaluation launcher. |
| `/app/projects` | `ProjectsListView` | Project catalog with real database records, search filter, scenario tags, status badges, sortable columns, and "New Evaluation" CTA. |
| `/app/projects/new` | `ProjectNewView` | Wizard to initialize evaluations using either preset benchmark scenarios (A–J) or custom telemetry payloads. |
| `/app/projects/{id}` | `ProjectDashboardView` | Project overview, target metadata, executive KPI strip, key findings, quick jump to analytical modules. |
| `/app/projects/{id}/claims` | `ClaimsModuleView` | Dedicated Claim Verification Matrix, status filter pills, observed vs stated delta, confidence interval inspection drawer. |
| `/app/projects/{id}/autonomy` | `AutonomyModuleView` | Autonomy Rate (AR), Human Intervention Rate (HIR), assisted tasks breakdown, reaction latency heuristic analysis. |
| `/app/projects/{id}/economics` | `EconomicsModuleView` | Cost Per Task (CPT), token usage breakdown, provider expenditure, Trust Tax overhead on automated evaluations. |
| `/app/projects/{id}/dependencies`| `DependenciesModuleView` | Vendor concentration (HHI), single points of failure (SPOF), failure cascade multipliers, retry loops. |
| `/app/projects/{id}/aibom` | `AIBOMModuleView` | Supply chain inventory (Models, Tools, Databases, Human Checkpoints), CycloneDX 1.6 / 1.5 JSON exporter with OWASP schema validation. |
| `/app/projects/{id}/evidence` | `EvidenceModuleView` | Proof & Evidence Graph, raw trace browser, span inspection, SHA-256 payload provenance references. |
| `/app/projects/{id}/security` | `SecurityModuleView` | Tool execution risk, privilege classification (read-only vs execute/write), unconstrained access analysis, blast radius. |
| `/app/projects/{id}/defensibility`| `DefensibilityModuleView`| AI Moat & Defensibility score, proprietary scaffolding index, data flywheel, estimated replication time and cost. |
| `/app/projects/{id}/stress-test` | `StressTestModuleView` | What-If Financial Simulator: interactive sliders for volume multiplier, provider price shock, labor rates, and gross margins. |
| `/app/projects/{id}/comparison` | `ComparisonModuleView` | Head-to-head diligence comparison between Target A and Target B across all dimensions. |
| `/app/projects/{id}/reports` | `ReportsModuleView` | Investment Committee (IC) Executive Memo, PDF Report download, JSON package, tamper-proof ZIP bundle, cryptographic seal. |
| `/app/integrations` | `IntegrationsView` | OpenTelemetry ingestion gateway details, MCP observer proxy status, browser extension bridge, API key management. |
| `/app/settings` | `SettingsView` | Workspace settings, tenant info, pricing rates (v2026_09), database diagnostic stats. |

---

## 6. Implementation Milestones

- **Milestone 8.1:** Repository Audit, Architecture Plan & Design Tokens (`docs/phase-8/architecture-and-implementation-plan.md`, `app/ui/static/css/design-system.css`).
- **Milestone 8.2:** Public Product Website (7 responsive pages: `/`, `/product`, `/capabilities`, `/how-it-works`, `/trust`, `/docs`, `/get-started`).
- **Milestone 8.3:** Enterprise Application Shell & Router (`app.html`, sidebar navigation, breadcrumbs, `app-router.js`).
- **Milestone 8.4:** Project Management Experience (`/app`, `/app/projects`, `/app/projects/new`, real database querying).
- **Milestone 8.5:** Dedicated Analytical Module Pages (Redesigning all 10 modules into distinct, deep-dive views).
- **Milestone 8.6:** Workflow, Telemetry Ingestion & Cryptographic Reporting (Interactive telemetry upload, instant bundle generation and verification).
- **Milestone 8.7:** Regression Testing, Responsiveness, Documentation & Quality Sign-Off.

---

## 7. Guardrail Compliance Verification

- **Preserve Existing Functionality:** All 35+ existing backend API endpoints and 10 analytical engines are retained without modification to analytical formulas.
- **No Fake Functionality:** Project counts, trace numbers, metrics, and claims are derived from actual SQLAlchemy models and database queries.
- **Test Integrity:** The 268 existing unit and integration tests must pass continuously across every milestone.
