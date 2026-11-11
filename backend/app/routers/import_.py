from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form, BackgroundTasks, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import os
import io
import logging
from uuid import UUID

from app.database import get_db, async_session_factory
from app.models.import_history import ImportType, ImportStatus, ImportHistory
from app.schemas.import_ import ImportHistoryResponse, ImportErrorResponse, ImportPreviewResponse, ImportResultResponse
from app.services.import_ import ImportService, ImportValidationError
from app.utils.dependencies import get_current_active_user
from app.services.audit import audit_service
from app.models.user import User
from app.services.import_storage import save_uploaded_import_file, validate_csv_content, get_import_file_path
from app.crud.import_history import import_history as import_history_crud
from datetime import datetime

logger = logging.getLogger("retailpulse")

router = APIRouter(prefix="/import", tags=["import"])


class ImportUploadResponse(BaseModel):
    import_id: UUID
    import_type: str
    filename: str
    total_records: int
    status: str


def check_import_permission(current_user):
    user_role = getattr(current_user.role, "value", str(current_user.role))
    if user_role not in ("COMPANY_ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only company administrators are authorized to perform data imports."
        )


@router.get("/template/{import_type}")
async def download_template(
    import_type: str,
    current_user=Depends(get_current_active_user),
):
    check_import_permission(current_user)
    try:
        itype = ImportType(import_type.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid import type: '{import_type}'. Supported: PRODUCTS, INVENTORY, CUSTOMERS, SALES")

    csv_data = ImportService.get_template_csv(itype)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=template_{itype.value.lower()}.csv"}
    )


@router.post("/upload", response_model=ImportUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    import_type: str = Form(...),
    file: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    try:
        itype = ImportType(import_type.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid import type: '{import_type}'. Supported: PRODUCTS, INVENTORY, CUSTOMERS, SALES")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files (.csv) are supported for data import.")

    content = await file.read()
    validate_csv_content(content, file.filename)

    service = ImportService(db, current_user.company_id, current_user.id)
    try:
        columns, rows = service.parse_csv(file_content=content)
        if not rows and not columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded CSV file is empty.")
        service.validate_columns(itype, columns)
    except ValueError as e:
        logger.warning(f"Validation error during upload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    history = await service.create_import_history(itype, file.filename, len(rows))

    # Persist file to disk
    try:
        file_path = get_import_file_path(current_user.company_id, history.id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.exception(f"Failed to persist import file: {e}")

    await audit_service.log(
        db,
        current_user.company_id,
        current_user.id,
        "File uploaded",
        request,
        resource_type="Import",
        resource_id=history.id,
        description=f"Uploaded {itype.value} import file '{file.filename}' with {len(rows)} records",
    )
    return ImportUploadResponse(
        import_id=history.id,
        import_type=itype.value,
        filename=file.filename,
        total_records=len(rows),
        status=history.status.value,
    )


@router.post("/validate", response_model=ImportPreviewResponse)
async def validate_import(
    import_type: str = Form(...),
    import_id: str = Form(None),
    duplicate_action: str = Form("SKIP"),
    file: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    try:
        itype = ImportType(import_type.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid import type: '{import_type}'")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files (.csv) are supported.")

    content = await file.read()
    validate_csv_content(content, file.filename)

    service = ImportService(db, current_user.company_id, current_user.id)
    parsed_id = UUID(import_id) if import_id else None

    # Persist file if parsed_id exists
    file_path = None
    if parsed_id:
        file_path = get_import_file_path(current_user.company_id, parsed_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)

    try:
        result = await service.validate_import(
            itype, file_content=content, filename=file.filename, import_id=parsed_id, duplicate_action=duplicate_action.upper(), file_path=str(file_path) if file_path else None
        )
    except Exception as e:
        logger.exception("Validation failed unexpectedly")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Validation processing encountered an internal error.")

    return ImportPreviewResponse(**result)


# Background task runner for processing bulk imports reliably
async def run_import_job_background(
    company_id: UUID,
    user_id: UUID,
    import_id: UUID,
    import_type: ImportType,
    file_content: Optional[bytes],
    filename: str,
    duplicate_action: str,
    file_path: Optional[str] = None,
):
    async with async_session_factory() as session:
        service = ImportService(session, company_id, user_id)
        try:
            await service.process_import(
                import_type=import_type,
                file_content=file_content,
                filename=filename,
                import_id=import_id,
                duplicate_action=duplicate_action,
                file_path=file_path,
            )
            # Log audit event for completion
            history = await service.get_import_history(import_id)
            if history:
                status_action = "Import completed" if history.status in (ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS) else "Import failed"
                await audit_service.log(
                    session,
                    company_id,
                    user_id,
                    status_action,
                    None,
                    resource_type="Import",
                    resource_id=history.id,
                    description=f"Import '{history.filename}' completed with status {history.status.value}. Success: {history.successful_records}, Failed: {history.failed_records}",
                )
                await session.commit()
        except Exception as e:
            logger.exception(f"Background import job {import_id} failed: {e}")
            history = await service.get_import_history(import_id)
            if history and history.status != ImportStatus.CANCELLED:
                history.status = ImportStatus.FAILED
                history.completed_at = datetime.utcnow()
                session.add(history)
                await import_history_crud.add_error(
                    session,
                    history.id,
                    1,
                    f"Background import processing failed: {str(e)}",
                    field="System",
                    raw_data=None,
                    error_type="SYSTEM_ERROR",
                    commit=False,
                )
                await audit_service.log(
                    session,
                    company_id,
                    user_id,
                    "Import failed",
                    None,
                    resource_type="Import",
                    resource_id=history.id,
                    description=f"Background import job for '{history.filename}' failed: {str(e)}",
                )
                await session.commit()


@router.post("/start", response_model=ImportUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_import(
    request: Request,
    background_tasks: BackgroundTasks,
    import_type: str = Form(...),
    import_id: str = Form(None),
    duplicate_action: str = Form("SKIP"),
    file: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    try:
        itype = ImportType(import_type.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid import type: '{import_type}'")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files (.csv) are supported.")

    content = await file.read()
    validate_csv_content(content, file.filename)

    service = ImportService(db, current_user.company_id, current_user.id)
    parsed_id = UUID(import_id) if import_id else None
    history = None
    if parsed_id:
        history = await service.get_import_history(parsed_id)

    if not history:
        columns, rows = service.parse_csv(file_content=content)
        service.validate_columns(itype, columns)
        history = await service.create_import_history(itype, file.filename, len(rows))
    else:
        history.status = ImportStatus.PROCESSING
        db.add(history)
        await db.commit()
        await db.refresh(history)

    # Persist file persistently on disk
    file_path = get_import_file_path(current_user.company_id, history.id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)

    await audit_service.log(
        db,
        current_user.company_id,
        current_user.id,
        "Import started",
        request,
        resource_type="Import",
        resource_id=history.id,
        description=f"Import {history.id} started for {itype.value} with file '{file.filename}'",
    )

    # Dispatch to reliable background tasks
    background_tasks.add_task(
        run_import_job_background,
        current_user.company_id,
        current_user.id,
        history.id,
        itype,
        None,
        file.filename,
        duplicate_action.upper(),
        file_path=str(file_path),
    )

    return ImportUploadResponse(
        import_id=history.id,
        import_type=itype.value,
        filename=file.filename,
        total_records=history.total_records,
        status=ImportStatus.PROCESSING.value,
    )


@router.post("/process", response_model=ImportResultResponse)
async def process_import(
    request: Request,
    import_type: str = Form(...),
    import_id: str = Form(None),
    duplicate_action: str = Form("SKIP"),
    file: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    try:
        itype = ImportType(import_type.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid import type: '{import_type}'")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files (.csv) are allowed.")

    content = await file.read()
    validate_csv_content(content, file.filename)

    service = ImportService(db, current_user.company_id, current_user.id)
    parsed_id = UUID(import_id) if import_id else None

    # Persist file
    file_path = None
    if parsed_id:
        file_path = get_import_file_path(current_user.company_id, parsed_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)

    if parsed_id:
        existing_history = await service.get_import_history(parsed_id)
        if existing_history:
            await audit_service.log(
                db, current_user.company_id, current_user.id,
                "Import started", request, resource_type="Import", resource_id=existing_history.id,
                description=f"Import started for {itype.value} from file '{file.filename}'"
            )
            await db.commit()

    try:
        result = await service.process_import(
            itype, file_content=content, filename=file.filename, import_id=parsed_id, duplicate_action=duplicate_action.upper(), file_path=str(file_path) if file_path else None
        )
    except ValueError as e:
        logger.warning(f"Validation error during process: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Import processing failed")
        if parsed_id:
            h = await service.get_import_history(parsed_id)
            if h:
                await audit_service.log(
                    db, current_user.company_id, current_user.id,
                    "Import failed", request, resource_type="Import", resource_id=h.id,
                    description=f"Import failed for {itype.value}: Internal error"
                )
                await db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Import execution failed.")

    import_history = await service.get_import_history(UUID(result["import_id"]))
    if import_history:
        status_action = "Import completed" if import_history.status in (ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS) else "Import failed"
        await audit_service.log(
            db,
            current_user.company_id,
            current_user.id,
            status_action,
            request,
            resource_type="Import",
            resource_id=import_history.id,
            description=f"Import '{import_history.filename}' finished with status {import_history.status.value}. Success: {import_history.successful_records}, Failed: {import_history.failed_records}",
        )
        await db.commit()

    return ImportResultResponse(**result)


@router.get("/history", response_model=list[ImportHistoryResponse])
async def get_import_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    import_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    itype = None
    if import_type:
        try:
            itype = ImportType(import_type.upper())
        except ValueError:
            pass

    istatus = None
    if status:
        try:
            istatus = ImportStatus(status.upper())
        except ValueError:
            pass

    histories, _ = await ImportService(db, current_user.company_id, current_user.id).list_import_history(
        skip=skip, limit=limit, import_type=itype, status=istatus
    )

    # Collect uploader names
    user_ids = {h.uploaded_by for h in histories if h.uploaded_by}
    user_names = {}
    if user_ids:
        from sqlalchemy import select
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in res.scalars().all():
            name = f"{u.first_name or ''} {u.last_name or ''}".strip()
            user_names[u.id] = name or u.email

    output = []
    for h in histories:
        duration = None
        if h.completed_at and h.created_at:
            duration = (h.completed_at - h.created_at).total_seconds()

        output.append(ImportHistoryResponse(
            id=h.id,
            company_id=h.company_id,
            import_type=h.import_type.value,
            filename=h.filename,
            uploaded_by=h.uploaded_by,
            uploaded_by_name=user_names.get(h.uploaded_by),
            total_records=h.total_records,
            successful_records=h.successful_records,
            failed_records=h.failed_records,
            duplicate_records=h.duplicate_records,
            skipped_records=getattr(h, "skipped_records", 0) or 0,
            status=h.status.value,
            created_at=h.created_at,
            completed_at=h.completed_at,
            duration_seconds=duration,
        ))
    return output


@router.get("/{import_id}", response_model=ImportHistoryResponse)
async def get_import_detail(
    import_id: UUID,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    service = ImportService(db, current_user.company_id, current_user.id)
    history = await service.get_import_history(import_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import record not found.")

    uploader_name = None
    if history.uploaded_by:
        user_res = await db.get(User, history.uploaded_by)
        if user_res:
            name = f"{user_res.first_name or ''} {user_res.last_name or ''}".strip()
            uploader_name = name or user_res.email

    duration = None
    if history.completed_at and history.created_at:
        duration = (history.completed_at - history.created_at).total_seconds()

    return ImportHistoryResponse(
        id=history.id,
        company_id=history.company_id,
        import_type=history.import_type.value,
        filename=history.filename,
        uploaded_by=history.uploaded_by,
        uploaded_by_name=uploader_name,
        total_records=history.total_records,
        successful_records=history.successful_records,
        failed_records=history.failed_records,
        duplicate_records=history.duplicate_records,
        skipped_records=getattr(history, "skipped_records", 0) or 0,
        status=history.status.value,
        created_at=history.created_at,
        completed_at=history.completed_at,
        duration_seconds=duration,
    )


@router.get("/{import_id}/errors", response_model=list[ImportErrorResponse])
async def get_import_errors(
    import_id: UUID,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    service = ImportService(db, current_user.company_id, current_user.id)
    history = await service.get_import_history(import_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import record not found.")
    errors = await service.get_import_errors(import_id)
    return [ImportErrorResponse(**e) for e in errors]


@router.get("/{import_id}/errors/download")
async def download_error_report(
    import_id: UUID,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    service = ImportService(db, current_user.company_id, current_user.id)
    history = await service.get_import_history(import_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import record not found.")

    csv_data = await service.generate_error_csv(import_id)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=errors_import_{import_id}.csv"},
    )


@router.post("/{import_id}/cancel", response_model=ImportHistoryResponse)
async def cancel_import(
    import_id: UUID,
    request: Request,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_import_permission(current_user)

    service = ImportService(db, current_user.company_id, current_user.id)
    history = await service.get_import_history(import_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import record not found.")

    if history.status in (ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS, ImportStatus.FAILED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel import in '{history.status.value}' status.")

    history.status = ImportStatus.CANCELLED
    history.completed_at = __import__('datetime').datetime.utcnow()
    db.add(history)
    await db.commit()
    await db.refresh(history)

    await audit_service.log(
        db,
        current_user.company_id,
        current_user.id,
        "Import cancelled",
        request,
        resource_type="Import",
        resource_id=history.id,
        description=f"Import '{history.filename}' was cancelled by user",
    )
    await db.commit()

    return ImportHistoryResponse(
        id=history.id,
        company_id=history.company_id,
        import_type=history.import_type.value,
        filename=history.filename,
        uploaded_by=history.uploaded_by,
        uploaded_by_name=None,
        total_records=history.total_records,
        successful_records=history.successful_records,
        failed_records=history.failed_records,
        duplicate_records=history.duplicate_records,
        skipped_records=getattr(history, "skipped_records", 0) or 0,
        status=history.status.value,
        created_at=history.created_at,
        completed_at=history.completed_at,
    )
