{
    'name': 'LLM Tool - Accounting Guard',
    'version': '18.0.1.0.1',
    'category': 'Accounting',
    'summary': 'Lock MCP/LLM tool calls to one company, guard accounting writes, and reconcile bank lines',
    'description': """
Accounting guard for the Apexive MCP tools
==========================================

The generic ``llm_tool`` tools (record retriever, creator, updater, unlinker,
method executor) take no context. Without one, Odoo makes every company the
user belongs to visible, and fills defaults and company-dependent fields
(account codes, partner receivable/payable accounts, payment terms) from the
user's *main* company. In a multi-company database that is how bookings end
up in the wrong company.

**Company lock**

* ``accounting_select_company`` stores the session company on the user
  (``llm_company_id``). Every following tool call runs with
  ``allowed_company_ids = [that company]``: record rules hide the other
  companies, and new records and defaults belong to the chosen company.
* Without a session company, tool calls on accounting models are refused
  (system parameter ``llm_tool_accounting.require_company``, default ``1``).

**Guards** (enforced in Odoo, whatever the assistant asks for)

* Customer invoices, credit notes and receipts are never posted or sent
  through the tools; they stay draft for a human to confirm.
* No ``state`` or ``auto_post`` values may be written on journal entries
  directly; posting goes through ``action_post`` only.
* In a company whose VAT regime is not *VAT registered*, a journal entry
  carrying non-zero VAT cannot be posted.
* In a company with *Analytic Required on Income and Expenses*, a journal entry
  cannot be posted, and a bank line cannot be reconciled, while an income or
  expense line lacks a complete analytic distribution.
* Nothing in ``account.*`` can be deleted, and no private method can be called
  on it, through the tools.

**Bank reconciliation**

``accounting_reconcile_statement_line`` matches a bank or credit card statement
line with open journal items and/or a counterpart account, using the same
widget logic as the reconciliation screen.
    """,
    'author': 'Johan Camp',
    'license': 'LGPL-3',
    'depends': [
        'account_accountant',
        'llm_tool',
        'llm_mcp_server',
    ],
    'data': [
        'data/ir_config_parameter.xml',
        'views/res_company_views.xml',
    ],
    'installable': True,
    'application': False,
}
