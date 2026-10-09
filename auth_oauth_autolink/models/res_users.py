import logging

from odoo import api, models
from odoo.http import request

_logger = logging.getLogger(__name__)

PARAM_DOMAINS = 'auth_oauth_autolink.allowed_domains'
PARAM_SKIP_MFA = 'auth_oauth_autolink.skip_mfa'
TRUTHY = ('1', 'true', 'True', 'yes')

# Session key recording how the *current* session was authenticated. Written on
# every credential check so it can never go stale, read back by
# _should_alert_new_device, which runs later in the same request but has no
# other way of knowing which method was used.
SESSION_OAUTH_LOGIN = 'auth_oauth_autolink_oauth_login'

# Claims that may carry the user's address, in order of preference. Microsoft's
# OIDC userinfo endpoint returns 'email'; the others appear depending on the
# provider, the scopes granted, and whether a data_endpoint is configured.
EMAIL_CLAIMS = ('email', 'preferred_username', 'upn', 'unique_name', 'mail')


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # Sign-in
    # ------------------------------------------------------------------

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        """Link an existing user to this provider on first login.

        Runs *before* the standard flow rather than as a fallback after it: the
        parent method reacts to a failed lookup by attempting a signup, and on
        some configurations that could create a second account for someone who
        already has one. Establishing the link first means the parent simply
        finds the user and proceeds normally.
        """
        oauth_uid = validation.get('user_id')
        if oauth_uid:
            already_linked = self.sudo().search_count([
                ('oauth_uid', '=', oauth_uid),
                ('oauth_provider_id', '=', provider),
            ])
            if not already_linked:
                self._autolink_link_user(provider, validation, oauth_uid)

        return super()._auth_oauth_signin(provider, validation, params)

    # ------------------------------------------------------------------
    # Second factor
    # ------------------------------------------------------------------

    def _check_credentials(self, credential, env):
        """Let Microsoft be the second factor.

        Entra already enforces MFA on these accounts, so Odoo's own step is a
        second prompt for a factor the user has just satisfied. Odoo 18 provides
        the switch directly: ``_check_credentials`` returns an ``auth_info``
        dict whose ``mfa`` key is read by ``Session.authenticate``, which
        finalises the session on the spot when it reads ``skip``. That check
        short-circuits before ``_mfa_url()``, so it covers the authenticator app
        (``auth_totp``) and the email code that ``auth_totp.policy`` forces on
        internal users (``auth_totp_mail_enforce``) alike.

        Only logins that actually went through OAuth are affected - the
        break-glass administrator and the accountant authenticate with a
        password and keep their Odoo second factor, which is the point: those
        accounts are the ones Entra is *not* protecting.
        """
        auth_info = super()._check_credentials(credential, env)

        is_oauth = auth_info.get('auth_method') == 'oauth'
        if request and getattr(request, 'session', None) is not None:
            request.session[SESSION_OAUTH_LOGIN] = is_oauth

        if is_oauth and self._autolink_skip_mfa_active():
            _logger.info(
                "SSO: skipping Odoo second factor for %s (id %s) - MFA was "
                "handled by the identity provider",
                self.login, self.id,
            )
            return dict(auth_info, mfa='skip')

        return auth_info

    def _should_alert_new_device(self):
        """Suppress the new-device alert on SSO logins.

        ``auth_totp`` treats "second factor enabled but no trusted-device
        cookie" as a new device and mails the user. That cookie is only ever set
        by completing the second-factor step, which SSO users now skip, so
        without this every single Microsoft login would generate an alert. Entra
        sends its own sign-in notifications for these accounts; an alert on
        every login is noise that only teaches people to ignore it.

        Password logins are untouched and still alert normally.
        """
        if request and getattr(request, 'session', None) is not None:
            if request.session.get(SESSION_OAUTH_LOGIN) and self._autolink_skip_mfa_active():
                return False
        return super()._should_alert_new_device()

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------

    def _autolink_link_user(self, provider, validation, oauth_uid):
        """Find the one active internal user matching the verified email, and link it."""
        email = self._autolink_email_from_validation(validation)
        if not email:
            _logger.info("SSO auto-link: no usable email claim in the validation response")
            return

        if not self._autolink_domain_allowed(email):
            _logger.warning("SSO auto-link refused: %s is outside the allowed domains", email)
            return

        candidates = self.sudo().search([
            ('login', '=ilike', email),
            ('active', '=', True),
            ('share', '=', False),          # internal users only
            ('oauth_uid', 'in', (False, '')),  # never touch an existing link
        ])

        if len(candidates) != 1:
            _logger.warning(
                "SSO auto-link refused for %s: %s matching linkable users (need exactly 1)",
                email, len(candidates),
            )
            return

        candidates.write({'oauth_uid': oauth_uid, 'oauth_provider_id': provider})
        _logger.info(
            "SSO auto-link: %s (uid %s) linked to provider %s on first login",
            email, candidates.id, provider,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _autolink_email_from_validation(self, validation):
        for claim in EMAIL_CLAIMS:
            value = validation.get(claim)
            if value and '@' in value:
                return value.strip().lower()
        return None

    def _autolink_skip_mfa_active(self):
        """Kill switch for the second-factor skip.

        Ships enabled - installing this module is the deliberate act. Setting it
        to 0 restores Odoo's own second factor on SSO logins immediately, which
        is what to reach for if the Entra MFA policy is ever relaxed.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(PARAM_SKIP_MFA, '1')
        return str(param).strip() in TRUTHY

    def _autolink_domain_allowed(self, email):
        raw = self.env['ir.config_parameter'].sudo().get_param(PARAM_DOMAINS, '')
        domains = [d.strip().lower() for d in raw.split(',') if d.strip()]
        if not domains:
            # No allowlist configured: rely on the identity provider alone. Only
            # appropriate when the Entra app registration is single-tenant.
            return True
        return any(email.endswith('@' + d) for d in domains)
