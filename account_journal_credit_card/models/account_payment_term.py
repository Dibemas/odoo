from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    credit_card_journal_id = fields.Many2one(
        'account.journal',
        domain="[('is_credit_card', '=', True)]",
        string='Credit Card Journal',
        help='If set, this payment term triggers automatic credit card payment with the selected journal.'
    )
