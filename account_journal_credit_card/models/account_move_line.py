from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, datetime
from odoo.tools.float_utils import float_compare
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


def _build_payment_search_domain(amount, trx_date, currency_id, tolerance=0.05, days_tolerance=0):
    base_domain = [
        ('move_type', '=', 'entry'),
        ('state', 'in', ['posted', 'in_progress']),
        ('journal_id.type', 'in', ['bank', 'cash']),
        ('line_ids.currency_id', '=', currency_id),
        ('line_ids.amount_currency', '>=', amount - tolerance),
        ('line_ids.amount_currency', '<=', amount + tolerance),
        ('date', '>=', trx_date - relativedelta(days=days_tolerance)),
        ('date', '<=', trx_date + relativedelta(days=days_tolerance)),
    ]
    return base_domain


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    linked_bill_id = fields.Many2one(
        'account.move',
        string="Linked Bill",
        domain="[('move_type', '=', 'in_invoice'), ('payment_state', '!=', 'paid')]"
    )

    linked_payment_id = fields.Many2one(
        'account.move',
        string="Linked Payment",
        domain="""
            [('move_type', '=', 'entry'),
            ('journal_id.type', 'in', ['bank', 'cash']),
            ('state', '=', 'posted')]
        """
    )

    @api.onchange('linked_payment_id')
    def _onchange_linked_payment_id(self):
        for line in self:
            if line.linked_payment_id:
                payment = line.linked_payment_id
                if not payment:
                    line.linked_bill_id = False
                    line.partner_id = False
                    continue

                bills, partner = self._get_bills_and_partner_from_payment(
                    payment)
                line.linked_bill_id = bills[0].id if bills else False
                line.partner_id = partner.id if partner else False

    def _find_matching_payment(self, date, amount, currency_id):
        """Match payments by amount in currency and date, with ±2 day tolerance."""
        AccountMove = self.env['account.move']

        trx_date = fields.Date.from_string(
            date) if isinstance(date, str) else date

        # First attempt: exact date
        domain = _build_payment_search_domain(
            amount, trx_date, currency_id, days_tolerance=0)
        payments = AccountMove.search(domain, limit=1)

        # Second attempt: ±2 days
        if not payments:
            domain = _build_payment_search_domain(
                amount, trx_date, currency_id, days_tolerance=2)
            payments = AccountMove.search(domain, limit=1)

        if not payments:
            return None, None, None

        payment = payments[0]
        bills, partner = self._get_bills_and_partner_from_payment(payment)
        return payment, bills, partner

    def _get_bills_and_partner_from_payment(self, payment):
        """Extract unpaid bills and partner from a payment move."""
        if not payment:
            return None, None

        debit_moves = payment.line_ids.mapped(
            'matched_debit_ids.debit_move_id.move_id')
        credit_moves = payment.line_ids.mapped(
            'matched_credit_ids.credit_move_id.move_id')
        payable_moves = debit_moves | credit_moves

        bills = payable_moves.filtered(
            lambda m: m.move_type == 'in_invoice' and m.payment_state != 'paid'
        )

        # If nothing found, try fetching via reconciled_bill_ids
        if not bills:
            bills = payment.origin_payment_id.reconciled_bill_ids
        partner = bills[0].partner_id if bills else payment.partner_id
        return bills, partner

    def _auto_reconcile_credit_card_journal_entries(self):
        self.ensure_one()

        if not self.linked_payment_id:
            return

        move_line = self
        payment_move = self.linked_payment_id

        payment_line = payment_move.line_ids.filtered(
            lambda l: l.account_id == move_line.account_id and not l.reconciled
        )

        if payment_line and not move_line.reconciled:
            (move_line + payment_line[0]).reconcile()
