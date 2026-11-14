from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from app.models.workflow import WorkflowRequestType, WorkflowStatus, WorkflowPriority


class WorkflowRequestCreate(BaseModel):
    request_type: WorkflowRequestType
    title: str = Field(..., min_length=3, max_length=200)
    reason: str = Field(..., min_length=5)
    priority: WorkflowPriority = WorkflowPriority.MEDIUM
    related_entity_type: str = Field(..., description="Product, Customer, Inventory, ImportHistory")
    related_entity_id: Optional[str] = None
    related_entity_name: Optional[str] = None
    requested_values: dict[str, Any]


class WorkflowActionRequest(BaseModel):
    comment: Optional[str] = None
    rejection_reason: Optional[str] = None


class WorkflowHistoryResponse(BaseModel):
    id: UUID
    request_id: UUID
    action: str
    actor_id: Optional[UUID] = None
    actor_name: str
    actor_role: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRequestResponse(BaseModel):
    id: UUID
    request_number: str
    company_id: UUID
    request_type: str
    priority: str
    status: str
    title: str
    reason: str
    requested_by: Optional[UUID] = None
    requested_by_name: Optional[str] = None
    related_entity_type: str
    related_entity_id: Optional[str] = None
    related_entity_name: Optional[str] = None
    current_values: Optional[dict[str, Any]] = None
    requested_values: dict[str, Any]
    diff_values: Optional[dict[str, Any]] = None
    reviewed_by: Optional[UUID] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None
    rejection_reason: Optional[str] = None
    execution_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    history: Optional[list[WorkflowHistoryResponse]] = None

    model_config = {"from_attributes": True}


class WorkflowConfigurationResponse(BaseModel):
    id: UUID
    company_id: UUID
    request_type: str
    approver_role: str
    is_approval_required: bool
    allow_self_approval: bool
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowConfigurationUpdate(BaseModel):
    approver_role: Optional[str] = None
    is_approval_required: Optional[bool] = None
    allow_self_approval: Optional[bool] = None
    status: Optional[str] = None


class WorkflowSummaryCounts(BaseModel):
    pending_count: int
    approved_count: int
    rejected_count: int
    my_requests_count: int
    total_count: int
    by_type: dict[str, int]

