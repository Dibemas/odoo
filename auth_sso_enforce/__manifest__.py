{
    'name': 'SSO Enforcement (Microsoft) with Bypass',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Enforce Microsoft SSO for interactive login, with a per-user bypass for break-glass and external accounts',
    'description': """
SSO Enforcement with Per-User Bypass
====================================

Forces users to authenticate through Microsoft Single Sign-On, while allowing a
configurable set of accounts (break-glass administrator, external accountant) to
keep using a local Odoo password.

**What is blocked**

* Interactive password login at ``/web/login`` for enforced users.
* Password authentication over JSON-RPC / XML-RPC for enforced users
  (via the native ``_rpc_api_keys_only`` hook).

**What keeps working**

* Microsoft OAuth login (``auth_oauth``) - untouched.
* API keys (``res.users.apikeys``) for integrations and MCP clients.
* Password re-checks for users who are *already* authenticated, so the
  identity-confirmation wizard - and therefore API key generation - still works.
* Any user with ``bypass_sso_enforcement`` set.

**Safety**

Enforcement is driven by the system parameter ``auth_sso_enforce.active``
and ships **disabled**. Installing the module changes no behaviour until that
parameter is set to ``1``. If OAuth ever breaks, the same parameter is the
break-glass switch and can be flipped directly in the database.

See README.md for the rollout and recovery procedure.
    """,
    'author': 'Johan Camp',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'auth_oauth',
    ],
    'data': [
        'data/ir_config_parameter.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
