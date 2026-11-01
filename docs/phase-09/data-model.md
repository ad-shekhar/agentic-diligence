# Phase 9 Data Model Specification
**Document:** `docs/phase-09/data-model.md`  
**Phase:** 9 — Complete Product Workflows  

---

## 1. Relational Entities & Schema Definitions

### 1.1 `Project` (`projects` table)
The primary organizational unit for technical due diligence assessments. Associates a diligence scope with a target company.

```python
class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_system = Column(String(255), nullable=True)
    target_type = Column(String(100), default="autonomous_agent", nullable=False)
    framework = Column(String(100), nullable=True)
    assessment_scope = Column(Text, nullable=True)
    evaluation_objective = Column(Text, nullable=True)
    status = Column(String(50), default="ACTIVE", nullable=False)  # ACTIVE, ARCHIVED, DRAFT
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant", backref="projects")
    company = relationship("Company", backref="projects")
    assessments = relationship("Assessment", back_populates="project", cascade="all, delete-orphan")
    ingestion_jobs = relationship("IngestionJob", back_populates="project", cascade="all, delete-orphan")
    activities = relationship("ProjectActivity", back_populates="project", cascade="all, delete-orphan")
```

---

### 1.2 `Assessment` (`assessments` table)
Represents an execution run of the diligence analysis pipeline against a project's evidence base.

```python
class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="PENDING", nullable=False) # PENDING, RUNNING, COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED
    selected_engines = Column(JSON, nullable=True)
    summary_findings = Column(JSON, nullable=True) # Red/yellow flags, deal verdict, overall confidence
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    project = relationship("Project", back_populates="assessments")
    company = relationship("Company", backref="assessments")
    engine_executions = relationship("AssessmentEngineExecution", back_populates="assessment", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="assessment", cascade="all, delete-orphan")
    reports = relationship("Report", backref="assessment")
```

---

### 1.3 `AssessmentEngineExecution` (`assessment_engine_executions` table)
Records the execution state, runtime metrics, and persisted output for each individual analytical engine within an assessment.

```python
class AssessmentEngineExecution(Base):
    __tablename__ = "assessment_engine_executions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    engine_key = Column(String(50), nullable=False) # claims, autonomy, economics, dependencies, aibom, evidence, security, defensibility, stress_test, comparison
    engine_name = Column(String(100), nullable=False)
    status = Column(String(50), default="PENDING", nullable=False) # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    duration_ms = Column(Float, default=0.0)
    result_json = Column(JSON, nullable=True)
    error_details = Column(Text, nullable=True)
    evidence_count = Column(Integer, default=0)
    executed_at = Column(DateTime, default=utc_now, nullable=False)

    assessment = relationship("Assessment", back_populates="engine_executions")
```

---

### 1.4 `Finding` (`findings` table)
Structured risk or integrity findings extracted from analytical engine results.

```python
class Finding(Base):
    __tablename__ = "findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    engine_key = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False) # CRITICAL, HIGH, MEDIUM, LOW, INFO
    confidence = Column(String(50), default="Calculated")
    evidence_references = Column(JSON, nullable=True) # list of trace/span IDs or hashes
    recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    assessment = relationship("Assessment", back_populates="findings")
    project = relationship("Project", backref="findings")
```

---

### 1.5 `IngestionJob` (`ingestion_jobs` table)
Tracks file uploads, parse jobs, and batch ingestion history.

```python
class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, default=0)
    format = Column(String(50), default="otlp_json", nullable=False)
    payload_hash = Column(String(64), nullable=True)
    status = Column(String(50), default="PROCESSING", nullable=False) # SUCCESS, FAILED, PARTIAL, DUPLICATE
    traces_count = Column(Integer, default=0)
    spans_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    project = relationship("Project", back_populates="ingestion_jobs")
```

---

### 1.6 `ProjectActivity` (`project_activities` table)
Maintains an immutable timeline of diligence lifecycle events.

```python
class ProjectActivity(Base):
    __tablename__ = "project_activities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    activity_type = Column(String(100), nullable=False) # PROJECT_CREATED, TELEMETRY_INGESTED, ASSESSMENT_RUN, REPORT_GENERATED, PROJECT_UPDATED
    description = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    project = relationship("Project", back_populates="activities")
```
