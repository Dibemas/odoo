import io
import csv
import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountJournalCreditCardImportWizard(models.TransientModel):
    _name = 'account.journal.credit.card.import.wizard'
    _description = 'Credit Card CSV Import Wizard'

    upload_file = fields.Binary("CSV File", required=True)
    filename = fields.Char("Filename")

    decimal_separator = fields.Selection([
        ('.', 'Dot (e.g. 1234.56)'),
        (',', 'Comma (e.g. 1234,56)')
    ], string="Decimal Separator", default=',', required=True)

    thousand_separator = fields.Selection([
        (',', 'Comma (e.g. 1,234.56)'),
        ('.', 'Dot (e.g. 1.234,56)'),
    ], string="Thousands Separator",  required=False,
        help="Leave empty to use a space (e.g. '1 234,56') as thousands separator."
    )

    journal_id = fields.Many2one(
        'account.journal',
        string="Credit Card Journal",
        required=True,
        domain=[('type', '=', 'cash')]
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_journal_id'):
            res['journal_id'] = self.env.context['default_journal_id']
        return res

    def action_import_csv(self):
        if not self.upload_file:
            raise UserError(_("Please upload a CSV file."))

        decimal_sep = self.decimal_separator
        thousand_sep = self.thousand_separator

        decoded_file = base64.b64decode(self.upload_file)
        file_stream = io.StringIO(decoded_file.decode("utf-8-sig"))

        # Detect delimiter automatically or enforce `;` if you prefer
        try:
            sample = file_stream.readline()
            file_stream.seek(0)
            delimiter = ';' if ';' in sample else ','
            reader = csv.DictReader(file_stream, delimiter=delimiter)
        except Exception as e:
            raise UserError(_("Failed to read CSV file: %s") % str(e))

        # Map multilingual headers to normalized field names
        header_map = {
            'Datum': 'date',
            'Date': 'date',
            'Omschrijving': 'description',
            'Description': 'description',
            'Bedrag': 'amount',
            'Amount': 'amount',
            'Bedrag (EUR)': 'amount_eur',
            'Munt': 'currency',
            'Currency': 'currency',
            'Koers': 'rate',
            'Rate': 'rate',
        }

        move_lines_vals = []

        _logger.info("========== Parsed CSV Lines ==========")

        rows = list(reader)  # convert to list to index last row

        for i, row in enumerate(rows):
            if not any(row.values()):
                continue

            normalized = {header_map.get(
                k.strip(), k.strip()): v for k, v in row.items()}

            amount_str = normalized.get(
                'amount_eur') or normalized.get('amount')
            if not amount_str:
                continue

            # Parse amount as float
            amount = self._parse_number(amount_str, decimal_sep, thousand_sep)

            if i == len(rows) - 1 and amount > 0:
                _logger.info("Skipping last row with positive amount: %s", row)
                continue

            try:
                description = normalized.get('description', '')
                date = self._parse_date(normalized.get('date', ''))
                currency = (normalized.get('currency') or 'EUR').upper()
                rate = self._parse_number(normalized.get(
                    'rate') or '1', decimal_sep, thousand_sep)

                amount_eur = normalized.get('amount_eur')
                raw_amount = normalized.get('amount')

                if amount_eur:
                    amount = self._parse_number(
                        amount_eur, decimal_sep, thousand_sep)
                elif raw_amount:
                    amount_val = self._parse_number(
                        raw_amount, decimal_sep, thousand_sep)
                    amount = round(amount_val / rate, 2)
                else:
                    raise UserError(
                        _("No valid amount found in row: %s") % row)

                debit = amount if amount > 0 else 0.0
                credit = -amount if amount < 0 else 0.0

                default_account = self.journal_id.default_account_id
                if not default_account:
                    raise UserError(
                        _("The selected journal has no 'Cash Account' configured."))

                line_val = {
                    'name': description,
                    'date': date,
                    'account_id': default_account.id,
                    'debit': debit,
                    'credit': credit,
                    'currency_id': self.env['res.currency'].search([('name', '=', currency)], limit=1).id,
                }

                move_lines_vals.append((0, 0, line_val))
                _logger.info("Imported line: %s", line_val)

            except Exception as e:
                _logger.error("Failed to parse row: %s\nError: %s", row, e)
                raise UserError(
                    _("CSV Parsing Error in row:\n%s\n\n%s") % (row, str(e)))

        # Create the journal entry
        journal = self.journal_id
        if not journal:
            raise UserError(_("No general journal found."))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'line_ids': move_lines_vals,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'target': 'current'
        }

    def _get_col(self, row, aliases):
        """Return first non-empty value from row for a list of possible aliases."""
        for alias in aliases:
            if alias in row and row[alias]:
                return row[alias]
        return None

    def _parse_number(self, value, decimal_sep, thousand_sep):
        """Convert string to float respecting thousands and decimal separators."""
        if not value:
            return 0.0
        if not thousand_sep:
            # User left the field empty = space is the separator
            value = value.replace(' ', '')
        else:
            value = value.replace(thousand_sep, '')
        value = value.replace(decimal_sep, '.')
        try:
            return float(value)
        except ValueError:
            raise UserError(_("Invalid number format: '%s'") % value)

    def _parse_date(self, date_str):
        """Parses date from CSV and returns it in YYYY-MM-DD format."""
        from datetime import datetime
        try:
            # Try European format: DD/MM/YYYY
            return datetime.strptime(date_str.strip(), '%d/%m/%Y').date().isoformat()
        except ValueError:
            # If already ISO format or empty, pass it through (or handle as needed)
            return date_str


# class AccountJournalCreditCardImportLine(models.TransientModel):
#     _name = 'account.journal.credit.card.import.line'
#     _description = 'Credit Card CSV Import Line'

#     wizard_id = fields.Many2one('account.journal.credit.card.import.wizard')
#     amount = fields.Float()
#     description = fields.Char()
#     match_booking_id = fields.Many2one(
#         'account.move.line')
#     partner_id = fields.Many2one(
#         related='match_booking_id.partner_id', readonly=True)
#     invoice_id = fields.Many2one(
#         related='match_booking_id.move_id', readonly=True)

#     @api.depends('match_booking_id')
#     def _compute_related_fields(self):
#         for line in self:
#             line.partner_id = line.match_booking_id.partner_id
#             line.invoice_id = line.match_booking_id.move_id
