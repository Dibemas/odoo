from odoo import api, fields, models, _


class MailMail(models.Model):
    _inherit = 'mail.mail'

    is_bcc_copy_sent = fields.Boolean(string='BCC Copy Sent', default=False)

    @api.model
    def send(self, auto_commit=False, raise_exception=False):
        result = super(MailMail, self).send(
            auto_commit=auto_commit, raise_exception=raise_exception)

        for mail in self:
            # Check if server has BCC enabled
            if mail.mail_server_id and mail.mail_server_id.bcc_active and mail.mail_server_id.bcc_email:
                bcc_email = mail.mail_server_id.bcc_email

                if mail.email_to != bcc_email and not mail.is_bcc_copy_sent:
                    mail_copy = mail.copy({
                        'email_to': bcc_email,
                        'email_cc': False,
                        'partner_ids': False,
                        'recipient_ids': False,
                    })
                    mail_copy._send(auto_commit=True)
                    mail.write({'is_bcc_copy_sent': True})

        return result
