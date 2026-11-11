import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime

from app.models.import_history import ImportType, ImportStatus, ImportHistory
from app.models.product import Product
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem
from app.services.import_ import ImportService, ImportValidationError, DuplicateRecordError
from app.services.import_storage import validate_csv_content


def test_validate_all_four_types_templates():
    for itype in [ImportType.PRODUCTS, ImportType.INVENTORY, ImportType.CUSTOMERS, ImportType.SALES]:
        template = ImportService.get_template_csv(itype)
        service = ImportService(AsyncMock(), uuid4(), uuid4())
        cols, rows = service.parse_csv(file_content=template.encode("utf-8"))
        service.validate_columns(itype, cols)
        assert len(cols) >= 3
        assert len(rows) >= 1


def test_malformed_csv_handling():
    service = ImportService(AsyncMock(), uuid4(), uuid4())

    # Empty content returns empty structures
    cols, rows = service.parse_csv(file_content=b"")
    assert cols == []
    assert rows == []

    # Missing mandatory product columns raises ValueError
    bad_csv = b"Product Name,Category\nItem 1,Electronics\n"
    cols, rows = service.parse_csv(file_content=bad_csv)
    with pytest.raises(ValueError) as exc:
        service.validate_columns(ImportType.PRODUCTS, cols)
    assert "Missing required column" in str(exc.value)


def test_inventory_duplicate_modes_validation():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    existing_skus = {"sku-inv-1"}
    dummy_prod = MagicMock()
    existing_map = {"sku-inv-1": dummy_prod}

    row = {"sku": "SKU-INV-1", "quantity": "10", "adjustment_type": "STOCK_IN", "reason": "Restock"}

    # In REJECT mode, multiple adjustments for same SKU in file raises DuplicateRecordError
    with pytest.raises(DuplicateRecordError):
        service.validate_row(ImportType.INVENTORY, 2, row, existing_skus, set(), set(), set(), {}, {}, {}, existing_products_map=existing_map, duplicate_action="REJECT")

    # In UPDATE mode, duplicate is accepted
    service.validate_row(ImportType.INVENTORY, 3, row, existing_skus, set(), set(), set(), {}, {}, {}, existing_products_map=existing_map, duplicate_action="UPDATE")


def test_sales_duplicate_modes_validation():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cust_id = uuid4()
    prod_id = uuid4()
    customer_names = {"Alice": cust_id}
    product_names = {"Widget": prod_id}
    available_stock = {prod_id: 100}
    existing_invoices = {"INV-EXISTING-01"}

    row = {
        "customer": "Alice",
        "product": "Widget",
        "quantity": "2",
        "unit_price": "10.00",
        "sale_date": "2026-05-01",
        "invoice_number": "INV-EXISTING-01",
    }

    # In REJECT mode, existing invoice raises DuplicateRecordError
    with pytest.raises(DuplicateRecordError):
        service.validate_row(ImportType.SALES, 2, row, set(), set(), set(), existing_invoices, customer_names, product_names, available_stock, duplicate_action="REJECT")

    # In UPDATE mode, existing invoice is allowed
    service.validate_row(ImportType.SALES, 3, row, set(), set(), set(), existing_invoices, customer_names, product_names, available_stock, duplicate_action="UPDATE")


def test_import_cancellation_and_result_building():
    company_id = uuid4()
    user_id = uuid4()
    service = ImportService(AsyncMock(), company_id, user_id)
    history = ImportHistory(
        id=uuid4(),
        company_id=company_id,
        import_type=ImportType.PRODUCTS,
        filename="test_upload.csv",
        total_records=100,
        successful_records=95,
        failed_records=5,
        duplicate_records=2,
        skipped_records=3,
        status=ImportStatus.COMPLETED_WITH_ERRORS,
    )

    result = service._build_result(history, errors=[], reconciliation={"status": "CHECKED", "issues_detected": 0})
    assert result["status"] == "COMPLETED_WITH_ERRORS"
    assert result["import_id"] == str(history.id)
    assert result["successful_records"] == 95
    assert result["reconciliation"]["status"] == "CHECKED"


def test_file_validation_security_enforcement():
    # Valid CSV content passes
    valid_bytes = b"Name,Email,Phone\nAlice,alice@example.com,+15551234\n"
    text = validate_csv_content(valid_bytes, "customers.csv")
    assert "alice@example.com" in text

    # Binary PE executable is blocked
    with pytest.raises(Exception) as exc:
        validate_csv_content(b"MZ\x90\x00\x03\x00\x00\x00", "malicious.csv")
    assert "binary file" in str(exc.value).lower()

    # Binary ZIP is blocked
    with pytest.raises(Exception) as exc:
        validate_csv_content(b"PK\x03\x04testdata", "fake.csv")
    assert "binary file" in str(exc.value).lower()
