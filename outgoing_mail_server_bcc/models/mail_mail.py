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
            if mail.is_bcc_copy_sent:
                continue

            # Determine which mail server will actually be used
            actual_server = mail.mail_server_id or self.env['ir.mail_server'].sudo().search(
                [('active', '=', True)],
                order='sequence asc',
                limit=1
            )

            if not actual_server:
                _logger.warning(
                    "No active outgoing server found for mail %s", mail.id)
                continue

            if actual_server.bcc_active and actual_server.bcc_email and mail.email_to != actual_server.bcc_email:
                try:
                    mail_copy = mail.copy({
                        'email_to': actual_server.bcc_email,
                        'email_cc': False,
                        'partner_ids': [(6, 0, [])],
                        'recipient_ids': [(6, 0, [])],
                        'is_bcc_copy': True,
                        'bcc_copy_of_id': mail.id,
                        'mail_server_id': actual_server.id,
                    })

                    mail_copy._send(
                        auto_commit=True,
                        smtp_session=smtp_session,
                        alias_domain_id=alias_domain_id,
                        mail_server=actual_server,
                        post_send_callback=post_send_callback,
                    )

                    # Mark original as having sent a BCC
                    mail.is_bcc_copy_sent = True
                    _logger.info(
                        "BCC copy created for mail %s -> %s", mail.id, mail_copy.id)

                except Exception as e:
                    _logger.error(
                        "Failed to send BCC copy for mail %s: %s", mail.id, e)

        return result
