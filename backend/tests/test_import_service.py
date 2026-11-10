import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from app.models.import_history import ImportType, ImportStatus, ImportHistory
from app.models.product import Product
from app.services.import_ import ImportService, ImportValidationError, DuplicateRecordError


def test_clean_header():
    assert ImportService._clean_header("Product Name") == "product name"
    assert ImportService._clean_header("product_name") == "product name"
    assert ImportService._clean_header("  Product-Name (Required) ") == "product name required"
    assert ImportService._clean_header('\ufeff"SKU"') == "sku"
    assert ImportService._clean_header("Unit_Price ($)") == "unit price"


def test_parse_csv_comma_delimiter():
    content = b"Product Name,SKU,Unit Price\nWidget A,SKU-001,19.99\nWidget B,SKU-002,29.99"
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols, rows = service.parse_csv(content)
    assert cols == ["Product Name", "SKU", "Unit Price"]
    assert len(rows) == 2
    assert rows[0]["Product Name"] == "Widget A"
    assert rows[0]["SKU"] == "SKU-001"
    assert rows[0]["Unit Price"] == "19.99"


def test_parse_csv_semicolon_delimiter():
    content = b"Product Name;SKU;Unit Price\nWidget A;SKU-001;19.99\nWidget B;SKU-002;29.99"
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols, rows = service.parse_csv(content)
    assert cols == ["Product Name", "SKU", "Unit Price"]
    assert len(rows) == 2
    assert rows[0]["Product Name"] == "Widget A"
    assert rows[0]["SKU"] == "SKU-001"


def test_parse_csv_tab_delimiter():
    content = b"Product Name\tSKU\tUnit Price\nWidget A\tSKU-001\t19.99"
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols, rows = service.parse_csv(content)
    assert cols == ["Product Name", "SKU", "Unit Price"]
    assert len(rows) == 1
    assert rows[0]["Product Name"] == "Widget A"


def test_validate_columns_with_aliases():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols = ["Name", "Product Code", "Category", "Price", "Stock"]
    service.validate_columns(ImportType.PRODUCTS, cols)

    norm = service.normalize_row(ImportType.PRODUCTS, {
        "Name": "Smart Watch",
        "Product Code": "SW-01",
        "Category": "Electronics",
        "Price": "199.99",
        "Stock": "50"
    })
    assert norm["product_name"] == "Smart Watch"
    assert norm["sku"] == "SW-01"
    assert norm["unit_price"] == "199.99"
    assert norm["category"] == "Electronics"
    assert norm["stock_quantity"] == "50"


def test_validate_columns_missing_required():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols = ["Category", "Stock Quantity"]
    with pytest.raises(ValueError) as exc_info:
        service.validate_columns(ImportType.PRODUCTS, cols)
    assert "Missing required column" in str(exc_info.value)
    assert "Product Name" in str(exc_info.value)


def test_validate_sales_multi_line_invoice():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cust_id = uuid4()
    prod1_id = uuid4()
    prod2_id = uuid4()

    customer_names = {"John Doe": cust_id}
    product_names = {"Widget A": prod1_id, "Widget B": prod2_id}
    available_stock = {prod1_id: 100, prod2_id: 100}

    row1 = {"customer": "John Doe", "product": "Widget A", "quantity": "2", "unit_price": "10.00", "sale_date": "2026-08-12", "invoice_number": "INV-2026-000005"}
    row2 = {"customer": "John Doe", "product": "Widget B", "quantity": "1", "unit_price": "20.00", "sale_date": "2026-08-12", "invoice_number": "INV-2026-000005"}

    existing_invoices = set()
    service.validate_row(ImportType.SALES, 2, row1, set(), set(), set(), existing_invoices, customer_names, product_names, available_stock)
    service.validate_row(ImportType.SALES, 3, row2, set(), set(), set(), existing_invoices, customer_names, product_names, available_stock)
    assert available_stock[prod1_id] == 98
    assert available_stock[prod2_id] == 99


def test_templates_for_all_four_types():
    for itype in [ImportType.PRODUCTS, ImportType.INVENTORY, ImportType.CUSTOMERS, ImportType.SALES]:
        csv_text = ImportService.get_template_csv(itype)
        assert len(csv_text) > 0
        lines = csv_text.strip().splitlines()
        assert len(lines) >= 2


def test_validate_inventory_columns_and_normalization():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    cols = ["Product Code", "Stock Quantity", "Movement Type", "Notes"]
    service.validate_columns(ImportType.INVENTORY, cols)
    norm = service.normalize_row(ImportType.INVENTORY, {
        "Product Code": "SKU-999",
        "Stock Quantity": "25",
        "Movement Type": "STOCK_IN",
        "Notes": "Restocked",
    })
    assert norm["sku"] == "SKU-999"
    assert norm["quantity"] == "25"
    assert norm["adjustment_type"] == "STOCK_IN"
    assert norm["reason"] == "Restocked"


def test_validate_inventory_row():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    dummy_product = MagicMock()
    dummy_product.sku = "SKU-100"
    existing_map = {"sku-100": dummy_product}
    existing_skus = set()

    # Valid row
    valid_row = {"sku": "SKU-100", "quantity": "10", "adjustment_type": "STOCK_IN", "reason": "Restock"}
    service.validate_row(
        ImportType.INVENTORY, 2, valid_row, existing_skus, set(), set(), set(), {}, {}, {},
        existing_products_map=existing_map, duplicate_action="SKIP"
    )
    assert "sku-100" in existing_skus

    # Product not found
    missing_prod_row = {"sku": "UNKNOWN-SKU", "quantity": "10", "adjustment_type": "STOCK_IN", "reason": "Restock"}
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(
            ImportType.INVENTORY, 3, missing_prod_row, existing_skus, set(), set(), set(), {}, {}, {},
            existing_products_map=existing_map, duplicate_action="SKIP"
        )
    assert "not found" in str(exc.value)

    # Invalid adjustment type
    bad_type_row = {"sku": "SKU-100", "quantity": "10", "adjustment_type": "INVALID_TYPE", "reason": "Restock"}
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(
            ImportType.INVENTORY, 4, bad_type_row, set(), set(), set(), set(), {}, {}, {},
            existing_products_map=existing_map, duplicate_action="SKIP"
        )
    assert "Invalid Adjustment Type" in str(exc.value)


def test_duplicate_modes_product():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    existing_skus = {"sku-001"}

    row = {"sku": "SKU-001", "product_name": "Test Product", "unit_price": "10.00", "stock_quantity": "5"}
    # REJECT mode raises DuplicateRecordError
    with pytest.raises(DuplicateRecordError) as exc:
        service.validate_row(ImportType.PRODUCTS, 2, row, existing_skus, set(), set(), set(), {}, {}, {}, duplicate_action="REJECT")
    assert "Duplicate SKU" in str(exc.value)

    # UPDATE mode allows it without exception
    service.validate_row(ImportType.PRODUCTS, 2, row, existing_skus, set(), set(), set(), {}, {}, {}, duplicate_action="UPDATE")


def test_customer_validation():
    service = ImportService(AsyncMock(), uuid4(), uuid4())
    existing_emails = set()
    existing_phones = set()

    # Valid customer
    valid = {"name": "Alice Johnson", "email": "alice@example.com", "phone": "+1-555-0144"}
    service.validate_row(ImportType.CUSTOMERS, 2, valid, set(), existing_emails, existing_phones, set(), {}, {}, {})
    assert "alice@example.com" in existing_emails

    # Invalid email
    invalid_email = {"name": "Bob", "email": "not-an-email", "phone": "+1-555-0155"}
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(ImportType.CUSTOMERS, 3, invalid_email, set(), existing_emails, existing_phones, set(), {}, {}, {})
    assert "Invalid email format" in str(exc.value)

    # Invalid phone
    invalid_phone = {"name": "Charlie", "email": "charlie@example.com", "phone": "abc"}
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(ImportType.CUSTOMERS, 4, invalid_phone, set(), existing_emails, existing_phones, set(), {}, {}, {})
    assert "Invalid phone format" in str(exc.value)


def test_product_validation_errors():
    service = ImportService(AsyncMock(), uuid4(), uuid4())

    # Missing SKU
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(ImportType.PRODUCTS, 2, {"product_name": "Test", "unit_price": "10.00"}, set(), set(), set(), set(), {}, {}, {})
    assert "SKU is required" in str(exc.value)

    # Negative price
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(ImportType.PRODUCTS, 3, {"sku": "S1", "product_name": "Test", "unit_price": "-5.00", "stock_quantity": "10"}, set(), set(), set(), set(), {}, {}, {})
    assert "greater than zero" in str(exc.value)

    # Negative stock
    with pytest.raises(ImportValidationError) as exc:
        service.validate_row(ImportType.PRODUCTS, 4, {"sku": "S2", "product_name": "Test", "unit_price": "5.00", "stock_quantity": "-1"}, set(), set(), set(), set(), {}, {}, {})
    assert "Stock Quantity cannot be negative" in str(exc.value)


def test_error_csv_generation():
    errors = [
        {"row_number": 2, "field": "sku", "error_type": "DUPLICATE", "error_message": "Duplicate SKU 'S1'", "raw_data": "{'sku': 'S1'}"},
        {"row_number": 5, "field": "unit_price", "error_type": "INVALID_VALUE", "error_message": "Unit Price must be greater than zero", "raw_data": "{'unit_price': '-10'}"},
    ]
    csv_str = ImportService.format_error_csv(errors)
    assert "Row Number,Field,Error Type,Error Message,Raw Data" in csv_str
    assert "Duplicate SKU 'S1'" in csv_str
    assert "Unit Price must be greater than zero" in csv_str
