# auth_sso_enforce

Enforces Microsoft SSO for interactive login while keeping a configurable set of
accounts (break-glass admin, external accountant) on local passwords.

## How it works

Odoo 18 funnels every credential check through
`res.users._check_credentials(credential, env)`, where `credential['type']` is
`password`, `oauth_token`, or an API key presented as a password. This module
hooks that single point rather than the login controller, which is what makes it
airtight:

| Path | Behaviour for an enforced user |
|---|---|
| `/web/login` with a password | refused, with an explanatory message |
| Microsoft OAuth | unaffected - handled by `auth_oauth` |
| JSON-RPC / XML-RPC with a password | refused, via `_rpc_api_keys_only()` |
| JSON-RPC / XML-RPC with an API key | works |
| Identity re-check (already logged in) | works - see below |

The original specification proposed overriding the `/web/login` controller. That
is not sufficient on its own: `res.users.authenticate()` accepts a password over
RPC without ever touching that controller, so an enforced user could bypass SSO
entirely. It also turned out to be unnecessary for the error message -
`Home.web_login` renders `e.args[0]` when `AccessDenied` carries custom args, so
raising the exception with text is enough to display it on the login page.

## Why password re-checks are still allowed

`res.users.identitycheck` re-confirms a password before sensitive actions; the
only alternative is a passkey, and only when `auth_passkey` is installed (it does
not install itself in Odoo 18). API key creation is decorated
with `@check_identity`, so blocking every interactive password check would make
it impossible for SSO users to generate API keys - including the keys the MCP
server needs.

The module distinguishes the two cases by session: a *login* arrives with no
session bound to the user, while a *re-check* arrives on a session already
authenticated as that same user. Allowing the latter grants no new access, since
the caller is demonstrably already inside.

Consequence to plan for: an SSO user still needs a local Odoo password (or a
registered passkey) to generate an API key. Either set one for employees who
need API access, or generate their keys before enabling enforcement.

## Rollout

Enforcement ships **disabled**. Installing the module changes nothing until you
turn it on, which is deliberate - a module upgrade should never be able to lock
out an organisation.

1. Install the module on staging first:
   ```bash
   odoo-bin -c odoo.conf -i auth_sso_enforce -d <staging-db> --stop-after-init
   ```
2. Set **Allow Local Password Login (Bypass SSO)** on the break-glass
   administrator and the accountant (Settings > Users > Access Rights tab,
   visible to System Administrators only).
3. Confirm Microsoft OAuth login actually works for a normal employee.
4. Only then enable enforcement:
   Settings > Technical > System Parameters > `auth_sso_enforce.active` = `1`

Do steps 2 and 3 in that order. Enabling enforcement before a bypass account
exists locks everyone out of password login simultaneously.

## Recovery

If Microsoft OAuth breaks and no bypass account can get in, disable enforcement
directly in the database - it takes effect immediately, no restart required:

```sql
UPDATE ir_config_parameter SET value = '0'
 WHERE key = 'auth_sso_enforce.active';
```

Odoo caches `ir.config_parameter`, so if the change does not appear to take
effect, restart the service.

## Testing

Per the specification, on staging:

1. **Enforced user** - password login at `/web/login` is refused and shows the
   SSO message; Microsoft login succeeds.
2. **Exempt user** - set the bypass flag on the accountant; password login
   succeeds.
3. **Break-glass** - deliberately misconfigure the OAuth provider on staging and
   confirm the exempt admin can still log in with a password.
4. **API keys** - confirm an existing API key still authenticates over
   JSON-RPC, and that password authentication over JSON-RPC is refused for an
   enforced user.
5. **Key generation** - as an enforced user with a session open, confirm
   Preferences > Account Security > New API Key still completes.
