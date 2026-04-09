# QuickBooks MCP Server

Built by **Shane Brady** — [Lightbreak Lab](https://lightbreaklab.com)

A local-first MCP (Model Context Protocol) server that connects Claude Desktop to QuickBooks Online. Ask Claude questions about your books in plain English — pull reports, create invoices, log expenses, and manage your entire chart of accounts through natural conversation.

## What It Does

### Read Operations (Reports & Queries)
- **Financial Reports**: Profit & Loss, Balance Sheet, Cash Flow, Trial Balance, General Ledger
- **Aging Reports**: Aged Receivables, Aged Payables
- **Sales Reports**: Sales by Customer, Sales by Product
- **Expense Reports**: Expenses by Vendor, Vendor Balance Detail
- **Tax Reports**: Tax Summary, Transaction List
- **Queries**: Invoices, Bills, Customers, Vendors, Employees, Items, Accounts, Classes, Departments, Tax Codes, Payment Methods, Terms
- **Drill-down**: Get full details on any entity by type and ID
- **Custom Queries**: Run any QuickBooks SQL-like query
- **Attachments**: List and download attachments on any transaction

### Write Operations (Create, Update, Delete)
- **Invoicing**: Create invoices, send invoices via email, create estimates
- **Expenses**: Record expenses/purchases, create bills, pay bills
- **Payments**: Record customer payments, create sales receipts, refund receipts
- **Contacts**: Create customers, create vendors, deactivate (soft-delete)
- **Accounting**: Journal entries, deposits, transfers, credit memos, vendor credits
- **Organization**: Create accounts, items (products/services), classes, departments, purchase orders, time activities
- **Modifications**: Update any entity (sparse update), delete transactions, void transactions
- **Notes**: Add text notes to any transaction

## Security

**This server runs locally on your machine.** Your QuickBooks credentials never leave your computer — they are stored in a `.env` file that is excluded from version control via `.gitignore`.

### How Authentication Works

1. Your QuickBooks OAuth credentials (Client ID, Client Secret) live in `.env` — **never committed to git**
2. The server exchanges your refresh token for short-lived access tokens (1 hour expiry)
3. QuickBooks rotates refresh tokens automatically — the server saves the new token back to `.env`
4. All API calls go directly from your machine to QuickBooks' API over HTTPS
5. No intermediate servers, no cloud functions, no data stored anywhere else

### Security Best Practices

- **Never commit `.env`** — it's in `.gitignore` but double-check before pushing
- **Use sandbox first** — set `QUICKBOOKS_ENV=sandbox` while testing
- **Rotate credentials** if you suspect they were exposed — regenerate keys in the [Intuit Developer Portal](https://developer.intuit.com)
- **Limit app scopes** — the auth helper requests only `com.intuit.quickbooks.accounting` (the minimum needed)
- **Review write operations** — Claude will ask for confirmation before creating/modifying/deleting records, but always review what's being sent
- **Localhost only** — the auth helper callback server binds to `localhost:8080` and handles exactly one request, then shuts down

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (fast Python package runner)
- A QuickBooks Online account (sandbox or production)
- A QuickBooks app registered at [developer.intuit.com](https://developer.intuit.com)

## Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone this repo

```bash
git clone https://github.com/shanebrady77/quickbooks-mcp-server.git
cd quickbooks-mcp-server
```

### 3. Create your QuickBooks app

1. Go to [developer.intuit.com](https://developer.intuit.com) and sign in
2. Create a new app (choose "QuickBooks Online and Payments")
3. Under **Keys & credentials**, copy your **Client ID** and **Client Secret**
4. Add this redirect URI: `http://localhost:8080/callback`

### 4. Configure your credentials

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
QUICKBOOKS_CLIENT_ID=your_client_id
QUICKBOOKS_CLIENT_SECRET=your_client_secret
QUICKBOOKS_REFRESH_TOKEN=PLACEHOLDER
QUICKBOOKS_COMPANY_ID=your_company_id
QUICKBOOKS_ENV=sandbox
```

> **Finding your Company ID**: Log into QuickBooks Online. The Company ID is in the URL: `https://app.qbo.intuit.com/app/homepage?companyId=XXXXXXXXXX`. For sandbox, find it in the Intuit Developer Portal under your sandbox company.

### 5. Authorize the app (get your refresh token)

```bash
uv run auth_helper.py
```

This will:
1. Open your browser to QuickBooks' authorization page
2. You approve the connection
3. The refresh token is saved to `.env` automatically

### 6. Configure Claude Desktop

Open **Claude Desktop** > **Settings** > **Developer** > **Edit Config**

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "QuickBooks": {
      "command": "uv",
      "args": [
        "--directory",
        "/FULL/PATH/TO/quickbooks-mcp-server",
        "run",
        "quickbooks_mcp.py"
      ]
    }
  }
}
```

Replace `/FULL/PATH/TO/quickbooks-mcp-server` with the actual path (e.g., `/Users/yourname/Documents/quickbooks-mcp-server`).

### 7. Restart Claude Desktop

The QuickBooks tools will appear after 10-20 seconds on first launch. You'll see a hammer icon indicating available tools.

## Example Questions

| What you ask | What happens |
|---|---|
| "Am I profitable this year?" | Pulls Profit & Loss report |
| "Who owes me money?" | Pulls Aged Receivables |
| "What bills do I need to pay?" | Lists unpaid bills |
| "Show me my biggest customers" | Sales by Customer report |
| "Create an invoice for Acme Corp for $5,000 consulting" | Creates invoice via API |
| "Log a $47.50 expense for office supplies" | Records a purchase |
| "What's my cash position?" | Balance Sheet + Cash Flow |
| "Send invoice #1042 to the customer" | Emails the invoice |

## All 40 Tools

| Tool | Type | Description |
|------|------|-------------|
| `qb_profit_and_loss` | Report | Income statement |
| `qb_profit_and_loss_detail` | Report | P&L with individual transactions |
| `qb_balance_sheet` | Report | Assets, liabilities, equity |
| `qb_cash_flow` | Report | Cash movement statement |
| `qb_aged_receivables` | Report | Who owes you and how late |
| `qb_aged_payables` | Report | What you owe and how late |
| `qb_vendor_expenses` | Report | Spending by vendor |
| `qb_expenses_by_vendor` | Report | Total expenses by vendor |
| `qb_customer_balance` | Report | Balances owed by customer |
| `qb_sales_by_customer` | Report | Revenue by customer |
| `qb_sales_by_product` | Report | Revenue by product/service |
| `qb_tax_summary` | Report | Sales tax liability |
| `qb_general_ledger` | Report | Every transaction, every account |
| `qb_trial_balance` | Report | Account balance summary |
| `qb_transaction_list` | Report | Full transaction log |
| `qb_list_invoices` | Query | List invoices (unpaid by default) |
| `qb_list_bills` | Query | List bills (unpaid by default) |
| `qb_list_customers` | Query | All customers |
| `qb_list_vendors` | Query | All vendors |
| `qb_list_accounts` | Query | Chart of accounts |
| `qb_list_items` | Query | Products and services |
| `qb_list_employees` | Query | All employees |
| `qb_list_classes` | Query | Transaction categorization tags |
| `qb_list_departments` | Query | Departments/locations |
| `qb_list_tax_codes` | Query | Tax rates |
| `qb_list_payment_methods` | Query | Payment method options |
| `qb_list_terms` | Query | Payment terms (Net 30, etc.) |
| `qb_query` | Query | Custom SQL-like query |
| `qb_get_entity` | Query | Full details of any entity |
| `qb_company_info` | Query | Business info and settings |
| `qb_get_preferences` | Query | Company preferences |
| `qb_list_attachments` | Query | Attachments on a transaction |
| `qb_download_attachment` | Query | Download attachment URL |
| `qb_create_invoice` | Write | Create invoice |
| `qb_send_invoice` | Write | Email invoice to customer |
| `qb_create_expense` | Write | Record expense/purchase |
| `qb_create_bill` | Write | Record a bill you owe |
| `qb_pay_bill` | Write | Pay a vendor bill |
| `qb_record_payment` | Write | Record customer payment |
| `qb_create_sales_receipt` | Write | Record immediate sale |
| `qb_create_estimate` | Write | Create quote/estimate |
| `qb_create_customer` | Write | Add new customer |
| `qb_create_vendor` | Write | Add new vendor |
| `qb_create_item` | Write | Add product/service |
| `qb_create_account` | Write | Add to chart of accounts |
| `qb_create_journal_entry` | Write | Manual journal entry |
| `qb_create_deposit` | Write | Bank deposit |
| `qb_create_transfer` | Write | Transfer between accounts |
| `qb_create_credit_memo` | Write | Customer credit/refund |
| `qb_create_vendor_credit` | Write | Vendor credit |
| `qb_create_refund_receipt` | Write | Cash refund to customer |
| `qb_create_purchase_order` | Write | Order from vendor |
| `qb_create_time_activity` | Write | Log billable time |
| `qb_create_class` | Write | Create categorization class |
| `qb_create_department` | Write | Create department/location |
| `qb_update_entity` | Write | Update any entity |
| `qb_delete_entity` | Write | Permanently delete transaction |
| `qb_void_entity` | Write | Void transaction (keep record) |
| `qb_deactivate` | Write | Soft-delete customer/vendor |
| `qb_add_note` | Write | Add note to any entity |

## Switching to Production

When you're ready to use real data:

1. In your Intuit Developer Portal, get **production** keys (different from sandbox)
2. Update `.env`:
   ```
   QUICKBOOKS_CLIENT_ID=your_production_client_id
   QUICKBOOKS_CLIENT_SECRET=your_production_client_secret
   QUICKBOOKS_ENV=production
   ```
3. Re-run `uv run auth_helper.py` to authorize with your production company
4. Restart Claude Desktop

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Authentication failed" | Your refresh token expired. Run `uv run auth_helper.py` again |
| Tools not showing in Claude | Check the path in `claude_desktop_config.json` is correct and absolute |
| "Permission denied" | Check your app scopes in the Intuit Developer Portal |
| Timeout errors | QuickBooks API can be slow — try again, or narrow your query date range |
| "Token has been revoked" | Re-run auth helper. Tokens expire after 100 days of inactivity |

## License

MIT
