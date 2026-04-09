# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp[cli]",
#   "httpx",
#   "python-dotenv",
#   "pydantic",
# ]
# ///
"""
QuickBooks MCP Server
Built by Shane Brady — shanebrady.com
A local-first MCP server that connects Claude Desktop to QuickBooks Online.
"""

import os
import json
import httpx
from datetime import datetime, timedelta
from typing import Optional
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("QUICKBOOKS_REFRESH_TOKEN", "")
COMPANY_ID = os.getenv("QUICKBOOKS_COMPANY_ID", "")
QB_ENV = os.getenv("QUICKBOOKS_ENV", "sandbox")

BASE_URL = (
    "https://sandbox-quickbooks.api.intuit.com"
    if QB_ENV == "sandbox"
    else "https://quickbooks.api.intuit.com"
)
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
MINOR_VERSION = "70"

# ── Token Management ────────────────────────────────────────────────────────
_access_token: str = ""
_token_expiry: datetime = datetime.min


async def _get_access_token() -> str:
    """Exchange refresh token for a fresh access token."""
    global _access_token, _token_expiry, REFRESH_TOKEN

    if _access_token and datetime.now() < _token_expiry:
        return _access_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={
                "grant_type": "refresh_token",
                "refresh_token": REFRESH_TOKEN,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _access_token = data["access_token"]
    _token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)

    # QuickBooks rotates refresh tokens — save the new one
    if "refresh_token" in data:
        REFRESH_TOKEN = data["refresh_token"]
        _save_refresh_token(data["refresh_token"])

    return _access_token


def _save_refresh_token(token: str):
    """Persist rotated refresh token back to .env so it survives restarts."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    lines = open(env_path).readlines()
    with open(env_path, "w") as f:
        for line in lines:
            if line.startswith("QUICKBOOKS_REFRESH_TOKEN"):
                f.write(f"QUICKBOOKS_REFRESH_TOKEN={token}\n")
            else:
                f.write(line)


# ── API Helpers ─────────────────────────────────────────────────────────────
async def _qb_get(endpoint: str, params: dict | None = None) -> dict:
    """Make an authenticated GET to the QBO API."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{endpoint}"
    p = {"minorversion": MINOR_VERSION}
    if params:
        p.update(params)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params=p,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def _qb_query(query: str) -> list:
    """Run a QBO SQL-like query and return the list of results."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/query"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params={"query": query, "minorversion": MINOR_VERSION},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    qr = data.get("QueryResponse", {})
    # The result key is the entity name — find the first list
    for v in qr.values():
        if isinstance(v, list):
            return v
    return []


async def _qb_post(endpoint: str, payload: dict) -> dict:
    """Make an authenticated POST to the QBO API."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"minorversion": MINOR_VERSION},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def _qb_delete(entity_type: str, entity_id: str, sync_token: str) -> dict:
    """Delete an entity from QuickBooks. Requires the entity's SyncToken."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{entity_type}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"operation": "delete", "minorversion": MINOR_VERSION},
            json={"Id": entity_id, "SyncToken": sync_token},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def _qb_void(entity_type: str, entity_id: str, sync_token: str) -> dict:
    """Void an entity in QuickBooks. Zeros out amounts but keeps the record."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{entity_type}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"operation": "void", "minorversion": MINOR_VERSION},
            json={"Id": entity_id, "SyncToken": sync_token},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def _qb_update(entity_type: str, payload: dict) -> dict:
    """Sparse update an entity. Payload must include Id and SyncToken."""
    token = await _get_access_token()
    url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{entity_type}"
    payload["sparse"] = True
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"minorversion": MINOR_VERSION},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def _handle_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        try:
            body = e.response.json()
        except Exception:
            body = e.response.text
        if status == 401:
            return "Error: Authentication failed. Your refresh token may have expired. Run the auth helper again: python auth_helper.py"
        if status == 403:
            return f"Error: Permission denied. Check your app scopes. Details: {body}"
        if status == 400:
            return f"Error: Bad request. Details: {body}"
        return f"Error: API returned {status}. Details: {body}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Try again."
    return f"Error: {type(e).__name__}: {e}"


# ── MCP Server ──────────────────────────────────────────────────────────────
mcp = FastMCP("quickbooks_mcp")


# ── REPORTS ─────────────────────────────────────────────────────────────────
class ReportInput(BaseModel):
    start_date: Optional[str] = Field(
        default=None,
        description="Start date in YYYY-MM-DD format. Defaults to start of current year.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM-DD format. Defaults to today.",
    )


@mcp.tool(
    name="qb_profit_and_loss",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_profit_and_loss(params: ReportInput) -> str:
    """Get the Profit and Loss (income statement) report. Shows total income, expenses, and net income for a date range. This is the #1 report for understanding if the business is making or losing money."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/ProfitAndLoss", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_balance_sheet",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_balance_sheet(params: ReportInput) -> str:
    """Get the Balance Sheet report. Shows what the business owns (assets), owes (liabilities), and the owner's equity. A snapshot of financial health at a point in time."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/BalanceSheet", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_cash_flow",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_cash_flow(params: ReportInput) -> str:
    """Get the Cash Flow statement. Shows how cash moved in and out of the business — operating, investing, and financing activities."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/CashFlow", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_aged_receivables",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_aged_receivables(params: ReportInput) -> str:
    """Get the Accounts Receivable Aging report. Shows who owes you money and how overdue they are (current, 1-30 days, 31-60 days, 61-90 days, 90+ days). Critical for cash flow management."""
    try:
        p = {}
        if params.end_date:
            p["report_date"] = params.end_date
        data = await _qb_get("reports/AgedReceivableDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_aged_payables",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_aged_payables(params: ReportInput) -> str:
    """Get the Accounts Payable Aging report. Shows what you owe to vendors and how overdue each bill is. Helps prioritize which bills to pay first."""
    try:
        p = {}
        if params.end_date:
            p["report_date"] = params.end_date
        data = await _qb_get("reports/AgedPayableDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── QUERIES ─────────────────────────────────────────────────────────────────
class QueryInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "A QuickBooks SQL-like query. Examples:\n"
            "  SELECT * FROM Invoice WHERE Balance > '0'\n"
            "  SELECT * FROM Customer\n"
            "  SELECT * FROM Bill WHERE DueDate < '2026-04-01'\n"
            "  SELECT * FROM Vendor\n"
            "  SELECT * FROM Purchase\n"
            "  SELECT * FROM Estimate\n"
            "Values must be in single quotes. Supported entities: "
            "Invoice, Bill, Customer, Vendor, Employee, Item, Account, "
            "Payment, Purchase, Estimate, CreditMemo, SalesReceipt, "
            "JournalEntry, Deposit, Transfer, VendorCredit, TimeActivity, PurchaseOrder, Term, PaymentMethod, Department, Class, TaxCode."
        ),
    )
    max_results: Optional[int] = Field(
        default=100,
        description="Max rows to return (1-1000).",
        ge=1,
        le=1000,
    )


@mcp.tool(
    name="qb_query",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_query(params: QueryInput) -> str:
    """Run a custom query against QuickBooks. Use this for any data retrieval — invoices, customers, vendors, bills, payments, items, employees, and more. Supports WHERE, ORDER BY, STARTPOSITION, and MAXRESULTS."""
    try:
        q = params.query.strip()
        if "MAXRESULTS" not in q.upper():
            q += f" MAXRESULTS {params.max_results}"
        results = await _qb_query(q)
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CONVENIENCE TOOLS ───────────────────────────────────────────────────────
class InvoiceListInput(BaseModel):
    unpaid_only: bool = Field(
        default=True, description="If true, only return invoices with a balance > 0."
    )
    max_results: Optional[int] = Field(default=50, ge=1, le=1000)


@mcp.tool(
    name="qb_list_invoices",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_invoices(params: InvoiceListInput) -> str:
    """List invoices. By default shows only unpaid invoices sorted by due date. This answers 'who owes me money?' and 'what invoices are outstanding?'"""
    try:
        q = "SELECT * FROM Invoice"
        if params.unpaid_only:
            q += " WHERE Balance > '0'"
        q += f" ORDER BY DueDate DESC MAXRESULTS {params.max_results}"
        results = await _qb_query(q)
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


class BillListInput(BaseModel):
    unpaid_only: bool = Field(
        default=True, description="If true, only return bills with a balance > 0."
    )
    max_results: Optional[int] = Field(default=50, ge=1, le=1000)


@mcp.tool(
    name="qb_list_bills",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_bills(params: BillListInput) -> str:
    """List bills (money you owe to vendors). By default shows only unpaid bills. Answers 'what do I need to pay?' and 'what bills are coming due?'"""
    try:
        q = "SELECT * FROM Bill"
        if params.unpaid_only:
            q += " WHERE Balance > '0'"
        q += f" ORDER BY DueDate DESC MAXRESULTS {params.max_results}"
        results = await _qb_query(q)
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


class SimpleListInput(BaseModel):
    max_results: Optional[int] = Field(default=100, ge=1, le=1000)


@mcp.tool(
    name="qb_list_customers",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_customers(params: SimpleListInput) -> str:
    """List all customers. Shows customer names, contact info, and balances."""
    try:
        results = await _qb_query(
            f"SELECT * FROM Customer MAXRESULTS {params.max_results}"
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_vendors",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_vendors(params: SimpleListInput) -> str:
    """List all vendors (people/companies you buy from). Shows vendor names, contact info, and balances."""
    try:
        results = await _qb_query(
            f"SELECT * FROM Vendor MAXRESULTS {params.max_results}"
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_accounts",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_accounts(params: SimpleListInput) -> str:
    """List all accounts in the chart of accounts. Shows account names, types (Bank, Expense, Income, etc.), and current balances."""
    try:
        results = await _qb_query(
            f"SELECT * FROM Account MAXRESULTS {params.max_results}"
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_items",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_items(params: SimpleListInput) -> str:
    """List all products and services. Shows item names, descriptions, prices, and types."""
    try:
        results = await _qb_query(
            f"SELECT * FROM Item MAXRESULTS {params.max_results}"
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_employees",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_employees(params: SimpleListInput) -> str:
    """List all employees. Shows names, contact info, and employment details."""
    try:
        results = await _qb_query(
            f"SELECT * FROM Employee MAXRESULTS {params.max_results}"
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CREATE OPERATIONS ───────────────────────────────────────────────────────
class CreateInvoiceInput(BaseModel):
    customer_id: str = Field(
        ..., description="The QuickBooks Customer ID to invoice."
    )
    line_items: str = Field(
        ...,
        description=(
            'JSON array of line items. Each item: {"amount": 100.00, "description": "Consulting", "item_id": "1"} '
            "item_id is optional — if omitted, a simple line with just amount and description is created."
        ),
    )


@mcp.tool(
    name="qb_create_invoice",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_invoice(params: CreateInvoiceInput) -> str:
    """Create a new invoice for a customer. Specify the customer ID and line items with amounts and descriptions."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "SalesItemLineDetail",
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {},
            }
            if "item_id" in item:
                line["SalesItemLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {
            "CustomerRef": {"value": params.customer_id},
            "Line": lines,
        }
        result = await _qb_post("invoice", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return "Error: line_items must be valid JSON. Example: [{\"amount\": 100, \"description\": \"Service\"}]"
    except Exception as e:
        return _handle_error(e)


class GetEntityInput(BaseModel):
    entity_type: str = Field(
        ...,
        description="Entity type: invoice, bill, customer, vendor, payment, purchase, estimate, etc.",
    )
    entity_id: str = Field(..., description="The QuickBooks entity ID.")


@mcp.tool(
    name="qb_get_entity",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_get_entity(params: GetEntityInput) -> str:
    """Get full details of a specific entity by type and ID. Use this to drill into a specific invoice, customer, bill, etc."""
    try:
        data = await _qb_get(f"{params.entity_type.lower()}/{params.entity_id}")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── COMPANY INFO ────────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_company_info",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_company_info() -> str:
    """Get company information — business name, address, fiscal year, industry, and preferences."""
    try:
        data = await _qb_get(f"companyinfo/{COMPANY_ID}")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── EXPENSES BY VENDOR ──────────────────────────────────────────────────────
@mcp.tool(
    name="qb_vendor_expenses",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_vendor_expenses(params: ReportInput) -> str:
    """Get expenses broken down by vendor. Answers 'where is my money going?' and 'which vendors am I spending the most with?'"""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/VendorBalanceDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CUSTOMER BALANCE ────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_customer_balance",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_customer_balance(params: ReportInput) -> str:
    """Get customer balance summary. Shows how much each customer owes you. The quickest way to see total outstanding receivables by customer."""
    try:
        p = {}
        if params.end_date:
            p["report_date"] = params.end_date
        data = await _qb_get("reports/CustomerBalanceDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE EXPENSE / PURCHASE ────────────────────────────────────────
class CreateExpenseInput(BaseModel):
    vendor_id: Optional[str] = Field(
        default=None,
        description="Vendor ID (who you paid). Optional — if unknown, leave blank and describe the vendor in the description.",
    )
    account_id: str = Field(
        ...,
        description="The bank/credit card account ID the money came from (e.g., your checking account or credit card).",
    )
    line_items: str = Field(
        ...,
        description=(
            'JSON array of expense lines. Each: {"amount": 47.50, "description": "Office supplies", "expense_account_id": "20"} '
            "expense_account_id is the category (e.g., Office Supplies, Meals, Travel). "
            "Use qb_list_accounts to find the right account IDs."
        ),
    )
    txn_date: Optional[str] = Field(
        default=None, description="Transaction date YYYY-MM-DD. Defaults to today."
    )
    memo: Optional[str] = Field(
        default=None, description="Memo or note for the expense."
    )


@mcp.tool(
    name="qb_create_expense",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_expense(params: CreateExpenseInput) -> str:
    """Record an expense or purchase. Use when someone says they bought something, paid for something, or has a receipt to log. This creates a Purchase entity in QuickBooks (check, cash, or credit card transaction)."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "AccountBasedExpenseLineDetail",
                "Description": item.get("description", ""),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": item["expense_account_id"]},
                },
            }
            lines.append(line)

        payload = {
            "PaymentType": "Cash",
            "AccountRef": {"value": params.account_id},
            "Line": lines,
        }
        if params.vendor_id:
            payload["EntityRef"] = {"value": params.vendor_id, "type": "Vendor"}
        if params.txn_date:
            payload["TxnDate"] = params.txn_date
        if params.memo:
            payload["PrivateNote"] = params.memo

        result = await _qb_post("purchase", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON. Example: [{"amount": 47.50, "description": "Supplies", "expense_account_id": "20"}]'
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE VENDOR ────────────────────────────────────────────────────
class CreateVendorInput(BaseModel):
    display_name: str = Field(
        ..., description="Vendor name as it should appear (e.g., 'Staples', 'Amazon', 'Joe the Plumber')."
    )
    email: Optional[str] = Field(default=None, description="Vendor email address.")
    phone: Optional[str] = Field(default=None, description="Vendor phone number.")
    company_name: Optional[str] = Field(default=None, description="Company name if different from display name.")


@mcp.tool(
    name="qb_create_vendor",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_vendor(params: CreateVendorInput) -> str:
    """Create a new vendor (someone you buy from or pay). Use when logging an expense for a vendor that doesn't exist yet."""
    try:
        payload = {"DisplayName": params.display_name}
        if params.email:
            payload["PrimaryEmailAddr"] = {"Address": params.email}
        if params.phone:
            payload["PrimaryPhone"] = {"FreeFormNumber": params.phone}
        if params.company_name:
            payload["CompanyName"] = params.company_name
        result = await _qb_post("vendor", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE CUSTOMER ──────────────────────────────────────────────────
class CreateCustomerInput(BaseModel):
    display_name: str = Field(
        ..., description="Customer name as it should appear."
    )
    email: Optional[str] = Field(default=None, description="Customer email address.")
    phone: Optional[str] = Field(default=None, description="Customer phone number.")
    company_name: Optional[str] = Field(default=None, description="Company name if different from display name.")


@mcp.tool(
    name="qb_create_customer",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_customer(params: CreateCustomerInput) -> str:
    """Create a new customer. Use when invoicing someone who isn't in QuickBooks yet."""
    try:
        payload = {"DisplayName": params.display_name}
        if params.email:
            payload["PrimaryEmailAddr"] = {"Address": params.email}
        if params.phone:
            payload["PrimaryPhone"] = {"FreeFormNumber": params.phone}
        if params.company_name:
            payload["CompanyName"] = params.company_name
        result = await _qb_post("customer", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE BILL ──────────────────────────────────────────────────────
class CreateBillInput(BaseModel):
    vendor_id: str = Field(..., description="Vendor ID (who sent you the bill).")
    line_items: str = Field(
        ...,
        description=(
            'JSON array of bill lines. Each: {"amount": 200.00, "description": "Monthly rent", "expense_account_id": "7"} '
            "expense_account_id is the expense category."
        ),
    )
    due_date: Optional[str] = Field(
        default=None, description="Due date YYYY-MM-DD."
    )
    txn_date: Optional[str] = Field(
        default=None, description="Bill date YYYY-MM-DD. Defaults to today."
    )


@mcp.tool(
    name="qb_create_bill",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_bill(params: CreateBillInput) -> str:
    """Record a bill you owe to a vendor. Use when you receive a bill or invoice from someone you need to pay later (e.g., rent, utilities, contractor invoices)."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            lines.append({
                "Amount": item["amount"],
                "DetailType": "AccountBasedExpenseLineDetail",
                "Description": item.get("description", ""),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": item["expense_account_id"]},
                },
            })

        payload = {
            "VendorRef": {"value": params.vendor_id},
            "Line": lines,
        }
        if params.due_date:
            payload["DueDate"] = params.due_date
        if params.txn_date:
            payload["TxnDate"] = params.txn_date

        result = await _qb_post("bill", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── WRITE: RECORD PAYMENT ──────────────────────────────────────────────────
class RecordPaymentInput(BaseModel):
    customer_id: str = Field(..., description="Customer ID who is paying.")
    amount: float = Field(..., description="Payment amount.")
    invoice_id: Optional[str] = Field(
        default=None,
        description="Invoice ID to apply this payment to. If omitted, creates an unapplied payment.",
    )
    payment_date: Optional[str] = Field(
        default=None, description="Payment date YYYY-MM-DD. Defaults to today."
    )


@mcp.tool(
    name="qb_record_payment",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_record_payment(params: RecordPaymentInput) -> str:
    """Record a payment received from a customer. Use when a customer pays an invoice or makes a payment on their account. This reduces their balance."""
    try:
        payload = {
            "CustomerRef": {"value": params.customer_id},
            "TotalAmt": params.amount,
        }
        if params.invoice_id:
            payload["Line"] = [{
                "Amount": params.amount,
                "LinkedTxn": [{
                    "TxnId": params.invoice_id,
                    "TxnType": "Invoice",
                }],
            }]
        if params.payment_date:
            payload["TxnDate"] = params.payment_date

        result = await _qb_post("payment", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── WRITE: PAY BILL ─────────────────────────────────────────────────────────
class PayBillInput(BaseModel):
    vendor_id: str = Field(..., description="Vendor ID you are paying.")
    bill_id: str = Field(..., description="Bill ID you are paying.")
    amount: float = Field(..., description="Amount to pay.")
    account_id: str = Field(
        ..., description="Bank account ID the payment comes from."
    )
    payment_date: Optional[str] = Field(
        default=None, description="Payment date YYYY-MM-DD. Defaults to today."
    )


@mcp.tool(
    name="qb_pay_bill",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_pay_bill(params: PayBillInput) -> str:
    """Pay a vendor bill. Use when you're writing a check or making a payment to a vendor for an existing bill."""
    try:
        payload = {
            "VendorRef": {"value": params.vendor_id},
            "APAccountRef": {"value": "33"},  # Accounts Payable default
            "CheckPayment": {
                "BankAccountRef": {"value": params.account_id},
            },
            "TotalAmt": params.amount,
            "Line": [{
                "Amount": params.amount,
                "LinkedTxn": [{
                    "TxnId": params.bill_id,
                    "TxnType": "Bill",
                }],
            }],
        }
        if params.payment_date:
            payload["TxnDate"] = params.payment_date

        result = await _qb_post("billpayment", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE ESTIMATE ──────────────────────────────────────────────────
class CreateEstimateInput(BaseModel):
    customer_id: str = Field(..., description="Customer ID to send the estimate to.")
    line_items: str = Field(
        ...,
        description=(
            'JSON array of line items. Each: {"amount": 500.00, "description": "Website redesign", "item_id": "1"} '
            "item_id is optional."
        ),
    )
    expiration_date: Optional[str] = Field(
        default=None, description="Estimate expiration date YYYY-MM-DD."
    )


@mcp.tool(
    name="qb_create_estimate",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_estimate(params: CreateEstimateInput) -> str:
    """Create a quote/estimate for a customer. Use when you want to send a price quote before doing the work."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "SalesItemLineDetail",
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {},
            }
            if "item_id" in item:
                line["SalesItemLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {
            "CustomerRef": {"value": params.customer_id},
            "Line": lines,
        }
        if params.expiration_date:
            payload["ExpirationDate"] = params.expiration_date

        result = await _qb_post("estimate", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── WRITE: CREATE SALES RECEIPT ─────────────────────────────────────────────
class CreateSalesReceiptInput(BaseModel):
    customer_id: Optional[str] = Field(
        default=None, description="Customer ID. Optional for walk-in/cash sales."
    )
    line_items: str = Field(
        ...,
        description=(
            'JSON array of line items. Each: {"amount": 75.00, "description": "Haircut", "item_id": "1"} '
            "item_id is optional."
        ),
    )
    payment_method_id: Optional[str] = Field(
        default=None, description="Payment method ID (cash, credit card, etc)."
    )


@mcp.tool(
    name="qb_create_sales_receipt",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_sales_receipt(params: CreateSalesReceiptInput) -> str:
    """Record a sale where the customer paid immediately (not invoiced). Use for cash sales, point-of-sale transactions, or any sale where payment is received on the spot."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "SalesItemLineDetail",
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {},
            }
            if "item_id" in item:
                line["SalesItemLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {"Line": lines}
        if params.customer_id:
            payload["CustomerRef"] = {"value": params.customer_id}
        if params.payment_method_id:
            payload["PaymentMethodRef"] = {"value": params.payment_method_id}

        result = await _qb_post("salesreceipt", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── WRITE: JOURNAL ENTRY ───────────────────────────────────────────────────
class CreateJournalEntryInput(BaseModel):
    lines: str = Field(
        ...,
        description=(
            'JSON array of journal entry lines. Each needs: '
            '{"amount": 100.00, "account_id": "1", "type": "Debit"} '
            'type must be "Debit" or "Credit". Debits must equal credits.'
        ),
    )
    txn_date: Optional[str] = Field(
        default=None, description="Journal entry date YYYY-MM-DD."
    )
    memo: Optional[str] = Field(default=None, description="Memo for the entry.")


@mcp.tool(
    name="qb_create_journal_entry",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_journal_entry(params: CreateJournalEntryInput) -> str:
    """Create a manual journal entry. Use for adjustments, corrections, or any transaction that doesn't fit standard categories. Debits must equal credits."""
    try:
        items = json.loads(params.lines)
        lines = []
        for item in items:
            posting_type = item["type"]  # "Debit" or "Credit"
            lines.append({
                "Amount": item["amount"],
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": posting_type,
                    "AccountRef": {"value": item["account_id"]},
                },
            })

        payload = {"Line": lines}
        if params.txn_date:
            payload["TxnDate"] = params.txn_date
        if params.memo:
            payload["PrivateNote"] = params.memo

        result = await _qb_post("journalentry", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: lines must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── WRITE: SEND INVOICE ────────────────────────────────────────────────────
class SendInvoiceInput(BaseModel):
    invoice_id: str = Field(..., description="Invoice ID to send via email.")
    email: Optional[str] = Field(
        default=None,
        description="Email to send to. If omitted, uses the customer's email on file.",
    )


@mcp.tool(
    name="qb_send_invoice",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_send_invoice(params: SendInvoiceInput) -> str:
    """Email an invoice to the customer. QuickBooks sends the invoice as a professional PDF email."""
    try:
        endpoint = f"invoice/{params.invoice_id}/send"
        p = {}
        if params.email:
            p["sendTo"] = params.email
        token = await _get_access_token()
        url = f"{BASE_URL}/v3/company/{COMPANY_ID}/{endpoint}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/octet-stream",
                },
                params={**p, "minorversion": MINOR_VERSION},
                timeout=30,
            )
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)
    except Exception as e:
        return _handle_error(e)


# ── UPDATE ENTITY ───────────────────────────────────────────────────────────
class UpdateEntityInput(BaseModel):
    entity_type: str = Field(
        ...,
        description=(
            "Entity type to update: invoice, bill, customer, vendor, employee, "
            "item, purchase, estimate, salesreceipt, payment, journalentry, etc."
        ),
    )
    entity_id: str = Field(..., description="The QuickBooks entity ID to update.")
    sync_token: str = Field(
        ...,
        description=(
            "The current SyncToken of the entity (required for optimistic locking). "
            "Get this by first fetching the entity with qb_get_entity."
        ),
    )
    updates: str = Field(
        ...,
        description=(
            'JSON object of fields to update. Only specified fields change; others stay the same. '
            'Examples: {"DueDate": "2026-05-01"} or {"PrimaryEmailAddr": {"Address": "new@email.com"}} '
            'or {"DisplayName": "New Name"}'
        ),
    )


@mcp.tool(
    name="qb_update_entity",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def qb_update_entity(params: UpdateEntityInput) -> str:
    """Update any entity in QuickBooks (sparse update — only changes the fields you specify). Use for changing due dates, names, emails, amounts, addresses, etc. Always fetch the entity first to get the current SyncToken."""
    try:
        updates = json.loads(params.updates)
        updates["Id"] = params.entity_id
        updates["SyncToken"] = params.sync_token
        result = await _qb_update(params.entity_type.lower(), updates)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: updates must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── DELETE ENTITY ───────────────────────────────────────────────────────────
class DeleteEntityInput(BaseModel):
    entity_type: str = Field(
        ...,
        description=(
            "Entity type to delete: purchase, bill, invoice, payment, deposit, "
            "transfer, journalentry, creditMemo, vendorCredit, billpayment, "
            "salesreceipt, estimate, purchaseorder, timeactivity. "
            "NOTE: Customers and Vendors cannot be deleted — only made inactive via update."
        ),
    )
    entity_id: str = Field(..., description="The QuickBooks entity ID to delete.")
    sync_token: str = Field(
        ...,
        description="The current SyncToken. Get this by fetching the entity first with qb_get_entity.",
    )


@mcp.tool(
    name="qb_delete_entity",
    annotations={"readOnlyHint": False, "destructiveHint": True},
)
async def qb_delete_entity(params: DeleteEntityInput) -> str:
    """Permanently delete a transaction from QuickBooks. The record is completely removed — use qb_void_entity instead if you want to keep the record but zero out amounts. Always confirm with the user before deleting."""
    try:
        result = await _qb_delete(
            params.entity_type.lower(), params.entity_id, params.sync_token
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── VOID ENTITY ─────────────────────────────────────────────────────────────
class VoidEntityInput(BaseModel):
    entity_type: str = Field(
        ...,
        description=(
            "Entity type to void: invoice, salesreceipt, billpayment, payment. "
            "Voiding keeps the record but sets all amounts to zero and marks it as voided."
        ),
    )
    entity_id: str = Field(..., description="The QuickBooks entity ID to void.")
    sync_token: str = Field(
        ...,
        description="The current SyncToken. Get this by fetching the entity first with qb_get_entity.",
    )


@mcp.tool(
    name="qb_void_entity",
    annotations={"readOnlyHint": False, "destructiveHint": True},
)
async def qb_void_entity(params: VoidEntityInput) -> str:
    """Void a transaction in QuickBooks. The record stays but amounts are zeroed out and 'Voided' is added to the notes. Preferred over delete when you want to keep a paper trail. Works for invoices, sales receipts, bill payments, and payments."""
    try:
        result = await _qb_void(
            params.entity_type.lower(), params.entity_id, params.sync_token
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── DEACTIVATE CUSTOMER/VENDOR ──────────────────────────────────────────────
class DeactivateInput(BaseModel):
    entity_type: str = Field(
        ...,
        description="'customer' or 'vendor' — these can't be deleted, only deactivated.",
    )
    entity_id: str = Field(..., description="The entity ID to deactivate.")
    sync_token: str = Field(..., description="Current SyncToken from qb_get_entity.")


@mcp.tool(
    name="qb_deactivate",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_deactivate(params: DeactivateInput) -> str:
    """Deactivate (soft-delete) a customer or vendor. They won't show up in lists but the record is preserved. QuickBooks doesn't allow hard-deleting customers or vendors."""
    try:
        result = await _qb_update(params.entity_type.lower(), {
            "Id": params.entity_id,
            "SyncToken": params.sync_token,
            "Active": False,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CREATE DEPOSIT ──────────────────────────────────────────────────────────
class CreateDepositInput(BaseModel):
    deposit_to_account_id: str = Field(
        ..., description="Bank account ID to deposit into."
    )
    line_items: str = Field(
        ...,
        description=(
            'JSON array of deposit lines. Each: {"amount": 500.00, "from_account_id": "4"} '
            "from_account_id is the source (e.g., Undeposited Funds)."
        ),
    )
    txn_date: Optional[str] = Field(default=None, description="Deposit date YYYY-MM-DD.")
    memo: Optional[str] = Field(default=None, description="Memo for the deposit.")


@mcp.tool(
    name="qb_create_deposit",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_deposit(params: CreateDepositInput) -> str:
    """Create a bank deposit. Use to move money from Undeposited Funds into a bank account, or to record cash/check deposits."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            lines.append({
                "Amount": item["amount"],
                "DetailType": "DepositLineDetail",
                "DepositLineDetail": {
                    "AccountRef": {"value": item["from_account_id"]},
                },
            })

        payload = {
            "DepositToAccountRef": {"value": params.deposit_to_account_id},
            "Line": lines,
        }
        if params.txn_date:
            payload["TxnDate"] = params.txn_date
        if params.memo:
            payload["PrivateNote"] = params.memo

        result = await _qb_post("deposit", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── CREATE TRANSFER ─────────────────────────────────────────────────────────
class CreateTransferInput(BaseModel):
    from_account_id: str = Field(..., description="Account ID to transfer money FROM.")
    to_account_id: str = Field(..., description="Account ID to transfer money TO.")
    amount: float = Field(..., description="Amount to transfer.")
    txn_date: Optional[str] = Field(default=None, description="Transfer date YYYY-MM-DD.")


@mcp.tool(
    name="qb_create_transfer",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_transfer(params: CreateTransferInput) -> str:
    """Transfer money between accounts (e.g., checking to savings, or between bank accounts)."""
    try:
        payload = {
            "FromAccountRef": {"value": params.from_account_id},
            "ToAccountRef": {"value": params.to_account_id},
            "Amount": params.amount,
        }
        if params.txn_date:
            payload["TxnDate"] = params.txn_date

        result = await _qb_post("transfer", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CREATE CREDIT MEMO ──────────────────────────────────────────────────────
class CreateCreditMemoInput(BaseModel):
    customer_id: str = Field(..., description="Customer ID to issue the credit to.")
    line_items: str = Field(
        ...,
        description='JSON array of credit lines. Each: {"amount": 50.00, "description": "Refund for damaged goods"}',
    )


@mcp.tool(
    name="qb_create_credit_memo",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_credit_memo(params: CreateCreditMemoInput) -> str:
    """Issue a credit memo (refund/credit) to a customer. Reduces what they owe. Use when you need to give a customer money back or credit their account."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "SalesItemLineDetail",
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {},
            }
            if "item_id" in item:
                line["SalesItemLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {
            "CustomerRef": {"value": params.customer_id},
            "Line": lines,
        }
        result = await _qb_post("creditmemo", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── CREATE VENDOR CREDIT ────────────────────────────────────────────────────
class CreateVendorCreditInput(BaseModel):
    vendor_id: str = Field(..., description="Vendor ID issuing the credit.")
    line_items: str = Field(
        ...,
        description='JSON array of credit lines. Each: {"amount": 100.00, "description": "Returned supplies", "expense_account_id": "20"}',
    )


@mcp.tool(
    name="qb_create_vendor_credit",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_vendor_credit(params: CreateVendorCreditInput) -> str:
    """Record a credit from a vendor (they owe you money or reduced a bill). Use when a vendor gives you a refund or credit on your account."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            lines.append({
                "Amount": item["amount"],
                "DetailType": "AccountBasedExpenseLineDetail",
                "Description": item.get("description", ""),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": item["expense_account_id"]},
                },
            })

        payload = {
            "VendorRef": {"value": params.vendor_id},
            "Line": lines,
        }
        result = await _qb_post("vendorcredit", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── CREATE ITEM (Product/Service) ───────────────────────────────────────────
class CreateItemInput(BaseModel):
    name: str = Field(..., description="Product or service name.")
    item_type: str = Field(
        default="Service",
        description="'Service', 'Inventory', or 'NonInventory'.",
    )
    income_account_id: str = Field(
        ..., description="Income account ID this item posts revenue to."
    )
    unit_price: Optional[float] = Field(default=None, description="Default sale price.")
    description: Optional[str] = Field(default=None, description="Item description.")
    expense_account_id: Optional[str] = Field(
        default=None, description="Expense/COGS account ID (required for Inventory items)."
    )


@mcp.tool(
    name="qb_create_item",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_item(params: CreateItemInput) -> str:
    """Create a new product or service. Use when you need to add a line item that doesn't exist yet for invoicing or sales receipts."""
    try:
        payload = {
            "Name": params.name,
            "Type": params.item_type,
            "IncomeAccountRef": {"value": params.income_account_id},
        }
        if params.unit_price is not None:
            payload["UnitPrice"] = params.unit_price
        if params.description:
            payload["Description"] = params.description
        if params.expense_account_id:
            payload["ExpenseAccountRef"] = {"value": params.expense_account_id}

        result = await _qb_post("item", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── PURCHASE ORDER ──────────────────────────────────────────────────────────
class CreatePurchaseOrderInput(BaseModel):
    vendor_id: str = Field(..., description="Vendor ID to order from.")
    line_items: str = Field(
        ...,
        description='JSON array of order lines. Each: {"amount": 200.00, "description": "50 widgets", "item_id": "5"}',
    )


@mcp.tool(
    name="qb_create_purchase_order",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_purchase_order(params: CreatePurchaseOrderInput) -> str:
    """Create a purchase order to a vendor. Use when ordering goods/services from a supplier before receiving a bill."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "ItemBasedExpenseLineDetail",
                "Description": item.get("description", ""),
                "ItemBasedExpenseLineDetail": {},
            }
            if "item_id" in item:
                line["ItemBasedExpenseLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {
            "VendorRef": {"value": params.vendor_id},
            "Line": lines,
        }
        result = await _qb_post("purchaseorder", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── TIME ACTIVITY ───────────────────────────────────────────────────────────
class CreateTimeActivityInput(BaseModel):
    employee_id: Optional[str] = Field(default=None, description="Employee ID logging time.")
    vendor_id: Optional[str] = Field(default=None, description="Vendor/contractor ID logging time (use instead of employee_id for contractors).")
    customer_id: Optional[str] = Field(default=None, description="Customer ID the time is billed to.")
    hours: int = Field(..., description="Hours worked.")
    minutes: int = Field(default=0, description="Minutes worked (0-59).")
    description: Optional[str] = Field(default=None, description="Description of work done.")
    billable: bool = Field(default=True, description="Whether this time is billable to the customer.")
    txn_date: Optional[str] = Field(default=None, description="Date of work YYYY-MM-DD.")


@mcp.tool(
    name="qb_create_time_activity",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_time_activity(params: CreateTimeActivityInput) -> str:
    """Log time worked by an employee or contractor. Can be billable to a customer. Use for time tracking, billable hours, and contractor time logging."""
    try:
        payload = {
            "Hours": params.hours,
            "Minutes": params.minutes,
            "BillableStatus": "Billable" if params.billable else "NotBillable",
        }
        if params.employee_id:
            payload["NameOf"] = "Employee"
            payload["EmployeeRef"] = {"value": params.employee_id}
        elif params.vendor_id:
            payload["NameOf"] = "Vendor"
            payload["VendorRef"] = {"value": params.vendor_id}
        if params.customer_id:
            payload["CustomerRef"] = {"value": params.customer_id}
        if params.description:
            payload["Description"] = params.description
        if params.txn_date:
            payload["TxnDate"] = params.txn_date

        result = await _qb_post("timeactivity", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── TAX SUMMARY ─────────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_tax_summary",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_tax_summary(params: ReportInput) -> str:
    """Get the sales tax liability report. Shows tax collected and owed by tax agency. Essential for quarterly tax filings."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/TaxSummary", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── GENERAL LEDGER ──────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_general_ledger",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_general_ledger(params: ReportInput) -> str:
    """Get the General Ledger report. Shows every transaction in every account. Used by accountants for tax prep and auditing."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/GeneralLedgerDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── TRIAL BALANCE ───────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_trial_balance",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_trial_balance(params: ReportInput) -> str:
    """Get the Trial Balance report. Summary of all account balances — debits and credits should equal. Used for verifying books before closing periods."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/TrialBalance", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── ATTACHMENTS (NOTES, LIST, DOWNLOAD — upload saved for hosted version) ──
class DownloadAttachmentInput(BaseModel):
    attachable_id: str = Field(..., description="Attachable ID to download.")


@mcp.tool(
    name="qb_download_attachment",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_download_attachment(params: DownloadAttachmentInput) -> str:
    """Get a temporary download URL for an attachment. The URL expires after 15 minutes."""
    try:
        data = await _qb_get(f"download/{params.attachable_id}")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


class ListAttachmentsInput(BaseModel):
    entity_type: str = Field(..., description="Entity type: Invoice, Bill, Purchase, etc.")
    entity_id: str = Field(..., description="Entity ID to list attachments for.")


@mcp.tool(
    name="qb_list_attachments",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_attachments(params: ListAttachmentsInput) -> str:
    """List all attachments linked to a specific transaction. Returns attachment IDs, filenames, and notes."""
    try:
        q = (
            f"SELECT * FROM Attachable WHERE "
            f"AttachableRef.EntityRef.Type = '{params.entity_type}' AND "
            f"AttachableRef.EntityRef.value = '{params.entity_id}'"
        )
        results = await _qb_query(q)
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


class AddNoteInput(BaseModel):
    entity_type: str = Field(..., description="Entity type to attach note to.")
    entity_id: str = Field(..., description="Entity ID.")
    note: str = Field(..., description="The note text (max 2000 chars).")


@mcp.tool(
    name="qb_add_note",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_add_note(params: AddNoteInput) -> str:
    """Add a text note to any QuickBooks transaction or entity. Use for internal memos, context, or bookkeeping notes."""
    try:
        payload = {
            "Note": params.note,
            "AttachableRef": [{
                "EntityRef": {
                    "type": params.entity_type,
                    "value": params.entity_id,
                },
                "IncludeOnSend": False,
            }],
        }
        result = await _qb_post("attachable", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── CREATE ACCOUNT ──────────────────────────────────────────────────────────
class CreateAccountInput(BaseModel):
    name: str = Field(..., description="Account name (max 100 chars). Must be unique. Cannot contain double quotes or colons.")
    account_type: str = Field(
        ...,
        description=(
            "Account type: Bank, Accounts Receivable, Other Current Asset, Fixed Asset, "
            "Other Asset, Accounts Payable, Credit Card, Other Current Liability, "
            "Long Term Liability, Equity, Income, Cost of Goods Sold, Expense, "
            "Other Income, Other Expense."
        ),
    )
    account_sub_type: Optional[str] = Field(
        default=None,
        description="Sub-type for more specific categorization (e.g., Checking, Savings, AdvertisingPromotional, OfficeGeneralAdministrativeExpenses).",
    )
    description: Optional[str] = Field(default=None, description="Account description (max 100 chars).")
    acct_num: Optional[str] = Field(default=None, description="User-defined account number (max 7 chars US).")


@mcp.tool(
    name="qb_create_account",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_account(params: CreateAccountInput) -> str:
    """Create a new account in the chart of accounts. Use when you need a new category for tracking income, expenses, assets, or liabilities that doesn't exist yet."""
    try:
        payload = {
            "Name": params.name,
            "AccountType": params.account_type,
        }
        if params.account_sub_type:
            payload["AccountSubType"] = params.account_sub_type
        if params.description:
            payload["Description"] = params.description
        if params.acct_num:
            payload["AcctNum"] = params.acct_num

        result = await _qb_post("account", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── REFUND RECEIPT ──────────────────────────────────────────────────────────
class CreateRefundReceiptInput(BaseModel):
    customer_id: Optional[str] = Field(default=None, description="Customer receiving the refund.")
    line_items: str = Field(
        ...,
        description='JSON array: [{"amount": 50.00, "description": "Refund for defective item", "item_id": "1"}]',
    )
    account_id: str = Field(..., description="Bank/credit card account the refund comes from.")


@mcp.tool(
    name="qb_create_refund_receipt",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_refund_receipt(params: CreateRefundReceiptInput) -> str:
    """Create a refund receipt — records giving money back to a customer. Different from a credit memo: this is actual money returned, not credit on their account."""
    try:
        items = json.loads(params.line_items)
        lines = []
        for item in items:
            line = {
                "Amount": item["amount"],
                "DetailType": "SalesItemLineDetail",
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {},
            }
            if "item_id" in item:
                line["SalesItemLineDetail"]["ItemRef"] = {"value": item["item_id"]}
            lines.append(line)

        payload = {
            "Line": lines,
            "DepositToAccountRef": {"value": params.account_id},
        }
        if params.customer_id:
            payload["CustomerRef"] = {"value": params.customer_id}

        result = await _qb_post("refundreceipt", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return 'Error: line_items must be valid JSON.'
    except Exception as e:
        return _handle_error(e)


# ── CLASS (Categorization) ──────────────────────────────────────────────────
class CreateClassInput(BaseModel):
    name: str = Field(..., description="Class name (e.g., 'Marketing', 'Construction', 'Retail').")
    parent_id: Optional[str] = Field(default=None, description="Parent class ID for sub-classes.")


@mcp.tool(
    name="qb_create_class",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_class(params: CreateClassInput) -> str:
    """Create a class for categorizing transactions across accounts. Useful for tracking by project, department, or business segment."""
    try:
        payload = {"Name": params.name}
        if params.parent_id:
            payload["ParentRef"] = {"value": params.parent_id}
        result = await _qb_post("class", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── DEPARTMENT ──────────────────────────────────────────────────────────────
class CreateDepartmentInput(BaseModel):
    name: str = Field(..., description="Department name.")
    parent_id: Optional[str] = Field(default=None, description="Parent department ID for sub-departments.")


@mcp.tool(
    name="qb_create_department",
    annotations={"readOnlyHint": False, "destructiveHint": False},
)
async def qb_create_department(params: CreateDepartmentInput) -> str:
    """Create a department/location for organizing transactions by business unit or location."""
    try:
        payload = {"Name": params.name}
        if params.parent_id:
            payload["ParentRef"] = {"value": params.parent_id}
        result = await _qb_post("department", payload)
        return json.dumps(result, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── LIST CLASSES & DEPARTMENTS ──────────────────────────────────────────────
@mcp.tool(
    name="qb_list_classes",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_classes(params: SimpleListInput) -> str:
    """List all classes (categorization tags for transactions)."""
    try:
        results = await _qb_query(f"SELECT * FROM Class MAXRESULTS {params.max_results}")
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_departments",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_departments(params: SimpleListInput) -> str:
    """List all departments/locations."""
    try:
        results = await _qb_query(f"SELECT * FROM Department MAXRESULTS {params.max_results}")
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_tax_codes",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_tax_codes(params: SimpleListInput) -> str:
    """List all tax codes. Shows active tax rates and their details."""
    try:
        results = await _qb_query(f"SELECT * FROM TaxCode MAXRESULTS {params.max_results}")
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_payment_methods",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_payment_methods(params: SimpleListInput) -> str:
    """List all payment methods (Cash, Check, Credit Card, etc.)."""
    try:
        results = await _qb_query(f"SELECT * FROM PaymentMethod MAXRESULTS {params.max_results}")
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_list_terms",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_list_terms(params: SimpleListInput) -> str:
    """List all payment terms (Net 30, Net 60, Due on Receipt, etc.)."""
    try:
        results = await _qb_query(f"SELECT * FROM Term MAXRESULTS {params.max_results}")
        return json.dumps(results, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── MORE REPORTS ────────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_expenses_by_vendor",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_expenses_by_vendor(params: ReportInput) -> str:
    """Get total expenses broken down by vendor. Quick way to see who you're spending the most with."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/VendorExpenses", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_sales_by_customer",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_sales_by_customer(params: ReportInput) -> str:
    """Get sales revenue broken down by customer. Shows who your biggest clients are."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/SalesByCustomer", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_sales_by_product",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_sales_by_product(params: ReportInput) -> str:
    """Get sales revenue broken down by product/service. Shows which offerings generate the most revenue."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/SalesByProduct", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_transaction_list",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_transaction_list(params: ReportInput) -> str:
    """Get a full transaction list for a date range. Shows every transaction across all accounts — the raw activity log of your business."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/TransactionList", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="qb_profit_and_loss_detail",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_profit_and_loss_detail(params: ReportInput) -> str:
    """Get detailed Profit & Loss showing individual transactions, not just totals. Use when you need to see exactly what makes up each income/expense line."""
    try:
        p = {}
        if params.start_date:
            p["start_date"] = params.start_date
        if params.end_date:
            p["end_date"] = params.end_date
        data = await _qb_get("reports/ProfitAndLossDetail", p)
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── PREFERENCES ─────────────────────────────────────────────────────────────
@mcp.tool(
    name="qb_get_preferences",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def qb_get_preferences() -> str:
    """Get company preferences and settings — accounting method (cash/accrual), fiscal year, tax settings, enabled features, etc."""
    try:
        data = await _qb_get("preferences")
        return json.dumps(data, indent=2)
    except Exception as e:
        return _handle_error(e)


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
