from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    is_credit_card = fields.Boolean(
        string="Credit Card Journal", help="Indicates this journal is used for credit card payments.")

    credit_card_payment_term_id = fields.One2many(
        'account.payment.term',
        'credit_card_journal_id',
        string="Related Payment Terms"
    )

    def open_statement_import_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Credit Card Statement',
            'res_model': 'account.bank.statement.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_journal_id': self.id,
            },
        }

    @api.model
    def action_add_credit_card_jornal(self):
        """Open the credit card journal form with prefilled values."""
        company_id = self.env.company.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Credit Card',
            'res_model': 'account.journal',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_journal_form').id,
            'target': 'new',
            'context': {
                    'default_type': 'cash',
                    'default_name': 'Credit Card',
                    'default_code': 'CCARD',
                    'default_company_id': company_id,
                    'default_is_credit_card': True,
                    'default_show_on_dashboard': True,
                    'default_update_posted': True,
            },
        }

    def action_open_credit_card_import_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Credit Card Statement'),
            'res_model': 'account.journal.credit.card.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_journal_id': self.id,
                'default_filename': '',
            }
        }

    def open_action(self):
        self.ensure_one()
        if self.is_credit_card:
            payment_moves = self.env['account.payment'].search(
                [('journal_id', '=', self.id)]).mapped('move_id').ids
            return {
                'name': 'Credit Card Transactions',
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'list,form',
                'domain': ['|', ('journal_id', '=', self.id), ('id', 'in', payment_moves)],
                'context': {'default_journal_id': self.id},
            }
        return super().open_action()

    @api.model_create_multi
    def create(self, vals):
        journals = super().create(vals)
        for journal in journals:
            if journal.is_credit_card:
                self.env['account.payment.term'].create_credit_card_payment_term(
                    journal)
        return journals

    def write(self, vals):
        res = super().write(vals)
        for journal in self:
            if 'is_credit_card' in vals:
                journal._sync_credit_card_payment_term()
        return res

    def _sync_credit_card_payment_term(self):
        """Ensure correct link/unlink between journal and credit card payment term."""
        self.ensure_one()

        PaymentTerm = self.env['account.payment.term']

        if self.is_credit_card:
            # First, look for an existing linked term
            existing_term = PaymentTerm.search(
                [('credit_card_journal_id', '=', self.id)], limit=1)

            # Or try to reuse a previously unlinked one (by name match)
            if not existing_term:
                existing_term = PaymentTerm.search([
                    ('credit_card_journal_id', '=', False),
                    ('name', 'ilike', self.name),
                ], limit=1)

            if existing_term and not existing_term.credit_card_journal_id:
                existing_term.write({'credit_card_journal_id': self.id})
            else:
                PaymentTerm.create_credit_card_payment_term(self)

        else:
            # If disabling credit card flag, unlink any existing terms
            terms = PaymentTerm.search(
                [('credit_card_journal_id', '=', self.id)])
            terms.write({'credit_card_journal_id': False})
