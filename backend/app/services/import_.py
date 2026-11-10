import csv
import io
import re
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.import_history import ImportHistory, ImportStatus, ImportType
from app.models.product import Product
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem, SalesChannel, PaymentMethod, SaleStatus, PaymentStatus
from app.models.invoice_sequence import InvoiceSequence
from app.models.inventory import StockMovement, InventoryAdjustment, MovementType, AdjustmentType
from app.crud.import_history import import_history as import_history_crud
from app.models.notification import NotificationType, NotificationPriority, NotificationResourceType
from app.crud.notification import notification as notification_crud
from app.services.notification import notification_service

logger = logging.getLogger("retailpulse")


class ImportNotificationError(Exception):
    pass


class ImportValidationError(Exception):
    def __init__(self, row_number: int, field: str | None, message: str, raw_data: str | None = None, error_type: str = "VALIDATION_ERROR"):
        self.row_number = row_number
        self.field = field
        self.message = message
        self.raw_data = raw_data
        self.error_type = error_type
        super().__init__(message)


class DuplicateRecordError(Exception):
    def __init__(self, row_number: int, field: str | None, message: str, raw_data: str | None = None, error_type: str = "DUPLICATE"):
        self.row_number = row_number
        self.field = field
        self.message = message
        self.raw_data = raw_data
        self.error_type = error_type
        super().__init__(message)


class ImportService:
    IMPORT_CONFIG = {
        ImportType.PRODUCTS: {
            "required_columns": ["Product Name", "SKU", "Category", "Unit Price", "Stock Quantity"],
            "column_map": {
                "Product Name": "product_name",
                "SKU": "sku",
                "Category": "category",
                "Unit Price": "unit_price",
                "Stock Quantity": "stock_quantity",
            },
            "aliases": {
                "product_name": ["product name", "product_name", "productname", "name", "title", "product", "item name", "item_name", "item", "description", "product title"],
                "sku": ["sku", "product sku", "item sku", "code", "product code", "item code", "id", "product id"],
                "category": ["category", "category name", "cat", "group", "type", "category_name"],
                "unit_price": ["unit price", "unit_price", "price", "cost", "unit cost", "rate", "selling price", "amount", "price ($)"],
                "stock_quantity": ["stock quantity", "stock_quantity", "stock", "quantity", "qty", "count", "inventory", "stock level", "current stock"],
            },
        },
        ImportType.INVENTORY: {
            "required_columns": ["SKU", "Quantity", "Adjustment Type", "Reason"],
            "column_map": {
                "SKU": "sku",
                "Quantity": "quantity",
                "Adjustment Type": "adjustment_type",
                "Reason": "reason",
            },
            "aliases": {
                "sku": ["sku", "product sku", "product_sku", "item code", "product code", "item sku", "code", "product id", "id"],
                "quantity": ["quantity", "qty", "count", "stock quantity", "adjustment quantity", "units", "amount", "change"],
                "adjustment_type": ["adjustment type", "adjustment_type", "type", "operation", "action", "movement type", "movement_type"],
                "reason": ["reason", "notes", "note", "remarks", "comment", "description", "details"],
            },
        },
        ImportType.CUSTOMERS: {
            "required_columns": ["Name", "Email", "Phone"],
            "column_map": {
                "Name": "name",
                "Email": "email",
                "Phone": "phone",
            },
            "aliases": {
                "name": ["name", "customer name", "customer_name", "full name", "client name", "client", "contact name", "customer", "first name"],
                "email": ["email", "email address", "email_address", "mail", "e mail"],
                "phone": ["phone", "phone number", "phone_number", "mobile", "contact", "tel", "telephone", "cell"],
            },
        },
        ImportType.SALES: {
            "required_columns": ["Customer", "Product", "Quantity", "Unit Price", "Sale Date", "Invoice Number"],
            "column_map": {
                "Customer": "customer",
                "Product": "product",
                "Quantity": "quantity",
                "Unit Price": "unit_price",
                "Sale Date": "sale_date",
                "Invoice Number": "invoice_number",
            },
            "aliases": {
                "customer": ["customer", "customer name", "customer_name", "client", "client name", "buyer"],
                "product": ["product", "product name", "product_name", "item", "item name", "title"],
                "quantity": ["quantity", "qty", "count", "amount", "units", "items count"],
                "unit_price": ["unit price", "unit_price", "price", "rate", "unit cost", "selling price"],
                "sale_date": ["sale date", "sale_date", "date", "transaction date", "created at", "timestamp", "order date"],
                "invoice_number": ["invoice number", "invoice_number", "invoice no", "invoice no.", "transaction number", "transaction id", "txn id", "ref number", "reference number"],
            },
        },
    }

    # Template definitions with sample rows for downloads
    TEMPLATES = {
        ImportType.PRODUCTS: (
            ["Product Name", "SKU", "Category", "Unit Price", "Stock Quantity"],
            [
                ["Organic Cotton T-Shirt", "TSH-ORG-001", "Apparel", "24.99", "150"],
                ["Wireless Ergonomic Mouse", "MOU-WIR-002", "Electronics", "49.99", "75"],
            ],
        ),
        ImportType.INVENTORY: (
            ["SKU", "Quantity", "Adjustment Type", "Reason"],
            [
                ["TSH-ORG-001", "50", "STOCK_IN", "Restock from supplier"],
                ["MOU-WIR-002", "5", "STOCK_OUT", "Damaged goods write-off"],
            ],
        ),
        ImportType.CUSTOMERS: (
            ["Name", "Email", "Phone"],
            [
                ["Jane Doe", "jane.doe@example.com", "+1-555-0199"],
                ["Alex Smith", "alex.smith@example.com", "+1-555-0288"],
            ],
        ),
        ImportType.SALES: (
            ["Customer", "Product", "Quantity", "Unit Price", "Sale Date", "Invoice Number"],
            [
                ["Jane Doe", "Organic Cotton T-Shirt", "2", "24.99", "2026-11-01", "INV-2026-000101"],
                ["Alex Smith", "Wireless Ergonomic Mouse", "1", "49.99", "2026-11-01", "INV-2026-000102"],
            ],
        ),
    }

    def __init__(self, db: AsyncSession, company_id: UUID, uploaded_by: UUID | None):
        self.db = db
        self.company_id = company_id
        self.uploaded_by = uploaded_by

    @classmethod
    def get_template_csv(cls, import_type: ImportType) -> str:
        headers, sample_rows = cls.TEMPLATES.get(import_type, ([], []))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in sample_rows:
            writer.writerow(row)
        return output.getvalue()

    @staticmethod
    def _clean_header(name: str) -> str:
        if not name:
            return ""
        cleaned = name.strip().strip('"').strip("'").lstrip("\ufeff").lower()
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _find_matching_header(self, import_type: ImportType, target_req: str, columns: list[str]) -> str | None:
        target_clean = self._clean_header(target_req)
        clean_cols = {self._clean_header(c): c for c in columns if c}
        if target_clean in clean_cols:
            return clean_cols[target_clean]

        field = self.IMPORT_CONFIG[import_type]["column_map"].get(target_req)
        aliases = self.IMPORT_CONFIG[import_type].get("aliases", {}).get(field, [])
        for alias in aliases:
            alias_clean = self._clean_header(alias)
            if alias_clean in clean_cols:
                return clean_cols[alias_clean]
        return None

    async def create_import_history(self, import_type: ImportType, filename: str, total_records: int, commit: bool = True) -> ImportHistory:
        return await import_history_crud.create(self.db, self.company_id, import_type, filename, self.uploaded_by, total_records, commit=commit)

    async def get_import_history(self, import_id: UUID) -> ImportHistory | None:
        return await import_history_crud.get(self.db, import_id, self.company_id)

    async def list_import_history(self, skip: int = 0, limit: int = 100, import_type: ImportType | None = None, status: ImportStatus | None = None) -> tuple[list[ImportHistory], int]:
        return await import_history_crud.list(self.db, self.company_id, skip=skip, limit=limit, import_type=import_type, status=status)

    async def get_import_errors(self, import_id: UUID) -> list[dict]:
        errors = await import_history_crud.get_errors(self.db, import_id, self.company_id)
        return [
            {
                "id": str(e.id),
                "import_id": str(e.import_id),
                "row_number": e.row_number,
                "field": e.field,
                "error_type": getattr(e, "error_type", "VALIDATION_ERROR") or "VALIDATION_ERROR",
                "error_message": e.error_message,
                "raw_data": e.raw_data,
            }
            for e in errors
        ]

    @staticmethod
    def format_error_csv(errors: list[dict]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Row Number", "Field", "Error Type", "Error Message", "Raw Data"])
        for err in errors:
            writer.writerow([
                err.get("row_number", ""),
                err.get("field", ""),
                err.get("error_type", "VALIDATION_ERROR"),
                err.get("error_message", ""),
                err.get("raw_data", ""),
            ])
        return output.getvalue()

    async def generate_error_csv(self, import_id: UUID) -> str:
        errors = await self.get_import_errors(import_id)
        return self.format_error_csv(errors)

    def parse_csv(self, file_content: bytes) -> tuple[list[str], list[dict[str, str]]]:
        try:
            text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = file_content.decode("latin-1")
            except UnicodeDecodeError:
                text = file_content.decode("utf-8", errors="replace")

        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return [], []

        sample = "\n".join(lines[:10])
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except Exception:
            header_line = lines[0]
            if ";" in header_line and "," not in header_line:
                delimiter = ";"
            elif "\t" in header_line:
                delimiter = "\t"
            elif "|" in header_line:
                delimiter = "|"

        reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
        columns = [c.strip().strip('"').strip("'").lstrip("\ufeff") for c in (reader.fieldnames or []) if c]
        rows = []
        for r in reader:
            clean_r = {}
            for k, v in r.items():
                if k:
                    clean_k = k.strip().strip('"').strip("'").lstrip("\ufeff")
                    clean_r[clean_k] = v.strip() if isinstance(v, str) else ""
            rows.append(clean_r)
        return columns, rows

    def validate_columns(self, import_type: ImportType, columns: list[str]) -> None:
        required = self.IMPORT_CONFIG[import_type]["required_columns"]
        missing = []
        for col in required:
            matched = self._find_matching_header(import_type, col, columns)
            if not matched:
                field = self.IMPORT_CONFIG[import_type]["column_map"].get(col)
                aliases = self.IMPORT_CONFIG[import_type].get("aliases", {}).get(field, [])
                missing.append(f"'{col}' (accepted names: {', '.join(aliases[:4])})")
        if missing:
            raise ValueError(f"Missing required column(s): {'; '.join(missing)}")

    def normalize_row(self, import_type: ImportType, row: dict[str, str]) -> dict[str, Any]:
        column_map = self.IMPORT_CONFIG[import_type]["column_map"]
        normalized: dict[str, Any] = {}
        columns = list(row.keys())
        for csv_col, field in column_map.items():
            matched_header = self._find_matching_header(import_type, csv_col, columns)
            value = row.get(matched_header, "").strip() if matched_header else ""
            normalized[field] = value
        return normalized

    def validate_row(
        self,
        import_type: ImportType,
        row_number: int,
        normalized_row: dict[str, Any],
        existing_skus: set[str],
        existing_emails: set[str],
        existing_phones: set[str],
        existing_invoices: set[str],
        customer_names: dict[str, UUID],
        product_names: dict[str, UUID],
        available_stock: dict[UUID, int],
        existing_products_map: Optional[dict[str, Product]] = None,
        duplicate_action: str = "SKIP",
    ) -> None:
        if import_type == ImportType.PRODUCTS:
            sku = (normalized_row.get("sku") or "").strip()
            product_name = (normalized_row.get("product_name") or "").strip()
            if not sku:
                raise ImportValidationError(row_number, "sku", "SKU is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not product_name:
                raise ImportValidationError(row_number, "product_name", "Product Name is required", str(normalized_row), "MANDATORY_FIELD_MISSING")

            sku_lower = sku.lower()
            if sku_lower in existing_skus:
                if duplicate_action == "REJECT":
                    raise DuplicateRecordError(row_number, "sku", f"Duplicate SKU: '{sku}'", str(normalized_row))
                elif duplicate_action == "SKIP":
                    raise DuplicateRecordError(row_number, "sku", f"Duplicate SKU '{sku}' (will be skipped)", str(normalized_row))
                # For UPDATE, we permit duplicate and record will be updated
            else:
                existing_skus.add(sku_lower)

            try:
                price = Decimal(str(normalized_row.get("unit_price", "0")))
            except (InvalidOperation, TypeError, ValueError):
                raise ImportValidationError(row_number, "unit_price", f"Invalid Unit Price: '{normalized_row.get('unit_price')}'", str(normalized_row), "DATA_TYPE_ERROR")
            if price <= 0:
                raise ImportValidationError(row_number, "unit_price", "Unit Price must be greater than zero", str(normalized_row), "INVALID_VALUE")

            try:
                stock = int(str(normalized_row.get("stock_quantity", "0")))
            except (TypeError, ValueError):
                raise ImportValidationError(row_number, "stock_quantity", f"Invalid Stock Quantity: '{normalized_row.get('stock_quantity')}'", str(normalized_row), "DATA_TYPE_ERROR")
            if stock < 0:
                raise ImportValidationError(row_number, "stock_quantity", "Stock Quantity cannot be negative", str(normalized_row), "INVALID_VALUE")

        elif import_type == ImportType.INVENTORY:
            sku = (normalized_row.get("sku") or "").strip()
            qty_raw = (normalized_row.get("quantity") or "").strip()
            adj_type = (normalized_row.get("adjustment_type") or "").strip().upper()
            reason = (normalized_row.get("reason") or "").strip()

            if not sku:
                raise ImportValidationError(row_number, "sku", "SKU is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not qty_raw:
                raise ImportValidationError(row_number, "quantity", "Quantity is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not adj_type:
                raise ImportValidationError(row_number, "adjustment_type", "Adjustment Type is required", str(normalized_row), "MANDATORY_FIELD_MISSING")

            valid_types = {"STOCK_IN", "STOCK_OUT", "SET", "MANUAL_ADJUSTMENT", "ADD", "SUBTRACT"}
            if adj_type not in valid_types:
                raise ImportValidationError(
                    row_number, "adjustment_type",
                    f"Invalid Adjustment Type '{adj_type}'. Accepted values: STOCK_IN, STOCK_OUT, SET, MANUAL_ADJUSTMENT",
                    str(normalized_row), "INVALID_VALUE",
                )

            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                raise ImportValidationError(row_number, "quantity", f"Invalid Quantity: '{qty_raw}'", str(normalized_row), "DATA_TYPE_ERROR")
            if qty < 0:
                raise ImportValidationError(row_number, "quantity", "Quantity cannot be negative", str(normalized_row), "INVALID_VALUE")

            sku_lower = sku.lower()
            if existing_products_map is not None and sku_lower not in existing_products_map:
                raise ImportValidationError(row_number, "sku", f"Product with SKU '{sku}' not found in database", str(normalized_row), "FOREIGN_KEY_ERROR")

            # Duplicate detection within file for inventory
            if sku_lower in existing_skus:
                if duplicate_action == "REJECT":
                    raise DuplicateRecordError(row_number, "sku", f"Multiple adjustments for SKU '{sku}' in the same file", str(normalized_row))
                elif duplicate_action == "SKIP":
                    raise DuplicateRecordError(row_number, "sku", f"Duplicate adjustment for SKU '{sku}' (will be skipped)", str(normalized_row))
            else:
                existing_skus.add(sku_lower)

        elif import_type == ImportType.CUSTOMERS:
            name = (normalized_row.get("name") or "").strip()
            email = (normalized_row.get("email") or "").strip().lower()
            phone = (normalized_row.get("phone") or "").strip()

            if not name:
                raise ImportValidationError(row_number, "name", "Name is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not email:
                raise ImportValidationError(row_number, "email", "Email is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                raise ImportValidationError(row_number, "email", f"Invalid email format: '{email}'", str(normalized_row), "DATA_TYPE_ERROR")

            if email in existing_emails:
                if duplicate_action == "REJECT":
                    raise DuplicateRecordError(row_number, "email", f"Duplicate email: '{email}'", str(normalized_row))
                elif duplicate_action == "SKIP":
                    raise DuplicateRecordError(row_number, "email", f"Duplicate email '{email}' (will be skipped)", str(normalized_row))
            else:
                existing_emails.add(email)

            if not phone:
                raise ImportValidationError(row_number, "phone", "Phone is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not re.match(r"^\+?[\d\s()\-]{7,}$", phone):
                raise ImportValidationError(row_number, "phone", f"Invalid phone format: '{phone}'", str(normalized_row), "DATA_TYPE_ERROR")

            phone_clean = re.sub(r"[^\d+]", "", phone)
            if phone_clean in existing_phones:
                if duplicate_action == "REJECT":
                    raise DuplicateRecordError(row_number, "phone", f"Duplicate phone: '{phone}'", str(normalized_row))
                elif duplicate_action == "SKIP":
                    raise DuplicateRecordError(row_number, "phone", f"Duplicate phone '{phone}' (will be skipped)", str(normalized_row))
            else:
                existing_phones.add(phone_clean)

        elif import_type == ImportType.SALES:
            customer_name = (normalized_row.get("customer") or "").strip()
            product_name = (normalized_row.get("product") or "").strip()
            quantity_raw = (normalized_row.get("quantity") or "").strip()
            unit_price_raw = (normalized_row.get("unit_price") or "").strip()
            sale_date_raw = (normalized_row.get("sale_date") or "").strip()
            invoice_number = (normalized_row.get("invoice_number") or "").strip()

            if not customer_name:
                raise ImportValidationError(row_number, "customer", "Customer is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not product_name:
                raise ImportValidationError(row_number, "product", "Product is required", str(normalized_row), "MANDATORY_FIELD_MISSING")
            if not invoice_number:
                raise ImportValidationError(row_number, "invoice_number", "Invoice Number is required", str(normalized_row), "MANDATORY_FIELD_MISSING")

            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                raise ImportValidationError(row_number, "quantity", f"Invalid Quantity: '{quantity_raw}'", str(normalized_row), "DATA_TYPE_ERROR")
            if quantity <= 0:
                raise ImportValidationError(row_number, "quantity", "Quantity must be greater than zero", str(normalized_row), "INVALID_VALUE")

            try:
                unit_price = Decimal(str(unit_price_raw))
            except (InvalidOperation, TypeError, ValueError):
                raise ImportValidationError(row_number, "unit_price", f"Invalid Unit Price: '{unit_price_raw}'", str(normalized_row), "DATA_TYPE_ERROR")
            if unit_price < 0:
                raise ImportValidationError(row_number, "unit_price", "Unit Price cannot be negative", str(normalized_row), "INVALID_VALUE")

            try:
                datetime.strptime(sale_date_raw, "%Y-%m-%d")
            except Exception:
                raise ImportValidationError(row_number, "sale_date", f"Invalid Sale Date '{sale_date_raw}', expected YYYY-MM-DD", str(normalized_row), "DATA_TYPE_ERROR")

            customer_id = customer_names.get(customer_name)
            if not customer_id:
                raise ImportValidationError(row_number, "customer", f"Customer '{customer_name}' not found", str(normalized_row), "FOREIGN_KEY_ERROR")

            product_id = product_names.get(product_name)
            if not product_id:
                raise ImportValidationError(row_number, "product", f"Product '{product_name}' not found", str(normalized_row), "FOREIGN_KEY_ERROR")

            available = available_stock.get(product_id, 0)
            if quantity > available:
                raise ImportValidationError(
                    row_number, "quantity",
                    f"Quantity exceeds available stock. Available: {available}, Requested: {quantity}",
                    str(normalized_row), "INSUFFICIENT_STOCK",
                )
            available_stock[product_id] -= quantity

            if invoice_number in existing_invoices and duplicate_action == "REJECT":
                raise DuplicateRecordError(row_number, "invoice_number", f"Duplicate Invoice Number: '{invoice_number}'", str(normalized_row))

    async def _get_existing_skus(self) -> set[str]:
        result = await self.db.execute(select(Product.sku).where(Product.company_id == self.company_id))
        return {str(row.sku).lower() for row in result.all() if row.sku}

    async def _get_existing_products_map(self) -> dict[str, Product]:
        result = await self.db.execute(select(Product).where(Product.company_id == self.company_id))
        products = result.scalars().all()
        return {p.sku.lower(): p for p in products if p.sku}

    async def _get_existing_customer_unique_values(self) -> tuple[set[str], set[str]]:
        result = await self.db.execute(select(Customer.email, Customer.phone).where(Customer.company_id == self.company_id, Customer.is_deleted == False))
        emails: set[str] = set()
        phones: set[str] = set()
        for row in result.all():
            if row.email:
                emails.add(row.email.strip().lower())
            if row.phone:
                phones.add(re.sub(r"[^\d+]", "", row.phone))
        return emails, phones

    async def _get_existing_invoices(self) -> set[str]:
        result = await self.db.execute(select(Sale.invoice_number).where(Sale.company_id == self.company_id))
        return {row.invoice_number for row in result.all() if row.invoice_number}

    async def _get_customer_names(self) -> dict[str, UUID]:
        result = await self.db.execute(select(Customer.first_name, Customer.last_name, Customer.id).where(Customer.company_id == self.company_id, Customer.is_deleted == False))
        names: dict[str, UUID] = {}
        for row in result.all():
            name = f"{row.first_name or ''} {row.last_name or ''}".strip()
            if name:
                names[name] = row.id
        return names

    async def _get_product_names(self) -> dict[str, UUID]:
        result = await self.db.execute(select(Product.name, Product.id).where(Product.company_id == self.company_id))
        return {row.name: row.id for row in result.all() if row.name}

    async def _get_available_stock(self) -> dict[UUID, int]:
        result = await self.db.execute(select(Product.id, Product.stock_quantity, Product.reserved_stock).where(Product.company_id == self.company_id))
        stock: dict[UUID, int] = {}
        for row in result.all():
            stock[row.id] = max((row.stock_quantity or 0) - (row.reserved_stock or 0), 0)
        return stock

    async def validate_import(
        self,
        import_type: ImportType,
        file_content: bytes,
        filename: str,
        import_id: UUID | None = None,
        duplicate_action: str = "SKIP",
    ) -> dict:
        columns, rows = self.parse_csv(file_content)
        errors: list[dict[str, Any]] = []

        if not rows and not columns:
            errors.append({
                "row_number": 1,
                "field": "File",
                "error_type": "EMPTY_FILE",
                "error_message": "The CSV file is empty or contains no records.",
                "raw_data": "",
            })
            return {
                "import_id": str(import_id) if import_id else "00000000-0000-0000-0000-000000000000",
                "import_type": import_type.value,
                "filename": filename,
                "total_records": 0,
                "columns": [],
                "preview_rows": [],
                "valid_records": 0,
                "invalid_records": 0,
                "duplicate_records": 0,
                "errors": errors,
                "status": "FAILED",
            }

        try:
            self.validate_columns(import_type, columns)
        except ValueError as e:
            errors.append({
                "row_number": 1,
                "field": "Header",
                "error_type": "MISSING_COLUMNS",
                "error_message": str(e),
                "raw_data": f"Columns found: {', '.join(columns)}" if columns else "Empty file or no columns found",
            })
            return {
                "import_id": str(import_id) if import_id else "00000000-0000-0000-0000-000000000000",
                "import_type": import_type.value,
                "filename": filename,
                "total_records": len(rows),
                "columns": columns,
                "preview_rows": [],
                "valid_records": 0,
                "invalid_records": len(rows) or 1,
                "duplicate_records": 0,
                "errors": errors,
                "status": "FAILED",
            }

        valid_rows = 0
        duplicate_rows = 0
        invalid_rows = 0

        existing_skus = await self._get_existing_skus() if import_type in (ImportType.PRODUCTS, ImportType.INVENTORY) else set()
        existing_products_map = await self._get_existing_products_map() if import_type == ImportType.INVENTORY else None
        existing_emails, existing_phones = await self._get_existing_customer_unique_values() if import_type == ImportType.CUSTOMERS else (set(), set())
        customer_names = await self._get_customer_names() if import_type == ImportType.SALES else {}
        product_names = await self._get_product_names() if import_type == ImportType.SALES else {}
        available_stock = await self._get_available_stock() if import_type == ImportType.SALES else {}
        existing_invoices = await self._get_existing_invoices() if import_type == ImportType.SALES else set()

        preview_rows = []
        for idx, row in enumerate(rows, start=2):
            normalized = self.normalize_row(import_type, row)
            try:
                self.validate_row(
                    import_type,
                    idx,
                    normalized,
                    existing_skus,
                    existing_emails,
                    existing_phones,
                    existing_invoices,
                    customer_names,
                    product_names,
                    available_stock,
                    existing_products_map,
                    duplicate_action=duplicate_action,
                )
                valid_rows += 1
            except DuplicateRecordError as e:
                duplicate_rows += 1
                errors.append({
                    "row_number": e.row_number,
                    "field": e.field,
                    "error_type": e.error_type,
                    "error_message": e.message,
                    "raw_data": str(normalized),
                })
            except ImportValidationError as e:
                invalid_rows += 1
                errors.append({
                    "row_number": e.row_number,
                    "field": e.field,
                    "error_type": e.error_type,
                    "error_message": e.message,
                    "raw_data": str(normalized),
                })

            if len(preview_rows) < 10:
                preview_rows.append(normalized)

        return {
            "import_id": str(import_id) if import_id else "00000000-0000-0000-0000-000000000000",
            "import_type": import_type.value,
            "filename": filename,
            "total_records": len(rows),
            "columns": columns,
            "preview_rows": preview_rows,
            "valid_records": valid_rows,
            "invalid_records": invalid_rows,
            "duplicate_records": duplicate_rows,
            "errors": errors,
            "status": "VALIDATED",
        }

    async def process_import(
        self,
        import_type: ImportType,
        file_content: bytes,
        filename: str,
        import_id: UUID | None = None,
        duplicate_action: str = "SKIP",
    ) -> dict:
        columns, rows = self.parse_csv(file_content)
        self.validate_columns(import_type, columns)

        history = None
        if import_id:
            history = await self.get_import_history(import_id)
            if not history:
                raise ValueError(f"Import history not found: {import_id}")
            await import_history_crud.update_status(self.db, history, ImportStatus.PROCESSING, commit=False)
        else:
            history = await self.create_import_history(import_type, filename, len(rows), commit=False)
            await import_history_crud.update_status(self.db, history, ImportStatus.PROCESSING, commit=False)

        # Notify start
        try:
            await self._create_import_notification(history, ImportStatus.PROCESSING)
        except Exception:
            logger.exception("Failed to create start import notification")

        existing_skus = await self._get_existing_skus() if import_type in (ImportType.PRODUCTS, ImportType.INVENTORY) else set()
        existing_products_map = await self._get_existing_products_map() if import_type in (ImportType.PRODUCTS, ImportType.INVENTORY) else None
        existing_emails, existing_phones = await self._get_existing_customer_unique_values() if import_type == ImportType.CUSTOMERS else (set(), set())
        customer_names = await self._get_customer_names() if import_type == ImportType.SALES else {}
        product_names = await self._get_product_names() if import_type == ImportType.SALES else {}
        available_stock = await self._get_available_stock() if import_type == ImportType.SALES else {}
        existing_invoices = await self._get_existing_invoices() if import_type == ImportType.SALES else set()

        valid_rows: list[tuple[int, dict[str, Any]]] = []
        errors: list[dict[str, Any]] = []
        duplicates = 0
        invalid_rows = 0
        skipped = 0

        for idx, row in enumerate(rows, start=2):
            normalized = self.normalize_row(import_type, row)
            try:
                self.validate_row(
                    import_type,
                    idx,
                    normalized,
                    existing_skus,
                    existing_emails,
                    existing_phones,
                    existing_invoices,
                    customer_names,
                    product_names,
                    available_stock,
                    existing_products_map,
                    duplicate_action=duplicate_action,
                )
                valid_rows.append((idx, normalized))
            except DuplicateRecordError as e:
                duplicates += 1
                if duplicate_action == "SKIP":
                    skipped += 1
                errors.append({
                    "row_number": e.row_number,
                    "field": e.field,
                    "error_type": e.error_type,
                    "error_message": e.message,
                    "raw_data": e.raw_data or str(normalized),
                })
            except ImportValidationError as e:
                invalid_rows += 1
                errors.append({
                    "row_number": e.row_number,
                    "field": e.field,
                    "error_type": e.error_type,
                    "error_message": e.message,
                    "raw_data": e.raw_data or str(normalized),
                })

        successful = 0
        failed = 0
        batch_size = 50

        if import_type == ImportType.SALES:
            sales_groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
            for original_idx, normalized in valid_rows:
                inv_num = normalized.get("invoice_number", f"AUTO_GRP_{original_idx}")
                sales_groups.setdefault(inv_num, []).append((original_idx, normalized))

            for inv_num, items_group in sales_groups.items():
                # Check cancellation
                await self.db.refresh(history)
                if history.status == ImportStatus.CANCELLED:
                    logger.info(f"Import {history.id} cancelled by user during sales processing.")
                    return self._build_result(history, errors)

                try:
                    await self._insert_sales_group(inv_num, items_group, customer_names, product_names)
                    await self.db.commit()
                    successful += len(items_group)
                except Exception as e:
                    await self.db.rollback()
                    failed += len(items_group)
                    logger.exception(f"Failed to import sales group for invoice {inv_num}: {e}")
                    for original_idx, normalized in items_group:
                        errors.append({
                            "row_number": original_idx,
                            "field": "Invoice",
                            "error_type": "PROCESSING_ERROR",
                            "error_message": "Unable to process sales record. Check database consistency.",
                            "raw_data": str(normalized),
                        })
                await import_history_crud.update_status(
                    self.db, history, ImportStatus.PROCESSING,
                    successful, failed + invalid_rows, duplicates, skipped, commit=True
                )

        elif import_type == ImportType.INVENTORY:
            for batch_start in range(0, len(valid_rows), batch_size):
                # Check cancellation
                await self.db.refresh(history)
                if history.status == ImportStatus.CANCELLED:
                    logger.info(f"Import {history.id} cancelled by user during inventory processing.")
                    return self._build_result(history, errors)

                batch = valid_rows[batch_start:batch_start + batch_size]
                try:
                    for original_idx, normalized in batch:
                        await self._insert_inventory(normalized)
                    await self.db.commit()
                    successful += len(batch)
                except Exception as e:
                    await self.db.rollback()
                    failed += len(batch)
                    logger.exception(f"Batch inventory insert failed: {e}")
                    for original_idx, normalized in batch:
                        errors.append({
                            "row_number": original_idx,
                            "field": "Inventory",
                            "error_type": "PROCESSING_ERROR",
                            "error_message": "Failed to update inventory record. Please check the data.",
                            "raw_data": str(normalized),
                        })

                await import_history_crud.update_status(
                    self.db, history, ImportStatus.PROCESSING,
                    successful, failed + invalid_rows, duplicates, skipped, commit=True
                )

        else:
            for batch_start in range(0, len(valid_rows), batch_size):
                # Check cancellation
                await self.db.refresh(history)
                if history.status == ImportStatus.CANCELLED:
                    logger.info(f"Import {history.id} cancelled by user during batch processing.")
                    return self._build_result(history, errors)

                batch = valid_rows[batch_start:batch_start + batch_size]
                try:
                    for original_idx, normalized in batch:
                        if import_type == ImportType.PRODUCTS:
                            await self._insert_product(normalized, duplicate_action=duplicate_action)
                        elif import_type == ImportType.CUSTOMERS:
                            await self._insert_customer(normalized, duplicate_action=duplicate_action)
                    await self.db.commit()
                    successful += len(batch)
                except Exception as e:
                    await self.db.rollback()
                    failed += len(batch)
                    logger.exception(f"Batch insert failed during import: {e}")
                    for original_idx, normalized in batch:
                        errors.append({
                            "row_number": original_idx,
                            "field": None,
                            "error_type": "PROCESSING_ERROR",
                            "error_message": "Unable to process this record. Please check the data.",
                            "raw_data": str(normalized),
                        })

                await import_history_crud.update_status(
                    self.db, history, ImportStatus.PROCESSING,
                    successful, failed + invalid_rows, duplicates, skipped, commit=True
                )

        # Record errors in DB
        for error in errors:
            await import_history_crud.add_error(
                self.db,
                history.id,
                error["row_number"],
                error["error_message"],
                field=error.get("field"),
                raw_data=error.get("raw_data"),
                error_type=error.get("error_type", "VALIDATION_ERROR"),
                commit=False,
            )

        total_failed = failed + invalid_rows + (duplicates if duplicate_action == "REJECT" else 0)
        final_status = ImportStatus.COMPLETED
        if total_failed > 0:
            if successful > 0:
                final_status = ImportStatus.COMPLETED_WITH_ERRORS
            else:
                final_status = ImportStatus.FAILED
        elif duplicates > 0 and duplicate_action == "SKIP":
            final_status = ImportStatus.COMPLETED

        await import_history_crud.update_status(
            self.db, history, final_status, successful, total_failed, duplicates, skipped, commit=True
        )
        await self.db.refresh(history)

        try:
            await self._create_import_notification(history, final_status)
        except Exception:
            logger.exception("Failed to create completion import notification")

        try:
            from app.services.data_quality_auto import data_quality_auto
            await data_quality_auto.check_import(self.db, history, self.company_id)
        except Exception:
            logger.exception("Failed to run data quality auto check on import")

        return self._build_result(history, errors)

    def _build_result(self, history: ImportHistory, errors: list[dict[str, Any]]) -> dict:
        duration = None
        if history.completed_at and history.created_at:
            duration = (history.completed_at - history.created_at).total_seconds()

        return {
            "import_id": str(history.id),
            "import_type": history.import_type.value,
            "filename": history.filename,
            "total_records": history.total_records,
            "successful_records": history.successful_records,
            "failed_records": history.failed_records,
            "duplicate_records": history.duplicate_records,
            "skipped_records": getattr(history, "skipped_records", 0) or 0,
            "status": history.status.value,
            "errors": errors,
            "duration_seconds": duration,
        }

    async def _get_or_create_category_id(self, category_name: str) -> UUID | None:
        if not category_name:
            return None
        from app.models.category import Category
        clean_target = self._clean_header(category_name)
        result = await self.db.execute(select(Category).where(Category.company_id == self.company_id))
        categories = result.scalars().all()
        for cat in categories:
            if self._clean_header(cat.name) == clean_target:
                return cat.id

        new_cat = Category(
            company_id=self.company_id,
            name=category_name.strip(),
            description="",
            status="ACTIVE",
        )
        self.db.add(new_cat)
        await self.db.flush()
        return new_cat.id

    async def _insert_product(self, normalized: dict[str, Any], duplicate_action: str = "SKIP") -> None:
        sku = normalized["sku"].strip()
        sku_lower = sku.lower()
        result = await self.db.execute(select(Product).where(Product.company_id == self.company_id))
        existing_products = {p.sku.lower(): p for p in result.scalars().all() if p.sku}

        category_name = normalized.get("category", "")
        category_id = await self._get_or_create_category_id(category_name) if category_name else None
        price = Decimal(str(normalized.get("unit_price", "0")))
        stock = int(normalized.get("stock_quantity", "0")) if normalized.get("stock_quantity") else 0

        if sku_lower in existing_products:
            if duplicate_action == "UPDATE":
                prod = existing_products[sku_lower]
                prod.name = normalized["product_name"]
                if category_id:
                    prod.category_id = category_id
                prod.unit_price = price
                prod.cost_price = price
                prod.stock_quantity = stock
                self.db.add(prod)
                await self.db.flush()
                return
            elif duplicate_action == "SKIP":
                return

        product = Product(
            company_id=self.company_id,
            name=normalized["product_name"],
            sku=sku,
            category_id=category_id,
            unit_price=price,
            cost_price=price,
            stock_quantity=stock,
            low_stock_threshold=5,
            lead_time_days=7,
            unit_of_measure="PCS",
            status="ACTIVE",
        )
        self.db.add(product)
        await self.db.flush()

    async def _insert_inventory(self, normalized: dict[str, Any]) -> None:
        sku = normalized["sku"].strip().lower()
        result = await self.db.execute(select(Product).where(Product.company_id == self.company_id))
        existing_products = {p.sku.lower(): p for p in result.scalars().all() if p.sku}
        product = existing_products.get(sku)
        if not product:
            raise ValueError(f"Product with SKU '{normalized['sku']}' not found")

        qty = int(normalized["quantity"])
        adj_type_raw = normalized["adjustment_type"].strip().upper()
        reason = normalized.get("reason", "Bulk Inventory Import")

        previous_quantity = product.stock_quantity or 0
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

        product.stock_quantity = updated_quantity
        self.db.add(product)

        stock_movement = StockMovement(
            company_id=self.company_id,
            product_id=product.id,
            movement_type=movement_type,
            previous_quantity=previous_quantity,
            updated_quantity=updated_quantity,
            quantity_changed=quantity_changed,
            reason=reason,
            user_id=self.uploaded_by,
        )
        self.db.add(stock_movement)

        inventory_adjustment = InventoryAdjustment(
            company_id=self.company_id,
            product_id=product.id,
            adjustment_type=adj_type,
            quantity=abs(quantity_changed),
            reason=reason,
            remarks=f"Imported via CSV: {adj_type_raw}",
            adjusted_by=self.uploaded_by,
        )
        self.db.add(inventory_adjustment)
        await self.db.flush()

    async def _insert_customer(self, normalized: dict[str, Any], duplicate_action: str = "SKIP") -> None:
        email = (normalized.get("email") or "").strip().lower()
        if email:
            result = await self.db.execute(select(Customer).where(Customer.company_id == self.company_id, Customer.email == email, Customer.is_deleted == False))
            existing_cust = result.scalar_one_or_none()
            if existing_cust:
                if duplicate_action == "UPDATE":
                    parts = normalized.get("name", "").split(" ", 1)
                    existing_cust.first_name = parts[0] if parts else existing_cust.first_name
                    existing_cust.last_name = parts[1] if len(parts) > 1 else existing_cust.last_name
                    if normalized.get("phone"):
                        existing_cust.phone = normalized.get("phone")
                    self.db.add(existing_cust)
                    await self.db.flush()
                    return
                elif duplicate_action == "SKIP":
                    return

        name = normalized.get("name", "")
        parts = name.split(" ", 1)
        first_name = parts[0] if parts else name
        last_name = parts[1] if len(parts) > 1 else ""
        customer = Customer(
            company_id=self.company_id,
            first_name=first_name,
            last_name=last_name,
            email=normalized.get("email") or None,
            phone=normalized.get("phone") or None,
            address="",
            city="",
            state="",
            country="",
            postal_code="",
            customer_type="RETAIL",
            status="ACTIVE",
        )
        self.db.add(customer)
        await self.db.flush()

    async def _insert_sales_group(self, inv_num: str, items_group: list[tuple[int, dict[str, Any]]], customer_names: dict[str, UUID], product_names: dict[str, UUID]) -> None:
        first_norm = items_group[0][1]
        customer_name = first_norm["customer"]
        sale_date_raw = first_norm["sale_date"]
        customer_id = customer_names.get(customer_name)
        sale_date = datetime.strptime(sale_date_raw, "%Y-%m-%d")

        existing_db_invoices = await self._get_existing_invoices()
        invoice_number = inv_num
        if not invoice_number or invoice_number in existing_db_invoices or invoice_number.startswith("AUTO_GRP_"):
            year = datetime.utcnow().year
            prefix = f"IMP-{year}-"
            result = await self.db.execute(
                select(InvoiceSequence)
                .where(InvoiceSequence.company_id == self.company_id)
                .with_for_update()
            )
            sequence = result.scalar_one_or_none()
            if not sequence:
                sequence = InvoiceSequence(company_id=self.company_id, last_invoice_number=0)
                self.db.add(sequence)
                await self.db.flush()
            sequence.last_invoice_number += 1
            invoice_number = f"{prefix}{sequence.last_invoice_number:06d}"

        sale_items = []
        total_amount = Decimal("0")

        for original_idx, normalized in items_group:
            product_name = normalized["product"]
            product_id = product_names.get(product_name)
            quantity = int(normalized["quantity"])
            unit_price = Decimal(str(normalized["unit_price"]))
            discount = Decimal(str(normalized.get("discount", "0"))) if normalized.get("discount") else Decimal("0")
            tax = Decimal(str(normalized.get("tax", "0"))) if normalized.get("tax") else Decimal("0")

            item_total = (unit_price * quantity) - discount + tax
            total_amount += item_total

            sale_items.append(SaleItem(
                product_id=product_id,
                quantity=quantity,
                unit_price=float(unit_price),
                discount=float(discount),
                tax=float(tax),
                total=float(item_total),
            ))

            if product_id:
                product = await self.db.get(Product, product_id)
                if product:
                    product.stock_quantity = max((product.stock_quantity or 0) - quantity, 0)
                    self.db.add(product)

        sale = Sale(
            company_id=self.company_id,
            invoice_number=invoice_number,
            customer_id=customer_id,
            customer_name=customer_name,
            sale_date=sale_date,
            sales_channel=SalesChannel.RETAIL,
            payment_method=PaymentMethod.CASH,
            payment_status=PaymentStatus.PAID,
            status=SaleStatus.COMPLETED,
            total_amount=float(total_amount),
            created_by=self.uploaded_by,
            items=sale_items,
        )
        self.db.add(sale)
        await self.db.flush()

    async def _create_import_notification(self, history: ImportHistory, status: ImportStatus) -> None:
        if status == ImportStatus.PROCESSING:
            notif_type = NotificationType.IMPORT_STARTED
            priority = NotificationPriority.LOW
            title = f"Import Started: {history.filename}"
            message = f"Processing started for {history.import_type.value} import '{history.filename}' ({history.total_records} records)."
        elif status == ImportStatus.COMPLETED:
            notif_type = NotificationType.IMPORT_COMPLETED
            priority = NotificationPriority.LOW
            title = f"Import Completed: {history.filename}"
            message = (
                f"Import of '{history.filename}' ({history.import_type.value}) completed successfully. "
                f"Total: {history.total_records}, Successful: {history.successful_records}."
            )
        elif status == ImportStatus.COMPLETED_WITH_ERRORS:
            notif_type = NotificationType.IMPORT_COMPLETED_WITH_ERRORS
            priority = NotificationPriority.MEDIUM
            title = f"Import Completed with Errors: {history.filename}"
            message = (
                f"Import of '{history.filename}' ({history.import_type.value}) completed with errors. "
                f"Total: {history.total_records}, Successful: {history.successful_records}, "
                f"Failed: {history.failed_records}, Duplicates: {history.duplicate_records}."
            )
        else:
            notif_type = NotificationType.IMPORT_FAILED
            priority = NotificationPriority.HIGH
            title = f"Import Failed: {history.filename}"
            message = (
                f"Import of '{history.filename}' ({history.import_type.value}) failed. "
                f"Total: {history.total_records}, Failed: {history.failed_records}."
            )

        # Check if identical alert already exists to avoid duplicate notifications
        existing_notif = await self.db.execute(
            select(notification_crud.model).where(
                notification_crud.model.company_id == self.company_id,
                notification_crud.model.type == notif_type,
                notification_crud.model.resource_id == history.id,
            )
        )
        if existing_notif.first():
            return

        await notification_service._create_alert_for_roles(
            self.db, self.company_id, notif_type, priority, title, message,
            NotificationResourceType.IMPORT, history.id, None,
        )
