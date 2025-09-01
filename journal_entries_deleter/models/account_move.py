from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_master_delete_entries(self):
        for invoice in self:
            invoice.sudo().write({'state': 'draft'})
            try:
                invoice.sudo().unlink()
                _logger.info(f"Successfully deleted invoice {invoice.id}")
            except Exception as e:
                _logger.error(f"Failed to delete invoice {invoice.id}: {e}")
