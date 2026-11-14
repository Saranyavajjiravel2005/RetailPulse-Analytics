from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class WorkflowRequestType(str, enum.Enum):
    STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
    PRODUCT_DEACTIVATION = "PRODUCT_DEACTIVATION"
    PRODUCT_PRICE_CHANGE = "PRODUCT_PRICE_CHANGE"
    CUSTOMER_INFO_CHANGE = "CUSTOMER_INFO_CHANGE"
    INVENTORY_IMPORT_APPROVAL = "INVENTORY_IMPORT_APPROVAL"


class WorkflowStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkflowPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class WorkflowRequest(Base):
    __tablename__ = "workflow_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_number = Column(String, nullable=False, unique=True, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type = Column(SQLEnum(WorkflowRequestType), nullable=False, index=True)
    priority = Column(SQLEnum(WorkflowPriority), nullable=False, default=WorkflowPriority.MEDIUM, index=True)
    status = Column(SQLEnum(WorkflowStatus), nullable=False, default=WorkflowStatus.PENDING_APPROVAL, index=True)

    title = Column(String, nullable=False)
    reason = Column(Text, nullable=False)

    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_by_name = Column(String, nullable=True)

    related_entity_type = Column(String, nullable=False)  # Product, Customer, Inventory, ImportHistory
    related_entity_id = Column(String, nullable=True, index=True)
    related_entity_name = Column(String, nullable=True)

    current_values = Column(JSON, nullable=True, default=dict)
    requested_values = Column(JSON, nullable=False, default=dict)

    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_name = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_comment = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    execution_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    company = relationship("Company", lazy="raise_on_sql")
    requester = relationship("User", foreign_keys=[requested_by], lazy="raise_on_sql")
    reviewer = relationship("User", foreign_keys=[reviewed_by], lazy="raise_on_sql")
    history = relationship("WorkflowHistory", back_populates="request", cascade="all, delete-orphan", order_by="WorkflowHistory.created_at.asc()", lazy="raise_on_sql")


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("workflow_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String, nullable=False)  # CREATED, SUBMITTED, VIEWED, APPROVED, REJECTED, CANCELLED, EXECUTED
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String, nullable=False)
    actor_role = Column(String, nullable=True)

    previous_status = Column(SQLEnum(WorkflowStatus), nullable=True)
    new_status = Column(SQLEnum(WorkflowStatus), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    request = relationship("WorkflowRequest", back_populates="history", lazy="raise_on_sql")


class WorkflowConfiguration(Base):
    __tablename__ = "workflow_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type = Column(SQLEnum(WorkflowRequestType), nullable=False, index=True)
    approver_role = Column(String, nullable=False, default="COMPANY_ADMIN")
    is_approval_required = Column(Boolean, nullable=False, default=True)
    allow_self_approval = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="ACTIVE")  # ACTIVE, INACTIVE
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", lazy="raise_on_sql")

