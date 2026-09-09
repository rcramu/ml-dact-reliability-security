"""Pydantic request models (response bodies are typed dicts — see routers/serializers)."""
from pydantic import BaseModel, Field


class TriggerTrainingRequest(BaseModel):
    trigger_type: str = Field(default="manual", description="drift | performance | schedule | data_availability | manual")
    scenario: str = Field(default="healthy", description="healthy | volume_anomaly | feature_drift | label_imbalance | regression")
    trigger_detail: str = Field(default="", description="Free-text reason, e.g. 'PSI=0.24 on support_tickets_90d'")


class RollbackRequest(BaseModel):
    reason: str = Field(default="manual rollback requested from UI")


class DriftCheckRequest(BaseModel):
    profile: str = Field(default="stable", description="stable | drifted | severe_drift — simulated production traffic profile")
    auto_retrain: bool = Field(default=True, description="If drift is HIGH and evaluation is BAD/UNKNOWN, automatically trigger retraining")


class PredictRequest(BaseModel):
    tenure_months: int = Field(default=12, ge=0, le=120)
    monthly_charges: float = Field(default=70.0, ge=0)
    age: int = Field(default=35, ge=18, le=100)
    support_tickets_90d: int = Field(default=1, ge=0)
    usage_hours_week: float = Field(default=12.0, ge=0)
    is_month_to_month: bool = False
    autopay_enabled: bool = True
    has_addons: bool = False
