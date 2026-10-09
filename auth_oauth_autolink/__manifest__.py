{
    'name': 'Microsoft SSO - automatic user linking and single second factor',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Link an existing Odoo user to their Microsoft account on first SSO login, and let Entra be the only second factor',
    'description': """
Automatic OAuth user linking
============================

Out of the box, ``auth_oauth`` signs a user in only when some ``res.users``
record already carries the right ``oauth_uid`` for the provider. Nothing sets
that value, so a correct Microsoft login still fails with *"You do not have
access to this database or your invitation has expired"* (``oauth_error=3``)
until an administrator fills it in by hand for every employee.

The value itself is awkward to provision: with Microsoft's OIDC userinfo
endpoint the subject is a **pairwise** identifier, unique per application *and*
per user, so it cannot be read from the Entra portal - you would have to make
each person attempt a login and harvest their value from the server log.

This module closes the gap once: on the first SSO login it matches the verified
email from the identity provider against the existing Odoo login, stores the
subject as ``oauth_uid``, and lets the standard flow proceed. Every later login
is an exact ``oauth_uid`` match with no fallback involved.

Safeguards
----------
* Only ever links an account that has **no** ``oauth_uid`` yet - an existing link
  is never overwritten or reassigned.
* Requires exactly **one** active matching user; an ambiguous match is refused.
* Optional domain allowlist (``auth_oauth_autolink.allowed_domains``),
  preset to the company's own mail domain, so only addresses in your own domains can ever be
  linked.
* Only internal users, never portal or public accounts.
* Every link is logged.

One second factor, not two
==========================

Entra enforces MFA before it ever issues a token, so Odoo's own second step
asks the employee for a factor they satisfied seconds earlier - on every single
login. This module drops it for SSO logins only.

Odoo 18 exposes the switch natively: ``_check_credentials`` returns an
``auth_info`` dict, and ``Session.authenticate`` finalises the session on the
spot when its ``mfa`` key reads ``skip``. That test short-circuits before
``_mfa_url()``, so it covers both the authenticator app (``auth_totp``) and the
emailed code that ``auth_totp.policy`` forces on internal users
(``auth_totp_mail_enforce``). No controller is overridden and no user record is
modified - nobody's TOTP secret is deleted, it simply is not asked for.

* **Password logins keep their Odoo second factor.** The break-glass
  administrator and the external accountant sign in with a password, and they
  are precisely the accounts Entra is *not* protecting.
* The new-device alert mail is suppressed for SSO logins. It fires when a second
  factor is enabled but no trusted-device cookie is present, and that cookie is
  only ever set by completing the second-factor step - so without this, skipping
  the step would mail the user on every login.
* Kill switch: ``auth_oauth_autolink.skip_mfa``, shipped as ``1``. Set it
  to ``0`` to hand the second step back to Odoo for SSO users too.
    """,
    'author': 'Johan Camp',
    'license': 'LGPL-3',
    # auth_totp is a hard dependency for load order, not just for the feature:
    # its _should_alert_new_device returns without calling super(), so this
    # module has to be loaded after it to sit ahead of it in the MRO.
    'depends': ['auth_oauth', 'auth_totp'],
    'data': ['data/ir_config_parameter.xml'],
    'installable': True,
    'application': False,
}
