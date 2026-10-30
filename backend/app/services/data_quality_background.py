from sqlalchemy.ext.asyncio import AsyncSession
from app.services.data_quality_service import data_quality_service
from app.crud.data_quality import reconciliation_run
from app.models.data_quality import ReconciliationStatus
from datetime import datetime
import asyncio


class BackgroundReconciliationService:
    _tasks = {}

    async def start_reconciliation(self, company_id, user_id=None, user_name=None):
        from app.database import SessionLocal
        async with SessionLocal() as db:
            run = await data_quality_service.run_reconciliation_create_run(db, company_id, user_id, user_name)
            execution_id = run.execution_id
        task = asyncio.create_task(self._run_background(company_id, user_id, user_name, execution_id))
        self._tasks[execution_id] = task
        return execution_id

    async def _run_background(self, company_id, user_id=None, user_name=None, execution_id=None):
        from app.database import SessionLocal
        async with SessionLocal() as db:
            try:
                run = await reconciliation_run.get_by_execution_id(db, company_id, execution_id) if execution_id else None
                result = await data_quality_service.run_reconciliation(db, company_id, user_id, user_name, existing_run=run)
                return result
            except Exception as e:
                if execution_id:
                    try:
                        run = await reconciliation_run.get_by_execution_id(db, company_id, execution_id)
                        if run:
                            await reconciliation_run.update(db, run, completed_at=datetime.utcnow(), status=ReconciliationStatus.FAILED, error_message=str(e), commit=True)
                    except Exception:
                        pass
                raise


data_quality_background = BackgroundReconciliationService()