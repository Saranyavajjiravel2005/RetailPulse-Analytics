from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from uuid import uuid4
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.models.product import Product, ProductStatus
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.customer import Customer
from app.models.inventory import StockMovement, MovementType
from app.models.report import ReportHistory, ReportExecutionStatus
from app.crud.data_quality import data_quality_issue, reconciliation_run
from app.models.data_quality import (
    DataQualityIssueType,
    DataQualitySeverity,
    DataQualityIssueStatus,
    ReconciliationStatus,
)


class DataQualityService:
    async def run_reconciliation_create_run(self, db: AsyncSession, company_id, user_id=None, user_name=None):
        execution_id = f"RC-{uuid4().hex[:12].upper()}"
        run = await reconciliation_run.create(
            db,
            company_id=company_id,
            execution_id=execution_id,
            triggered_by=user_id,
            triggered_by_name=user_name,
            commit=True,
        )
        return run

    async def _upsert_issue(
        self,
        db: AsyncSession,
        company_id,
        issue_type: DataQualityIssueType,
        severity: DataQualitySeverity,
        affected_module: str,
        affected_record_id: Optional[str],
        affected_record_type: Optional[str],
        description: str,
        details: Optional[Dict[str, Any]],
        run_id=None,
    ) -> bool:
        """Helper to create new issue or update existing unresolved issue without duplication."""
        existing = await data_quality_issue.get_open_issue_for_record(
            db, company_id, issue_type, affected_record_id, affected_module
        )
        if existing:
            # Update existing unresolved issue details & run reference
            existing.description = description
            existing.details = details
            if run_id:
                existing.detected_by_run_id = run_id
            existing.updated_at = datetime.utcnow()
            db.add(existing)
            await db.commit()
            return False  # not a new issue detected
        else:
            await data_quality_issue.create(
                db,
                company_id=company_id,
                issue_type=issue_type,
                severity=severity,
                affected_module=affected_module,
                affected_record_id=affected_record_id,
                affected_record_type=affected_record_type,
                description=description,
                details=details,
                detected_by_run_id=run_id,
                commit=True,
            )
            return True

    async def run_reconciliation(self, db: AsyncSession, company_id, user_id=None, user_name=None, existing_run=None):
        if existing_run:
            run = existing_run
        else:
            execution_id = f"RC-{uuid4().hex[:12].upper()}"
            run = await reconciliation_run.create(
                db,
                company_id=company_id,
                execution_id=execution_id,
                triggered_by=user_id,
                triggered_by_name=user_name,
                commit=True,
            )

        records_checked = 0
        issues_detected = 0
        failed_checks = 0

        # Pre-fetch relevant data for checks
        try:
            sales_res = await db.execute(
                select(Sale).where(Sale.company_id == company_id)
            )
            sales = sales_res.scalars().all()
        except Exception:
            sales = []

        try:
            prods_res = await db.execute(
                select(Product).where(Product.company_id == company_id)
            )
            products = prods_res.scalars().all()
            products_map = {p.id: p for p in products}
        except Exception:
            products = []
            products_map = {}

        # -------------------------------------------------------------------------
        # Check 1: Sales referencing inactive or missing products
        # -------------------------------------------------------------------------
        try:
            for sale in sales:
                records_checked += 1
                items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
                items = items_res.scalars().all()
                for item in items:
                    records_checked += 1
                    if not item.product_id:
                        continue
                    prod = products_map.get(item.product_id)
                    is_active = prod and (getattr(prod.status, "value", str(prod.status)) == "ACTIVE")
                    if not prod or not is_active:
                        is_new = await self._upsert_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.SALE_INACTIVE_OR_MISSING_PRODUCT,
                            severity=DataQualitySeverity.HIGH,
                            affected_module="Sales",
                            affected_record_id=str(sale.id),
                            affected_record_type="Sale",
                            description=f"Sale {sale.invoice_number} references {'inactive' if prod else 'non-existent'} product",
                            details={
                                "sale_id": str(sale.id),
                                "invoice_number": sale.invoice_number,
                                "product_id": str(item.product_id),
                                "product_name": prod.name if prod else "Unknown",
                                "product_status": getattr(prod.status, "value", str(prod.status)) if prod else "MISSING",
                            },
                            run_id=run.id,
                        )
                        if is_new:
                            issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 2: Sales referencing invalid customers
        # -------------------------------------------------------------------------
        try:
            cust_res = await db.execute(select(Customer).where(Customer.company_id == company_id))
            customers = cust_res.scalars().all()
            customer_ids = {c.id for c in customers}

            for sale in sales:
                if sale.customer_id:
                    records_checked += 1
                    if sale.customer_id not in customer_ids:
                        is_new = await self._upsert_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.SALE_INVALID_CUSTOMER,
                            severity=DataQualitySeverity.MEDIUM,
                            affected_module="Sales",
                            affected_record_id=str(sale.id),
                            affected_record_type="Sale",
                            description=f"Sale {sale.invoice_number} references invalid or deleted customer ID {sale.customer_id}",
                            details={
                                "sale_id": str(sale.id),
                                "invoice_number": sale.invoice_number,
                                "customer_id": str(sale.customer_id),
                                "recorded_customer_name": sale.customer_name,
                            },
                            run_id=run.id,
                        )
                        if is_new:
                            issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 3: Duplicate or invalid product SKUs
        # -------------------------------------------------------------------------
        try:
            sku_tracker = {}
            for p in products:
                records_checked += 1
                raw_sku = (p.sku or "").strip()
                normalized_sku = raw_sku.lower()
                if not normalized_sku:
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU,
                        severity=DataQualitySeverity.HIGH,
                        affected_module="Products",
                        affected_record_id=str(p.id),
                        affected_record_type="Product",
                        description=f"Product '{p.name}' has an empty or invalid SKU",
                        details={"product_id": str(p.id), "name": p.name, "sku": p.sku},
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
                elif normalized_sku in sku_tracker:
                    duplicate_prod = sku_tracker[normalized_sku]
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU,
                        severity=DataQualitySeverity.HIGH,
                        affected_module="Products",
                        affected_record_id=str(p.id),
                        affected_record_type="Product",
                        description=f"Duplicate SKU '{p.sku}' detected (conflicts with product '{duplicate_prod.name}')",
                        details={
                            "product_id": str(p.id),
                            "product_name": p.name,
                            "sku": p.sku,
                            "conflicting_product_id": str(duplicate_prod.id),
                            "conflicting_product_name": duplicate_prod.name,
                        },
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
                else:
                    sku_tracker[normalized_sku] = p
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 4: Missing mandatory product/customer information
        # -------------------------------------------------------------------------
        try:
            for p in products:
                records_checked += 1
                missing_fields = []
                if not (p.name or "").strip():
                    missing_fields.append("name")
                if not (p.sku or "").strip():
                    missing_fields.append("sku")
                if p.unit_price is None:
                    missing_fields.append("unit_price")

                if missing_fields:
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                        severity=DataQualitySeverity.MEDIUM,
                        affected_module="Products",
                        affected_record_id=str(p.id),
                        affected_record_type="Product",
                        description=f"Product {p.name or p.id} is missing mandatory field(s): {', '.join(missing_fields)}",
                        details={"product_id": str(p.id), "missing_fields": missing_fields, "name": p.name, "sku": p.sku},
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1

            for c in customers:
                records_checked += 1
                missing_cust_fields = []
                if not (c.first_name or "").strip():
                    missing_cust_fields.append("first_name")
                if not (c.email or "").strip() and not (c.phone or "").strip():
                    missing_cust_fields.append("contact_info (email or phone)")

                if missing_cust_fields:
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                        severity=DataQualitySeverity.LOW,
                        affected_module="Customers",
                        affected_record_id=str(c.id),
                        affected_record_type="Customer",
                        description=f"Customer {c.first_name or c.id} is missing mandatory field(s): {', '.join(missing_cust_fields)}",
                        details={"customer_id": str(c.id), "missing_fields": missing_cust_fields, "first_name": c.first_name, "last_name": c.last_name},
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 5: Sale quantity exceeding available stock
        # -------------------------------------------------------------------------
        try:
            for sale in sales:
                if getattr(sale.status, "value", str(sale.status)) == "CANCELLED":
                    continue
                items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
                items = items_res.scalars().all()
                for item in items:
                    records_checked += 1
                    if not item.product_id:
                        continue
                    prod = products_map.get(item.product_id)
                    if prod and prod.stock_quantity < 0:
                        is_new = await self._upsert_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.SALE_EXCEEDS_STOCK,
                            severity=DataQualitySeverity.CRITICAL,
                            affected_module="Sales",
                            affected_record_id=str(sale.id),
                            affected_record_type="Sale",
                            description=f"Sale {sale.invoice_number} resulted in negative stock ({prod.stock_quantity}) for product '{prod.name}'",
                            details={
                                "sale_id": str(sale.id),
                                "invoice_number": sale.invoice_number,
                                "product_id": str(prod.id),
                                "product_name": prod.name,
                                "quantity_sold": item.quantity,
                                "current_stock": prod.stock_quantity,
                            },
                            run_id=run.id,
                        )
                        if is_new:
                            issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 6: Stock movement records with inconsistent previous/current quantities
        # -------------------------------------------------------------------------
        try:
            moves_res = await db.execute(select(StockMovement).where(StockMovement.company_id == company_id))
            moves = moves_res.scalars().all()
            for mv in moves:
                records_checked += 1
                expected_curr = mv.previous_quantity + mv.quantity_changed
                if mv.updated_quantity != expected_curr:
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.STOCK_MOVEMENT_INCONSISTENT,
                        severity=DataQualitySeverity.HIGH,
                        affected_module="Inventory",
                        affected_record_id=str(mv.id),
                        affected_record_type="StockMovement",
                        description=f"Stock movement {mv.id} math error: previous ({mv.previous_quantity}) + changed ({mv.quantity_changed}) != updated ({mv.updated_quantity})",
                        details={
                            "movement_id": str(mv.id),
                            "product_id": str(mv.product_id),
                            "previous_quantity": mv.previous_quantity,
                            "quantity_changed": mv.quantity_changed,
                            "updated_quantity": mv.updated_quantity,
                            "expected_quantity": expected_curr,
                            "difference": mv.updated_quantity - expected_curr,
                        },
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 7: Inventory quantity becoming inconsistent with stock movements
        # -------------------------------------------------------------------------
        try:
            for prod in products:
                records_checked += 1
                latest_mv_res = await db.execute(
                    select(StockMovement)
                    .where(and_(StockMovement.company_id == company_id, StockMovement.product_id == prod.id))
                    .order_by(desc(StockMovement.created_at))
                    .limit(1)
                )
                latest_mv = latest_mv_res.scalar_one_or_none()

                if latest_mv and latest_mv.updated_quantity != prod.stock_quantity:
                    # Fetch recent stock movements and sales for rich issue context
                    recent_mv_res = await db.execute(
                        select(StockMovement)
                        .where(and_(StockMovement.company_id == company_id, StockMovement.product_id == prod.id))
                        .order_by(desc(StockMovement.created_at))
                        .limit(5)
                    )
                    recent_movements = [
                        {
                            "id": str(m.id),
                            "type": m.movement_type.value if hasattr(m.movement_type, "value") else str(m.movement_type),
                            "quantity_changed": m.quantity_changed,
                            "previous_quantity": m.previous_quantity,
                            "updated_quantity": m.updated_quantity,
                            "reason": m.reason,
                            "created_at": m.created_at.isoformat() if m.created_at else None,
                        }
                        for m in recent_mv_res.scalars().all()
                    ]

                    recent_sales_res = await db.execute(
                        select(Sale, SaleItem)
                        .join(SaleItem, Sale.id == SaleItem.sale_id)
                        .where(and_(Sale.company_id == company_id, SaleItem.product_id == prod.id))
                        .order_by(desc(Sale.created_at))
                        .limit(5)
                    )
                    recent_sales = [
                        {
                            "sale_id": str(s.id),
                            "invoice_number": s.invoice_number,
                            "quantity": si.quantity,
                            "sale_date": s.sale_date.isoformat() if s.sale_date else None,
                        }
                        for s, si in recent_sales_res.all()
                    ]

                    diff = prod.stock_quantity - latest_mv.updated_quantity
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.INVENTORY_INCONSISTENT_WITH_MOVEMENTS,
                        severity=DataQualitySeverity.CRITICAL,
                        affected_module="Inventory",
                        affected_record_id=str(prod.id),
                        affected_record_type="Product",
                        description=f"Inventory for '{prod.name}' ({prod.stock_quantity}) does not match latest stock movement updated quantity ({latest_mv.updated_quantity})",
                        details={
                            "product_id": str(prod.id),
                            "product_name": prod.name,
                            "sku": prod.sku,
                            "current_inventory": prod.stock_quantity,
                            "expected_quantity": latest_mv.updated_quantity,
                            "difference": diff,
                            "latest_movement_id": str(latest_mv.id),
                            "relevant_stock_movements": recent_movements,
                            "related_sales": recent_sales,
                            "detected_time": datetime.utcnow().isoformat(),
                        },
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Check 8: Report / transaction totals not matching underlying transaction data
        # -------------------------------------------------------------------------
        try:
            for sale in sales:
                records_checked += 1
                items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
                items = items_res.scalars().all()
                if not items:
                    continue
                calculated_items_total = sum(float(item.total or (item.quantity * item.unit_price)) for item in items)
                header_total = float(sale.total_amount or 0.0)
                diff = round(header_total - calculated_items_total, 2)

                if abs(diff) > 0.05:  # discrepancy > 5 cents
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.REPORT_TOTAL_MISMATCH,
                        severity=DataQualitySeverity.HIGH,
                        affected_module="Sales",
                        affected_record_id=str(sale.id),
                        affected_record_type="Sale",
                        description=f"Sale {sale.invoice_number} total ({header_total:.2f}) does not match line items sum ({calculated_items_total:.2f})",
                        details={
                            "sale_id": str(sale.id),
                            "invoice_number": sale.invoice_number,
                            "header_total": header_total,
                            "calculated_items_total": calculated_items_total,
                            "difference": diff,
                            "item_count": len(items),
                        },
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1

            # Also check ReportHistory records for failure or mismatches
            rep_res = await db.execute(select(ReportHistory).where(ReportHistory.company_id == company_id))
            reports = rep_res.scalars().all()
            for rep in reports:
                records_checked += 1
                if getattr(rep.status, "value", str(rep.status)) == "FAILED":
                    is_new = await self._upsert_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.REPORT_TOTAL_MISMATCH,
                        severity=DataQualitySeverity.MEDIUM,
                        affected_module="Reports",
                        affected_record_id=str(rep.id),
                        affected_record_type="ReportHistory",
                        description=f"Generated report '{rep.report_name}' execution failed: {rep.error_message or 'Unknown error'}",
                        details={
                            "report_id": str(rep.id),
                            "report_name": rep.report_name,
                            "report_type": getattr(rep.report_type, "value", str(rep.report_type)),
                            "error_message": rep.error_message,
                            "generated_at": rep.generated_at.isoformat() if rep.generated_at else None,
                        },
                        run_id=run.id,
                    )
                    if is_new:
                        issues_detected += 1
        except Exception:
            failed_checks += 1

        # -------------------------------------------------------------------------
        # Finalize Reconciliation Run Record
        # -------------------------------------------------------------------------
        if failed_checks > 0 and issues_detected == 0 and records_checked == 0:
            final_status = ReconciliationStatus.FAILED
        elif issues_detected > 0:
            final_status = ReconciliationStatus.COMPLETED_WITH_ISSUES
        else:
            final_status = ReconciliationStatus.COMPLETED

        await reconciliation_run.update(
            db,
            run,
            completed_at=datetime.utcnow(),
            records_checked=records_checked,
            issues_detected=issues_detected,
            failed_checks=failed_checks,
            status=final_status,
            summary={"issues_detected": issues_detected, "failed_checks": failed_checks},
            commit=True,
        )
        return run


data_quality_service = DataQualityService()
