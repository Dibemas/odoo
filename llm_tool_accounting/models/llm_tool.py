import json
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ACCOUNTING_MODEL_PREFIXES = ('account.', 'account_', 'bank.rec.')
CUSTOMER_MOVE_TYPES = ('out_invoice', 'out_refund', 'out_receipt')
# Public account.move methods that post or send a document.
POST_METHODS = ('action_post',)
SEND_METHODS = ('action_send_and_print', 'action_invoice_sent')
# Generic ORM writes that would bypass the record creator/updater guards.
ORM_WRITE_METHODS = ('create', 'write', 'unlink', 'copy', 'update')
# Tools of this module that must work before a company is chosen.
SESSION_TOOLS = ('accounting_select_company', 'accounting_end_session', 'accounting_session_info')


class LLMTool(models.Model):
    _inherit = 'llm.tool'

    def execute(self, parameters):
        company = self.env.user.sudo().llm_company_id
        self._llm_accounting_check_company_required(company, parameters)
        if not company:
            self._llm_accounting_guard(parameters)
            return super().execute(parameters)
        # Run the tool inside the session company only: record rules then hide
        # the other companies, and defaults and company-dependent fields
        # (account codes, partner accounts, payment terms) follow this company.
        tool = self.with_context(allowed_company_ids=[company.id])
        tool._llm_accounting_guard(parameters)
        return super(LLMTool, tool).execute(parameters)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _llm_accounting_target_model(self, parameters):
        if self.implementation == 'function':
            return self.decorator_model
        return parameters.get('model')

    def _llm_accounting_is_accounting_call(self, parameters):
        if self.implementation == 'function':
            return self.decorator_model == 'llm.accounting.tools' and self.decorator_method not in SESSION_TOOLS
        model = parameters.get('model') or ''
        return model.startswith(ACCOUNTING_MODEL_PREFIXES)

    def _llm_accounting_check_company_required(self, company, parameters):
        if company:
            return
        required = self.env['ir.config_parameter'].sudo().get_param('llm_tool_accounting.require_company', '1')
        if required not in ('0', 'False', 'false') and self._llm_accounting_is_accounting_call(parameters):
            raise UserError(_(
                "No accounting company selected for this session. "
                "Call accounting_select_company first."
            ))

    def _llm_accounting_guard(self, parameters):
        if self.implementation == 'function' or not self._llm_accounting_is_accounting_call(parameters):
            return
        model = parameters['model']
        if self.implementation == 'odoo_record_unlinker':
            raise UserError(_("Deleting %(model)s records through the LLM tools is not allowed.", model=model))
        if self.implementation in ('odoo_record_creator', 'odoo_record_updater'):
            values_list = []
            if parameters.get('fields'):
                values_list.append(parameters['fields'])
            if parameters.get('values'):
                values_list.append(parameters['values'])
            values_list.extend(parameters.get('records') or [])
            self._llm_accounting_check_values(model, values_list, parameters)
        if self.implementation == 'odoo_model_method_executor':
            self._llm_accounting_check_method(model, parameters)

    def _llm_accounting_check_values(self, model, values_list, parameters):
        if model.startswith(('account.move.send',)):
            raise UserError(_("Sending invoices through the LLM tools is not allowed."))
        if model != 'account.move':
            return
        for values in values_list:
            if not isinstance(values, dict):
                continue
            if 'state' in values:
                raise UserError(_(
                    "The state of a journal entry cannot be written directly; "
                    "post with action_post after approval."
                ))
            if values.get('auto_post') not in (None, False, 'no'):
                raise UserError(_("Journal entries cannot be set to post automatically through the LLM tools."))

    def _llm_accounting_check_method(self, model, parameters):
        method = parameters.get('method') or ''
        if method.startswith('_') or parameters.get('allow_private'):
            raise UserError(_("Private methods on %(model)s cannot be called through the LLM tools.", model=model))
        if method in ORM_WRITE_METHODS:
            raise UserError(_(
                "Use the record creator/updater tools instead of calling %(method)s on %(model)s.",
                method=method, model=model,
            ))
        if model.startswith('account.move.send'):
            raise UserError(_("Sending invoices through the LLM tools is not allowed."))
        if model != 'account.move' or method not in POST_METHODS + SEND_METHODS:
            return
        moves = self.env['account.move'].browse(self._llm_accounting_record_ids(parameters)).exists()
        customer_moves = moves.filtered(lambda m: m.move_type in CUSTOMER_MOVE_TYPES)
        if customer_moves:
            raise UserError(_(
                "Customer invoices and credit notes are never posted or sent through the LLM tools. "
                "Leave %(names)s in draft for a person to confirm.",
                names=", ".join(customer_moves.mapped('display_name')),
            ))
        if method in SEND_METHODS:
            raise UserError(_("Sending documents through the LLM tools is not allowed."))
        self._llm_accounting_check_no_vat(moves)
        self._llm_accounting_check_analytic(moves)

    def _llm_accounting_record_ids(self, parameters):
        record_ids = parameters.get('record_ids') or []
        if isinstance(record_ids, str):
            record_ids = json.loads(record_ids)
        return [int(rid) for rid in record_ids]

    def _llm_accounting_check_no_vat(self, moves):
        for move in moves:
            company = move.company_id
            if company.llm_vat_regime == 'vat':
                continue
            taxed_lines = move.line_ids.filtered(
                lambda line: any(tax.amount for tax in line.tax_ids)
                or (line.display_type == 'tax' and not company.currency_id.is_zero(line.balance))
            )
            if taxed_lines:
                raise UserError(_(
                    "%(company)s is not VAT registered, but %(move)s carries VAT on: %(lines)s. "
                    "Remove the taxes and book the full amount (VAT included) before posting.",
                    company=company.name,
                    move=move.display_name,
                    lines=", ".join(taxed_lines.mapped(lambda line: line.name or line.account_id.display_name)),
                ))

    def _llm_accounting_check_analytic(self, moves):
        for move in moves:
            if not move.company_id.llm_analytic_required:
                continue
            missing = move.line_ids.filtered(
                lambda line: line.account_id.internal_group in ('income', 'expense')
                and not self._llm_accounting_distribution_complete(line.analytic_distribution)
            )
            if missing:
                raise UserError(_(
                    "%(company)s requires an analytic account on every income and expense line, "
                    "but %(move)s has none (or less than 100 %%) on: %(lines)s.",
                    company=move.company_id.name,
                    move=move.display_name,
                    lines=", ".join(missing.mapped(lambda line: line.name or line.account_id.display_name)),
                ))

    @api.model
    def _llm_accounting_distribution_complete(self, distribution):
        return bool(distribution) and sum(distribution.values()) >= 99.99
