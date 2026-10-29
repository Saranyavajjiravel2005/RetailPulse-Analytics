from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    COMPANY_ADMIN = "COMPANY_ADMIN"
    MANAGER = "MANAGER"
    ANALYST = "ANALYST"
    SALES_REP = "SALES_REP"
    VIEWER = "VIEWER"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    PENDING = "PENDING"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.COMPANY_ADMIN)
    status = Column(SQLEnum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="users", lazy="raise_on_sql")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan", lazy="raise_on_sql")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan", lazy="raise_on_sql")
    sales = relationship("Sale", back_populates="created_by_user", lazy="raise_on_sql")
    stock_movements = relationship("StockMovement", back_populates="user", lazy="raise_on_sql")
    inventory_adjustments = relationship("InventoryAdjustment", back_populates="adjusted_by_user", lazy="raise_on_sql")
    customer_timelines = relationship("CustomerTimeline", back_populates="user", cascade="all, delete-orphan", lazy="raise_on_sql")
    imports = relationship("ImportHistory", back_populates="uploaded_by_user", lazy="raise_on_sql")
    resolved_data_quality_issues = relationship("DataQualityIssue", back_populates="resolved_by_user", foreign_keys="DataQualityIssue.resolved_by", lazy="raise_on_sql")
    triggered_reconciliation_runs = relationship("ReconciliationRun", back_populates="triggered_by_user", foreign_keys="ReconciliationRun.triggered_by", lazy="raise_on_sql")
