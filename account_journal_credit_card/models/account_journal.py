from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging


class AccountJournal(models.Model):
    _inherit = 'account.journal'
