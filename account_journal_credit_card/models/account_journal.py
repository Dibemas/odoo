from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    is_credit_card = fields.Boolean(
        string="Credit Card Journal", help="Indicates this journal is used for credit card payments.")

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
    def action_add_credit_card(self):
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
                'default_filename': '',
            }
        }
