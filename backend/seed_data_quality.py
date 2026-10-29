import asyncio
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select
from app.database import SessionLocal
from app.models.company import Company
from app.models.user import User
from app.models.customer import Customer, CustomerType, CustomerStatus
from app.models.product import Product, ProductStatus, UnitOfMeasure
from app.models.sale import Sale, SaleItem, SalesChannel, PaymentMethod, PaymentStatus, SaleStatus
from app.models.inventory import StockMovement, MovementType
from app.services.data_quality_service import data_quality_service


async def seed():
    async with SessionLocal() as db:
        # Find active user & company
        user_res = await db.execute(select(User).limit(1))
        user = user_res.scalar_one_or_none()
        if not user:
            print("No user found in database. Please register/create a user first.")
            return

        company_id = user.company_id
        user_id = user.id
        user_name = user.name
        print(f"Seeding Data Quality test data for Company: {company_id}, User: {user_name} ({user.email})")

        phone_suffix = uuid.uuid4().hex[:4]
        c1 = Customer(
            company_id=company_id,
            first_name="Alex",
            last_name="Morgan",
            email=f"alex.morgan.{uuid.uuid4().hex[:6]}@example.com",
            phone=f"+1 555-{phone_suffix}1",
            city="New York",
            state="NY",
            country="USA",
            customer_type=CustomerType.RETAIL,
        )
        c2 = Customer(
            company_id=company_id,
            first_name="Priya",
            last_name="Sharma",
            email=f"priya.sharma.{uuid.uuid4().hex[:6]}@example.com",
            phone=f"+1 555-{phone_suffix}2",
            city="San Francisco",
            state="CA",
            country="USA",
            customer_type=CustomerType.WHOLESALE,
        )
        c3 = Customer(
            company_id=company_id,
            first_name="Liam",
            last_name="Johnson",
            email=f"liam.j.{uuid.uuid4().hex[:6]}@example.com",
            phone=f"+1 555-{phone_suffix}3",
            city="Chicago",
            state="IL",
            country="USA",
            customer_type=CustomerType.CORPORATE,
        )
        db.add_all([c1, c2, c3])
        await db.flush()

        # 2. Products (Valid)
        p_monitor = Product(
            company_id=company_id,
            name="4K Ultra-HD Gaming Monitor 27\"",
            sku=f"MON-4K-{uuid.uuid4().hex[:4].upper()}",
            brand="VisionTech",
            description="144Hz IPS Gaming Monitor with HDR",
            unit_price=349.99,
            cost_price=210.00,
            stock_quantity=45,
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )
        p_keyboard = Product(
            company_id=company_id,
            name="Mechanical Wireless Keyboard",
            sku=f"KB-MECH-{uuid.uuid4().hex[:4].upper()}",
            brand="KeyCraft",
            description="RGB Hot-swappable mechanical switches",
            unit_price=89.99,
            cost_price=42.00,
            stock_quantity=110,
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )
        p_chair = Product(
            company_id=company_id,
            name="Ergonomic Lumbar Office Chair",
            sku=f"CHR-ERGO-{uuid.uuid4().hex[:4].upper()}",
            brand="ErgoPlus",
            description="Breathable mesh ergonomic desk chair",
            unit_price=199.99,
            cost_price=110.00,
            stock_quantity=28,
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )

        # 3. Products with Intentional Quality Issues:
        # Issue 3A: Product with duplicate SKU of p_keyboard
        p_duplicate_sku = Product(
            company_id=company_id,
            name="Mechanical Keyboard - Special Edition",
            sku=p_keyboard.sku,  # DUPLICATE SKU!
            brand="KeyCraft",
            description="Duplicate SKU test item",
            unit_price=99.99,
            cost_price=50.00,
            stock_quantity=15,
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )

        # Issue 3B: Product missing mandatory name/sku
        p_missing_info = Product(
            company_id=company_id,
            name="",  # MISSING MANDATORY NAME!
            sku="",   # MISSING MANDATORY SKU!
            brand="Generic",
            description="Item with missing mandatory name and SKU fields",
            unit_price=19.99,
            cost_price=10.00,
            stock_quantity=50,
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )

        # Issue 3C: Inactive product (used later in a sale)
        p_inactive = Product(
            company_id=company_id,
            name="Vintage Bluetooth Radio (Discontinued)",
            sku=f"RAD-DISC-{uuid.uuid4().hex[:4].upper()}",
            brand="RetroSound",
            description="Discontinued vintage style radio",
            unit_price=65.00,
            cost_price=30.00,
            stock_quantity=12,
            status=ProductStatus.INACTIVE,  # INACTIVE STATUS!
            unit_of_measure=UnitOfMeasure.PCS,
        )

        # Issue 3D: Product with very low stock (used for oversell)
        p_low_stock = Product(
            company_id=company_id,
            name="Smart Noise-Canceling Earbuds Pro",
            sku=f"EAR-PRO-{uuid.uuid4().hex[:4].upper()}",
            brand="AudioSync",
            description="Active noise canceling wireless earbuds",
            unit_price=149.99,
            cost_price=75.00,
            stock_quantity=5,  # Only 5 in stock!
            status=ProductStatus.ACTIVE,
            unit_of_measure=UnitOfMeasure.PCS,
        )

        db.add_all([p_monitor, p_keyboard, p_chair, p_duplicate_sku, p_missing_info, p_inactive, p_low_stock])
        await db.flush()

        # 4. Valid Sales
        uid_s = uuid.uuid4().hex[:6].upper()
        s_valid_1 = Sale(
            company_id=company_id,
            invoice_number=f"INV-{uid_s}-101",
            customer_id=c1.id,
            customer_name=f"{c1.first_name} {c1.last_name}",
            sale_date=datetime.utcnow() - timedelta(days=2),
            sales_channel=SalesChannel.ONLINE,
            payment_method=PaymentMethod.CARD,
            payment_status=PaymentStatus.PAID,
            total_amount=699.98,
            status=SaleStatus.COMPLETED,
            created_by=user_id,
        )
        db.add(s_valid_1)
        await db.flush()

        item_valid_1 = SaleItem(
            sale_id=s_valid_1.id,
            product_id=p_monitor.id,
            quantity=2,
            unit_price=349.99,
            total=699.98,
        )
        db.add(item_valid_1)

        # 5. Sales with Quality Issues:
        # Issue 5A: SALE_EXCEEDS_STOCK (Critical)
        s_exceeds_stock = Sale(
            company_id=company_id,
            invoice_number=f"INV-{uid_s}-ERR-STOCK",
            customer_id=c2.id,
            customer_name=f"{c2.first_name} {c2.last_name}",
            sale_date=datetime.utcnow() - timedelta(days=1),
            sales_channel=SalesChannel.RETAIL,
            payment_method=PaymentMethod.CARD,
            payment_status=PaymentStatus.PAID,
            total_amount=7499.50,
            status=SaleStatus.COMPLETED,
            created_by=user_id,
            notes="Bulk sale order exceeding current on-hand warehouse stock",
        )
        db.add(s_exceeds_stock)
        await db.flush()

        item_exceeds_stock = SaleItem(
            sale_id=s_exceeds_stock.id,
            product_id=p_low_stock.id,
            quantity=50,  # 50 ordered, but p_low_stock has only 5 in stock!
            unit_price=149.99,
            total=7499.50,
        )
        db.add(item_exceeds_stock)

        # Issue 5B: SALE_INACTIVE_OR_MISSING_PRODUCT (High)
        s_inactive_prod = Sale(
            company_id=company_id,
            invoice_number=f"INV-{uid_s}-ERR-INACTIVE",
            customer_id=c3.id,
            customer_name=f"{c3.first_name} {c3.last_name}",
            sale_date=datetime.utcnow() - timedelta(hours=18),
            sales_channel=SalesChannel.ONLINE,
            payment_method=PaymentMethod.UPI,
            payment_status=PaymentStatus.PAID,
            total_amount=130.00,
            status=SaleStatus.COMPLETED,
            created_by=user_id,
            notes="Sale processed with discontinued product item",
        )
        db.add(s_inactive_prod)
        await db.flush()

        item_inactive = SaleItem(
            sale_id=s_inactive_prod.id,
            product_id=p_inactive.id,  # Points to inactive product
            quantity=2,
            unit_price=65.00,
            total=130.00,
        )
        db.add(item_inactive)

        # Issue 5C: SALE_INVALID_CUSTOMER (Medium)
        fake_cust_id = uuid.uuid4()
        s_invalid_cust = Sale(
            company_id=company_id,
            invoice_number=f"INV-{uid_s}-ERR-BADCUST",
            customer_id=fake_cust_id,  # Does not exist in customers table!
            customer_name="Orphan Customer Record",
            sale_date=datetime.utcnow() - timedelta(hours=6),
            sales_channel=SalesChannel.MARKETPLACE,
            payment_method=PaymentMethod.CASH,
            payment_status=PaymentStatus.PAID,
            total_amount=199.99,
            status=SaleStatus.COMPLETED,
            created_by=user_id,
            notes="Imported order with missing foreign key customer link",
        )
        db.add(s_invalid_cust)
        await db.flush()

        item_invalid_cust = SaleItem(
            sale_id=s_invalid_cust.id,
            product_id=p_chair.id,
            quantity=1,
            unit_price=199.99,
            total=199.99,
        )
        db.add(item_invalid_cust)

        # 6. Stock Movements
        # Valid movement
        sm_valid = StockMovement(
            company_id=company_id,
            product_id=p_monitor.id,
            movement_type=MovementType.SALE,
            previous_quantity=47,
            quantity_changed=-2,
            updated_quantity=45,  # 47 - 2 = 45 (CORRECT)
            reason="Sale fulfilled for invoice INV-101",
            user_id=user_id,
        )
        # Inconsistent movement (High)
        sm_inconsistent = StockMovement(
            company_id=company_id,
            product_id=p_chair.id,
            movement_type=MovementType.MANUAL_ADJUSTMENT,
            previous_quantity=100,
            quantity_changed=-20,
            updated_quantity=50,  # 100 - 20 should be 80, but stored as 50! (MISMATCH)
            reason="Manual count adjustment discrepancies",
            user_id=user_id,
        )
        db.add_all([sm_valid, sm_inconsistent])

        await db.commit()
        print("Test data seeded successfully into the database.")

        # 7. Run Reconciliation
        print("\nTriggering Data Quality Reconciliation Run...")
        run = await data_quality_service.run_reconciliation(
            db, company_id=company_id, user_id=user_id, user_name=user_name
        )
        print(f"Reconciliation Execution ID: {run.execution_id}")
        print(f"Status: {run.status}")
        print(f"Records Checked: {run.records_checked}")
        print(f"Issues Detected: {run.issues_detected}")
        print(f"Failed Checks: {run.failed_checks}")

        # 8. Check Dashboard Summary
        from app.routers.data_quality import get_dashboard
        dash = await get_dashboard(current_user=user, db=db)
        print("\n--- Data Quality Dashboard Summary ---")
        print(f"Total Records Checked: {dash.total_records_checked}")
        print(f"Valid Records: {dash.valid_records}")
        print(f"Records with Errors (CRITICAL / HIGH): {dash.records_with_errors}")
        print(f"Records with Warnings (MEDIUM / LOW): {dash.records_with_warnings}")
        print(f"Unresolved Issues: {dash.unresolved_issues}")
        print(f"Issues by Status: {dash.issues_by_status}")
        print(f"Issues by Severity: {dash.issues_by_severity}")
        print(f"Issues by Module: {dash.issues_by_module}")


if __name__ == "__main__":
    asyncio.run(seed())
