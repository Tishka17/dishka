__all__ = [
    "DISHKA_CONTAINER_KEY",
    "FromDishka",
    "inject",
    "setup_dishka",
    "AiohttpProvider",
]

from collections.abc import Callable, Coroutine
from typing import Any, Final, TypeAlias, TypeVar, cast

from aiohttp import web
from aiohttp.abc import AbstractView
from aiohttp.typedefs import Handler
from aiohttp.web_app import Application
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse

from dishka import AsyncContainer, FromDishka, Provider, Scope, from_context
from dishka.integrations.base import (
    InjectDecorator,
    is_dishka_injected,
    wrap_injection,
)

T = TypeVar("T")
DISHKA_CONTAINER_KEY: Final = web.AppKey("dishka_container", AsyncContainer)
AiohttpHandler: TypeAlias = type[AbstractView] | Callable[
    [Request], Coroutine[Any, Any, StreamResponse],
]


def inject(func: Callable[..., T]) -> AiohttpHandler:
    return cast(
        AiohttpHandler,
        wrap_injection(
            func=func,
            is_async=True,
            container_getter=lambda p, _: p[0][DISHKA_CONTAINER_KEY],
        ),
    )


class AiohttpProvider(Provider):
    request = from_context(Request, scope=Scope.SESSION)


@web.middleware
async def container_middleware(
    request: Request,
    handler: Handler,
) -> StreamResponse:
    container = request.app[DISHKA_CONTAINER_KEY]

    if (
        request.headers.get("Upgrade") == "websocket"
        and request.headers.get("Connection") == "Upgrade"
    ):
        scope = Scope.SESSION

    else:
        scope = Scope.REQUEST

    context = {Request: request}

    async with container(context=context, scope=scope) as request_container:
        request[
            DISHKA_CONTAINER_KEY] = request_container  # type: ignore[index]
        return await handler(request)


def _inject_routes(
    router: web.UrlDispatcher,
    inject_decorator: InjectDecorator,
) -> None:
    for route in router.routes():
        _inject_route(route, inject_decorator)

    for resource in router.resources():
        for route in resource._routes:  # type: ignore[attr-defined] # noqa: SLF001
            _inject_route(route, inject_decorator)


def _inject_route(
    route: web.AbstractRoute,
    inject_decorator: InjectDecorator,
) -> None:
    if not is_dishka_injected(route.handler):
        # typing.cast is used because AbstractRoute._handler
        # is Handler or Type[AbstractView]
        route._handler = cast( # noqa: SLF001
            AiohttpHandler,
            inject_decorator(route.handler),
        )


async def _on_shutdown(app: web.Application) -> None:
    await app[DISHKA_CONTAINER_KEY].close()


def setup_dishka(
    container: AsyncContainer,
    app: Application,
    *,
    auto_inject: bool = False,
    inject_decorator: InjectDecorator = inject,
) -> None:
    app[DISHKA_CONTAINER_KEY] = container
    app.middlewares.append(container_middleware)
    app.on_shutdown.append(_on_shutdown)

    if auto_inject:
        _inject_routes(app.router, inject_decorator)
