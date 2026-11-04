"""
Phase 9: Project Lifecycle Management Service.

Provides complete project management, target metadata association,
and activity audit trail without duplicating underlying Company entities.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from app.db.models import Project, ProjectActivity, Company, Tenant, Trace, Assessment, Report


def get_default_tenant(db: Session) -> Tenant:
    """Retrieves or provisions the default workspace tenant."""
    tenant = db.query(Tenant).first()
    if not tenant:
        tenant = Tenant(name="Default Workspace Tenant")
        db.add(tenant)
        db.flush()
    return tenant


def get_or_create_project_for_company(db: Session, company: Company) -> Project:
    """
    Ensures every existing or newly ingested company has an associated Project,
    guaranteeing seamless backward compatibility across historical evaluations.
    """
    project = db.query(Project).filter(Project.company_id == company.id).first()
    if not project:
        tenant_id = company.tenant_id or get_default_tenant(db).id
        project = Project(
            tenant_id=tenant_id,
            company_id=company.id,
            name=f"{company.name} Due Diligence",
            target_system=company.name,
            target_type="autonomous_agent",
            framework="OpenTelemetry GenAI",
            description=f"Technical diligence project evaluating {company.name}.",
            status="ACTIVE",
        )
        db.add(project)
        db.flush()
        
        # Log initial creation activity
        log_project_activity(
            db,
            project.id,
            activity_type="PROJECT_CREATED",
            description=f"Diligence project initialized for target {company.name}."
        )
        db.commit()
    return project


def create_project(
    db: Session,
    name: str,
    target_name: str,
    target_system: Optional[str] = None,
    target_type: str = "autonomous_agent",
    framework: Optional[str] = None,
    description: Optional[str] = None,
    assessment_scope: Optional[str] = None,
    evaluation_objective: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Project:
    """
    Creates a genuine diligence project with an associated target Company.
    Does NOT substitute or inject synthetic benchmark data.
    """
    if not tenant_id:
        tenant = get_default_tenant(db)
        tenant_id = tenant.id

    # Create target Company entity
    company = Company(
        name=target_name,
        tenant_id=tenant_id,
    )
    db.add(company)
    db.flush()

    project = Project(
        tenant_id=tenant_id,
        company_id=company.id,
        name=name,
        target_system=target_system or target_name,
        target_type=target_type,
        framework=framework,
        description=description,
        assessment_scope=assessment_scope,
        evaluation_objective=evaluation_objective,
        status="ACTIVE",
    )
    db.add(project)
    db.flush()

    log_project_activity(
        db,
        project.id,
        activity_type="PROJECT_CREATED",
        description=f"Project '{name}' created for target '{target_name}'."
    )
    db.commit()
    return project


def list_projects(
    db: Session,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Lists all accessible projects, ensuring legacy companies are represented.
    Optimized with batch counts and joined queries to eliminate N+1 database queries.
    """
    from sqlalchemy import func

    # Auto-seed projects for any orphan companies
    orphan_companies = (
        db.query(Company)
        .outerjoin(Project, Company.id == Project.company_id)
        .filter(Project.id == None)
        .all()
    )
    if orphan_companies:
        for c in orphan_companies:
            get_or_create_project_for_company(db, c)

    query = db.query(Project, Company.name.label("comp_name")).join(Company, Project.company_id == Company.id)

    if status and status.upper() != "ALL":
        query = query.filter(Project.status == status.upper())
    elif not status:
        # Default excludes ARCHIVED unless explicitly requested or status=ALL
        query = query.filter(Project.status != "ARCHIVED")

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Project.name.ilike(term),
                Project.target_system.ilike(term),
                Company.name.ilike(term)
            )
        )

    projects_with_comp = query.order_by(desc(Project.created_at)).all()
    if not projects_with_comp:
        return []

    # Batch compute trace counts and assessment counts in 2 single queries
    trace_counts = dict(db.query(Trace.company_id, func.count(Trace.id)).group_by(Trace.company_id).all())
    assessment_counts = dict(db.query(Assessment.project_id, func.count(Assessment.id)).group_by(Assessment.project_id).all())

    # Batch load latest assessments
    latest_assessments = {}
    for a in db.query(Assessment).order_by(desc(Assessment.created_at)).all():
        if a.project_id not in latest_assessments:
            latest_assessments[a.project_id] = a

    results = []
    for p, comp_name in projects_with_comp:
        la = latest_assessments.get(p.id)
        results.append({
            "id": p.id,
            "company_id": p.company_id,
            "name": p.name,
            "target_name": comp_name or p.target_system,
            "target_system": p.target_system,
            "target_type": p.target_type,
            "framework": p.framework,
            "description": p.description,
            "status": p.status,
            "trace_count": trace_counts.get(p.company_id, 0),
            "assessment_count": assessment_counts.get(p.id, 0),
            "last_assessment_status": la.status if la else None,
            "last_assessment_at": (
                la.completed_at.isoformat()
                if la and la.completed_at
                else (la.created_at.isoformat() if la else None)
            ),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return results


def get_project_by_id_or_company(db: Session, identifier: str) -> Optional[Project]:
    """Resolves project by either project.id or company_id for robust URL compatibility."""
    project = db.query(Project).filter(Project.id == identifier).first()
    if not project:
        # Try resolving by company_id
        company = db.query(Company).filter(Company.id == identifier).first()
        if company:
            project = get_or_create_project_for_company(db, company)
    return project


def update_project(
    db: Session,
    project_id: str,
    update_data: Dict[str, Any]
) -> Project:
    """Updates editable project metadata."""
    project = get_project_by_id_or_company(db, project_id)
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    allowed_fields = [
        "name", "description", "target_system", "target_type",
        "framework", "assessment_scope", "evaluation_objective", "status"
    ]
    changed = []
    for field in allowed_fields:
        if field in update_data and update_data[field] is not None:
            setattr(project, field, update_data[field])
            changed.append(field)

    if changed:
        project.updated_at = datetime.now(timezone.utc)
        log_project_activity(
            db,
            project.id,
            activity_type="PROJECT_UPDATED",
            description=f"Updated project fields: {', '.join(changed)}."
        )
        db.commit()
    return project


def archive_project(db: Session, project_id: str) -> Project:
    """Soft-archives a project."""
    project = get_project_by_id_or_company(db, project_id)
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    project.status = "ARCHIVED"
    project.updated_at = datetime.now(timezone.utc)
    log_project_activity(
        db,
        project.id,
        activity_type="PROJECT_ARCHIVED",
        description="Project moved to archive."
    )
    db.commit()
    return project


def log_project_activity(
    db: Session,
    project_id: str,
    activity_type: str,
    description: str,
    metadata_json: Optional[Dict[str, Any]] = None
) -> ProjectActivity:
    """Records an activity event on the project timeline."""
    activity = ProjectActivity(
        project_id=project_id,
        activity_type=activity_type,
        description=description,
        metadata_json=metadata_json,
    )
    db.add(activity)
    db.flush()
    return activity


def get_project_activities(db: Session, project_id: str) -> List[Dict[str, Any]]:
    """Retrieves chronological activity timeline."""
    acts = (
        db.query(ProjectActivity)
        .filter(ProjectActivity.project_id == project_id)
        .order_by(desc(ProjectActivity.created_at))
        .all()
    )
    return [
        {
            "id": a.id,
            "activity_type": a.activity_type,
            "description": a.description,
            "metadata": a.metadata_json,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in acts
    ]

