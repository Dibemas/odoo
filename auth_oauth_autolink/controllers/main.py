from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home


class AutolinkHome(Home):

    @http.route()
    def web_client(self, s_action=None, **kw):
        """Forbid browsers from reusing a stored copy of the web client page.

        The page embeds per-session state in its HTML: ``session_info``
        (including the subscription expiry the Enterprise banner reads) and the
        CSRF token that file uploads send. Odoo serves it without any cache
        headers, so Chrome's *Duplicate tab* and back/forward restore the old
        document instead of asking the server. The copy then carries whatever
        was true when it was first loaded - a long-resolved "database expired"
        banner, and an upload token for a session that no longer exists, which
        fails with "Session expired (invalid CSRF token)".

        This one route serves every backend page (``/odoo``, ``/odoo/...``,
        ``/web``, ``/scoped_app/...``), so the header covers all of them.
        """
        response = super().web_client(s_action=s_action, **kw)
        response.headers['Cache-Control'] = 'no-store'
        return response


class AutolinkSession(http.Controller):

    @http.route('/auth_oauth_autolink/session/csrf_token', type='json', auth='user', readonly=True)
    def csrf_token(self):
        """Current CSRF token for this session, for tabs that outlived theirs.

        A tab keeps the token it was loaded with. After a new login - which
        every Microsoft sign-in is - the session changes and that token no
        longer validates, so uploads fail while everything else in the tab
        still works (JSON calls are not CSRF-checked). The client asks for a
        fresh one when the tab becomes active again.

        Safe to expose: the route requires the session cookie, and a JSON
        response cannot be read cross-origin, so only the page that already
        belongs to this session can obtain its token.
        """
        return request.csrf_token(None)
