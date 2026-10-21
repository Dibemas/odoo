from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    supplier_payment_method_id = fields.Many2one(
        comodel_name='account.supplier.payment.method',
        string='Payment Method',
        compute='_compute_supplier_payment_method_id',
        store=True,
        readonly=False,
        precompute=True,
        index='btree_not_null',
        tracking=True,
        help="How this bill is paid. Defaults to the supplier's Default Payment Method.",
    )

    is_ready_for_payment = fields.Boolean(
        string='Ready for Payment',
        compute='_compute_is_ready_for_payment',
        store=True,
        help="The bill is posted, has an amount left to pay and no payment in progress, is not blocked, "
             "has a trusted bank account, a supplier with a country, "
             "and a payment method that is empty or included in the payment run.",
    )

    @api.depends('partner_id', 'move_type')
    def _compute_supplier_payment_method_id(self):
        for move in self:
            if move.is_purchase_document(include_receipts=True) and move.partner_id:
                partner = move.partner_id.commercial_partner_id.with_company(move.company_id)
                move.supplier_payment_method_id = partner.property_supplier_payment_method_id
            else:
                move.supplier_payment_method_id = False

    @api.depends(
        'move_type', 'state', 'amount_residual', 'payment_state',
        'partner_bank_id.allow_out_payment',
        'commercial_partner_id.country_id',
        'supplier_payment_method_id.include_in_payment_run',
    )
    def _compute_is_ready_for_payment(self):
        for move in self:
            method = move.supplier_payment_method_id
            move.is_ready_for_payment = bool(
                move.move_type in ('in_invoice', 'in_receipt')
                and move.state == 'posted'
                and move.currency_id.compare_amounts(move.amount_residual, 0.0) > 0
                # A payment without its own journal entry (until bank matching) leaves the
                # residual untouched but sets 'in_payment'; 'blocked' is Odoo's manual hold.
                and move.payment_state not in ('in_payment', 'paid', 'reversed', 'blocked')
                # The 'Pay' wizard refuses untrusted bank accounts.
                and move.partner_bank_id.allow_out_payment
                # The SEPA file needs the country of the partner being paid.
                and move.commercial_partner_id.country_id
                and (not method or method.include_in_payment_run)
            )
