from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    llm_vat_regime = fields.Selection(
        selection=[
            ('vat', "VAT registered"),
            ('none', "Not VAT registered (e.g. small association)"),
            ('franchise', "VAT franchise for small enterprises (art. 56bis)"),
        ],
        string="VAT Regime",
        default='vat',
        required=True,
        help="Used by the LLM accounting tools. Outside 'VAT registered', no journal "
             "entry carrying VAT can be posted through the tools: purchases are booked "
             "at their full amount including VAT, and sales carry no VAT.",
    )
    llm_analytic_required = fields.Boolean(
        string="Analytic Required on Income and Expenses",
        help="Used by the LLM accounting tools. When set, every income or expense line must carry "
             "a complete analytic distribution before an entry is posted or a bank line is "
             "reconciled through the tools.",
    )
