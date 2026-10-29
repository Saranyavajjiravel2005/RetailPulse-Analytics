from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from uuid import UUID
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.user import UserRole
from app.models.data_quality import (
    DataQualityIssue,
    DataQualityIssueStatus,
    DataQualityIssueType,
    DataQualitySeverity,
    ReconciliationStatus,
)
from app.schemas.data_quality import (
    DataQualityIssueResponse,
    DataQualityIssueListResponse,
    DataQualityIssueUpdate,
    ReconciliationRunResponse,
    ReconciliationRunListResponse,
    ReconciliationTriggerResponse,
    DataQualityDashboardResponse,
)
from app.utils.dependencies import get_current_active_user
from app.crud.data_quality import data_quality_issue, reconciliation_run
from app.services.data_quality_service import data_quality_service
from app.services.audit import audit_service

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


def is_admin(user):
    return user.role in (UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)


@router.get("/dashboard", response_model=DataQualityDashboardResponse)
async def get_dashboard(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # counts
    total_issues_res = await db.execute(
        select(func.count(DataQualityIssue.id)).where(DataQualityIssue.company_id == current_user.company_id)
    )
    total_issues = total_issues_res.scalar() or 0

    unresolved_res = await db.execute(
        select(func.count(DataQualityIssue.id)).where(
            and_(DataQualityIssue.company_id == current_user.company_id, DataQualityIssue.status.in_([DataQualityIssueStatus.OPEN, DataQualityIssueStatus.INVESTIGATING]))
        )
    )
    unresolved_issues = unresolved_res.scalar() or 0

    last_run = await reconciliation_run.get_last_completed(db, current_user.company_id)

    # by status
    status_res = await db.execute(
        select(DataQualityIssue.status, func.count(DataQualityIssue.id))
        .where(DataQualityIssue.company_id == current_user.company_id)
        .group_by(DataQualityIssue.status)
    )
    issues_by_status = {(s.value if hasattr(s, "value") else str(s)): c for s, c in status_res.all() if s is not None}

    # by severity
    sev_res = await db.execute(
        select(DataQualityIssue.severity, func.count(DataQualityIssue.id))
        .where(DataQualityIssue.company_id == current_user.company_id)
        .group_by(DataQualityIssue.severity)
    )
    issues_by_severity = {(s.value if hasattr(s, "value") else str(s)): c for s, c in sev_res.all() if s is not None}

    # by module
    mod_res = await db.execute(
        select(DataQualityIssue.affected_module, func.count(DataQualityIssue.id))
        .where(DataQualityIssue.company_id == current_user.company_id)
        .group_by(DataQualityIssue.affected_module)
    )
    issues_by_module = {(m.value if hasattr(m, "value") else str(m)): c for m, c in mod_res.all() if m is not None}

    total_records_checked = last_run.records_checked if last_run else 0
    valid_records = max(0, total_records_checked - total_issues)
    records_with_errors = sum(c for k, c in issues_by_severity.items() if k in ("HIGH", "CRITICAL"))
    records_with_warnings = sum(c for k, c in issues_by_severity.items() if k in ("MEDIUM", "LOW"))

    return DataQualityDashboardResponse(
        total_records_checked=total_records_checked,
        valid_records=valid_records,
        records_with_warnings=records_with_warnings,
        records_with_errors=records_with_errors,
        unresolved_issues=unresolved_issues,
        last_reconciliation_time=last_run.completed_at if last_run else None,
        issues_by_status=issues_by_status,
        issues_by_severity=issues_by_severity,
        issues_by_module=issues_by_module,
    )


@router.get("/issues", response_model=DataQualityIssueListResponse)
async def list_issues(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    issue_type: Optional[DataQualityIssueType] = Query(None),
    severity: Optional[DataQualitySeverity] = Query(None),
    affected_module: Optional[str] = Query(None),
    status: Optional[DataQualityIssueStatus] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
):
    skip = (page - 1) * limit
    issues, total = await data_quality_issue.get_multi(
        db,
        current_user.company_id,
        skip=skip,
        limit=limit,
        issue_type=issue_type.value if issue_type else None,
        severity=severity.value if severity else None,
        affected_module=affected_module,
        status=status.value if status else None,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    data = []
    for issue in issues:
        resolved_by_name = issue.resolved_by_user.name if issue.resolved_by_user else None
        data.append(
            DataQualityIssueResponse(
                id=issue.id,
                company_id=issue.company_id,
                issue_type=issue.issue_type,
                severity=issue.severity,
                affected_module=issue.affected_module,
                affected_record_id=issue.affected_record_id,
                affected_record_type=issue.affected_record_type,
                description=issue.description,
                details=issue.details,
                status=issue.status,
                detected_at=issue.detected_at,
                detected_by_run_id=issue.detected_by_run_id,
                resolved_by=issue.resolved_by,
                resolved_by_name=resolved_by_name,
                resolved_at=issue.resolved_at,
                resolution_note=issue.resolution_note,
                previous_status=issue.previous_status,
                created_at=issue.created_at,
                updated_at=issue.updated_at,
            )
        )
    return DataQualityIssueListResponse(data=data, total=total, page=page, limit=limit)


@router.get("/issues/{issue_id}", response_model=DataQualityIssueResponse)
async def get_issue(
    issue_id: UUID,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    issue = await data_quality_issue.get(db, issue_id)
    if not issue or issue.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Issue not found")
    resolved_by_name = issue.resolved_by_user.name if issue.resolved_by_user else None
    return DataQualityIssueResponse(
        id=issue.id,
        company_id=issue.company_id,
        issue_type=issue.issue_type,
        severity=issue.severity,
        affected_module=issue.affected_module,
        affected_record_id=issue.affected_record_id,
        affected_record_type=issue.affected_record_type,
        description=issue.description,
        details=issue.details,
        status=issue.status,
        detected_at=issue.detected_at,
        detected_by_run_id=issue.detected_by_run_id,
        resolved_by=issue.resolved_by,
        resolved_by_name=resolved_by_name,
        resolved_at=issue.resolved_at,
        resolution_note=issue.resolution_note,
        previous_status=issue.previous_status,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.put("/issues/{issue_id}/status")
async def update_issue_status(
    issue_id: UUID,
    payload: DataQualityIssueUpdate,
    request: Request,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    issue = await data_quality_issue.get(db, issue_id)
    if not issue or issue.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Issue not found")

    old_status = issue.status.value if hasattr(issue.status, "value") else str(issue.status)
    issue = await data_quality_issue.update_status(
        db, issue, payload.status, resolved_by=current_user.id, resolution_note=payload.resolution_note, commit=True
    )
    new_status = issue.status.value if hasattr(issue.status, "value") else str(issue.status)

    await audit_service.log(
        db,
        current_user.company_id,
        current_user.id,
        "Data Quality Issue Status Updated",
        request,
        resource_type="DataQualityIssue",
        resource_id=issue.id,
        description=f"Updated issue status from {old_status} to {new_status}",
        after_values={"status": new_status, "resolution_note": payload.resolution_note},
        status="SUCCESS",
    )
    await db.commit()

    return {"message": "Issue status updated", "issue_id": str(issue.id), "status": new_status}


@router.post("/reconcile", response_model=ReconciliationTriggerResponse)
async def trigger_reconciliation(
    request: Request,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    try:
        run = await data_quality_service.run_reconciliation(
            db, current_user.company_id, user_id=current_user.id, user_name=current_user.name
        )
        await audit_service.log(
            db,
            current_user.company_id,
            current_user.id,
            "Data Quality Reconciliation Triggered",
            request,
            resource_type="ReconciliationRun",
            resource_id=run.id,
            description=f"Triggered reconciliation run {run.execution_id}",
            status="SUCCESS",
        )
        await db.commit()
        return ReconciliationTriggerResponse(
            execution_id=run.execution_id,
            status=run.status,
            message="Reconciliation completed",
            issues_detected=run.issues_detected,
        )
    except Exception as e:
        await audit_service.log(
            db,
            current_user.company_id,
            current_user.id,
            "Data Quality Reconciliation Triggered",
            request,
            resource_type="ReconciliationRun",
            description=f"Reconciliation failed: {str(e)}",
            status="FAILURE",
        )
        await db.commit()
        raise


@router.get("/reconciliation/history", response_model=ReconciliationRunListResponse)
async def get_reconciliation_history(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
):
    skip = (page - 1) * limit
    runs, total = await reconciliation_run.get_multi(db, current_user.company_id, skip=skip, limit=limit)
    data = []
    for run in runs:
        triggered_by_name = run.triggered_by_user.name if run.triggered_by_user else run.triggered_by_name
        data.append(
            ReconciliationRunResponse(
                id=run.id,
                company_id=run.company_id,
                execution_id=run.execution_id,
                started_at=run.started_at,
                completed_at=run.completed_at,
                triggered_by=run.triggered_by,
                triggered_by_name=triggered_by_name,
                records_checked=run.records_checked,
                issues_detected=run.issues_detected,
                issues_resolved=run.issues_resolved,
                failed_checks=run.failed_checks,
                status=run.status,
                error_message=run.error_message,
                summary=run.summary,
            )
        )
    return ReconciliationRunListResponse(data=data, total=total, page=page, limit=limit)
