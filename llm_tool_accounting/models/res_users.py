from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    llm_company_id = fields.Many2one(
        'res.company',
        string="LLM Session Company",
        copy=False,
        help="Company that every LLM/MCP tool call of this user is locked to. "
             "Set and cleared by the accounting_select_company and "
             "accounting_end_session tools.",
    )

    @api.constrains('llm_company_id', 'company_ids')
    def _check_llm_company_id(self):
        for user in self:
            if user.llm_company_id and user.llm_company_id not in user.company_ids:
                raise ValidationError(_(
                    "%(user)s has no access to %(company)s.",
                    user=user.name, company=user.llm_company_id.name,
                ))
