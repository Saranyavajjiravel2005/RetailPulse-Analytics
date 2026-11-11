from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from uuid import UUID
import logging
from datetime import datetime

from app.models.sale import Sale, SaleItem
from app.models.product import Product, ProductStatus
from app.models.customer import Customer
from app.models.inventory import StockMovement
from app.crud.data_quality import data_quality_issue
from app.models.data_quality import DataQualityIssueType, DataQualitySeverity

logger = logging.getLogger(__name__)


class DataQualityAutoService:
    async def _upsert_open_issue(
        self,
        db: AsyncSession,
        company_id: UUID,
        issue_type: DataQualityIssueType,
        severity: DataQualitySeverity,
        affected_module: str,
        affected_record_id: str,
        affected_record_type: str,
        description: str,
        details: dict,
    ):
        """Only create an issue if an open/investigating issue does not already exist for this record."""
        existing = await data_quality_issue.get_open_issue_for_record(
            db, company_id, issue_type, affected_record_id, affected_module
        )
        if not existing:
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
                commit=False,
            )

    async def check_sale(self, db: AsyncSession, sale: Sale, company_id: UUID):
        """Targeted check triggered after a sale is created or updated."""
        try:
            items_res = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
            items = items_res.scalars().all()
            items_total = 0.0

            for item in items:
                line_total = float(item.total or (item.quantity * item.unit_price))
                items_total += line_total

                if not item.product_id:
                    continue

                prod_res = await db.execute(select(Product).where(Product.id == item.product_id))
                prod = prod_res.scalar_one_or_none()

                # Check inactive or missing product
                if not prod or prod.company_id != company_id or getattr(prod.status, "value", str(prod.status)) != "ACTIVE":
                    await self._upsert_open_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.SALE_INACTIVE_OR_MISSING_PRODUCT,
                        severity=DataQualitySeverity.HIGH,
                        affected_module="Sales",
                        affected_record_id=str(sale.id),
                        affected_record_type="Sale",
                        description=f"Sale {sale.invoice_number} references inactive or missing product",
                        details={"sale_id": str(sale.id), "invoice_number": sale.invoice_number, "product_id": str(item.product_id)},
                    )

                # Check sale quantity exceeding available stock
                if prod and prod.stock_quantity < 0 and getattr(sale.status, "value", str(sale.status)) != "CANCELLED":
                    await self._upsert_open_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.SALE_EXCEEDS_STOCK,
                        severity=DataQualitySeverity.CRITICAL,
                        affected_module="Sales",
                        affected_record_id=str(sale.id),
                        affected_record_type="Sale",
                        description=f"Sale {sale.invoice_number} exceeded stock for product '{prod.name}' (current stock: {prod.stock_quantity})",
                        details={"sale_id": str(sale.id), "invoice_number": sale.invoice_number, "product_id": str(prod.id), "stock_quantity": prod.stock_quantity},
                    )

            # Check invalid customer reference
            if sale.customer_id:
                cust_res = await db.execute(select(Customer).where(Customer.id == sale.customer_id))
                cust = cust_res.scalar_one_or_none()
                if not cust or cust.company_id != company_id:
                    await self._upsert_open_issue(
                        db,
                        company_id=company_id,
                        issue_type=DataQualityIssueType.SALE_INVALID_CUSTOMER,
                        severity=DataQualitySeverity.MEDIUM,
                        affected_module="Sales",
                        affected_record_id=str(sale.id),
                        affected_record_type="Sale",
                        description=f"Sale {sale.invoice_number} references invalid customer ID {sale.customer_id}",
                        details={"sale_id": str(sale.id), "customer_id": str(sale.customer_id)},
                    )

            # Check total mismatch
            header_total = float(sale.total_amount or 0.0)
            if items and abs(header_total - items_total) > 0.05:
                await self._upsert_open_issue(
                    db,
                    company_id=company_id,
                    issue_type=DataQualityIssueType.REPORT_TOTAL_MISMATCH,
                    severity=DataQualitySeverity.HIGH,
                    affected_module="Sales",
                    affected_record_id=str(sale.id),
                    affected_record_type="Sale",
                    description=f"Sale {sale.invoice_number} total ({header_total:.2f}) does not match line items sum ({items_total:.2f})",
                    details={"sale_id": str(sale.id), "header_total": header_total, "items_total": items_total, "diff": header_total - items_total},
                )

            await db.commit()
        except Exception as e:
            logger.warning(f"Data quality auto check on sale failed (non-blocking): {e}")

    async def check_product_stock(self, db: AsyncSession, product: Product, company_id: UUID):
        """Targeted check triggered after inventory adjustment or product update."""
        try:
            # Check latest stock movement vs current product inventory
            latest_mv_res = await db.execute(
                select(StockMovement)
                .where(and_(StockMovement.company_id == company_id, StockMovement.product_id == product.id))
                .order_by(desc(StockMovement.created_at))
                .limit(1)
            )
            latest_mv = latest_mv_res.scalar_one_or_none()
            if latest_mv and latest_mv.updated_quantity != product.stock_quantity:
                await self._upsert_open_issue(
                    db,
                    company_id=company_id,
                    issue_type=DataQualityIssueType.INVENTORY_INCONSISTENT_WITH_MOVEMENTS,
                    severity=DataQualitySeverity.CRITICAL,
                    affected_module="Inventory",
                    affected_record_id=str(product.id),
                    affected_record_type="Product",
                    description=f"Product '{product.name}' stock ({product.stock_quantity}) does not match latest stock movement updated quantity ({latest_mv.updated_quantity})",
                    details={
                        "product_id": str(product.id),
                        "product_name": product.name,
                        "current_inventory": product.stock_quantity,
                        "expected_quantity": latest_mv.updated_quantity,
                        "difference": product.stock_quantity - latest_mv.updated_quantity,
                        "latest_movement_id": str(latest_mv.id),
                        "detection_time": datetime.utcnow().isoformat(),
                    },
                )

            # Check mandatory product info
            if not (product.name or "").strip() or not (product.sku or "").strip():
                await self._upsert_open_issue(
                    db,
                    company_id=company_id,
                    issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                    severity=DataQualitySeverity.MEDIUM,
                    affected_module="Products",
                    affected_record_id=str(product.id),
                    affected_record_type="Product",
                    description=f"Product {product.id} missing mandatory name or SKU",
                    details={"product_id": str(product.id), "name": product.name, "sku": product.sku},
                )

            await db.commit()
        except Exception as e:
            logger.warning(f"Data quality auto check on product failed (non-blocking): {e}")

    async def check_customer(self, db: AsyncSession, customer: Customer, company_id: UUID):
        """Targeted check triggered after customer creation or update."""
        try:
            missing = []
            if not (customer.first_name or "").strip():
                missing.append("first_name")
            if not (customer.email or "").strip() and not (customer.phone or "").strip():
                missing.append("email or phone")

            if missing:
                await self._upsert_open_issue(
                    db,
                    company_id=company_id,
                    issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                    severity=DataQualitySeverity.LOW,
                    affected_module="Customers",
                    affected_record_id=str(customer.id),
                    affected_record_type="Customer",
                    description=f"Customer {customer.first_name or customer.id} missing mandatory contact info",
                    details={"customer_id": str(customer.id), "missing_fields": missing},
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Data quality auto check on customer failed (non-blocking): {e}")

    async def check_import(self, db: AsyncSession, import_history, company_id: UUID):
        """Targeted check triggered after an import job completes."""
        try:
            import_type_str = getattr(import_history.import_type, "value", str(import_history.import_type)).upper()
            if "PRODUCT" in import_type_str:
                # Scan for duplicate SKUs
                prods_res = await db.execute(select(Product).where(Product.company_id == company_id))
                prods = prods_res.scalars().all()
                sku_set = set()
                for p in prods:
                    sku = (p.sku or "").strip().lower()
                    if sku in sku_set and sku:
                        await self._upsert_open_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU,
                            severity=DataQualitySeverity.HIGH,
                            affected_module="Products",
                            affected_record_id=str(p.id),
                            affected_record_type="Product",
                            description=f"Duplicate SKU '{p.sku}' detected after product import",
                            details={"product_id": str(p.id), "sku": p.sku, "import_id": str(import_history.id)},
                        )
                    elif sku:
                        sku_set.add(sku)
                await db.commit()

            elif "INVENTORY" in import_type_str:
                # Check for negative inventory or stock movements inconsistency
                prods_res = await db.execute(select(Product).where(Product.company_id == company_id))
                prods = prods_res.scalars().all()
                for p in prods:
                    if (p.stock_quantity or 0) < 0:
                        await self._upsert_open_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.INVENTORY_INCONSISTENT_WITH_MOVEMENTS,
                            severity=DataQualitySeverity.CRITICAL,
                            affected_module="Inventory",
                            affected_record_id=str(p.id),
                            affected_record_type="Product",
                            description=f"Negative stock quantity ({p.stock_quantity}) detected for product '{p.name}' after inventory import",
                            details={"product_id": str(p.id), "sku": p.sku, "stock_quantity": p.stock_quantity, "import_id": str(import_history.id)},
                        )
                    # Verify latest stock movement match
                    latest_mv_res = await db.execute(
                        select(StockMovement)
                        .where(and_(StockMovement.company_id == company_id, StockMovement.product_id == p.id))
                        .order_by(desc(StockMovement.created_at))
                        .limit(1)
                    )
                    latest_mv = latest_mv_res.scalar_one_or_none()
                    if latest_mv and latest_mv.updated_quantity != p.stock_quantity:
                        await self._upsert_open_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.STOCK_MOVEMENT_INCONSISTENT,
                            severity=DataQualitySeverity.HIGH,
                            affected_module="Inventory",
                            affected_record_id=str(p.id),
                            affected_record_type="Product",
                            description=f"Product '{p.name}' stock ({p.stock_quantity}) does not match latest stock movement updated quantity ({latest_mv.updated_quantity}) after inventory import",
                            details={
                                "product_id": str(p.id),
                                "product_name": p.name,
                                "current_inventory": p.stock_quantity,
                                "expected_quantity": latest_mv.updated_quantity,
                                "difference": p.stock_quantity - latest_mv.updated_quantity,
                                "import_id": str(import_history.id),
                            },
                        )
                await db.commit()

            elif "CUSTOMER" in import_type_str:
                # Scan for missing mandatory customer info and duplicate contacts
                custs_res = await db.execute(select(Customer).where(Customer.company_id == company_id, Customer.is_deleted == False))
                custs = custs_res.scalars().all()
                seen_emails = set()
                seen_phones = set()
                for c in custs:
                    if not (c.first_name or "").strip():
                        await self._upsert_open_issue(
                            db,
                            company_id=company_id,
                            issue_type=DataQualityIssueType.MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO,
                            severity=DataQualitySeverity.LOW,
                            affected_module="Customers",
                            affected_record_id=str(c.id),
                            affected_record_type="Customer",
                            description=f"Customer {c.id} missing first name after import",
                            details={"customer_id": str(c.id), "import_id": str(import_history.id)},
                        )
                    # Check duplicates
                    if c.email:
                        clean_email = c.email.strip().lower()
                        if clean_email in seen_emails:
                            await self._upsert_open_issue(
                                db,
                                company_id=company_id,
                                issue_type=DataQualityIssueType.CUSTOMER_DUPLICATE_OR_INVALID_CONTACT,
                                severity=DataQualitySeverity.MEDIUM,
                                affected_module="Customers",
                                affected_record_id=str(c.id),
                                affected_record_type="Customer",
                                description=f"Duplicate customer email '{c.email}' detected after import",
                                details={"customer_id": str(c.id), "email": c.email, "import_id": str(import_history.id)},
                            )
                        else:
                            seen_emails.add(clean_email)
                    if c.phone:
                        clean_phone = "".join(filter(str.isdigit, c.phone))
                        if len(clean_phone) >= 7 and clean_phone in seen_phones:
                            await self._upsert_open_issue(
                                db,
                                company_id=company_id,
                                issue_type=DataQualityIssueType.CUSTOMER_DUPLICATE_OR_INVALID_CONTACT,
                                severity=DataQualitySeverity.MEDIUM,
                                affected_module="Customers",
                                affected_record_id=str(c.id),
                                affected_record_type="Customer",
                                description=f"Duplicate customer phone '{c.phone}' detected after import",
                                details={"customer_id": str(c.id), "phone": c.phone, "import_id": str(import_history.id)},
                            )
                        elif len(clean_phone) >= 7:
                            seen_phones.add(clean_phone)
                await db.commit()

            elif "SALE" in import_type_str:
                # Scan for sales exceeding stock
                sales_res = await db.execute(
                    select(Sale).where(Sale.company_id == company_id).order_by(desc(Sale.created_at)).limit(50)
                )
                sales = sales_res.scalars().all()
                for s in sales:
                    await self.check_sale(db, s, company_id)
        except Exception as e:
            logger.warning(f"Data quality auto check on import failed (non-blocking): {e}")


data_quality_auto = DataQualityAutoService()
