from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from uuid import uuid4
from datetime import datetime

from app.models.product import Product, ProductStatus
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.customer import Customer
from app.models.inventory import StockMovement
from app.crud.data_quality import data_quality_issue, reconciliation_run
from app.models.data_quality import (
    DataQualityIssueType,
    DataQualitySeverity,
    DataQualityIssueStatus,
    ReconciliationStatus,
)


class DataQualityService:
    async def run_reconciliation(self, db: AsyncSession, company_id, user_id=None, user_name=None):
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

        try:
            # 1) Check sales referencing inactive/missing products
            sales_res = await db.execute(
                select(Sale).where(and_(Sale.company_id == company_id, Sale.status == SaleStatus.COMPLETED))
            )
            sales = sales_res.scalars().all()
            for sale in sales:
                items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
                items = items_res.scalars().all()
                for item in items:
                    records_checked += 1
                    if not item.product_id:
                        continue
                    prod_res = await db.execute(select(Product).where(Product.id == item.product_id))
                    prod = prod_res.scalar_one_or_none()
                    if not prod or prod.company_id != company_id or prod.status != ProductStatus.ACTIVE:
                        existing = await data_quality_issue.get_open_issue_for_record(
                            db, company_id, DataQualityIssueType.SALE_INACTIVE_OR_MISSING_PRODUCT, str(sale.id), "Sales"
                        )
                        if not existing:
                            await data_quality_issue.create(
                                db,
                                company_id=company_id,
                                issue_type=DataQualityIssueType.SALE_INACTIVE_OR_MISSING_PRODUCT,
                                severity=DataQualitySeverity.HIGH,
                                affected_module="Sales",
                                affected_record_id=str(sale.id),
                                affected_record_type="Sale",
                                description=f"Sale {sale.invoice_number} references inactive or missing product",
                                details={"sale_id": str(sale.id), "invoice_number": sale.invoice_number, "product_id": str(item.product_id)},
                                detected_by_run_id=run.id,
                                commit=True,
                            )
                            issues_detected += 1

            # 2) Check sales referencing invalid customers (if customer_id set but not found)
            for sale in sales:
                if sale.customer_id:
                    records_checked += 1
                    cust_res = await db.execute(select(Customer).where(Customer.id == sale.customer_id))
                    cust = cust_res.scalar_one_or_none()
                    if not cust or cust.company_id != company_id:
                        existing = await data_quality_issue.get_open_issue_for_record(
                            db, company_id, DataQualityIssueType.SALE_INVALID_CUSTOMER, str(sale.id), "Sales"
                        )
                        if not existing:
                            await data_quality_issue.create(
                                db,
                                company_id=company_id,
                                issue_type=DataQualityIssueType.SALE_INVALID_CUSTOMER,
                                severity=DataQualitySeverity.MEDIUM,
                                affected_module="Sales",
                                affected_record_id=str(sale.id),
                                affected_record_type="Sale",
                                description=f"Sale {sale.invoice_number} references invalid customer",
                                details={"sale_id": str(sale.id), "invoice_number": sale.invoice_number, "customer_id": str(sale.customer_id)},
                                detected_by_run_id=run.id,
                                commit=True,
                            )
                            issues_detected += 1

            # 3) Duplicate/invalid product SKUs
            prods_res = await db.execute(select(Product).where(Product.company_id == company_id))
            prods = prods_res.scalars().all()
            sku_map = {}
            for p in prods:
                records_checked += 1
                key = p.sku.lower().strip() if p.sku else ""
                if not key or key in sku_map:
                    existing = await data_quality_issue.get_open_issue_for_record(
                        db, company_id, DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU, str(p.id), "Products"
                    )
                    if not existing:
                        await data_quality_issue.create(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU,
                            severity=DataQualitySeverity.HIGH,
                            affected_module="Products",
                            affected_record_id=str(p.id),
                            affected_record_type="Product",
                            description=f"Duplicate or invalid SKU detected for product {p.name}",
                            details={"product_id": str(p.id), "sku": p.sku, "name": p.name},
                            detected_by_run_id=run.id,
                            commit=True,
                        )
                        issues_detected += 1
                else:
                    sku_map[key] = p.id

                # Missing mandatory info
                if not p.name or not p.sku:
                    existing = await data_quality_issue.get_open_issue_for_record(
                        db, company_id, DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO, str(p.id), "Products"
                    )
                    if not existing:
                        await data_quality_issue.create(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                            severity=DataQualitySeverity.MEDIUM,
                            affected_module="Products",
                            affected_record_id=str(p.id),
                            affected_record_type="Product",
                            description=f"Missing mandatory product information for {p.name}",
                            details={"product_id": str(p.id), "missing": ["name" if not p.name else None, "sku" if not p.sku else None]},
                            detected_by_run_id=run.id,
                            commit=True,
                        )
                        issues_detected += 1

            # 4) Sale quantity exceeding available stock (basic check using current stock)
            for sale in sales:
                items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
                items = items_res.scalars().all()
                for item in items:
                    if not item.product_id:
                        continue
                    prod_res = await db.execute(select(Product).where(Product.id == item.product_id))
                    prod = prod_res.scalar_one_or_none()
                    if prod and prod.stock_quantity < item.quantity:
                        existing = await data_quality_issue.get_open_issue_for_record(
                            db, company_id, DataQualityIssueType.SALE_EXCEEDS_STOCK, str(sale.id), "Sales"
                        )
                        if not existing:
                            await data_quality_issue.create(
                                db,
                                company_id=company_id,
                                issue_type=DataQualityIssueType.SALE_EXCEEDS_STOCK,
                                severity=DataQualitySeverity.CRITICAL,
                                affected_module="Sales",
                                affected_record_id=str(sale.id),
                                affected_record_type="Sale",
                                description=f"Sale {sale.invoice_number} quantity exceeds available stock for product {prod.name}",
                                details={"sale_id": str(sale.id), "invoice_number": sale.invoice_number, "product_id": str(prod.id), "quantity_sold": item.quantity, "stock_quantity": prod.stock_quantity},
                                detected_by_run_id=run.id,
                                commit=True,
                            )
                            issues_detected += 1

            # 5) Stock movement inconsistencies
            moves_res = await db.execute(select(StockMovement).where(StockMovement.company_id == company_id))
            moves = moves_res.scalars().all()
            for mv in moves:
                records_checked += 1
                if mv.updated_quantity != mv.previous_quantity + mv.quantity_changed:
                    existing = await data_quality_issue.get_open_issue_for_record(
                        db, company_id, DataQualityIssueType.STOCK_MOVEMENT_INCONSISTENT, str(mv.id), "Inventory"
                    )
                    if not existing:
                        await data_quality_issue.create(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.STOCK_MOVEMENT_INCONSISTENT,
                            severity=DataQualitySeverity.HIGH,
                            affected_module="Inventory",
                            affected_record_id=str(mv.id),
                            affected_record_type="StockMovement",
                            description="Stock movement has inconsistent previous/current quantities",
                            details={"movement_id": str(mv.id), "previous_quantity": mv.previous_quantity, "updated_quantity": mv.updated_quantity, "quantity_changed": mv.quantity_changed},
                            detected_by_run_id=run.id,
                            commit=True,
                        )
                        issues_detected += 1

            status = ReconciliationStatus.COMPLETED_WITH_ISSUES if issues_detected > 0 else ReconciliationStatus.COMPLETED
            await reconciliation_run.update(
                db,
                run,
                completed_at=datetime.utcnow(),
                records_checked=records_checked,
                issues_detected=issues_detected,
                failed_checks=failed_checks,
                status=status,
                summary={"issues_detected": issues_detected},
                commit=True,
            )
            return run
        except Exception as e:
            failed_checks += 1
            await reconciliation_run.update(
                db,
                run,
                completed_at=datetime.utcnow(),
                records_checked=records_checked,
                issues_detected=issues_detected,
                failed_checks=failed_checks,
                status=ReconciliationStatus.FAILED,
                error_message=str(e),
                commit=True,
            )
            raise


data_quality_service = DataQualityService()
