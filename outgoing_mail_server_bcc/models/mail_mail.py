from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class MailMail(models.Model):
    _inherit = 'mail.mail'

    is_bcc_copy_sent = fields.Boolean(
        string='BCC Copy Sent',
        default=False,
        copy=False
    )

    is_bcc_copy = fields.Boolean(
        string='Is BCC Copy',
        default=False,
        readonly=True,
        copy=False
    )

    bcc_copy_ids = fields.One2many(
        'mail.mail',
        'bcc_copy_of_id',
        string='BCC Copies',
        readonly=True,
    )

    bcc_copy_of_id = fields.Many2one(
        'mail.mail',
        string='Original Mail',
        readonly=True,
        ondelete='cascade',
    )

    def _send(self, auto_commit=False, raise_exception=False, smtp_session=None, alias_domain_id=None, mail_server=None, post_send_callback=None,):
        result = super()._send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            smtp_session=smtp_session,
            alias_domain_id=alias_domain_id,
            mail_server=mail_server,
            post_send_callback=post_send_callback,
        )

        for mail in self:
            if not mail.is_bcc_copy_sent and mail.mail_server_id and mail.mail_server_id.bcc_active and mail.mail_server_id.bcc_email:
                if mail.email_to != mail.mail_server_id.bcc_email:
                    mail_copy = mail.copy({
                        'email_to': mail.mail_server_id.bcc_email,
                        'email_cc': False,
                        'partner_ids': [(6, 0, [])],
                        'recipient_ids': [(6, 0, [])],
                        'is_bcc_copy': True,
                        'bcc_copy_of_id': mail.id,
                    })
                    try:
                        mail_copy._send(
                            auto_commit=True,
                            smtp_session=smtp_session,
                            alias_domain_id=alias_domain_id,
                            mail_server=mail_server,
                            post_send_callback=post_send_callback,
                        )
                    except Exception as e:
                        _logger.error(
                            "BCC copy send failed for mail %s: %s", mail.id, e)
                    mail.is_bcc_copy_sent = True

        return result
