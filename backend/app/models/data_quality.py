from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class DataQualityIssueType(str, enum.Enum):
    SALE_EXCEEDS_STOCK = "SALE_EXCEEDS_STOCK"
    INVENTORY_INCONSISTENT_WITH_MOVEMENTS = "INVENTORY_INCONSISTENT_WITH_MOVEMENTS"
    SALE_INACTIVE_OR_MISSING_PRODUCT = "SALE_INACTIVE_OR_MISSING_PRODUCT"
    SALE_INVALID_CUSTOMER = "SALE_INVALID_CUSTOMER"
    DUPLICATE_OR_INVALID_PRODUCT_SKU = "DUPLICATE_OR_INVALID_PRODUCT_SKU"
    MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO = "MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO"
    STOCK_MOVEMENT_INCONSISTENT = "STOCK_MOVEMENT_INCONSISTENT"
    REPORT_TOTAL_MISMATCH = "REPORT_TOTAL_MISMATCH"
    OTHER = "OTHER"


class DataQualitySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DataQualityIssueStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class ReconciliationStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ISSUES = "COMPLETED_WITH_ISSUES"
    FAILED = "FAILED"


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_type = Column(SQLEnum(DataQualityIssueType), nullable=False, index=True)
    severity = Column(SQLEnum(DataQualitySeverity), nullable=False, index=True)
    affected_module = Column(String, nullable=False, index=True)
    affected_record_id = Column(String, nullable=True)
    affected_record_type = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    status = Column(SQLEnum(DataQualityIssueStatus), nullable=False, default=DataQualityIssueStatus.OPEN, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    detected_by_run_id = Column(UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="SET NULL"), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    previous_status = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="data_quality_issues", lazy="raise_on_sql")
    resolved_by_user = relationship("User", back_populates="resolved_data_quality_issues", lazy="raise_on_sql")
    reconciliation_run = relationship("ReconciliationRun", back_populates="issues", lazy="raise_on_sql")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id = Column(String, nullable=False, unique=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    triggered_by_name = Column(String, nullable=True)
    records_checked = Column(Integer, nullable=False, default=0)
    issues_detected = Column(Integer, nullable=False, default=0)
    issues_resolved = Column(Integer, nullable=False, default=0)
    failed_checks = Column(Integer, nullable=False, default=0)
    status = Column(SQLEnum(ReconciliationStatus), nullable=False, default=ReconciliationStatus.RUNNING)
    error_message = Column(Text, nullable=True)
    summary = Column(JSON, nullable=True)

    company = relationship("Company", back_populates="reconciliation_runs", lazy="raise_on_sql")
    triggered_by_user = relationship("User", back_populates="triggered_reconciliation_runs", lazy="raise_on_sql")
    issues = relationship("DataQualityIssue", back_populates="reconciliation_run", lazy="raise_on_sql")
