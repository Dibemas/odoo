from odoo import api, fields, models, _


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    bcc_active = fields.Boolean(string="BCC", default=False)
    bcc_email = fields.Char(string="Email")
