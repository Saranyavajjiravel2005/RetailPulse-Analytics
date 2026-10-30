from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.data_quality import DataQualityIssueHistory
from uuid import UUID
from datetime import datetime


class CRUDDataQualityIssueHistory:
    async def create(
        self,
        db: AsyncSession,
        issue_id: UUID,
        company_id: UUID,
        previous_status: str | None,
        new_status: str,
        changed_by: UUID | None = None,
        changed_by_name: str | None = None,
        resolution_note: str | None = None,
        commit: bool = True,
    ) -> DataQualityIssueHistory:
        entry = DataQualityIssueHistory(
            issue_id=issue_id,
            company_id=company_id,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=changed_by,
            changed_by_name=changed_by_name,
            resolution_note=resolution_note,
            changed_at=datetime.utcnow(),
        )
        db.add(entry)
        if commit:
            await db.commit()
            await db.refresh(entry)
        return entry

    async def get_multi_by_issue(self, db: AsyncSession, issue_id: UUID):
        result = await db.execute(select(DataQualityIssueHistory).where(DataQualityIssueHistory.issue_id == issue_id).order_by(DataQualityIssueHistory.changed_at.desc()))
        return list(result.scalars().all())

    get_by_issue = get_multi_by_issue


data_quality_issue_history = CRUDDataQualityIssueHistory()
