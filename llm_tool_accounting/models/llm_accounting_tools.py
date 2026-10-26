from odoo import Command, _, models
from odoo.exceptions import UserError

from odoo.addons.llm_tool.decorators import llm_tool


class LLMAccountingTools(models.AbstractModel):
    _name = 'llm.accounting.tools'
    _description = "LLM Accounting Tools"

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    @llm_tool(idempotent_hint=True)
    def accounting_select_company(self, company_id: int) -> dict:
        """Lock this user's LLM tool calls to one company and return its accounting context.

        Call this before any accounting work. Until accounting_end_session is
        called, every tool call runs inside this company only: other companies'
        records are invisible, and new records belong to this company. The
        result lists the company's VAT regime, journals and fiscal year settings.
        """
        # sudo: under a company lock, record rules hide the user's other companies.
        user = self.env.user.sudo()
        company = self.env['res.company'].sudo().browse(company_id).exists()
        if not company or company not in user.company_ids:
            allowed = ", ".join(f"{c.id}: {c.name}" for c in user.company_ids)
            raise UserError(_("Unknown or unauthorised company %(id)s. Choose one of: %(allowed)s",
                              id=company_id, allowed=allowed))
        user.llm_company_id = company
        return self.with_context(allowed_company_ids=[company.id])._llm_accounting_company_info()

    @llm_tool(read_only_hint=True)
    def accounting_session_info(self) -> dict:
        """Return the company this session is locked to (or none) and the companies the user may choose from."""
        user = self.env.user.sudo()
        company = user.llm_company_id
        result = {
            'session_company': {'id': company.id, 'name': company.name} if company else None,
            'available_companies': [
                {'id': c.id, 'name': c.name, 'vat_regime': c.llm_vat_regime} for c in user.company_ids
            ],
        }
        if company:
            result.update(self.with_context(allowed_company_ids=[company.id])._llm_accounting_company_info())
        return result

    @llm_tool(idempotent_hint=True)
    def accounting_end_session(self) -> dict:
        """Release the company lock at the end of an accounting session."""
        self.env.user.sudo().llm_company_id = False
        return {'session_company': None, 'message': "Company lock released."}

    def _llm_accounting_check_distribution(self, distribution):
        """Validate {"<analytic account id>": percentage}; ids may be comma-joined across plans."""
        if not distribution:
            return {}
        company = self.env.company
        account_ids = {int(part) for key in distribution for part in str(key).split(',')}
        analytic_accounts = self.env['account.analytic.account'].browse(account_ids).exists()
        if len(analytic_accounts) != len(account_ids):
            raise UserError(_("Unknown analytic account in %(distribution)s.", distribution=distribution))
        foreign = analytic_accounts.filtered(lambda a: a.company_id and a.company_id != company)
        if foreign:
            raise UserError(_("Analytic account %(names)s belongs to another company.",
                              names=", ".join(foreign.mapped('display_name'))))
        return {str(key): float(value) for key, value in distribution.items()}

    def _llm_accounting_company_info(self):
        company = self.env.company
        journals = self.env['account.journal'].search([('company_id', '=', company.id)])
        return {
            'session_company': {'id': company.id, 'name': company.name},
            'vat_regime': company.llm_vat_regime,
            'analytic_required': company.llm_analytic_required,
            'analytic_accounts': [
                {'id': a.id, 'name': a.name, 'plan': a.plan_id.name}
                for a in self.env['account.analytic.account'].search(
                    [('company_id', 'in', [company.id, False])], order='plan_id, name')
            ],
            'vat': company.vat or None,
            'company_registry': company.company_registry or None,
            'currency': company.currency_id.name,
            'fiscal_year_end': f"{company.fiscalyear_last_day}/{company.fiscalyear_last_month}",
            'lock_dates': {
                'fiscalyear_lock_date': str(company.fiscalyear_lock_date or ''),
                'tax_lock_date': str(company.tax_lock_date or ''),
                'sale_lock_date': str(company.sale_lock_date or ''),
                'purchase_lock_date': str(company.purchase_lock_date or ''),
                'hard_lock_date': str(company.hard_lock_date or ''),
            },
            'journals': [
                {
                    'id': j.id,
                    'code': j.code,
                    'name': j.name,
                    'type': j.type,
                    'default_account': j.default_account_id.display_name or None,
                    'bank_account': j.bank_account_id.display_name or None,
                }
                for j in journals
            ],
        }

    # ------------------------------------------------------------------
    # Bank reconciliation
    # ------------------------------------------------------------------

    @llm_tool(destructive_hint=True)
    def accounting_reconcile_statement_line(
        self,
        statement_line_id: int,
        move_line_ids: list[int] | None = None,
        counterpart_account_id: int | None = None,
        counterpart_partner_id: int | None = None,
        counterpart_label: str | None = None,
        counterpart_tax_ids: list[int] | None = None,
        counterpart_analytic_distribution: dict[str, float] | None = None,
    ) -> dict:
        """Reconcile one bank or credit card statement line. Only call this after the user approved the match.

        - move_line_ids: open receivable/payable journal items to match (from posted invoices, bills or payments).
          A partial payment is allowed: the invoice stays partly open.
        - counterpart_account_id: account for the amount that is not matched by move_line_ids
          (e.g. bank costs, membership fees, an internal transfer account). Required when the
          matched items do not cover the whole statement line amount; omit it otherwise.
        - counterpart_partner_id / counterpart_label / counterpart_tax_ids: optional details of
          that counterpart line. Taxes are only allowed in a VAT-registered company.
        - counterpart_analytic_distribution: analytic distribution of that counterpart line, as
          {"<analytic account id>": percentage}, e.g. {"41": 100}. Required on income and expense
          accounts in a company that requires analytic accounting.

        Uses the same logic as Odoo's reconciliation screen. Everything is rolled back if the
        line cannot be fully balanced.
        """
        company = self.env.company
        st_line = self.env['account.bank.statement.line'].browse(statement_line_id).exists()
        if not st_line or st_line.company_id != company:
            raise UserError(_("Statement line %(id)s does not exist in %(company)s.",
                              id=statement_line_id, company=company.name))
        if st_line.is_reconciled:
            raise UserError(_("Statement line %(id)s is already reconciled.", id=statement_line_id))

        amls = self.env['account.move.line'].browse(move_line_ids or []).exists()
        if len(amls) != len(set(move_line_ids or [])):
            raise UserError(_("Some journal items do not exist: %(ids)s", ids=move_line_ids))
        for aml in amls:
            if aml.company_id != company:
                raise UserError(_("Journal item %(id)s belongs to another company.", id=aml.id))
            if aml.parent_state != 'posted' or aml.reconciled or not aml.account_id.reconcile:
                raise UserError(_(
                    "Journal item %(id)s (%(name)s) is not an open, posted, reconcilable item.",
                    id=aml.id, name=aml.move_id.display_name,
                ))

        account = self.env['account.account'].browse(counterpart_account_id or []).exists()
        if counterpart_account_id and (not account or company not in account.company_ids):
            raise UserError(_("Account %(id)s does not exist in %(company)s.", id=counterpart_account_id, company=company.name))
        partner = self.env['res.partner'].browse(counterpart_partner_id or []).exists()
        taxes = self.env['account.tax'].browse(counterpart_tax_ids or []).exists()
        if taxes and (company.llm_vat_regime != 'vat' and any(t.amount for t in taxes)):
            raise UserError(_("%(company)s is not VAT registered; no VAT on the counterpart line.", company=company.name))
        if taxes.filtered(lambda t: t.company_id != company):
            raise UserError(_("Some taxes belong to another company."))
        if not amls and not account:
            raise UserError(_("Give move_line_ids to match and/or a counterpart_account_id."))
        distribution = self._llm_accounting_check_distribution(counterpart_analytic_distribution)
        if (
            account
            and company.llm_analytic_required
            and account.internal_group in ('income', 'expense')
            and not self.env['llm.tool']._llm_accounting_distribution_complete(distribution)
        ):
            raise UserError(_(
                "%(company)s requires an analytic account on income and expenses: give "
                "counterpart_analytic_distribution for %(account)s.",
                company=company.name, account=account.display_name,
            ))

        with self.env.cr.savepoint():
            wizard = self.env['bank.rec.widget'].with_context(default_st_line_id=st_line.id).new({})
            if amls:
                wizard._action_add_new_amls(amls)
            balance_line = wizard.line_ids.filtered(lambda line: line.flag == 'auto_balance')
            if balance_line and not account:
                raise UserError(_(
                    "The matched items leave %(amount)s %(currency)s open on statement line %(id)s. "
                    "Give a counterpart_account_id for the difference, or match more items.",
                    amount=balance_line.amount_currency, currency=balance_line.currency_id.name, id=st_line.id,
                ))
            if account and not balance_line:
                raise UserError(_("The matched items already cover the full amount; leave counterpart_account_id empty."))
            if balance_line:
                wizard._js_action_mount_line_in_edit(balance_line.index)
                # The partner first: setting it switches the account to the partner's
                # receivable/payable account, which the explicit account then overrides.
                if partner:
                    balance_line.partner_id = partner
                    wizard._line_value_changed_partner_id(balance_line)
                balance_line.account_id = account
                wizard._line_value_changed_account_id(balance_line)
                if counterpart_label:
                    balance_line.name = counterpart_label
                    wizard._line_value_changed_name(balance_line)
                if taxes:
                    balance_line.tax_ids = [Command.set(taxes.ids)]
                    wizard._line_value_changed_tax_ids(balance_line)
                if distribution:
                    balance_line.analytic_distribution = distribution
                    wizard._line_value_changed_analytic_distribution(balance_line)
            if wizard.state != 'valid':
                raise UserError(_("Statement line %(id)s could not be balanced; nothing was changed.", id=st_line.id))
            wizard._action_validate()

        return {
            'statement_line_id': st_line.id,
            'reconciled': st_line.is_reconciled,
            'entry': st_line.move_id.display_name,
            'lines': [
                {
                    'account': line.account_id.display_name,
                    'partner': line.partner_id.display_name or None,
                    'label': line.name,
                    'analytic_distribution': line.analytic_distribution or None,
                    'debit': line.debit,
                    'credit': line.credit,
                    'matched_with': line.matched_debit_ids.debit_move_id.move_id.mapped('display_name')
                    + line.matched_credit_ids.credit_move_id.move_id.mapped('display_name'),
                }
                for line in st_line.move_id.line_ids
            ],
        }
