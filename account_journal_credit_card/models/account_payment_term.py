from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    credit_card_journal_id = fields.Many2one(
        'account.journal',
        string="Credit Card Journal",
        domain=[('is_credit_card', '=', True)],
        ondelete='set null',
    )

    _sql_constraints = [
        (
            'unique_credit_card_journal',
            'UNIQUE(credit_card_journal_id)',
            'Each credit card journal can only be assigned to one payment term.'
        )
    ]

    @api.model
    def create_credit_card_payment_term(self, journal):
        if not journal or not journal.is_credit_card:
            return None

        existing_term = self.search(
            [('credit_card_journal_id', '=', journal.id)], limit=1)
        if existing_term:
            return existing_term

        term = self.create({
            'name': f'{journal.name} Credit Card Payment Term',
            'credit_card_journal_id': journal.id,
            'note': 'Auto-created for credit card usage',
        })
        return term
