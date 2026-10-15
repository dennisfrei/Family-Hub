"""Support for path-stripping reverse proxies that do not send `X-Forwarded-Prefix` (e.g. code-server)."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = b"x-forwarded-prefix"


class ForwardedPrefixMiddleware:
    """Pretend the proxy sent `X-Forwarded-Prefix`, so NiceGUI prefixes its asset and socket URLs.

    Redirects get the prefix removed again, because such proxies add it to `Location` themselves.
    """

    def __init__(self, app: ASGIApp, prefix: str) -> None:
        """Wrap `app`; `prefix` is the public path the proxy strips, e.g. `/proxy/8080`."""
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Add the header to HTTP and WebSocket requests."""
        if scope["type"] not in ("http", "websocket") or not self.prefix:
            await self.app(scope, receive, send)
            return
        headers = [(key, value) for key, value in scope["headers"] if key != HEADER]
        scope = {**scope, "headers": [*headers, (HEADER, self.prefix.encode("latin-1"))]}

        async def send_without_prefix(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, self._strip(value) if key.lower() == b"location" else value)
                    for key, value in message.get("headers", [])
                ]
            await send(message)

        await self.app(scope, receive, send_without_prefix)

    def _strip(self, location: bytes) -> bytes:
        prefix = self.prefix.encode("latin-1")
        if not location.startswith(prefix + b"/"):
            return location
        return location[len(prefix) :]
