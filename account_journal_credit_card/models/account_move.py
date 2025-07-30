from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, datetime
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def refresh_journal_entry_lines(self):
        for journal_entry in self:
            for line in journal_entry.line_ids:
                if not line.linked_bill_id or not line.linked_payment_id:
                    if not line.date_maturity:
                        raise UserError(
                            f"Set a value on the due date for the line {line.name}")
                    else:
                        payment, bills, partner = line._find_matching_payment(
                            line.date_maturity, line.amount_currency)
                        if payment or bills or partner:
                            line_vals = {}
                            if payment:
                                line_vals['linked_payment_id'] = payment.id
                            if bills:
                                line_vals['linked_bill_id'] = bills[0].id
                            if partner:
                                line_vals['partner_id'] = partner.id
                            if line_vals:
                                line.write(line_vals)

    def action_post(self):
        res = super().action_post()
        self._auto_reconcile_credit_card_jornal_entries()
        return res

    def _auto_reconcile_credit_card_jornal_entries(self):
        for move in self:
            for line in move.line_ids:
                if line.linked_payment_id:
                    payment_move = line.linked_payment_id

                    # Get matching lines on both sides (same account, unreconciled)
                    move_line = line
                    payment_line = payment_move.line_ids.filtered(
                        lambda l: l.account_id == move_line.account_id and not l.reconciled
                    )

                    if payment_line and not move_line.reconciled:
                        lines_to_reconcile = move_line + payment_line[0]
                        lines_to_reconcile.reconcile()
