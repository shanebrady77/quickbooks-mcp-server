# QuickBooks MCP Server

Built by **Shane Brady** — [shanebrady.com](https://shanebrady.com)

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

## Important Security Considerations

This server gives Claude **read and write access** to your QuickBooks account. That's powerful — and worth understanding before you connect it to production data.

### Your Financial Data Passes Through AI

When Claude reads your QuickBooks data (invoices, customer emails, revenue, expenses), that data is sent to Anthropic's servers for processing as part of your conversation. Your OAuth tokens stay on your machine, but the financial data Claude pulls **does leave your computer** during the session. Review [Anthropic's data usage policy](https://www.anthropic.com/policies) to understand how your data is handled.

### Write Operations Carry Real Risk

Claude can create invoices, send emails to your customers, record expenses, and delete transactions. A vague or careless prompt could:
- **Send an incorrect invoice** to a real customer
- **Email reminders** to the wrong contacts
- **Create duplicate or miscategorized expenses** that mess up your books at tax time
- **Delete or void transactions** that are hard to recover

**Always review what Claude is about to do before confirming write actions.** Especially anything that sends emails or modifies records.

### Automations Run Without Supervision

If you set up scheduled tasks (e.g., "every Monday, chase overdue invoices"), those run unattended. If something goes wrong — duplicate sends, wrong amounts, emails to the wrong people — nobody catches it until the damage is done. Start with manual runs and only automate after you trust the output.

### Prompt Injection via Customer Data

If a customer name, invoice memo, or note contains adversarial text (e.g., instructions that try to manipulate the AI), Claude could theoretically act on it when processing that record. This is a known risk with AI systems reading untrusted data.

### Recommendations

1. **Start with sandbox** — set `QUICKBOOKS_ENV=sandbox` and test thoroughly before touching real data
2. **Read-only first** — use reports and queries before trusting write operations
3. **Never run on a shared machine** — anyone with access to your `.env` file has full access to your QuickBooks
4. **Review before sending** — always confirm before Claude sends emails or creates customer-facing documents
5. **Monitor automations** — check scheduled task outputs regularly, don't set-and-forget
6. **Rotate credentials** if you suspect exposure — regenerate keys in the [Intuit Developer Portal](https://developer.intuit.com)

---

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

## All 60 Tools

### Reports (15)

| Tool | Description |
|------|-------------|
| `qb_profit_and_loss` | Income statement — are you making money? |
| `qb_profit_and_loss_detail` | P&L with individual transactions, not just totals |
| `qb_balance_sheet` | Assets, liabilities, equity snapshot |
| `qb_cash_flow` | Cash in/out — operating, investing, financing |
| `qb_aged_receivables` | Who owes you and how overdue |
| `qb_aged_payables` | What you owe and how overdue |
| `qb_vendor_expenses` | Spending breakdown by vendor |
| `qb_expenses_by_vendor` | Total expenses by vendor |
| `qb_customer_balance` | Balances owed by each customer |
| `qb_sales_by_customer` | Revenue by customer |
| `qb_sales_by_product` | Revenue by product/service |
| `qb_tax_summary` | Sales tax liability by agency |
| `qb_general_ledger` | Every transaction in every account |
| `qb_trial_balance` | All account balances — debits vs credits |
| `qb_transaction_list` | Full transaction log for a date range |

### Queries (18)

| Tool | Description |
|------|-------------|
| `qb_list_invoices` | List invoices (unpaid by default) |
| `qb_list_bills` | List bills (unpaid by default) |
| `qb_list_customers` | All customers with contact info and balances |
| `qb_list_vendors` | All vendors with contact info and balances |
| `qb_list_accounts` | Chart of accounts — names, types, balances |
| `qb_list_items` | Products and services with prices |
| `qb_list_employees` | All employees with details |
| `qb_list_classes` | Transaction categorization tags |
| `qb_list_departments` | Departments and locations |
| `qb_list_tax_codes` | Active tax rates |
| `qb_list_payment_methods` | Payment methods (Cash, Check, CC, etc.) |
| `qb_list_terms` | Payment terms (Net 30, Due on Receipt, etc.) |
| `qb_list_attachments` | Attachments on a specific transaction |
| `qb_query` | Custom SQL-like query against any entity |
| `qb_get_entity` | Full details of any entity by type + ID |
| `qb_company_info` | Business name, address, fiscal year, settings |
| `qb_get_preferences` | Accounting method, tax settings, enabled features |
| `qb_download_attachment` | Get temporary download URL for an attachment |

### Write Operations (27)

| Tool | Description |
|------|-------------|
| `qb_create_invoice` | Create a new invoice for a customer |
| `qb_send_invoice` | Email an invoice as a professional PDF |
| `qb_create_expense` | Record an expense or purchase |
| `qb_create_bill` | Record a bill you owe to a vendor |
| `qb_pay_bill` | Pay a vendor bill from a bank account |
| `qb_record_payment` | Record a payment received from a customer |
| `qb_create_sales_receipt` | Record an immediate/cash sale |
| `qb_create_estimate` | Create a quote or estimate |
| `qb_create_customer` | Add a new customer |
| `qb_create_vendor` | Add a new vendor |
| `qb_create_item` | Add a product or service |
| `qb_create_account` | Add to chart of accounts |
| `qb_create_journal_entry` | Manual journal entry (debits must equal credits) |
| `qb_create_deposit` | Bank deposit from Undeposited Funds |
| `qb_create_transfer` | Transfer money between accounts |
| `qb_create_credit_memo` | Issue credit/refund to a customer's account |
| `qb_create_vendor_credit` | Record a credit from a vendor |
| `qb_create_refund_receipt` | Cash refund back to a customer |
| `qb_create_purchase_order` | Order goods/services from a vendor |
| `qb_create_time_activity` | Log billable or non-billable time |
| `qb_create_class` | Create a categorization class |
| `qb_create_department` | Create a department or location |
| `qb_update_entity` | Sparse update any entity (change specific fields) |
| `qb_delete_entity` | Permanently delete a transaction |
| `qb_void_entity` | Void a transaction (keep record, zero amounts) |
| `qb_deactivate` | Soft-delete a customer or vendor |
| `qb_add_note` | Add a text note to any transaction or entity |

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
