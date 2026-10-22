# Phase 4 Data Contracts

**Version:** 1.0.0  
**Status:** Approved Post-Audit Specification  
**Date:** 2026-10-22  
**Dependency:** Phase 1–3 Audit Complete (166 passing tests)  

---

## 1. Claim Verification Matrix Schema (v1.0)

The Claim Verification Matrix provides a deterministic, auditable link between a vendor's pitch-deck or marketing assertion and the empirical runtime evidence gathered across OpenTelemetry traces.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ClaimVerificationMatrixEntry",
  "type": "object",
  "required": [
    "claim_id",
    "verbatim_claim_text",
    "claim_source",
    "source_trust_level",
    "target_dimension",
    "target_operator",
    "target_threshold",
    "target_units",
    "metric_name",
    "metric_version",
    "metric_denominator",
    "observed_epistemic_value",
    "verification_verdict",
    "verdict_reason",
    "evidence_references",
    "limitations_and_assumptions"
  ],
  "properties": {
    "claim_id": {
      "type": "string",
      "pattern": "^CLM-[0-9]{3,6}$"
    },
    "verbatim_claim_text": {
      "type": "string"
    },
    "claim_source": {
      "type": "string",
      "description": "Pitch deck slide, whitepaper, commercial contract"
    },
    "source_trust_level": {
      "type": "string",
      "enum": ["T0", "T1", "T2", "T3"]
    },
    "target_dimension": {
      "type": "string",
      "enum": [
        "autonomy",
        "unit_economics",
        "provider_concentration",
        "reliability",
        "evaluation_overhead",
        "least_privilege",
        "cost_allocation",
        "evidence_coverage"
      ]
    },
    "target_operator": {
      "type": "string",
      "enum": [">=", "<=", "==", "<", ">", "in_range"]
    },
    "target_threshold": {
      "type": ["number", "array"]
    },
    "target_units": {
      "type": "string"
    },
    "metric_name": {
      "type": "string"
    },
    "metric_version": {
      "type": "string"
    },
    "metric_denominator": {
      "type": "string",
      "description": "Explicit declaration: total_tasks, total_spans, total_cost_usd, etc."
    },
    "observed_epistemic_value": {
      "type": "object",
      "required": ["value", "tag", "trust_level", "sample_size", "unknown_fraction"],
      "properties": {
        "value": {"type": ["number", "null"]},
        "tag": {"type": "string", "enum": ["OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"]},
        "trust_level": {"type": "string", "enum": ["T0", "T1", "T2", "T3"]},
        "bounds": {
          "type": ["object", "null"],
          "properties": {
            "lower": {"type": "number"},
            "point": {"type": "number"},
            "upper": {"type": "number"}
          }
        },
        "sample_size": {"type": "integer", "minimum": 0},
        "unknown_fraction": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "notes": {"type": "string"}
      }
    },
    "verification_verdict": {
      "type": "string",
      "enum": [
        "VERIFIED",
        "PARTIALLY_VERIFIED",
        "CONTRADICTED",
        "INSUFFICIENT_EVIDENCE",
        "UNVERIFIED"
      ]
    },
    "verdict_reason": {
      "type": "string"
    },
    "evidence_references": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["artifact_name", "artifact_sha256", "trace_ids"],
        "properties": {
          "artifact_name": {"type": "string"},
          "artifact_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "trace_ids": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "limitations_and_assumptions": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

---

## 2. Canonical Diligence Report Schema (v1.0)

Separates canonical calculation facts from formatting/presentation layers. Downstream renderers (Markdown, HTML, PDF) parse this schema to produce human-facing diligence documents.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CanonicalDiligenceReport",
  "type": "object",
  "required": [
    "schema_version",
    "report_id",
    "generated_at_utc",
    "subject_company",
    "evaluation_scope",
    "executive_summary",
    "signals",
    "claim_matrix",
    "provenance_trail"
  ],
  "properties": {
    "schema_version": {"type": "string", "const": "1.0.0"},
    "report_id": {"type": "string"},
    "generated_at_utc": {"type": "string", "format": "date-time"},
    "subject_company": {
      "type": "object",
      "required": ["company_id", "company_name"],
      "properties": {
        "company_id": {"type": "string"},
        "company_name": {"type": "string"}
      }
    },
    "evaluation_scope": {
      "type": "object",
      "required": [
        "total_traces_analyzed",
        "total_spans_analyzed",
        "total_tasks_segmented",
        "evidence_trust_summary",
        "unobserved_intervals_count"
      ],
      "properties": {
        "total_traces_analyzed": {"type": "integer"},
        "total_spans_analyzed": {"type": "integer"},
        "total_tasks_segmented": {"type": "integer"},
        "evidence_trust_summary": {"type": "object"},
        "unobserved_intervals_count": {"type": "integer"}
      }
    },
    "executive_summary": {
      "type": "object",
      "required": ["overall_verdict", "headline_findings", "epistemic_confidence_level"],
      "properties": {
        "overall_verdict": {"type": "string"},
        "headline_findings": {"type": "array", "items": {"type": "string"}},
        "epistemic_confidence_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW", "UNVERIFIED"]}
      }
    },
    "signals": {
      "type": "object",
      "required": [
        "autonomy",
        "unit_economics",
        "evaluation_overhead",
        "cost_allocation",
        "provider_concentration",
        "least_privilege",
        "reliability",
        "evidence_coverage"
      ],
      "additionalProperties": true
    },
    "claim_matrix": {
      "type": "array",
      "items": {"$ref": "#/definitions/ClaimVerificationMatrixEntry"}
    },
    "provenance_trail": {
      "type": "object",
      "required": ["manifest_sha256", "trace_payload_digests"],
      "properties": {
        "manifest_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "trace_payload_digests": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

---

## 3. Epistemic Tagging & Invariant Rules

1. **No Silent Upgrades:** If any underlying span in a segmented task has trust level $T$, the task trust level $\le T$.
2. **Bounds Invariance:** Any bounded metric MUST adhere to $\text{lower} \le \text{point} \le \text{upper}$.
3. **Explicit Unknowns:** An uninstrumented or unobserved interval must NEVER be counted as autonomous; it must increment `unknown_tasks` and widen bounds.
4. **Scale Transparency:** HHI is stored on a 0–10,000 scale. Any normalized fraction must explicitly label its denominator.
