import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from family_hub.proxy_prefix import ForwardedPrefixMiddleware


async def _echo(request: Request) -> JSONResponse:
    return JSONResponse({"prefix": request.headers.get("x-forwarded-prefix")})


async def _redirect(request: Request) -> RedirectResponse:
    return RedirectResponse("/proxy/8080/target")


def _client(prefix: str) -> httpx.AsyncClient:
    app = Starlette(routes=[Route("/echo", _echo), Route("/redirect", _redirect)])
    app.add_middleware(ForwardedPrefixMiddleware, prefix=prefix)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_header_is_set_and_overrides_client_value() -> None:
    async with _client("/proxy/8080/") as client:
        response = await client.get("/echo", headers={"X-Forwarded-Prefix": "/evil"})

    assert response.json() == {"prefix": "/proxy/8080"}


async def test_redirect_prefix_is_removed() -> None:
    async with _client("/proxy/8080") as client:
        response = await client.get("/redirect")

    assert response.headers["location"] == "/target"


async def test_disabled_without_prefix() -> None:
    async with _client("") as client:
        response = await client.get("/echo")

    assert response.json() == {"prefix": None}
