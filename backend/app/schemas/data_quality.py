from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any, List
from app.models.data_quality import DataQualityIssueType, DataQualitySeverity, DataQualityIssueStatus, ReconciliationStatus


class DataQualityIssueBase(BaseModel):
    issue_type: DataQualityIssueType
    severity: DataQualitySeverity
    affected_module: str
    affected_record_id: Optional[str] = None
    affected_record_type: Optional[str] = None
    description: str
    details: Optional[Dict[str, Any]] = None


class DataQualityIssueResponse(BaseModel):
    id: UUID
    company_id: UUID
    issue_type: DataQualityIssueType
    severity: DataQualitySeverity
    affected_module: str
    affected_record_id: Optional[str] = None
    affected_record_type: Optional[str] = None
    description: str
    details: Optional[Dict[str, Any]] = None
    status: DataQualityIssueStatus
    detected_at: datetime
    detected_by_run_id: Optional[UUID] = None
    resolved_by: Optional[UUID] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    previous_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataQualityIssueListResponse(BaseModel):
    data: List[DataQualityIssueResponse]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class DataQualityIssueUpdate(BaseModel):
    status: DataQualityIssueStatus
    resolution_note: Optional[str] = None


class ReconciliationRunResponse(BaseModel):
    id: UUID
    company_id: UUID
    execution_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    triggered_by: Optional[UUID] = None
    triggered_by_name: Optional[str] = None
    records_checked: int
    issues_detected: int
    issues_resolved: int
    failed_checks: int
    status: ReconciliationStatus
    error_message: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ReconciliationRunListResponse(BaseModel):
    data: List[ReconciliationRunResponse]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class ReconciliationTriggerResponse(BaseModel):
    execution_id: str
    status: ReconciliationStatus
    message: str
    issues_detected: int = 0


class DataQualityDashboardResponse(BaseModel):
    total_records_checked: int = 0
    valid_records: int = 0
    records_with_warnings: int = 0
    records_with_errors: int = 0
    unresolved_issues: int = 0
    last_reconciliation_time: Optional[datetime] = None
    issues_by_status: Dict[str, int] = {}
    issues_by_severity: Dict[str, int] = {}
    issues_by_module: Dict[str, int] = {}


class DataQualityIssueHistoryResponse(BaseModel):
    id: UUID
    issue_id: UUID
    company_id: UUID
    previous_status: Optional[str] = None
    new_status: str
    changed_by: Optional[UUID] = None
    changed_by_name: Optional[str] = None
    resolution_note: Optional[str] = None
    changed_at: datetime
    model_config = {"from_attributes": True}


class DataQualityIssueDetailResponse(DataQualityIssueResponse):
    history: List[DataQualityIssueHistoryResponse] = []
    related_records: Optional[Dict[str, Any]] = None
