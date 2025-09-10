from odoo import api, fields, models, _


class MailMail(models.Model):
    _inherit = 'mail.mail'

    is_bcc_copy_sent = fields.Boolean(string='BCC Copy Sent', default=False)

    def _send(self, auto_commit=False, raise_exception=False):
        result = super()._send(auto_commit=auto_commit, raise_exception=raise_exception)

        for mail in self:
            if (
                mail.mail_server_id
                and mail.mail_server_id.bcc_active
                and mail.mail_server_id.bcc_email
                and mail.email_to != mail.mail_server_id.bcc_email
                and not mail.is_bcc_copy_sent
            ):
                mail_copy = mail.copy({
                    'email_to': mail.mail_server_id.bcc_email,
                    'email_cc': False,
                    'partner_ids': False,
                    'recipient_ids': False,
                })
                super(MailMail, mail_copy)._send(auto_commit=True)
                mail.is_bcc_copy_sent = True

        return result
