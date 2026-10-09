import logging

from odoo import fields, models
from odoo.exceptions import AccessDenied
from odoo.http import request

_logger = logging.getLogger(__name__)

ENFORCE_PARAM = 'auth_sso_enforce.active'
TRUTHY = ('1', 'true', 'True', 'yes')


class ResUsers(models.Model):
    _inherit = 'res.users'

    bypass_sso_enforcement = fields.Boolean(
        string="Allow Local Password Login (Bypass SSO)",
        default=False,
        help="When enabled, this user may authenticate with a local Odoo password "
             "instead of Microsoft SSO. Reserved for the break-glass administrator "
             "and external accounts such as the accountant. Leave disabled for all "
             "regular employees.",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sso_enforcement_active(self):
        """Global kill switch.

        Enforcement is opt-in so that installing or upgrading the module can
        never lock anyone out on its own. Flipping this parameter to 0 in the
        database is also the recovery path if Microsoft OAuth becomes
        unavailable and no bypass account is reachable.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(ENFORCE_PARAM, '0')
        return str(param).strip() in TRUTHY

    def _sso_is_enforced(self):
        """True when this specific user must use SSO."""
        if len(self) != 1:
            # Defensive: never enforce on an ambiguous recordset, since the
            # consequence of a false positive here is a locked-out user.
            return False
        if not self._sso_enforcement_active():
            return False
        return not self.sudo().bypass_sso_enforcement

    def _sso_is_session_recheck(self):
        """True when a password check comes from an already-authenticated session.

        Odoo reuses ``_check_credentials`` for two very different things: proving
        who you are at login, and re-confirming an existing session before a
        sensitive action (the ``res.users.identitycheck`` wizard, which guards
        API key creation among others).

        Blocking the second would mean SSO users could never generate an API
        key, which is exactly what the MCP integration needs. A re-check is
        recognisable because the session is already bound to this same user - no
        new access is being granted, so allowing the password here does not
        weaken the SSO requirement at the front door.
        """
        if not request:
            return False
        session = getattr(request, 'session', None)
        if not session:
            return False
        return bool(session.uid) and session.uid == self.env.uid

    # ------------------------------------------------------------------
    # Authentication overrides
    # ------------------------------------------------------------------

    def _check_credentials(self, credential, env):
        """Block interactive password authentication for SSO-enforced users.

        Only ``type == 'password'`` is refused. OAuth tokens fall through to
        ``auth_oauth``, and API keys are handled further down the chain in
        non-interactive contexts, so both keep working untouched.

        The message passed to AccessDenied matters: ``Home.web_login`` renders
        ``e.args[0]`` when the exception carries custom args, so raising with
        text here is what puts the explanation on the login page - no controller
        override needed.
        """
        if (
            credential.get('type') == 'password'
            and (env or {}).get('interactive', True)
            and self._sso_is_enforced()
            and not self._sso_is_session_recheck()
        ):
            _logger.info(
                "SSO enforcement: refused interactive password login for user %s (id %s)",
                self.login, self.id,
            )
            raise AccessDenied(self._sso_enforcement_message())
        return super()._check_credentials(credential, env)

    def _sso_enforcement_message(self):
        """The refusal text, in a language the user will actually read.

        ``Home.web_login`` translates its own "Wrong login/password" itself, in
        the request context, but renders a *custom* AccessDenied straight through
        ``e.args[0]`` - the string exactly as it was built here. Since
        ``_check_credentials`` runs as SUPERUSER with an empty context, a bare
        ``_()`` resolves to English, and the one message every enforced employee
        reads ends up in a different language from the page around it.

        The user's own language wins; the language the page was rendered in is
        the fallback, for an account that has never set one.
        """
        user = self.sudo()
        lang = user.lang or (request.env.lang if request else None) or self.env.lang
        return user.with_context(lang=lang).env._(
            "Single Sign-On (SSO) is enforced for your account. "
            "Please log in using the 'Log in with Microsoft' button."
        )

    def _rpc_api_keys_only(self):
        """Require API keys - not passwords - for RPC access by enforced users.

        This is Odoo's own hook for exactly this purpose (it is what two-factor
        authentication uses). Reusing it closes the RPC bypass without touching
        the API key code path: integrations keep working, passwords stop working.
        """
        if self._sso_is_enforced():
            return True
        return super()._rpc_api_keys_only()
