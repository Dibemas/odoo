from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, datetime
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _auto_register_credit_card_payment(self):
        for move in self:
            if move.move_type != 'in_invoice' or move.state != 'posted':
                continue

            payment_term = move.invoice_payment_term_id
            journal = payment_term.credit_card_journal_id

            if journal:
                self.env['account.payment'].create({
                    'payment_type': 'outbound',
                    'partner_type': 'supplier',
                    'partner_id': move.partner_id.id,
                    'amount': move.amount_total,
                    'payment_date': move.invoice_date or fields.Date.context_today(self),
                    'journal_id': journal.id,
                    'payment_method_line_id': journal.outbound_payment_method_line_ids[:1].id,
                    'ref': f'Auto CC Payment for {move.name}',
                    'destination_account_id': move.partner_id.property_account_payable_id.id,
                }).action_post()

    def action_post(self):
        res = super().action_post()
        self._auto_register_credit_card_payment()
        return res
