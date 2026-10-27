from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account_accountant.tests.test_bank_rec_widget_common import TestBankRecWidgetCommon


@tagged('post_install', '-at_install')
class TestLLMToolAccounting(TestBankRecWidgetCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.company_data['company']
        cls.company_data_b = cls.setup_other_company(name="Vereniging zonder btw")
        cls.company_b = cls.company_data_b['company']
        cls.company_b.llm_vat_regime = 'none'

        cls.user = new_test_user(
            cls.env,
            login='llm_accountant',
            groups='base.group_user,account.group_account_manager',
            company_id=cls.company_a.id,
            company_ids=[Command.set((cls.company_a + cls.company_b).ids)],
        )

        Tool = cls.env['llm.tool']
        if not Tool.search_count([('decorator_model', '=', 'llm.accounting.tools')]):
            Tool._scan_tool_decorators()
            Tool._sync_tools_to_db()
        cls.retriever = cls.env.ref('llm_tool.llm_tool_odoo_record_retriever')
        cls.creator = cls.env.ref('llm_tool.llm_tool_odoo_record_creator')
        cls.unlinker = cls.env.ref('llm_tool.llm_tool_odoo_record_unlinker')
        cls.executor = cls.env.ref('llm_tool.llm_tool_odoo_model_method_executor')

        cls.bill_a = cls.init_invoice('in_invoice', partner=cls.partner_a, amounts=[100.0], company=cls.company_a)
        cls.bill_b = cls.init_invoice('in_invoice', partner=cls.partner_a, amounts=[50.0], company=cls.company_b)

    def _tool(self, method):
        return self.env['llm.tool'].search([
            ('decorator_model', '=', 'llm.accounting.tools'),
            ('decorator_method', '=', method),
        ])

    def _run(self, tool, **parameters):
        return tool.with_user(self.user).execute(parameters)

    def _select(self, company):
        return self._run(self._tool('accounting_select_company'), company_id=company.id)

    # ------------------------------------------------------------------
    # Company lock
    # ------------------------------------------------------------------

    def test_accounting_call_without_session_company_is_refused(self):
        with self.assertRaisesRegex(UserError, "accounting_select_company"):
            self._run(self.retriever, model='account.move', domain=[], fields=['name'])
        # Non-accounting models stay available, e.g. to look up a partner.
        self._run(self.retriever, model='res.partner', domain=[['id', '=', self.partner_a.id]], fields=['name'])

    def test_select_company_returns_context(self):
        info = self._select(self.company_b)
        self.assertEqual(info['session_company']['id'], self.company_b.id)
        self.assertEqual(info['vat_regime'], 'none')
        self.assertTrue(info['journals'])
        self.assertEqual(self.user.llm_company_id, self.company_b)

    def test_select_company_with_foreign_bank_account(self):
        # A bank journal of company B whose bank account is stored under company A
        # (inconsistent data, as found in production).
        bank_account = self.env['res.partner.bank'].create({
            'acc_number': 'BE61733076948817',
            'partner_id': self.company_b.partner_id.id,
        })
        journal = self.company_data_b['default_journal_bank']
        journal.bank_account_id = bank_account
        self.env.flush_all()
        self.env.cr.execute("UPDATE res_partner_bank SET company_id = %s WHERE id = %s",
                            (self.company_a.id, bank_account.id))
        self.env.invalidate_all()
        info = self._select(self.company_b)
        bank_journal = next(j for j in info['journals'] if j['id'] == journal.id)
        self.assertEqual(bank_journal['bank_account'], bank_account.display_name)
        self.assertEqual(len(info['warnings']), 1)
        self.assertIn(self.company_a.name, info['warnings'][0])
        self.assertEqual(self._run(self._tool('accounting_session_info'))['warnings'], info['warnings'])

    def test_reads_are_limited_to_session_company(self):
        self._select(self.company_a)
        moves = self._run(self.retriever, model='account.move', domain=[], fields=['company_id'], limit=1000)
        self.assertTrue(moves)
        self.assertEqual({m['company_id'][0] for m in moves}, {self.company_a.id})

        self._select(self.company_b)
        moves = self._run(self.retriever, model='account.move', domain=[], fields=['company_id'], limit=1000)
        self.assertEqual({m['company_id'][0] for m in moves}, {self.company_b.id})

    def test_new_records_belong_to_session_company(self):
        self._select(self.company_b)
        result = self._run(self.creator, model='account.move', fields={
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2019-01-01',
            'invoice_line_ids': [Command.create({'name': 'Zaalhuur', 'price_unit': 121.0, 'tax_ids': []})],
        })
        bill = self.env['account.move'].browse(result['id'])
        self.assertEqual(bill.company_id, self.company_b)
        self.assertEqual(bill.journal_id.company_id, self.company_b)

    def test_end_session_releases_lock(self):
        self._select(self.company_a)
        self._run(self._tool('accounting_end_session'))
        self.assertFalse(self.user.llm_company_id)
        with self.assertRaises(UserError):
            self._run(self.retriever, model='account.move', domain=[], fields=['name'])

    def test_cannot_select_unauthorised_company(self):
        company_c = self.setup_other_company(name="Elders")['company']
        with self.assertRaises(UserError):
            self._select(company_c)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def test_customer_invoice_is_never_posted(self):
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], company=self.company_a)
        self._select(self.company_a)
        with self.assertRaisesRegex(UserError, "never posted"):
            self._run(self.executor, model='account.move', method='action_post', record_ids=invoice.ids)
        self.assertEqual(invoice.state, 'draft')

    def test_supplier_bill_can_be_posted(self):
        self._select(self.company_a)
        self._run(self.executor, model='account.move', method='action_post', record_ids=self.bill_a.ids)
        self.assertEqual(self.bill_a.state, 'posted')

    def test_no_vat_company_refuses_taxed_bill(self):
        taxed = self.init_invoice(
            'in_invoice', partner=self.partner_a, amounts=[100.0], company=self.company_b,
            taxes=self.company_data_b['default_tax_purchase'],
        )
        self._select(self.company_b)
        with self.assertRaisesRegex(UserError, "not VAT registered"):
            self._run(self.executor, model='account.move', method='action_post', record_ids=taxed.ids)
        self.assertEqual(taxed.state, 'draft')

        self.bill_b.invoice_line_ids.tax_ids = [Command.clear()]
        self._run(self.executor, model='account.move', method='action_post', record_ids=self.bill_b.ids)
        self.assertEqual(self.bill_b.state, 'posted')

    def test_state_and_auto_post_cannot_be_written(self):
        self._select(self.company_a)
        with self.assertRaisesRegex(UserError, "state"):
            self._run(self.creator, model='account.move', fields={'move_type': 'entry', 'state': 'posted'})
        with self.assertRaisesRegex(UserError, "automatically"):
            self._run(self.creator, model='account.move', fields={'move_type': 'out_invoice', 'auto_post': 'at_date'})

    def test_orm_writes_deletes_and_private_methods_are_refused(self):
        self._select(self.company_a)
        with self.assertRaises(UserError):
            self._run(self.unlinker, model='account.move', domain=[['id', '=', self.bill_a.id]])
        with self.assertRaises(UserError):
            self._run(self.executor, model='account.move', method='write', record_ids=self.bill_a.ids,
                      kwargs={'vals': '{"ref": "x"}'})
        with self.assertRaises(UserError):
            self._run(self.executor, model='account.move', method='_post', record_ids=self.bill_a.ids,
                      allow_private=True)
        self.assertTrue(self.bill_a.exists())
        self.assertEqual(self.bill_a.state, 'draft')

    # ------------------------------------------------------------------
    # Bank reconciliation
    # ------------------------------------------------------------------

    def _receivable_line(self, amount, company_data=None):
        company_data = company_data or self.company_data
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount],
                                    company=company_data['company'], post=True)
        return invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')

    def test_reconcile_with_invoice(self):
        receivable = self._receivable_line(100.0)
        st_line = self._create_st_line(receivable.balance, partner_id=self.partner_a.id)
        self._select(self.company_a)
        result = self._run(self._tool('accounting_reconcile_statement_line'),
                           statement_line_id=st_line.id, move_line_ids=receivable.ids)
        self.assertTrue(result['reconciled'])
        self.assertTrue(receivable.reconciled)

    def test_reconcile_with_difference_requires_counterpart(self):
        receivable = self._receivable_line(100.0)
        st_line = self._create_st_line(receivable.balance - 2.5, partner_id=self.partner_a.id)
        self._select(self.company_a)
        tool = self._tool('accounting_reconcile_statement_line')
        # Without a counterpart the invoice is matched partially and the line balances.
        result = self._run(tool, statement_line_id=st_line.id, move_line_ids=receivable.ids)
        self.assertTrue(result['reconciled'])
        self.assertFalse(receivable.reconciled)

        st_line_2 = self._create_st_line(-12.10)
        with self.assertRaisesRegex(UserError, "counterpart"):
            self._run(tool, statement_line_id=st_line_2.id)
        expense = self.company_data['default_account_expense']
        result = self._run(tool, statement_line_id=st_line_2.id, counterpart_account_id=expense.id,
                           counterpart_label="Bankkosten")
        self.assertTrue(result['reconciled'])
        self.assertIn(expense, st_line_2.move_id.line_ids.account_id)
        self.assertIn("Bankkosten", st_line_2.move_id.line_ids.mapped('name'))

    def test_reconcile_other_company_line_is_refused(self):
        st_line_b = self._create_st_line(10.0, journal_id=self.company_data_b['default_journal_bank'].id)
        self._select(self.company_a)
        # Odoo's assertRaises takes a single exception class: the line is hidden by the
        # record rules (AccessError) or refused by the tool (UserError).
        try:
            self._run(self._tool('accounting_reconcile_statement_line'),
                      statement_line_id=st_line_b.id,
                      counterpart_account_id=self.company_data['default_account_revenue'].id)
        except (UserError, AccessError):
            pass
        else:
            self.fail("A statement line of another company was reconciled.")
        self.assertFalse(st_line_b.is_reconciled)

    def test_reconcile_no_vat_company_refuses_tax(self):
        st_line = self._create_st_line(-12.10, journal_id=self.company_data_b['default_journal_bank'].id)
        self._select(self.company_b)
        with self.assertRaisesRegex(UserError, "not VAT registered"):
            self._run(self._tool('accounting_reconcile_statement_line'),
                      statement_line_id=st_line.id,
                      counterpart_account_id=self.company_data_b['default_account_expense'].id,
                      counterpart_tax_ids=self.company_data_b['default_tax_purchase'].ids)

    # ------------------------------------------------------------------
    # Analytic accounting
    # ------------------------------------------------------------------

    def _analytic_account(self):
        plan = self.env['account.analytic.plan'].create({'name': "Jaarwerking"})
        return self.env['account.analytic.account'].create({
            'name': "26 - Lidgelden", 'plan_id': plan.id, 'company_id': self.company_a.id,
        })

    def test_analytic_required_on_post(self):
        analytic = self._analytic_account()
        self.company_a.llm_analytic_required = True
        self._select(self.company_a)
        with self.assertRaisesRegex(UserError, "analytic"):
            self._run(self.executor, model='account.move', method='action_post', record_ids=self.bill_a.ids)
        self.assertEqual(self.bill_a.state, 'draft')

        self.bill_a.invoice_line_ids.analytic_distribution = {str(analytic.id): 100.0}
        self._run(self.executor, model='account.move', method='action_post', record_ids=self.bill_a.ids)
        self.assertEqual(self.bill_a.state, 'posted')

    def test_reconcile_with_analytic_distribution(self):
        analytic = self._analytic_account()
        self.company_a.llm_analytic_required = True
        revenue = self.company_data['default_account_revenue']
        st_line = self._create_st_line(50.0, payment_ref="LIDGELD 2026")
        self._select(self.company_a)
        tool = self._tool('accounting_reconcile_statement_line')
        with self.assertRaisesRegex(UserError, "counterpart_analytic_distribution"):
            self._run(tool, statement_line_id=st_line.id, counterpart_account_id=revenue.id)
        self.assertFalse(st_line.is_reconciled)

        result = self._run(tool, statement_line_id=st_line.id, counterpart_account_id=revenue.id,
                           counterpart_label="Lidgeld 2026",
                           counterpart_analytic_distribution={str(analytic.id): 100.0})
        self.assertTrue(result['reconciled'])
        revenue_line = st_line.move_id.line_ids.filtered(lambda line: line.account_id == revenue)
        self.assertEqual(revenue_line.analytic_distribution, {str(analytic.id): 100.0})

    def test_reconcile_refuses_foreign_analytic_account(self):
        foreign = self.env['account.analytic.account'].create({
            'name': "Elders", 'plan_id': self.env['account.analytic.plan'].create({'name': "X"}).id,
            'company_id': self.company_b.id,
        })
        st_line = self._create_st_line(50.0)
        self._select(self.company_a)
        with self.assertRaisesRegex(UserError, "another company|Unknown"):
            self._run(self._tool('accounting_reconcile_statement_line'),
                      statement_line_id=st_line.id,
                      counterpart_account_id=self.company_data['default_account_revenue'].id,
                      counterpart_analytic_distribution={str(foreign.id): 100.0})
