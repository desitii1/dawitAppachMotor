from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.auth import SESSION_COOKIE_NAME, read_admin_id
from itsdangerous import BadSignature


class AdminSessionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            headers = dict(scope.get("headers", []))
            cookie_header = headers.get(b"cookie", b"").decode("latin-1")
            for item in cookie_header.split(";"):
                name, separator, value = item.strip().partition("=")
                if separator and name == SESSION_COOKIE_NAME:
                    try:
                        scope["state"]["admin_id"] = read_admin_id(value)
                    except (BadSignature, ValueError, KeyError):
                        scope["state"]["admin_id"] = None
                    break
        await self.app(scope, receive, send)
