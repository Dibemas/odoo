import io
import csv
import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
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

    move_id = fields.Many2one('account.move', string="Journal Entry")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        journal_id = self.env.context.get('default_journal_id')
        if journal_id:
            res['journal_id'] = journal_id
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
        header_map = self._build_translation_header_map([
            'periode', 'date', 'description', 'amount', 'amount_eur', 'currency', 'rate'
        ])

        account = None
        move_lines_vals = []

        _logger.info("========== Parsed CSV Lines ==========")

        rows = list(reader)

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
            periode = normalized.get('periode')

            try:
                description = normalized.get('description', '')
                date = self._parse_date(normalized.get('date', ''))
                currency = (normalized.get('currency') or 'EUR').upper()
                rate = self._parse_number(normalized.get(
                    'rate') or '1', decimal_sep, thousand_sep)

                amount_eur = normalized.get('amount_eur')
                raw_amount = normalized.get('amount')

                if amount_eur and raw_amount:
                    # Parse amount in company currency (EUR)
                    amount = self._parse_number(
                        amount_eur, decimal_sep, thousand_sep)

                    # Parse amount in transaction currency
                    amount_currency = round(
                        self._parse_number(
                            raw_amount, decimal_sep, thousand_sep), 2 if rate == 1 else 4
                    )
                else:
                    raise UserError(
                        _("Missing amount or raw_amount in row: %s") % row)

                debit = -amount if amount > 0 else 0.0
                credit = amount if amount < 0 else 0.0
                currency_id = self.env['res.currency'].search(
                    [('name', '=', currency)], limit=1).id

                payment_move, linked_bills, partner = self.env['account.move.line']._find_matching_payment(
                    date, amount_currency, amount, currency_id)

                payment_account = self._get_payment_account(payment_move)

                account = payment_account if payment_account else None

                if not payment_account:
                    raise UserError(
                        _("No account found from payment or journal."))

                currency_code = currency or 'EUR'
                # This will ensure a currency is given in case the field is empty
                currency_id = self._check_currency_available(currency_code)

                line_val = {
                    'name': description,
                    'partner_id': partner.id if partner else False,
                    'date': date,
                    'date_maturity': date,
                    'account_id': account.id,
                    'amount_currency': -amount_currency,
                    'debit': debit,
                    'credit': credit,
                    'currency_id': currency_id,
                    'linked_payment_id': payment_move.id if payment_move else False,
                    'linked_bill_id': linked_bills[0].id if linked_bills else False,
                }

                move_lines_vals.append((0, 0, line_val))
                _logger.info("Imported line: %s", line_val)

            except Exception as e:
                _logger.error("Failed to parse row: %s\nError: %s", row, e)
                raise UserError(
                    _("CSV Parsing Error in row:\n%s\n\n%s") % (row, str(e)))

        # Create the journal entry
        journal = self.journal_id
        ref = periode or "Imported from Credit Card"

        if not journal:
            raise UserError(_("No general journal found."))

        if not move_lines_vals:
            raise UserError(_("No valid lines to import from the CSV."))

        # Ensure entry is balanced
        move_lines_vals = self._add_balancing_line_if_needed(
            move_lines_vals, journal, ref, account)

        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'line_ids': move_lines_vals,
            'ref': ref,
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

    def _build_translation_header_map(self, field_names):
        header_map = {}

        # Defensive: ensure model is loaded
        if 'ir.translation' not in self.env.registry.models:
            _logger.warning(
                "Translation model not found. Using fallback header mapping.")
            return self._static_header_map()

        IrTranslation = self.env['ir.translation']
        IrLang = self.env['res.lang']

        # Get all active languages from system
        all_languages = IrLang.search([('active', '=', True)]).mapped('code')

        for field in field_names:
            label = field.replace('_', ' ').capitalize()

            # Add default English-style label
            header_map[label] = field

            # Add all translations for this label across all active languages
            translations = IrTranslation.search([
                ('name', 'like', 'account.journal.credit.card.import.wizard,%'),
                ('type', '=', 'model'),
                ('src', '=', label),
                ('lang', 'in', all_languages),
                ('value', '!=', ''),
            ])

            for trans in translations:
                translated = trans.value.strip()
                if translated:
                    header_map[translated] = field

        # Manual case
        header_map['Bedrag (EUR)'] = 'amount_eur'

        return header_map

    def _static_header_map(self):
        return {
            'Periode': 'periode',
            'Period': 'periode',
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
        try:
            # Try European format: DD/MM/YYYY
            return datetime.strptime(date_str.strip(), '%d/%m/%Y').date().isoformat()
        except ValueError:
            # If already ISO format or empty, pass it through (or handle as needed)
            return date_str

    def _get_payment_account(self, payment_move):
        """Return account from payment move or journal fallback."""
        if payment_move and payment_move.line_ids:
            return payment_move.line_ids[0].account_id
        return self.journal_id.default_account_id

    def _add_balancing_line_if_needed(self, move_lines_vals, journal, ref, account):
        total_debit = sum(line[2]['debit'] for line in move_lines_vals)
        total_credit = sum(line[2]['credit'] for line in move_lines_vals)
        diff = round(total_debit - total_credit, 2)

        if diff == 0.0:
            return move_lines_vals

        # Check if foreign currency involved → delegate
        # if self._has_foreign_currency(move_lines_vals):
        #     return self._add_currency_diff_line(move_lines_vals, diff, journal, ref)

        debit = diff if diff < 0 else 0.0
        credit = diff if diff > 0 else 0.0
        balancing_line = {
            'name': f"{journal.name} - {ref} balancing line",
            'account_id': account.id,
            'debit': debit,
            'credit': credit,
            'date': fields.Date.today(),
            'date_maturity': fields.Date.today(),
            'currency_id': self.env.company.currency_id.id,
            'amount_currency': -debit if debit else -credit,
        }
        move_lines_vals.append((0, 0, balancing_line))
        return move_lines_vals

    def _has_foreign_currency(self, move_lines_vals):
        company_currency = self.env.company.currency_id.id
        return any(
            line[2].get(
                'currency_id') and line[2]['currency_id'] != company_currency
            for line in move_lines_vals
        )

    def _add_currency_diff_line(self, move_lines_vals, diff, journal, ref):
        # TODO: Should it be read from journal settings instead?
        if diff > 0:
            balancing_account = self.env.company.income_currency_exchange_account_id
        else:
            balancing_account = self.env.company.expense_currency_exchange_account_id

        debit = diff if diff < 0 else 0.0
        credit = diff if diff > 0 else 0.0
        balancing_line = {
            'name': f"{journal.name} - {ref} FX difference",
            'account_id': balancing_account.id,
            'debit': debit,
            'credit': credit,
            'date': fields.Date.today(),
            'date_maturity': fields.Date.today(),
            'currency_id': self.env.company.currency_id.id,
            'amount_currency': -debit if debit else -credit,
        }
        move_lines_vals.append((0, 0, balancing_line))
        return move_lines_vals

    def _check_currency_available(self, currency_code):
        """Ensure a currency exists and is active. 
        If missing, raise an error; if inactive, activate it."""
        if not currency_code:
            raise UserError(_("No currency code provided."))

        currency_code = currency_code.upper()
        currency_obj = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', currency_code)], limit=1
        )

        if not currency_obj:
            raise UserError(
                _("Currency '%s' is not available in the system. Please create it before importing.")
                % currency_code
            )

        if not currency_obj.active:
            currency_obj.write({'active': True})

        return currency_obj.id
