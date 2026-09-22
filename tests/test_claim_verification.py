import pytest
from app.db.models import VerificationStatus, ConfidenceLevel
from app.evidence.verifier import verify_autonomy_claim, verify_economics_claim, verify_dependency_claim

def test_verify_autonomy_claim_statuses():
    # Fully Verified
    v_stat, _, conf = verify_autonomy_claim("95% Autonomous", 95.0, 96.0, 500)
    assert v_stat == VerificationStatus.VERIFIED
    assert conf == ConfidenceLevel.HIGH
    
    # Partially Verified
    v_stat, _, conf = verify_autonomy_claim("95% Autonomous", 95.0, 75.6, 500)
    assert v_stat == VerificationStatus.PARTIALLY_VERIFIED
    
    # Contradicted
    v_stat, _, conf = verify_autonomy_claim("95% Autonomous", 95.0, 20.0, 500)
    assert v_stat == VerificationStatus.CONTRADICTED
    
    # Insufficient Evidence
    v_stat, _, conf = verify_autonomy_claim("95% Autonomous", 95.0, 95.0, 5)
    assert v_stat == VerificationStatus.INSUFFICIENT_EVIDENCE
    assert conf == ConfidenceLevel.UNVERIFIED

def test_verify_economics_claim_statuses():
    # Verified
    v_stat, _, _ = verify_economics_claim("$0.0010 per task", 0.0010, 0.0009, 500)
    assert v_stat == VerificationStatus.VERIFIED
    
    # Contradicted (4.1x higher)
    v_stat, _, _ = verify_economics_claim("$0.0010 per task", 0.0010, 0.0041, 500)
    assert v_stat == VerificationStatus.CONTRADICTED

def test_verify_dependency_claim_statuses():
    # Contradicted (OpenAI 98% share)
    v_stat, _, _ = verify_dependency_claim("Multi-cloud resilient", 0.96, 98.0)
    assert v_stat == VerificationStatus.CONTRADICTED
    
    # Verified (Balanced)
    v_stat, _, _ = verify_dependency_claim("Multi-cloud resilient", 0.33, 34.0)
    assert v_stat == VerificationStatus.VERIFIED
