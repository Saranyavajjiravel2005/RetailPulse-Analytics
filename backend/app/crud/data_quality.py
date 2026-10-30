from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import joinedload
from app.models.data_quality import DataQualityIssue, ReconciliationRun, DataQualityIssueStatus, ReconciliationStatus
from app.models.user import User
from uuid import UUID
from datetime import datetime
from typing import Optional


class CRUDDataQualityIssue:
    async def create(
        self,
        db: AsyncSession,
        company_id: UUID,
        issue_type,
        severity,
        affected_module: str,
        description: str,
        affected_record_id: str | None = None,
        affected_record_type: str | None = None,
        details: dict | None = None,
        detected_by_run_id: UUID | None = None,
        commit: bool = True,
    ) -> DataQualityIssue:
        issue = DataQualityIssue(
            company_id=company_id,
            issue_type=issue_type,
            severity=severity,
            affected_module=affected_module,
            affected_record_id=affected_record_id,
            affected_record_type=affected_record_type,
            description=description,
            details=details,
            detected_by_run_id=detected_by_run_id,
            status=DataQualityIssueStatus.OPEN,
        )
        db.add(issue)
        if commit:
            await db.commit()
            await db.refresh(issue)
        return issue

    async def get(self, db: AsyncSession, issue_id: UUID) -> DataQualityIssue | None:
        result = await db.execute(
            select(DataQualityIssue)
            .options(joinedload(DataQualityIssue.resolved_by_user))
            .where(DataQualityIssue.id == issue_id)
        )
        return result.scalar_one_or_none()

    async def get_open_issue_for_record(
        self,
        db: AsyncSession,
        company_id: UUID,
        issue_type,
        affected_record_id: str | None,
        affected_module: str,
    ) -> DataQualityIssue | None:
        if not affected_record_id:
            return None
        result = await db.execute(
            select(DataQualityIssue).where(
                and_(
                    DataQualityIssue.company_id == company_id,
                    DataQualityIssue.issue_type == issue_type,
                    DataQualityIssue.affected_record_id == affected_record_id,
                    DataQualityIssue.affected_module == affected_module,
                    DataQualityIssue.status.in_([DataQualityIssueStatus.OPEN, DataQualityIssueStatus.INVESTIGATING]),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        company_id: UUID,
        skip: int = 0,
        limit: int = 25,
        issue_type: str | None = None,
        severity: str | None = None,
        affected_module: str | None = None,
        status: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[DataQualityIssue], int]:
        query = select(DataQualityIssue).options(joinedload(DataQualityIssue.resolved_by_user)).where(
            DataQualityIssue.company_id == company_id
        )

        if issue_type:
            query = query.where(DataQualityIssue.issue_type == issue_type)
        if severity:
            query = query.where(DataQualityIssue.severity == severity)
        if affected_module:
            query = query.where(DataQualityIssue.affected_module.ilike(f"%{affected_module}%"))
        if status:
            query = query.where(DataQualityIssue.status == status)
        if date_from:
            query = query.where(DataQualityIssue.detected_at >= date_from)
        if date_to:
            query = query.where(DataQualityIssue.detected_at <= date_to)
        if search:
            query = query.where(
                or_(
                    DataQualityIssue.description.ilike(f"%{search}%"),
                    DataQualityIssue.affected_record_id.ilike(f"%{search}%"),
                    DataQualityIssue.affected_module.ilike(f"%{search}%"),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(DataQualityIssue.detected_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def get_by_key(
        self,
        db: AsyncSession,
        company_id: UUID,
        issue_type,
        affected_record_id: str | None,
        affected_module: str,
    ) -> DataQualityIssue | None:
        if not affected_record_id:
            return None
        result = await db.execute(
            select(DataQualityIssue).where(
                and_(
                    DataQualityIssue.company_id == company_id,
                    DataQualityIssue.issue_type == issue_type,
                    DataQualityIssue.affected_record_id == affected_record_id,
                    DataQualityIssue.affected_module == affected_module,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        db: AsyncSession,
        issue: DataQualityIssue,
        new_status: DataQualityIssueStatus,
        resolved_by: UUID | None = None,
        resolution_note: str | None = None,
        commit: bool = True,
    ) -> DataQualityIssue:
        issue.previous_status = issue.status.value if hasattr(issue.status, "value") else str(issue.status)
        issue.status = new_status
        if new_status == DataQualityIssueStatus.RESOLVED:
            issue.resolved_by = resolved_by
            issue.resolved_at = datetime.utcnow()
            issue.resolution_note = resolution_note
        else:
            issue.resolved_by = resolved_by
            issue.resolution_note = resolution_note
            if new_status != DataQualityIssueStatus.RESOLVED:
                issue.resolved_at = None
                if new_status == DataQualityIssueStatus.OPEN or new_status == DataQualityIssueStatus.INVESTIGATING:
                    pass
        if commit:
            await db.commit()
            await db.refresh(issue)
        return issue


class CRUDReconciliationRun:
    async def create(
        self,
        db: AsyncSession,
        company_id: UUID,
        execution_id: str,
        triggered_by: UUID | None = None,
        triggered_by_name: str | None = None,
        commit: bool = True,
    ) -> ReconciliationRun:
        run = ReconciliationRun(
            company_id=company_id,
            execution_id=execution_id,
            triggered_by=triggered_by,
            triggered_by_name=triggered_by_name,
            status=ReconciliationStatus.RUNNING,
        )
        db.add(run)
        if commit:
            await db.commit()
            await db.refresh(run)
        return run

    async def update(
        self,
        db: AsyncSession,
        run: ReconciliationRun,
        **kwargs,
    ) -> ReconciliationRun:
        for k, v in kwargs.items():
            if hasattr(run, k):
                setattr(run, k, v)
        await db.commit()
        await db.refresh(run)
        return run

    async def get(self, db: AsyncSession, run_id: UUID) -> ReconciliationRun | None:
        result = await db.execute(
            select(ReconciliationRun)
            .options(joinedload(ReconciliationRun.triggered_by_user))
            .where(ReconciliationRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_by_execution_id(self, db: AsyncSession, company_id: UUID, execution_id: str) -> ReconciliationRun | None:
        result = await db.execute(
            select(ReconciliationRun)
            .options(joinedload(ReconciliationRun.triggered_by_user))
            .where(and_(ReconciliationRun.company_id == company_id, ReconciliationRun.execution_id == execution_id))
        )
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        company_id: UUID,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[ReconciliationRun], int]:
        query = select(ReconciliationRun).options(joinedload(ReconciliationRun.triggered_by_user)).where(
            ReconciliationRun.company_id == company_id
        )
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        query = query.order_by(ReconciliationRun.started_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def get_last_completed(self, db: AsyncSession, company_id: UUID) -> ReconciliationRun | None:
        result = await db.execute(
            select(ReconciliationRun)
            .where(
                and_(
                    ReconciliationRun.company_id == company_id,
                    ReconciliationRun.completed_at.isnot(None),
                )
            )
            .order_by(ReconciliationRun.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


data_quality_issue = CRUDDataQualityIssue()
reconciliation_run = CRUDReconciliationRun()
