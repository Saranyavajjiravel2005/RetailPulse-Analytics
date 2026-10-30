# Task 16: Data Quality & Reconciliation Module

## Overview
The Data Quality & Reconciliation module provides an automated, centralized diagnostic and reconciliation engine across the RetailPulse application. It monitors consistency across Sales, Inventory, Stock Movements, Products, Customers, and Reporting data, providing administrators with tools to identify, investigate, audit, and resolve data anomalies.

---

## Key Architecture & Features

### 1. Data Quality Dashboard (`/data-quality`)
- **System Health Summary**: Real-time calculated health score percentage and pass/warn status.
- **KPI Metrics**:
  - `Total Records Checked`: Total count of transactional, master, and reporting records inspected during reconciliation.
  - `Valid Records`: Records adhering strictly to all referential and mathematical integrity constraints.
  - `Records with Warnings`: Medium / Low severity non-blocking inconsistencies.
  - `Records with Errors`: High / Critical severity discrepancies (e.g. negative stock, orphan references).
  - `Unresolved Issues`: Total open/investigating issues requiring administrative review.
  - `Last Reconciliation Time`: Timestamp of the latest completed reconciliation execution.
- **Breakdown Cards**:
  - Issues by Module (Sales, Inventory, Products, Customers, Reports).
  - Issues by Severity (Critical, High, Medium, Low).
  - Issues by Status (Open, Investigating, Resolved, Ignored).

### 2. Full Suite of Reconciliation Checks
Implemented in `backend/app/services/data_quality_service.py` and `backend/app/services/data_quality_auto.py`:

| # | Check Type | Enum Code | Severity | Description |
|---|---|---|---|---|
| 1 | **Sale Quantity Exceeds Stock** | `SALE_EXCEEDS_STOCK` | `CRITICAL` | Detects when a sale transaction causes negative on-hand stock or ordered quantity exceeds available inventory at transaction time. |
| 2 | **Inventory Inconsistent with Movements** | `INVENTORY_INCONSISTENT_WITH_MOVEMENTS` | `CRITICAL` | Validates that product current `stock_quantity` strictly matches the latest `StockMovement.updated_quantity`. |
| 3 | **Inactive / Missing Product in Sale** | `SALE_INACTIVE_OR_MISSING_PRODUCT` | `HIGH` | Flags completed sales referencing products that are deactivated (`INACTIVE`) or missing from the database. |
| 4 | **Sale Invalid Customer** | `SALE_INVALID_CUSTOMER` | `MEDIUM` | Flags sales with customer IDs that do not exist or belong to another organization. |
| 5 | **Duplicate or Invalid SKU** | `DUPLICATE_OR_INVALID_PRODUCT_SKU` | `HIGH` | Identifies products with empty, blank, or duplicate SKUs within the company. |
| 6 | **Missing Mandatory Info** | `MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO` | `MEDIUM` / `LOW` | Verifies products have name and SKU; verifies customers have first name and email/phone. |
| 7 | **Stock Movement Inconsistency** | `STOCK_MOVEMENT_INCONSISTENT` | `HIGH` | Audits inventory movements for math errors: verifies `updated_quantity == previous_quantity + quantity_changed`. |
| 8 | **Report Total Discrepancy** | `REPORT_TOTAL_MISMATCH` | `HIGH` | Compares sale transaction header totals against calculated line item sums and monitors failed generated reports. |

### 3. Automatic & Event-Driven Checks
Targeted, lightweight automatic checks are hooked directly into existing workflows without running expensive full-database scans:
- **Sale Creation / Update** (`routers/sale.py`): Checks customer validity, inactive product references, and overselling.
- **Stock Adjustment** (`routers/inventory.py`): Re-evaluates product stock against latest movements.
- **Data Imports** (`services/import_.py`): Verifies SKU uniqueness and stock integrity upon completing product/inventory imports.
- **Product & Customer Updates** (`routers/product.py`, `routers/customer.py`): Ensures mandatory fields remain populated.

### 4. Issues Management & Multi-Field Filtering (`/data-quality/issues`)
- Search by free text (description, record ID, module).
- Filter simultaneously by:
  - Issue Type
  - Severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`)
  - Module (`Sales`, `Inventory`, `Products`, `Customers`, `Reports`)
  - Status (`OPEN`, `INVESTIGATING`, `RESOLVED`, `IGNORED`)
  - Date Range (`date_from` to `date_to`)
- Multiple filters function together without resetting previously selected parameters.
- Server-side pagination with custom page limits.

### 5. Detailed Inconsistency Analysis (`/data-quality/issues/:id`)
- **Comparison Banner**: Displays current inventory, expected quantity, and computed difference.
- **Audit Context**:
  - Recent relevant stock movements table.
  - Related sales and line item details.
  - Detection timestamp and run ID.
- **Issue Resolution Panel**:
  - Authorized admin status updates (`OPEN` -> `INVESTIGATING` -> `RESOLVED` / `IGNORED`).
  - Resolution notes tracking root cause.
  - Complete status change history trail.
  - Integrated with the **Audit Logs** module.

### 6. Reconciliation Execution & History (`/data-quality/reconciliation`)
- Manual trigger execution with asynchronous non-blocking background workers (`data_quality_background.py`).
- Real-time status polling and loading indicators (`RUNNING`, `COMPLETED`, `COMPLETED_WITH_ISSUES`, `FAILED`).
- Execution history table displaying:
  - Run ID / Execution ID (`RC-...`)
  - Started & Completed timestamps
  - Triggered by user
  - Records checked
  - Issues detected / resolved
  - Failed checks

---

## REST API Specification

| Method | Endpoint | Description | Role Required |
|---|---|---|---|
| `GET` | `/api/data-quality/dashboard` | Retrieve overall KPI counts, health score, and breakdowns | Authenticated |
| `GET` | `/api/data-quality/issues` | Filtered and paginated list of data quality issues | Authenticated |
| `GET` | `/api/data-quality/issues/{issue_id}` | Detailed issue information with diagnostic analysis | Authenticated |
| `PUT` | `/api/data-quality/issues/{issue_id}/status` | Update issue status (`RESOLVED`, `INVESTIGATING`, etc.) and log resolution | Admin |
| `GET` | `/api/data-quality/issues/{issue_id}/history` | Retrieve full status transition history | Authenticated |
| `POST` | `/api/data-quality/reconcile` | Manually trigger a new reconciliation run | Admin |
| `GET` | `/api/data-quality/reconciliation/history` | Paginated reconciliation run history log | Authenticated |
| `GET` | `/api/data-quality/reconciliation/status/{execution_id}` | Poll execution status of a specific run | Authenticated |

---

## Recommended Screenshots to Place in this Directory
1. `01_data_quality_dashboard.png`: Overview of KPI cards, Health Score, and module breakdown.
2. `02_reconciliation_execution.png`: Triggering manual reconciliation with status update.
3. `03_data_quality_issues_filters.png`: Filtered issues table demonstrating multi-filter capabilities.
4. `04_issue_details_analysis.png`: Inconsistency breakdown view showing current vs expected quantities, related movements, and sales.
5. `05_issue_status_resolved.png`: Resolving an issue with resolution note and viewing status history trail.
6. `06_reconciliation_history.png`: Reconciliation run logs showing Execution IDs, records checked, and completion status.
