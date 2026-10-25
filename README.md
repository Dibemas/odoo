# Dibemas — Odoo 18 addons

Custom and vendored Odoo 18 (Enterprise) modules for Dibemas, Johan Camp's own
company. The set is small: Microsoft SSO, supplier payment methods, a one-off
clean-up tool, and the Apexive LLM/MCP stack that lets Claude work with Odoo
data. Two older modules (credit card, CC/BCC) are still in the repo but are not
installed.

Every top-level directory is one Odoo addon. The repository is the addons
repository of an **odoo.sh** project (`dibemas-odoo.odoo.com`).

Several modules also run at Shield VZW (`../shield-vzw`, self-hosted on
level27). That repo has the longer write-ups; this file links to them where
they apply and says where Dibemas differs.

Last reviewed: 2026-10-25.

---

## Branches and deploy (odoo.sh)

| Branch | odoo.sh stage | Notes |
|---|---|---|
| `prod` | Production | Every push triggers a production build. |
| `stag` | Staging | Usual landing branch. Each build gets a **neutralized** copy of the production database. The LLM stack skips it and goes straight to `prod` (already validated on Shield). |
| `DEV` | Development | Old (July 2025). Only holds the abandoned v17 credit card work (`account_journal_credit_card`, plus the OCA `account_payment_credit_card` 17.0). Not used. |

How odoo.sh differs from Shield's level27 servers:

- **No manual `odoo-bin -u`.** A push triggers a build. odoo.sh upgrades a
  module when its `version` in `__manifest__.py` changes. A **new** module is
  not installed automatically: install it through **Apps** after the build.
  So bump `version` on every change you want applied.
- **Python packages come from `requirements.txt`** at the repository root. odoo.sh
  installs it on every build. On Shield this is a manual `pip install` in the
  venv.
- **No nginx access.** Shield's nginx problems (WAF POST burst, missing
  `X-Forwarded-Host`, the `shield_proxy_scheme_fix` workaround) do not apply
  here. It also means you cannot restrict `/mcp` to Anthropic's IP range at the
  proxy.
- **Staging is neutralized.** odoo.sh runs `neutralize` on the staging copy. Among
  other things, `auth_oauth/data/neutralize.sql` disables every OAuth provider.
  Microsoft login therefore does not work on staging until you re-enable the
  provider there. Keep `auth_sso_enforce.active` at `0` on staging, or nobody
  without a bypass can log in.
- **Push one branch at a time.** On 2026-10-25, `stag` and `prod` were pushed
  seconds apart. The staging build succeeded, and the production build failed
  with "Failed to clone the repository" (the repository is 4.5 GB, with full
  Odoo history). Push `stag`, wait for its build, then push `prod`.
- **A failed production build cannot be rebuilt from the menu.** Only a new
  commit starts one: `git commit --allow-empty -m "Trigger odoo.sh production
  build"` on `prod`, then push. The previous production build keeps running
  meanwhile.
- **Recovery** goes through the odoo.sh web shell (`psql`, `odoo-bin shell`)
  rather than SSH.

---

## Module overview

| Module | Version | Author / licence | Status |
|---|---|---|---|
| [`account_supplier_payment_method`](#account_supplier_payment_method) | 18.0.1.1.1 | Johan Camp / LGPL-3 | Same code as Shield. Install via Apps if not done yet |
| [`auth_sso_enforce`](#microsoft-sso-auth_sso_enforce--auth_oauth_autolink) | 18.0.1.0.0 | Johan Camp / LGPL-3 | Installed, **not enforced** (`auth_sso_enforce.active` = `0`) |
| [`auth_oauth_autolink`](#microsoft-sso-auth_sso_enforce--auth_oauth_autolink) | **18.0.1.2.0** | Johan Camp / LGPL-3 | Installed. Microsoft login works on production. 1.2.0 (Shield's stale-tab fix) merged into `prod` on 2026-10-25; the build upgrades it |
| [`journal_entries_deleter`](#journal_entries_deleter) | 1.0 | Marco Silva, Johan Camp / LGPL-3 | **One-off** clean-up tool. Uninstall when finished |
| [`llm_tool_accounting`](#llm_tool_accounting) | 18.0.1.0.0 | Johan Camp / LGPL-3 | **New, on `stag`, uncommitted.** Company lock, accounting guards and bank reconciliation for the MCP tools |
| [`llm`](llm/README.md) | 18.0.1.7.2 | Apexive / LGPL-3 | Merged into `prod` on 2026-10-25. Install via Apps |
| [`llm_tool`](llm_tool/README.md) | 18.0.4.1.2 | Apexive / LGPL-3 | Merged into `prod` on 2026-10-25. Install via Apps |
| [`llm_mcp_server`](llm_mcp_server/README.md) | 18.0.1.3.3 | Apexive, patched / LGPL-3 | Merged into `prod` on 2026-10-25. Install via Apps |
| [`web_json_editor`](web_json_editor/README.md) | 18.0.1.0.0 | Apexive / LGPL-3 | Merged into `prod` on 2026-10-25. Install via Apps |
| `requirements.txt` | – | – | Merged into `prod` on 2026-10-25. Needed by `llm_tool` and `llm_mcp_server` |

**Removed on 2026-10-25.** These were never installed on production (the Apps
screen showed *Activeer*). Both were written for Odoo 17; standard Odoo 18
covers what they did. The code stays in git history, and an identical copy of
both is in the Shield repo.

| Module | Version | Author / licence | Replaced by |
|---|---|---|---|
| [`account_journal_credit_card`](#account_journal_credit_card-removed) | 1.0 | Marco Silva, Johan Camp / OPL-1 | Standard Odoo 18 credit card journals |
| [`odoo_email_cc_bcc`](#odoo_email_cc_bcc-removed) | 1.1.0 | Webkul / proprietary | Standard Odoo 18 mail composer |

### Relation to the Shield copies

Compared with `diff -r` on 2026-10-25:

| Dibemas | Shield | Result |
|---|---|---|
| `llm`, `llm_tool`, `llm_mcp_server`, `web_json_editor` | same names | Identical, including Shield's two in-tree fixes to `llm_mcp_server` |
| `account_supplier_payment_method` | same name | Identical except `author` |
| `auth_sso_enforce` | `custom_auth_sso_enforce` 18.0.1.0.2 | Renames only (module name, `auth_sso_enforce.active` key, author). README adapted |
| `auth_oauth_autolink` | `shield_auth_oauth_autolink` 18.0.1.2.0 | Renames only, since 2026-10-25 (brought up to 1.2.0, see below) |

None of Shield's top-level documents could be symlinked here. They name Shield's
modules and parameters (`custom_auth_sso_enforce.*`, `shield_*`), or describe
modules Dibemas does not use (`shield_mcp_oauth`, the Jira connector). A
symlink to `../shield-vzw/...` would also be a dangling link in odoo.sh's
clone, which only contains this repository. The module READMEs inside the
identical vendored modules are already here because the modules are copies.

---

## Module details

### `account_journal_credit_card` (removed)

Bookkeeping for company credit cards, written in-house for Odoo 17. Never
installed on production, and removed from the repository on 2026-10-25; Odoo
18 handles credit card journals with standard features. Described here only as
a record of what it did.

- **Journal flag**: *Credit Card Journal* (`is_credit_card`) on a cash journal.
  Setting it creates a matching payment term (`<journal> Credit Card Payment
  Term`). The payment term then points back to the journal, and each journal
  can have only one. A debug-mode menu, *Add a Credit Card Journal*, opens a
  prefilled journal form (cash, code `CCARD`).
- **Auto-payment of bills**: when a vendor bill with that payment term is
  posted, an outbound payment on the card journal is created and posted, linked
  to the bill (`memo` = bill reference).
- **Statement import**: an *Upload* button on the journal's dashboard card opens
  a CSV wizard for the card issuer's monthly statement. It understands Dutch
  and English headers (`Periode`, `Datum`, `Omschrijving`, `Bedrag`,
  `Bedrag (EUR)`, `Munt`, `Koers`), detects `;` or `,`, and lets you choose the
  decimal and thousands separators. It creates one journal entry with a line per
  transaction and a balancing line.
- **Matching**: each line is matched to an existing bank or cash payment by
  amount and date (exact date first, then ±2 days). This works in the company
  currency and across currencies, with a 0.5 % / €0.50 tolerance on
  conversion. The match fills `linked_payment_id`, `linked_bill_id` and the
  partner. *Refresh Entries* on a draft entry retries the matching, and posting
  reconciles the line with the linked payment.

Known issues, in case it is ever revived:
- The `assets` list in the manifest is missing a comma, so both JS paths are
  glued into one string. They also point at `static/src/js/`, while the files
  live in `static/description/src/js/`. Neither file loads. Nothing seems to
  depend on them.
- The header translation lookup uses `ir.translation`, which no longer exists.
  The wizard always falls back to the built-in header map above.
- The import wizard's ACL row has no group, so every user has access to it.
- The licence says OPL-1 although the module is in-house.

### `account_supplier_payment_method`

Same code as Shield. A default payment method per supplier (Prepayment, Bank
transfer, Credit Card, Direct Debit) is copied onto each vendor bill, plus a
*Ready for Payment* flag that is only set when a bill can go into a SEPA
payment file without errors. Full description in
[Shield's README](../shield-vzw/README.md#account_supplier_payment_method).
Depends on `account_iso20022` (Enterprise).

Bills with the *Credit Card* or *Direct Debit* method never count as ready for
a bank payment run.

### Microsoft SSO (`auth_sso_enforce` + `auth_oauth_autolink`)

Ported from Shield on 2026-10-08. The behaviour is the same; the spec is Shield's
[`02_sso_enforcement.md`](../shield-vzw/02_sso_enforcement.md). Read it with
these renames:

| Shield | Dibemas |
|---|---|
| `custom_auth_sso_enforce` | `auth_sso_enforce` |
| `custom_auth_sso_enforce.active` | `auth_sso_enforce.active` |
| `shield_auth_oauth_autolink` | `auth_oauth_autolink` |
| `shield_auth_oauth_autolink.allowed_domains` (`shield-vzw.be`) | `auth_oauth_autolink.allowed_domains` (`dibemas.be`) |
| `shield_auth_oauth_autolink.skip_mfa` | `auth_oauth_autolink.skip_mfa` |

- **`auth_sso_enforce`**: when `auth_sso_enforce.active` = `1`, password login
  (web and RPC) is refused for every user except those with *Allow Local
  Password Login (Bypass SSO)* on the user form. API keys keep working.
  Password re-checks inside an existing session also keep working, so users can
  still create API keys. Rollout and recovery are in
  [`auth_sso_enforce/README.md`](auth_sso_enforce/README.md). On odoo.sh, run
  the recovery SQL from the web shell.
- **`auth_oauth_autolink`**: on a user's first Microsoft login, the verified
  e-mail is matched to an existing internal login (only `dibemas.be`) and stored
  as `oauth_uid`. After a Microsoft login, Odoo's own second factor is skipped,
  because Entra already enforced MFA. Password logins still get it.
  Since 1.2.0 (same as Shield) it also prevents stale tabs: backend pages are
  sent with `Cache-Control: no-store`, so *Duplicate tab* and back/forward
  always load a fresh page. A tab that outlived a new login fetches the current
  CSRF token from `/auth_oauth_autolink/session/csrf_token` when it becomes
  active again, so uploads keep working. Without this, a duplicated tab could
  show an old "database expired" banner, and uploads failed with "Session
  expired (invalid CSRF token)". The upgrade needs no data migration; odoo.sh
  applies it because the version changed.

State: Microsoft login works on production (2026-10-19). Enforcement is **off**.
The Entra app needed three settings that Shield did not: Web redirect URI
`/auth_oauth/signin`, implicit grant *Access tokens* enabled (otherwise
`AADSTS700051`), and system parameter `auth_oauth.authorization_header` = `1`.

To enforce: set the bypass on the break-glass admin (and the accountant, if
there is one), check that a normal user can log in with Microsoft, then set
`auth_sso_enforce.active` = `1` on production only.

### `journal_entries_deleter`

**A one-off tool**, written to clean up a large number of wrong journal entries.
It adds a *Force Delete* button to the journal entry list (Accounting managers
only). For each selected entry it sets `state = 'draft'` with `sudo()` and then
deletes it. This skips `button_draft`, the lock date check, reconciliation
undo and the audit trail. Errors are only logged; the user gets no message.

Uninstall it once the clean-up is finished. Keeping it installed lets any
accounting manager delete posted entries without a trace.

### `odoo_email_cc_bcc` (removed)

Webkul's CC and BCC module (proprietary licence, one per client). It adds CC,
BCC and Reply-To fields to the mail composer, with per-company switches and
default addresses on the company form, and shows CC/BCC on messages in the
chatter. It replaced an earlier in-house BCC module (commit `2c0acfb595d`).
Never installed on production, and removed from the repository on 2026-10-25;
the standard Odoo 18 composer is used instead.

---

## LLM / MCP (Claude integration)

The four Apexive modules and `requirements.txt` were copied from Shield on
2026-10-21 and merged into `prod` on 2026-10-25. They go **straight to
production**, without a Dibemas staging round: the stack is identical to
Shield's, where it was tested and validated.

```
Claude ──► POST https://<host>/mcp ──► llm_mcp_server ──► llm.tool.execute()
                │                                         (as the requesting user, no sudo)
                └─ auth="bearer": personal Odoo API key
```

| Module | Role |
|---|---|
| `llm` | Base registry for LLM providers, models and publishers. No provider modules (OpenAI, Anthropic, …) are installed. None is needed for the MCP server, which only exposes tools. |
| `llm_tool` | The `llm.tool` records: record retriever, model inspector, record creator, record updater, record unlinker, model method executor. |
| `llm_mcp_server` | The `/mcp` endpoint (MCP over HTTP, stateless or stateful). Sessions are stored in the database (`llm.mcp.session`), so they work across odoo.sh workers. Test scripts are in `llm_mcp_server/tests/`. |
| `web_json_editor` | JSON field widget used by the tool forms. |

Choices already made (see the hub `INVENTORY.md`, port log of 2026-10-21):
- **API-key route only.** Each user connects Claude with a personal Odoo API key
  (*Preferences → Account Security → New API Key*). Shield's Entra resource
  server (`shield_mcp_oauth`, spec in
  [`04_mcp_oauth_entra.md`](../shield-vzw/04_mcp_oauth_entra.md)) was **not**
  ported, so `PyJWT` is not in `requirements.txt`.
- **All six tools stay active**, write, delete and method execution included.
  Every call runs as the requesting user, so ACLs and record rules apply.
  For an administrator's key that still means full control of the database.

Things to know from the Shield rollout (details in
[`../shield-vzw/TODO.md`](../shield-vzw/TODO.md)):
- `llm_mcp_server` carries two local fixes (public ACL on
  `llm.mcp.server.config`, protocol version negotiation; Shield commit
  `2ba73dd`). Installing a newer Apexive release removes them.
- Still unfixed upstream: JSON-RPC errors with `"id": null`. A strict client
  shows them as a vague "Invalid input".
- Claude Code binds its tool list at session start. Restart it after adding
  the server.
- If SSO enforcement is switched on, an SSO user still needs a local password
  to create an API key, because creating a key asks for the password again.

### `llm_tool_accounting`

Written in-house on 2026-10-25 for the accounting assistant (Claude Desktop skill `odoo-boekhouding`,
kept in `~/Claude/skills/`). The Apexive tools take no context, so without it Odoo makes all four
companies visible and fills defaults and per-company fields (account codes, partner accounts) from the
user's main company. The module fixes that inside Odoo:

- **Company lock.** `accounting_select_company` stores a session company on the user
  (`llm_company_id`); every following tool call runs with `allowed_company_ids = [that company]`.
  Without a session company, calls on `account.*` models are refused
  (`llm_tool_accounting.require_company`, default `1`).
- **Guards.** Customer invoices/credit notes are never posted or sent through the tools; no direct
  `state`/`auto_post` writes; no deletes, ORM `create`/`write` or private methods on `account.*` via the
  method executor; in a company whose *VAT Regime* is not "VAT registered" nothing carrying VAT can be
  posted; in a company with *Analytic Required on Income and Expenses* every class 6/7 line needs a
  complete analytic distribution.
- **Bank reconciliation.** `accounting_reconcile_statement_line` reconciles one statement line with
  open items and/or a counterpart account (label, partner, taxes, analytic distribution), using the
  reconciliation widget's own logic inside a savepoint.
- Two fields on the company form: **VAT Regime** and **Analytic Required on Income and Expenses**.

Tests: 18 in `llm_tool_accounting/tests/`, all passing on a local Odoo 18 Enterprise database
(2026-10-25). Apexive's own `llm_tool` tests have 9 errors with or without this module (an upstream
test bug: they assign `_tool_registry` on a recordset).

After installing on production, set on the company form: Jazz and NORB → *Not VAT registered*,
Camp Dirk → *VAT franchise (art. 56bis)*, NORB → *Analytic Required*. Dibemas keeps the defaults.

### Getting it to production

1. Commit `llm`, `llm_tool`, `llm_mcp_server`, `web_json_editor` and
   `requirements.txt` (on `stag`, so the branches stay aligned), merge into
   `prod` and push `prod`. Commit and merge done on 2026-10-25.
2. Watch the production build log: `mcp==1.29.0` and `pydantic==2.13.4` must
   install. `mcp` pulls in `starlette`, `httpx`, `uvicorn` and `anyio`. A
   dependency conflict fails the build, and odoo.sh then keeps the previous
   build running, so production is not left broken.
3. Install **`llm_mcp_server`** through Apps on production. It pulls in the
   other three. Nothing changes for users until someone connects a client.
4. Create a personal API key (*Preferences → Account Security → New API Key*).
   Add `https://dibemas-odoo.odoo.com/mcp` in Claude Code with
   `Authorization: Bearer <key>`, restart Claude Code, and check `tools/list`
   and a record read. `llm_mcp_server/tests/test_stateless.sh` does the same
   with curl.
5. Push `stag` too. The next staging build then has the modules in its code,
   and on its database too as soon as it is rebuilt from production.

Rollback: uninstall `llm_mcp_server` (then `llm_tool`, `web_json_editor` and
`llm` if wanted) through Apps. That removes the `/mcp` route immediately.
Revoking a user's API key cuts off just that user.

---

## Configuration reference (system parameters)

| Key | Value | Module | Meaning |
|---|---|---|---|
| `auth_sso_enforce.active` | `0` | `auth_sso_enforce` | `1` enforces SSO. Also the emergency switch. Keep `0` on staging. |
| `auth_oauth_autolink.allowed_domains` | `dibemas.be` | `auth_oauth_autolink` | E-mail domains that can be linked automatically |
| `auth_oauth_autolink.skip_mfa` | `1` | `auth_oauth_autolink` | Skip Odoo's second factor after a Microsoft login |
| `auth_oauth.authorization_header` | `1` | `auth_oauth` (standard) | Send the token as a Bearer header; Microsoft Graph userinfo needs it |

## Dependencies

- **Enterprise**: `account_iso20022` (supplier payment method).
- **Community**: `account`, `sale`, `product`, `mail`, `web`, `auth_oauth`,
  `auth_totp`.
- **Python** (`requirements.txt`): `mcp==1.29.0`, `pydantic==2.13.4`,
  `packaging`. Odoo needs `packaging` to check the versioned `pydantic>=2.0.0`
  dependency; a missing `packaging` broke Shield's first production install.
