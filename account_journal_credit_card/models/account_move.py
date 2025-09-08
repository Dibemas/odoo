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
                            line.date_maturity, line.debit)
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
        for line in self.mapped('line_ids'):
            if line.linked_payment_id:
                line._auto_reconcile_credit_card_journal_entries()
        for move in self:
            if move.move_type == 'in_invoice':
                if move.invoice_payment_term_id.credit_card_journal_id:
                    move._auto_register_credit_card_payment()
        return res

    def _auto_register_credit_card_payment(self):
        self.ensure_one()

        term = self.invoice_payment_term_id
        journal = term.credit_card_journal_id if term else False

        if not journal or not self.amount_total or self.payment_state != 'not_paid':
            return  # No journal, no amount, or already paid

        method_line = journal.outbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(
                f"No outbound payment method configured on journal '{journal.display_name}'."
            )

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': self.amount_total,
            'journal_id': journal.id,
            'payment_method_line_id': method_line.id,
            'date': self.invoice_date or fields.Date.context_today(self),
            'memo': self.ref,
            'invoice_ids': [(4, self.id)],
        }

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        if payment:
            self.payment_state = 'in_payment'
