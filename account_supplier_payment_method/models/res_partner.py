from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    property_supplier_payment_method_id = fields.Many2one(
        comodel_name='account.supplier.payment.method',
        string='Default Payment Method',
        company_dependent=True,
        help="Proposed as the payment method on new vendor bills from this supplier.",
    )
