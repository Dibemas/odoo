import io
import csv
import base64
from odoo import models, fields, api, _
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountJournalCreditCardImportWizard(models.TransientModel):
    _name = 'account.journal.credit.card.import.wizard'
    _description = 'Credit Card CSV Import Wizard'

    upload_file = fields.Binary("CSV File", required=True)
    filename = fields.Char("Filename")
    line_ids = fields.One2many(
        'account.journal.credit.card.import.line', 'wizard_id', string="Parsed Lines")

    def action_parse_file(self):
        if not self.upload_file:
            raise UserError("Please upload a CSV file.")

        decoded_file = base64.b64decode(self.upload_file)
        file_stream = io.StringIO(decoded_file.decode("utf-8"))
        reader = csv.DictReader(file_stream)

        lines = []
        for row in reader:
            amount = float(row.get("Credit", 0.0))
            description = row.get("Description")

            match = self.env['account.move.line'].search([
                ('account_id.code', '=', '550003'),
                ('credit', '=', amount),
                ('reconciled', '=', False)
            ], limit=1)

            lines.append((0, 0, {
                'amount': amount,
                'description': description,
                'match_booking_id': match.id if match else False,
            }))

        self.line_ids = [(5, 0, 0)] + lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.journal.credit.card.import.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new'
        }


class AccountJournalCreditCardImportLine(models.TransientModel):
    _name = 'account.journal.credit.card.import.line'
    _description = 'Credit Card CSV Import Line'

    wizard_id = fields.Many2one('account.journal.credit.card.import.wizard')
    amount = fields.Float()
    description = fields.Char()
    match_booking_id = fields.Many2one(
        'account.move.line')
    partner_id = fields.Many2one(
        related='match_booking_id.partner_id', readonly=True)
    invoice_id = fields.Many2one(
        related='match_booking_id.move_id', readonly=True)

    @api.depends('match_booking_id')
    def _compute_related_fields(self):
        for line in self:
            line.partner_id = line.match_booking_id.partner_id
            line.invoice_id = line.match_booking_id.move_id
