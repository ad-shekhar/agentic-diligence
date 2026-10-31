"""
Authentication and Tenant Authorization Boundary (Phase 7.1 — Milestone A).

Provides secure service-to-service API key authentication, tenant isolation,
cryptographic key hashing, and scope enforcement for diligence endpoints.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.models import Company, Tenant, TenantApiKey
from app.db.session import get_db


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
HTTP_BEARER = HTTPBearer(auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """Computes SHA-256 digest of plaintext API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_raw_key() -> str:
    """Generates an unguessable high-entropy service API key."""
    return f"agd_live_{secrets.token_hex(24)}"


@dataclass(frozen=True)
class AuthenticatedContext:
    """Security context establishing authenticated caller identity and permissions."""
    tenant_id: str
    company_id: Optional[str]
    api_key_id: str
    key_prefix: str
    scopes: List[str]

    def has_scope(self, required_scope: str) -> bool:
        """Checks if key possesses the requested scope or admin wildcard."""
        return required_scope in self.scopes or "admin" in self.scopes

    def can_access_company(self, target_company_id: str, db: Session) -> bool:
        """
        Enforces tenant/company isolation boundaries.
        Returns True if the authenticated credential is authorized for the target company.
        """
        if not target_company_id:
            return False

        # If key is scoped to a single company, strict equality is required
        if self.company_id is not None:
            return self.company_id == target_company_id

        # If tenant-wide key (company_id is None), verify company belongs to this tenant
        company = db.query(Company).filter(Company.id == target_company_id).first()
        if company is not None:
            return company.tenant_id == self.tenant_id

        # Unregistered company not associated with this tenant
        return False


def get_authenticated_context(
    request: Request,
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    bearer_token: Optional[HTTPAuthorizationCredentials] = Security(HTTP_BEARER),
    db: Session = Depends(get_db),
) -> AuthenticatedContext:
    """
    FastAPI dependency validating API key credentials and constructing caller context.
    Raises 401 Unauthorized on missing, invalid, expired, or revoked keys.
    """
    raw_key: Optional[str] = None

    if api_key_header:
        raw_key = api_key_header.strip()
    elif bearer_token and bearer_token.credentials:
        raw_key = bearer_token.credentials.strip()

    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials missing. Provide 'X-API-Key' or 'Authorization: Bearer <key>' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Hash the candidate key to look up against stored digest
    key_hash = hash_api_key(raw_key)

    api_key_record = (
        db.query(TenantApiKey)
        .filter(TenantApiKey.key_hash == key_hash, TenantApiKey.is_active.is_(True))
        .first()
    )

    if not api_key_record:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    now_utc = datetime.now(timezone.utc)

    # Check expiration
    if api_key_record.expires_at is not None:
        exp = api_key_record.expires_at
        if not exp.tzinfo:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now_utc:
            raise HTTPException(
                status_code=401,
                detail="API key has expired.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # Update last_used_at timestamp non-blockingly
    try:
        api_key_record.last_used_at = now_utc
        db.commit()
    except Exception:
        db.rollback()

    raw_scopes = api_key_record.allowed_scopes or "evidence:read,evidence:write"
    scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()]

    return AuthenticatedContext(
        tenant_id=api_key_record.tenant_id,
        company_id=api_key_record.company_id,
        api_key_id=api_key_record.id,
        key_prefix=api_key_record.key_prefix,
        scopes=scopes,
    )


def generate_api_key(
    db: Session,
    tenant_id: str,
    company_id: Optional[str] = None,
    name: str = "Production API Key",
    scopes: str = "evidence:read,evidence:write",
    expires_at: Optional[datetime] = None,
) -> Tuple[str, TenantApiKey]:
    """
    Creates a new TenantApiKey record in the database.
    Returns the plaintext raw key (displayed once) and the saved ORM model.
    """
    raw_key = generate_raw_key()
    key_hash = hash_api_key(raw_key)
    prefix = raw_key[:12]

    key_record = TenantApiKey(
        key_hash=key_hash,
        key_prefix=prefix,
        tenant_id=tenant_id,
        company_id=company_id,
        name=name,
        is_active=True,
        allowed_scopes=scopes,
        expires_at=expires_at,
    )
    db.add(key_record)
    db.commit()
    db.refresh(key_record)
    return raw_key, key_record


def create_test_api_key(
    db: Session,
    company_id: str,
    tenant_id: Optional[str] = None,
    scopes: str = "evidence:read,evidence:write",
    name: str = "Test API Key",
) -> Tuple[str, TenantApiKey]:
    """
    Test helper ensuring Tenant and Company exist before provisioning an API key.
    """
    # 1. Ensure Tenant exists
    t_id = tenant_id or f"tenant-for-{company_id}"
    tenant = db.query(Tenant).filter(Tenant.id == t_id).first()
    if not tenant:
        tenant = Tenant(id=t_id, name=f"Tenant for {company_id}")
        db.add(tenant)
        db.flush()

    # 2. Ensure Company exists
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        company = Company(
            id=company_id,
            tenant_id=tenant.id,
            name=f"Company {company_id}",
        )
        db.add(company)
        db.flush()
    elif company.tenant_id != tenant.id:
        company.tenant_id = tenant.id
        db.flush()

    # 3. Provision API key
    return generate_api_key(
        db=db,
        tenant_id=tenant.id,
        company_id=company_id,
        name=name,
        scopes=scopes,
    )
