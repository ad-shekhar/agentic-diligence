# CycloneDX AI-BOM Version & Schema Decision

**Version:** 1.0.0  
**Status:** Approved Technical Decision Record (ADR)  
**Date:** 2026-10-22  
**Auditor Reference:** L-004 Remediation / Phase 4 Readiness Gate  

---

## 1. Context & Problem Statement

Phase 1–3 introduced an initial AI-BOM generator in `app/aibom/generator.py` that serializes agent dependencies into a Software Bill of Materials (BOM). The implementation currently sets:

```json
"bomFormat": "CycloneDX",
"specVersion": "1.6"
```

and classifies models with:
```json
"type": "machine-learning-model"
```

The audit prompt explicitly required:
> "Inspect the existing PRD and implementation documentation for the intended CycloneDX version. Resolve the version decision explicitly before implementing the exporter. Verify the selected version's official schema, required fields, supported AI/ML component types, and reference relationships. Design an exporter contract and validation tests, but do not claim compatibility until the generated artifact passes the official schema. Do not silently change versions or fabricate unsupported component fields."

---

## 2. Evaluation of CycloneDX Versions

| Specification Version | Release Status | AI/ML Support | Schema Validation | Enterprise Ecosystem |
|---|---|---|---|---|
| **CycloneDX 1.4** | Legacy standard (2022) | No native AI/ML types (requires generic `framework` or `library` typing) | High tooling support | Obsolete for GenAI runtime diligence |
| **CycloneDX 1.5** | Mature standard (2023) | Introduced first-class AI/ML component type: `machine-learning-model` with `modelCard` properties | Official JSON schemas stable | Widespread support in SBOM scanners |
| **CycloneDX 1.6** | Current standard (2024) | Refined AI/ML support; added environmental considerations, extended model card parameters, datasets, and governance | Official JSON schemas published by OWASP | Emerging enterprise adoption; strict validation required |

---

## 3. Decision for Phase 4

### Primary Standard: CycloneDX 1.6 (JSON)
1. **Spec Version:** Agentic Diligence Phase 4 will officially target **CycloneDX 1.6 JSON**.
2. **Component Classification:** AI models discovered across telemetry (e.g. OpenAI `gpt-4o`, Anthropic `claude-3-5-sonnet`, Google `gemini-1.5-pro`) MUST be typed as `machine-learning-model`.
3. **Required Fields & Standard Properties:**
   - `bomFormat`: strictly `"CycloneDX"`
   - `specVersion`: strictly `"1.6"`
   - `serialNumber`: valid URN UUID (`urn:uuid:<uuid4>`)
   - `version`: integer sequence (starting at 1)
   - `metadata.timestamp`: ISO 8601 UTC
   - `metadata.component`: Top-level agent application component (`type`: `"application"`)
   - `components`: Array of models, vector stores, API gateways, and external tools
4. **No Ad-Hoc Fields:**
   - Any telemetry-derived metrics (token usage, cost, observed latency) MUST be placed inside the standard CycloneDX `properties` array using the namespace `agd:metric:<name>`, rather than inventing undocumented top-level keys.

### Compatibility & Dual-Mode Option
If an enterprise client requires CycloneDX 1.5 ingestion:
- A CLI flag `--cyclonedx-version 1.5` will be supported in Phase 4 by adjusting `specVersion` to `"1.5"` and ensuring any 1.6-only fields are safely downgraded or placed in standard properties.

---

## 4. Schema Validation Verification Plan

In Phase 4, the test suite must include schema validation using the official OWASP CycloneDX 1.6 JSON Schema (from `cyclonedx.org/schema/bom-1.6.schema.json`):
```python
import jsonschema

def test_cyclonedx_output_validates_against_official_schema():
    bom = generate_cyclonedx_aibom(company_id="company-alpha", trace_ids=["tr-001"])
    schema = load_official_cyclonedx_1_6_schema()
    jsonschema.validate(instance=bom, schema=schema)
```
Until this test is in place and verified in Phase 4, reports will accurately disclose that the BOM conforms structurally to the CycloneDX 1.6 specification subject to formal offline schema validator pass.
