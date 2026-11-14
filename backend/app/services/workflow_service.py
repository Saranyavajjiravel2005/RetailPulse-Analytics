import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc

from app.models.workflow import (
    WorkflowRequest,
    WorkflowHistory,
    WorkflowConfiguration,
    WorkflowRequestType,
    WorkflowStatus,
    WorkflowPriority,
)
from app.models.product import Product, ProductStatus
from app.models.customer import Customer
from app.models.inventory import StockMovement, InventoryAdjustment, MovementType, AdjustmentType
from app.models.import_history import ImportHistory, ImportStatus
from app.models.user import User, UserRole
from app.models.notification import NotificationType, NotificationPriority, NotificationResourceType
from app.services.notification import notification_service
from app.services.audit import audit_service
from app.schemas.workflow import WorkflowRequestCreate, WorkflowActionRequest

logger = logging.getLogger("retailpulse")


class WorkflowService:
    def __init__(self, db: AsyncSession, company_id: UUID, current_user_id: UUID, current_user_name: str, current_user_role: str):
        self.db = db
        self.company_id = company_id
        self.user_id = current_user_id
        self.user_name = current_user_name
        self.user_role = current_user_role

    async def get_or_create_default_configurations(self) -> List[WorkflowConfiguration]:
        """Ensure standard configurations exist for all workflow types for this company."""
        res = await self.db.execute(
            select(WorkflowConfiguration).where(WorkflowConfiguration.company_id == self.company_id)
        )
        existing_configs = {c.request_type: c for c in res.scalars().all()}

        created = False
        all_configs = []
        for w_type in WorkflowRequestType:
            if w_type not in existing_configs:
                cfg = WorkflowConfiguration(
                    id=uuid4(),
                    company_id=self.company_id,
                    request_type=w_type,
                    approver_role="COMPANY_ADMIN",
                    is_approval_required=True,
                    allow_self_approval=False,
                    status="ACTIVE",
                )
                self.db.add(cfg)
                all_configs.append(cfg)
                created = True
            else:
                all_configs.append(existing_configs[w_type])

        if created:
            await self.db.flush()
        return all_configs

    async def get_configuration(self, request_type: WorkflowRequestType) -> WorkflowConfiguration:
        res = await self.db.execute(
            select(WorkflowConfiguration).where(
                WorkflowConfiguration.company_id == self.company_id,
                WorkflowConfiguration.request_type == request_type,
            )
        )
        cfg = res.scalar_one_or_none()
        if not cfg:
            await self.get_or_create_default_configurations()
            res = await self.db.execute(
                select(WorkflowConfiguration).where(
                    WorkflowConfiguration.company_id == self.company_id,
                    WorkflowConfiguration.request_type == request_type,
                )
            )
            cfg = res.scalar_one_or_none()
        return cfg

    async def generate_request_number(self) -> str:
        year = datetime.utcnow().year
        res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(WorkflowRequest.company_id == self.company_id)
        )
        count = res.scalar() or 0
        return f"REQ-{year}-{count + 1:04d}"

    async def capture_current_entity_snapshot(
        self, request_type: WorkflowRequestType, entity_id_str: Optional[str]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Fetch current entity state from database to snapshot for diff viewer."""
        if not entity_id_str:
            return {}, None

        try:
            entity_id = UUID(entity_id_str)
        except Exception:
            return {}, None

        if request_type in (
            WorkflowRequestType.STOCK_ADJUSTMENT,
            WorkflowRequestType.PRODUCT_DEACTIVATION,
            WorkflowRequestType.PRODUCT_PRICE_CHANGE,
        ):
            prod_res = await self.db.execute(
                select(Product).where(Product.company_id == self.company_id, Product.id == entity_id)
            )
            prod = prod_res.scalar_one_or_none()
            if not prod:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Target product {entity_id} not found.")

            snapshot = {
                "product_id": str(prod.id),
                "name": prod.name,
                "sku": prod.sku,
                "stock_quantity": prod.stock_quantity or 0,
                "unit_price": float(prod.unit_price or 0.0),
                "cost_price": float(prod.cost_price or 0.0),
                "status": getattr(prod.status, "value", str(prod.status)),
            }
            display_name = f"{prod.name} ({prod.sku})"
            return snapshot, display_name

        elif request_type == WorkflowRequestType.CUSTOMER_INFO_CHANGE:
            cust_res = await self.db.execute(
                select(Customer).where(Customer.company_id == self.company_id, Customer.id == entity_id, Customer.is_deleted == False)
            )
            cust = cust_res.scalar_one_or_none()
            if not cust:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Target customer {entity_id} not found.")

            snapshot = {
                "customer_id": str(cust.id),
                "first_name": cust.first_name,
                "last_name": cust.last_name,
                "email": cust.email,
                "phone": cust.phone,
                "address": cust.address or "",
                "city": cust.city or "",
                "state": cust.state or "",
                "postal_code": cust.postal_code or "",
                "customer_type": getattr(cust.customer_type, "value", str(cust.customer_type)),
            }
            display_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or cust.email or str(cust.id)
            return snapshot, display_name

        elif request_type == WorkflowRequestType.INVENTORY_IMPORT_APPROVAL:
            imp_res = await self.db.execute(
                select(ImportHistory).where(ImportHistory.company_id == self.company_id, ImportHistory.id == entity_id)
            )
            imp = imp_res.scalar_one_or_none()
            if not imp:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Target import {entity_id} not found.")

            snapshot = {
                "import_id": str(imp.id),
                "filename": imp.filename,
                "total_records": imp.total_records,
                "import_type": getattr(imp.import_type, "value", str(imp.import_type)),
                "status": getattr(imp.status, "value", str(imp.status)),
            }
            display_name = f"Import: {imp.filename} ({imp.total_records} rows)"
            return snapshot, display_name

        return {}, None

    def calculate_diff(self, request_type: WorkflowRequestType, current_values: Dict[str, Any], requested_values: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured diff for visual highlighting in approval details."""
        diff: Dict[str, Any] = {}

        if request_type == WorkflowRequestType.STOCK_ADJUSTMENT:
            curr_stock = current_values.get("stock_quantity", 0)
            adj_type = (requested_values.get("adjustment_type") or "SET").upper()
            qty = int(requested_values.get("quantity", 0))

            if adj_type in ("STOCK_IN", "ADD"):
                target_stock = curr_stock + qty
                difference = qty
            elif adj_type in ("STOCK_OUT", "SUBTRACT"):
                target_stock = max(curr_stock - qty, 0)
                difference = -qty
            else:  # SET / MANUAL_ADJUSTMENT
                target_stock = qty
                difference = qty - curr_stock

            diff["stock_quantity"] = {
                "current": curr_stock,
                "requested": target_stock,
                "difference": f"+{difference}" if difference > 0 else str(difference),
                "adjustment_type": adj_type,
                "adjustment_units": qty,
            }

        elif request_type == WorkflowRequestType.PRODUCT_PRICE_CHANGE:
            curr_price = current_values.get("unit_price", 0.0)
            new_price = float(requested_values.get("unit_price", curr_price))
            price_diff = round(new_price - curr_price, 2)
            diff["unit_price"] = {
                "current": curr_price,
                "requested": new_price,
                "difference": f"+{price_diff:.2f}" if price_diff > 0 else f"{price_diff:.2f}",
                "percentage_change": f"{(price_diff / curr_price * 100):.1f}%" if curr_price > 0 else "N/A",
            }

        elif request_type == WorkflowRequestType.PRODUCT_DEACTIVATION:
            diff["status"] = {
                "current": current_values.get("status", "ACTIVE"),
                "requested": "INACTIVE",
                "action": "DEACTIVATE_PRODUCT",
            }

        elif request_type == WorkflowRequestType.CUSTOMER_INFO_CHANGE:
            for field in ["first_name", "last_name", "email", "phone", "address", "city", "state", "postal_code"]:
                if field in requested_values:
                    curr_val = current_values.get(field, "")
                    req_val = requested_values.get(field, "")
                    if curr_val != req_val:
                        diff[field] = {
                            "current": curr_val or "(empty)",
                            "requested": req_val or "(empty)",
                        }

        elif request_type == WorkflowRequestType.INVENTORY_IMPORT_APPROVAL:
            diff["import_status"] = {
                "current": current_values.get("status", "PENDING"),
                "requested": "APPROVED_FOR_PROCESSING",
                "filename": current_values.get("filename"),
                "records": current_values.get("total_records"),
            }

        return diff

    async def create_request(self, payload: WorkflowRequestCreate, request_obj=None) -> WorkflowRequest:
        config = await self.get_configuration(payload.request_type)
        if config and config.status == "INACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workflow type '{payload.request_type.value}' is currently deactivated.",
            )

        current_values, resolved_name = await self.capture_current_entity_snapshot(
            payload.request_type, payload.related_entity_id
        )

        display_name = payload.related_entity_name or resolved_name or payload.related_entity_id or "Record"
        diff_values = self.calculate_diff(payload.request_type, current_values, payload.requested_values)

        # Store diff alongside requested values
        enriched_requested = dict(payload.requested_values)
        if diff_values:
            enriched_requested["_diff"] = diff_values

        req_number = await self.generate_request_number()
        req = WorkflowRequest(
            id=uuid4(),
            request_number=req_number,
            company_id=self.company_id,
            request_type=payload.request_type,
            priority=payload.priority,
            status=WorkflowStatus.PENDING_APPROVAL,
            title=payload.title,
            reason=payload.reason,
            requested_by=self.user_id,
            requested_by_name=self.user_name,
            related_entity_type=payload.related_entity_type,
            related_entity_id=payload.related_entity_id,
            related_entity_name=display_name,
            current_values=current_values,
            requested_values=enriched_requested,
        )
        self.db.add(req)
        await self.db.flush()

        # Initial history timeline entry
        history_entry = WorkflowHistory(
            id=uuid4(),
            request_id=req.id,
            company_id=self.company_id,
            action="SUBMITTED",
            actor_id=self.user_id,
            actor_name=self.user_name,
            actor_role=self.user_role,
            previous_status=WorkflowStatus.DRAFT,
            new_status=WorkflowStatus.PENDING_APPROVAL,
            comment=payload.reason,
        )
        self.db.add(history_entry)

        # Send notification to approvers
        try:
            target_role = getattr(UserRole, config.approver_role, UserRole.COMPANY_ADMIN)
            await notification_service._create_alert_for_roles(
                self.db,
                self.company_id,
                NotificationType.WORKFLOW_PENDING,
                NotificationPriority.HIGH if payload.priority in (WorkflowPriority.HIGH, WorkflowPriority.URGENT) else NotificationPriority.MEDIUM,
                f"New Approval Request: {req.request_number}",
                f"{self.user_name} submitted a {payload.request_type.value.replace('_', ' ')} request for '{display_name}'.",
                NotificationResourceType.WORKFLOW,
                req.id,
                target_role,
            )
        except Exception:
            logger.exception("Failed to dispatch workflow notification to approvers")

        # Audit log event
        try:
            await audit_service.log(
                self.db,
                self.company_id,
                self.user_id,
                "Workflow request created",
                request_obj,
                resource_type="Workflow",
                resource_id=req.id,
                description=f"Created {payload.request_type.value} approval request {req.request_number} for {display_name}",
                after_values=enriched_requested,
            )
        except Exception:
            logger.exception("Failed to record workflow audit log")

        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def list_requests(
        self,
        request_type: Optional[WorkflowRequestType] = None,
        status_filter: Optional[WorkflowStatus] = None,
        my_requests: bool = False,
        pending_only: bool = False,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[WorkflowRequest], int]:
        query = select(WorkflowRequest).where(WorkflowRequest.company_id == self.company_id)

        if my_requests:
            query = query.where(WorkflowRequest.requested_by == self.user_id)
        if pending_only:
            query = query.where(WorkflowRequest.status.in_([WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED]))
        if status_filter:
            query = query.where(WorkflowRequest.status == status_filter)
        if request_type:
            query = query.where(WorkflowRequest.request_type == request_type)
        if search:
            pattern = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(WorkflowRequest.request_number).like(pattern),
                    func.lower(WorkflowRequest.title).like(pattern),
                    func.lower(WorkflowRequest.reason).like(pattern),
                    func.lower(WorkflowRequest.requested_by_name).like(pattern),
                    func.lower(WorkflowRequest.related_entity_name).like(pattern),
                )
            )

        # Count total matching
        count_stmt = select(func.count()).select_from(query.subquery())
        count_res = await self.db.execute(count_stmt)
        total = count_res.scalar() or 0

        # Execute paginated query sorted by created_at desc
        query = query.order_by(desc(WorkflowRequest.created_at)).offset(skip).limit(limit)
        res = await self.db.execute(query)
        items = res.scalars().all()

        return items, total

    async def get_request_by_id(self, request_id: UUID) -> WorkflowRequest:
        res = await self.db.execute(
            select(WorkflowRequest).where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.id == request_id,
            )
        )
        req = res.scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
        return req

    async def get_request_history(self, request_id: UUID) -> List[WorkflowHistory]:
        await self.get_request_by_id(request_id)
        res = await self.db.execute(
            select(WorkflowHistory)
            .where(WorkflowHistory.request_id == request_id, WorkflowHistory.company_id == self.company_id)
            .order_by(WorkflowHistory.created_at.asc())
        )
        return res.scalars().all()

    async def approve_request(self, request_id: UUID, payload: WorkflowActionRequest, request_obj=None) -> WorkflowRequest:
        req = await self.get_request_by_id(request_id)

        # 1. State machine check: Must be in PENDING_APPROVAL
        if req.status not in (WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve request in '{req.status.value}' state. Only pending requests can be approved.",
            )

        # 2. Self-approval rule enforcement
        config = await self.get_configuration(req.request_type)
        if req.requested_by == self.user_id and not (config and config.allow_self_approval):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Violation: Requesters are not permitted to approve their own requests.",
            )

        # 3. Role check: Verify approver role permission
        required_role = config.approver_role if config else "COMPANY_ADMIN"
        if self.user_role not in (required_role, "SUPER_ADMIN", "COMPANY_ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not possess the required approver role ({required_role}) to approve this workflow.",
            )

        # 4. Atomic Execution of Business Data Modification
        try:
            await self._apply_business_change(req)
        except Exception as e:
            logger.exception(f"Business change execution failed for request {req.request_number}: {e}")
            req.execution_error = str(e)
            self.db.add(req)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Approval execution failed to apply business change: {str(e)}",
            )

        # 5. Update Request Status
        previous_status = req.status
        req.status = WorkflowStatus.APPROVED
        req.reviewed_by = self.user_id
        req.reviewed_by_name = self.user_name
        req.reviewed_at = datetime.utcnow()
        req.review_comment = payload.comment
        self.db.add(req)

        # 6. Immutable Timeline History
        history_entry = WorkflowHistory(
            id=uuid4(),
            request_id=req.id,
            company_id=self.company_id,
            action="APPROVED",
            actor_id=self.user_id,
            actor_name=self.user_name,
            actor_role=self.user_role,
            previous_status=previous_status,
            new_status=WorkflowStatus.APPROVED,
            comment=payload.comment or "Request approved and changes applied successfully.",
        )
        self.db.add(history_entry)

        # 7. Notify the Requester
        if req.requested_by:
            try:
                await notification_service._create_alert_for_roles(
                    self.db,
                    self.company_id,
                    NotificationType.WORKFLOW_APPROVED,
                    NotificationPriority.MEDIUM,
                    f"Request Approved: {req.request_number}",
                    f"Your request '{req.title}' has been approved by {self.user_name}. Changes have been applied.",
                    NotificationResourceType.WORKFLOW,
                    req.id,
                    None,
                )
            except Exception:
                logger.exception("Failed to dispatch workflow approval notification")

        # 8. Audit Log Integration
        try:
            await audit_service.log(
                self.db,
                self.company_id,
                self.user_id,
                "Workflow request approved",
                request_obj,
                resource_type="Workflow",
                resource_id=req.id,
                description=f"Approved request {req.request_number} ({req.request_type.value}) for '{req.related_entity_name}'",
                before_values=req.current_values,
                after_values=req.requested_values,
            )
        except Exception:
            logger.exception("Failed to record workflow approval audit log")

        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def reject_request(self, request_id: UUID, payload: WorkflowActionRequest, request_obj=None) -> WorkflowRequest:
        req = await self.get_request_by_id(request_id)

        if req.status not in (WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reject request in '{req.status.value}' state. Only pending requests can be rejected.",
            )

        # Rejection reason is strictly mandatory
        reason = (payload.rejection_reason or payload.comment or "").strip()
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A mandatory rejection reason must be provided to reject an approval request.",
            )

        config = await self.get_configuration(req.request_type)
        if req.requested_by == self.user_id and not (config and config.allow_self_approval):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Violation: Requesters cannot reject their own requests (use Cancel instead).",
            )

        previous_status = req.status
        req.status = WorkflowStatus.REJECTED
        req.reviewed_by = self.user_id
        req.reviewed_by_name = self.user_name
        req.reviewed_at = datetime.utcnow()
        req.rejection_reason = reason
        req.review_comment = reason
        self.db.add(req)

        history_entry = WorkflowHistory(
            id=uuid4(),
            request_id=req.id,
            company_id=self.company_id,
            action="REJECTED",
            actor_id=self.user_id,
            actor_name=self.user_name,
            actor_role=self.user_role,
            previous_status=previous_status,
            new_status=WorkflowStatus.REJECTED,
            comment=f"Rejected: {reason}",
        )
        self.db.add(history_entry)

        # Notify the Requester
        if req.requested_by:
            try:
                await notification_service._create_alert_for_roles(
                    self.db,
                    self.company_id,
                    NotificationType.WORKFLOW_REJECTED,
                    NotificationPriority.HIGH,
                    f"Request Rejected: {req.request_number}",
                    f"Your request '{req.title}' was rejected by {self.user_name}. Reason: {reason}",
                    NotificationResourceType.WORKFLOW,
                    req.id,
                    None,
                )
            except Exception:
                logger.exception("Failed to dispatch workflow rejection notification")

        # Audit Log
        try:
            await audit_service.log(
                self.db,
                self.company_id,
                self.user_id,
                "Workflow request rejected",
                request_obj,
                resource_type="Workflow",
                resource_id=req.id,
                description=f"Rejected request {req.request_number} ({req.request_type.value}). Reason: {reason}",
            )
        except Exception:
            logger.exception("Failed to record workflow rejection audit log")

        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def cancel_request(self, request_id: UUID, payload: WorkflowActionRequest, request_obj=None) -> WorkflowRequest:
        req = await self.get_request_by_id(request_id)

        if req.status not in (WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED, WorkflowStatus.DRAFT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel request in '{req.status.value}' state. It has already been finalized.",
            )

        # Only requester or admin can cancel
        if req.requested_by != self.user_id and self.user_role not in ("COMPANY_ADMIN", "SUPER_ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the request creator or an administrator can cancel this request.",
            )

        reason = payload.comment or "Cancelled by user."
        previous_status = req.status
        req.status = WorkflowStatus.CANCELLED
        self.db.add(req)

        history_entry = WorkflowHistory(
            id=uuid4(),
            request_id=req.id,
            company_id=self.company_id,
            action="CANCELLED",
            actor_id=self.user_id,
            actor_name=self.user_name,
            actor_role=self.user_role,
            previous_status=previous_status,
            new_status=WorkflowStatus.CANCELLED,
            comment=reason,
        )
        self.db.add(history_entry)

        # Audit Log
        try:
            await audit_service.log(
                self.db,
                self.company_id,
                self.user_id,
                "Workflow request cancelled",
                request_obj,
                resource_type="Workflow",
                resource_id=req.id,
                description=f"Cancelled request {req.request_number}. Note: {reason}",
            )
        except Exception:
            logger.exception("Failed to record workflow cancellation audit log")

        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def _apply_business_change(self, req: WorkflowRequest) -> None:
        """Transactionally execute the approved business data modification."""
        req_values = req.requested_values

        if req.request_type == WorkflowRequestType.STOCK_ADJUSTMENT:
            entity_id = UUID(req.related_entity_id)
            prod_res = await self.db.execute(
                select(Product).where(Product.company_id == self.company_id, Product.id == entity_id)
            )
            prod = prod_res.scalar_one_or_none()
            if not prod:
                raise ValueError(f"Product {entity_id} does not exist.")

            adj_type_raw = (req_values.get("adjustment_type") or "SET").upper()
            qty = int(req_values.get("quantity", 0))
            reason = req.reason or "Stock Adjustment via Approved Workflow"

            previous_quantity = prod.stock_quantity or 0
            if adj_type_raw in ("STOCK_IN", "ADD"):
                quantity_changed = qty
                updated_quantity = previous_quantity + qty
                movement_type = MovementType.STOCK_ADDITION
                adj_type = AdjustmentType.STOCK_IN
            elif adj_type_raw in ("STOCK_OUT", "SUBTRACT"):
                quantity_changed = -qty
                updated_quantity = max(previous_quantity - qty, 0)
                movement_type = MovementType.STOCK_REMOVAL
                adj_type = AdjustmentType.STOCK_OUT
            else:  # SET / MANUAL_ADJUSTMENT
                quantity_changed = qty - previous_quantity
                updated_quantity = qty
                movement_type = MovementType.MANUAL_ADJUSTMENT
                adj_type = AdjustmentType.MANUAL_ADJUSTMENT

            prod.stock_quantity = updated_quantity
            self.db.add(prod)

            stock_movement = StockMovement(
                company_id=self.company_id,
                product_id=prod.id,
                movement_type=movement_type,
                previous_quantity=previous_quantity,
                updated_quantity=updated_quantity,
                quantity_changed=quantity_changed,
                reason=f"[Workflow {req.request_number}] {reason}",
                user_id=self.user_id,
            )
            self.db.add(stock_movement)

            inventory_adjustment = InventoryAdjustment(
                company_id=self.company_id,
                product_id=prod.id,
                adjustment_type=adj_type,
                quantity=abs(quantity_changed),
                reason=reason,
                remarks=f"Authorized by {self.user_name} (Workflow {req.request_number})",
                adjusted_by=self.user_id,
            )
            self.db.add(inventory_adjustment)
            await self.db.flush()

        elif req.request_type == WorkflowRequestType.PRODUCT_DEACTIVATION:
            entity_id = UUID(req.related_entity_id)
            prod_res = await self.db.execute(
                select(Product).where(Product.company_id == self.company_id, Product.id == entity_id)
            )
            prod = prod_res.scalar_one_or_none()
            if not prod:
                raise ValueError(f"Product {entity_id} does not exist.")
            prod.status = ProductStatus.INACTIVE
            self.db.add(prod)
            await self.db.flush()

        elif req.request_type == WorkflowRequestType.PRODUCT_PRICE_CHANGE:
            entity_id = UUID(req.related_entity_id)
            prod_res = await self.db.execute(
                select(Product).where(Product.company_id == self.company_id, Product.id == entity_id)
            )
            prod = prod_res.scalar_one_or_none()
            if not prod:
                raise ValueError(f"Product {entity_id} does not exist.")

            new_unit_price = Decimal(str(req_values.get("unit_price", prod.unit_price)))
            prod.unit_price = new_unit_price
            if "cost_price" in req_values:
                prod.cost_price = Decimal(str(req_values["cost_price"]))
            self.db.add(prod)
            await self.db.flush()

        elif req.request_type == WorkflowRequestType.CUSTOMER_INFO_CHANGE:
            entity_id = UUID(req.related_entity_id)
            cust_res = await self.db.execute(
                select(Customer).where(Customer.company_id == self.company_id, Customer.id == entity_id, Customer.is_deleted == False)
            )
            cust = cust_res.scalar_one_or_none()
            if not cust:
                raise ValueError(f"Customer {entity_id} does not exist.")

            if "first_name" in req_values:
                cust.first_name = req_values["first_name"]
            if "last_name" in req_values:
                cust.last_name = req_values["last_name"]
            if "email" in req_values:
                cust.email = req_values["email"]
            if "phone" in req_values:
                cust.phone = req_values["phone"]
            if "address" in req_values:
                cust.address = req_values["address"]
            if "city" in req_values:
                cust.city = req_values["city"]
            if "state" in req_values:
                cust.state = req_values["state"]
            if "postal_code" in req_values:
                cust.postal_code = req_values["postal_code"]

            self.db.add(cust)
            await self.db.flush()

        elif req.request_type == WorkflowRequestType.INVENTORY_IMPORT_APPROVAL:
            entity_id = UUID(req.related_entity_id)
            imp_res = await self.db.execute(
                select(ImportHistory).where(ImportHistory.company_id == self.company_id, ImportHistory.id == entity_id)
            )
            imp = imp_res.scalar_one_or_none()
            if imp and imp.status == ImportStatus.PENDING:
                imp.status = ImportStatus.UPLOADED
                self.db.add(imp)
                await self.db.flush()

    async def get_summary_counts(self) -> Dict[str, Any]:
        """Get pending, approved, rejected, and per-type statistics."""
        base_query = select(WorkflowRequest).where(WorkflowRequest.company_id == self.company_id)

        pending_res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.status.in_([WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED]),
            )
        )
        pending_count = pending_res.scalar() or 0

        approved_res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.status == WorkflowStatus.APPROVED,
            )
        )
        approved_count = approved_res.scalar() or 0

        rejected_res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.status == WorkflowStatus.REJECTED,
            )
        )
        rejected_count = rejected_res.scalar() or 0

        my_res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.requested_by == self.user_id,
            )
        )
        my_requests_count = my_res.scalar() or 0

        total_res = await self.db.execute(
            select(func.count(WorkflowRequest.id)).where(WorkflowRequest.company_id == self.company_id)
        )
        total_count = total_res.scalar() or 0

        # Group by type for pending items
        type_res = await self.db.execute(
            select(WorkflowRequest.request_type, func.count(WorkflowRequest.id))
            .where(
                WorkflowRequest.company_id == self.company_id,
                WorkflowRequest.status.in_([WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.SUBMITTED]),
            )
            .group_by(WorkflowRequest.request_type)
        )
        by_type = {t.value if hasattr(t, "value") else str(t): cnt for t, cnt in type_res.all()}

        return {
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "my_requests_count": my_requests_count,
            "total_count": total_count,
            "by_type": by_type,
        }

    async def update_configuration(
        self,
        request_type: WorkflowRequestType,
        approver_role: Optional[str] = None,
        is_approval_required: Optional[bool] = None,
        allow_self_approval: Optional[bool] = None,
        status_val: Optional[str] = None,
        request_obj=None,
    ) -> WorkflowConfiguration:
        if self.user_role not in ("COMPANY_ADMIN", "SUPER_ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only company administrators can manage workflow configurations.",
            )

        cfg = await self.get_configuration(request_type)
        before_state = {
            "approver_role": cfg.approver_role,
            "is_approval_required": cfg.is_approval_required,
            "allow_self_approval": cfg.allow_self_approval,
            "status": cfg.status,
        }

        if approver_role is not None:
            cfg.approver_role = approver_role
        if is_approval_required is not None:
            cfg.is_approval_required = is_approval_required
        if allow_self_approval is not None:
            cfg.allow_self_approval = allow_self_approval
        if status_val is not None:
            cfg.status = status_val.upper()

        cfg.updated_at = datetime.utcnow()
        self.db.add(cfg)

        try:
            await audit_service.log(
                self.db,
                self.company_id,
                self.user_id,
                "Workflow configuration updated",
                request_obj,
                resource_type="WorkflowConfiguration",
                resource_id=cfg.id,
                description=f"Updated approval rule for '{request_type.value}'",
                before_values=before_state,
                after_values={
                    "approver_role": cfg.approver_role,
                    "is_approval_required": cfg.is_approval_required,
                    "allow_self_approval": cfg.allow_self_approval,
                    "status": cfg.status,
                },
            )
        except Exception:
            logger.exception("Failed to record workflow configuration audit log")

        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

