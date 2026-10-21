{
    'name': 'Supplier Payment Method',
    'version': '18.0.1.1.1',
    'category': 'Accounting/Accounting',
    'summary': 'Record how each supplier is paid, and carry it onto every vendor bill',
    'description': """
Supplier Payment Method
=======================

Adds a configurable list of payment methods (Prepayment, Bank transfer,
Credit Card, Direct Debit), maintained by accounting administrators under
**Accounting > Configuration > Invoicing > Supplier Payment Methods**.

* **Supplier**: a *Default Payment Method* in the *Miscellaneous* group of the
  Invoicing tab, next to the LEI. The value is per company.
* **Vendor bill / refund / receipt**: a *Payment Method* that is filled in from
  the supplier when the supplier is selected. It can be changed on each bill,
  also after the bill is posted, and changes are logged in the chatter.

Changing a supplier's default does not touch existing bills.

**Ready for Payment** is set on a vendor bill only when it can go into a bank
payment file without errors:

* the bill is posted, has an amount left to pay, no payment in progress
  ("In Payment") and is not blocked;
* its bank account is trusted ("Send Money"), otherwise *Pay* refuses it;
* the supplier has a country, otherwise generating the SEPA file fails;
* its payment method is empty or has *Include in Payment Run* set. Only
  *Bank transfer* has it by default, so bills paid by credit card or direct
  debit are never included.

This list is unrelated to Odoo's own technical payment methods
(``account.payment.method.line``: Manual, SEPA Credit Transfer, ...), which
decide how a payment is executed from a journal.
    """,
    'author': 'Johan Camp',
    'license': 'LGPL-3',
    'depends': [
        'account',
        # Provides the 'Miscellaneous' group (with the LEI) on the partner's Invoicing tab.
        'account_iso20022',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_supplier_payment_method_data.xml',
        'views/account_supplier_payment_method_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
