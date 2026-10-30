import pytest
import uuid
from datetime import datetime
from app.models.company import Company
from app.models.user import User, UserRole
from app.models.product import Product, ProductStatus
from app.models.sale import Sale, SaleItem, SaleStatus, SalesChannel, PaymentMethod, PaymentStatus
from app.models.customer import Customer
from app.models.inventory import StockMovement, MovementType
from app.models.data_quality import (
    DataQualityIssue,
    DataQualityIssueStatus,
    DataQualityIssueType,
    DataQualitySeverity,
    ReconciliationStatus,
)
from app.services.data_quality_service import data_quality_service
from app.services.data_quality_auto import data_quality_auto
from app.crud.data_quality import data_quality_issue, reconciliation_run


@pytest.mark.asyncio
async def test_reconciliation_detects_inconsistencies(db_session):
    company_id = uuid.uuid4()
    company = Company(id=company_id, name="Test Company", is_active=True)
    db_session.add(company)

    user = User(
        id=uuid.uuid4(),
        company_id=company_id,
        email="admin@test.com",
        name="Admin User",
        hashed_password="pw",
        role=UserRole.COMPANY_ADMIN,
        is_active=True,
    )
    db_session.add(user)

    # 1. Product with duplicate SKU & negative stock
    prod1 = Product(
        id=uuid.uuid4(),
        company_id=company_id,
        name="Widget A",
        sku="SKU-DUP",
        unit_price=10.0,
        cost_price=5.0,
        stock_quantity=-2,
        status=ProductStatus.ACTIVE,
    )
    prod2 = Product(
        id=uuid.uuid4(),
        company_id=company_id,
        name="Widget B",
        sku="SKU-DUP",
        unit_price=15.0,
        cost_price=8.0,
        stock_quantity=10,
        status=ProductStatus.ACTIVE,
    )
    db_session.add_all([prod1, prod2])

    # 2. Inactive product referenced by completed sale
    inactive_prod = Product(
        id=uuid.uuid4(),
        company_id=company_id,
        name="Old Widget",
        sku="SKU-OLD",
        unit_price=20.0,
        cost_price=10.0,
        stock_quantity=5,
        status=ProductStatus.INACTIVE,
    )
    db_session.add(inactive_prod)

    sale1 = Sale(
        id=uuid.uuid4(),
        company_id=company_id,
        invoice_number="INV-001",
        sales_channel=SalesChannel.RETAIL,
        payment_method=PaymentMethod.CASH,
        payment_status=PaymentStatus.PAID,
        total_amount=50.0,
        status=SaleStatus.COMPLETED,
    )
    db_session.add(sale1)
    item1 = SaleItem(
        id=uuid.uuid4(),
        sale_id=sale1.id,
        product_id=inactive_prod.id,
        quantity=2,
        unit_price=20.0,
        total=40.0,
    )
    db_session.add(item1)

    # 3. Stock movement with math error
    movement = StockMovement(
        id=uuid.uuid4(),
        company_id=company_id,
        product_id=prod1.id,
        movement_type=MovementType.MANUAL_ADJUSTMENT,
        previous_quantity=10,
        quantity_changed=5,
        updated_quantity=20,  # 10 + 5 != 20
        reason="Adjustment error test",
    )
    db_session.add(movement)

    await db_session.commit()

    # Run reconciliation
    run = await data_quality_service.run_reconciliation(
        db_session, company_id=company_id, user_id=user.id, user_name=user.name
    )

    assert run is not None
    assert run.records_checked > 0
    assert run.issues_detected >= 3
    assert run.status in (ReconciliationStatus.COMPLETED_WITH_ISSUES, ReconciliationStatus.COMPLETED)

    # Verify issues retrieved
    issues, total = await data_quality_issue.get_multi(db_session, company_id=company_id)
    assert total >= 3
    types = [i.issue_type for i in issues]
    assert DataQualityIssueType.DUPLICATE_OR_INVALID_PRODUCT_SKU in types
    assert DataQualityIssueType.SALE_INACTIVE_OR_MISSING_PRODUCT in types
    assert DataQualityIssueType.STOCK_MOVEMENT_INCONSISTENT in types


@pytest.mark.asyncio
async def test_issue_status_update_and_tenant_isolation(db_session):
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    db_session.add_all([
        Company(id=company_a, name="Company A", is_active=True),
        Company(id=company_b, name="Company B", is_active=True),
    ])

    user_a = User(
        id=uuid.uuid4(),
        company_id=company_a,
        email="usera@test.com",
        name="User A",
        hashed_password="pw",
        role=UserRole.COMPANY_ADMIN,
        is_active=True,
    )
    db_session.add(user_a)

    # Issue in Company A
    issue = await data_quality_issue.create(
        db_session,
        company_id=company_a,
        issue_type=DataQualityIssueType.SALE_EXCEEDS_STOCK,
        severity=DataQualitySeverity.CRITICAL,
        affected_module="Sales",
        description="Sale exceeds stock test",
        details={"sale_id": "123"},
        commit=True,
    )

    # Company B cannot see Company A's issue
    issues_b, total_b = await data_quality_issue.get_multi(db_session, company_id=company_b)
    assert total_b == 0

    # Company A sees the issue
    issues_a, total_a = await data_quality_issue.get_multi(db_session, company_id=company_a)
    assert total_a == 1
    assert issues_a[0].status == DataQualityIssueStatus.OPEN

    # Update status to RESOLVED
    updated = await data_quality_issue.update_status(
        db_session,
        issue=issue,
        new_status=DataQualityIssueStatus.RESOLVED,
        resolved_by=user_a.id,
        resolution_note="Manually adjusted stock and reconciled",
        commit=True,
    )
    assert updated.status == DataQualityIssueStatus.RESOLVED
    assert updated.resolved_by == user_a.id
    assert updated.resolution_note == "Manually adjusted stock and reconciled"
    assert updated.previous_status == "OPEN"


@pytest.mark.asyncio
async def test_automatic_checks_on_sale_and_inventory(db_session):
    company_id = uuid.uuid4()
    db_session.add(Company(id=company_id, name="Auto Check Co", is_active=True))

    prod = Product(
        id=uuid.uuid4(),
        company_id=company_id,
        name="Auto Prod",
        sku="SKU-AUTO",
        unit_price=25.0,
        cost_price=12.0,
        stock_quantity=-5,
        status=ProductStatus.ACTIVE,
    )
    db_session.add(prod)

    sale = Sale(
        id=uuid.uuid4(),
        company_id=company_id,
        invoice_number="INV-AUTO-1",
        sales_channel=SalesChannel.RETAIL,
        payment_method=PaymentMethod.UPI,
        payment_status=PaymentStatus.PAID,
        total_amount=100.0,
        status=SaleStatus.COMPLETED,
    )
    db_session.add(sale)
    item = SaleItem(
        id=uuid.uuid4(),
        sale_id=sale.id,
        product_id=prod.id,
        quantity=4,
        unit_price=25.0,
        total=100.0,
    )
    db_session.add(item)
    await db_session.commit()

    # Trigger automatic check on sale
    await data_quality_auto.check_sale(db_session, sale, company_id)

    # Verify SALE_EXCEEDS_STOCK detected automatically
    issue = await data_quality_issue.get_open_issue_for_record(
        db_session,
        company_id=company_id,
        issue_type=DataQualityIssueType.SALE_EXCEEDS_STOCK,
        affected_record_id=str(sale.id),
        affected_module="Sales",
    )
    assert issue is not None
    assert issue.severity == DataQualitySeverity.CRITICAL
