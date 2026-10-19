from odoo import fields, models


class AccountSupplierPaymentMethod(models.Model):
    _name = 'account.supplier.payment.method'
    _description = 'Supplier Payment Method'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    include_in_payment_run = fields.Boolean(
        string='Include in Payment Run',
        help="Bills with this payment method can be paid through a bank payment file. "
             "Leave it off for methods that are paid outside the payment run, such as credit card or direct debit.",
    )

