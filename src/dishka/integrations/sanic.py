__all__ = [
    "FromDishka",
    "inject",
    "setup_dishka",
    "SanicProvider",
]

from collections.abc import Iterable
from typing import Any, cast

from sanic import HTTPResponse, Request, Sanic
from sanic.models.handler_types import RouteHandler
from sanic_routing import Route

from dishka import AsyncContainer, Provider, Scope, from_context
from dishka.integrations.base import (
    FromDishka,
    InjectDecorator,
    is_dishka_injected,
    wrap_injection,
)


def inject(func: RouteHandler) -> RouteHandler:
    return cast(
        RouteHandler,
        wrap_injection(
            func=func,
            is_async=True,
            container_getter=lambda args, _: args[0].ctx.dishka_container,
        ),
    )


class SanicProvider(Provider):
    request = from_context(Request, scope=Scope.REQUEST)


class ContainerMiddleware:
    def __init__(self, container: AsyncContainer) -> None:
        self.container = container

    async def on_request(self, request: Request) -> None:
        request.ctx.container_wrapper = self.container({Request: request})
        request.ctx.dishka_container = await request.ctx.container_wrapper.__aenter__()  # noqa: E501

    async def on_response(self, request: Request, _: HTTPResponse) -> None:
        await request.ctx.dishka_container.close()


def _inject_routes(
    routes: Iterable[Route],
    inject_decorator: InjectDecorator = inject,
) -> None:
    for route in routes:
        if not is_dishka_injected(route.handler):
            route.handler = inject_decorator(route.handler)


def setup_dishka(
    container: AsyncContainer,
    app: Sanic[Any, Any],
    *,
    auto_inject: bool = False,
    inject_decorator: InjectDecorator = inject,
) -> None:
    middleware = ContainerMiddleware(container)
    app.on_request(middleware.on_request)
    app.on_response(middleware.on_response)  # type: ignore[no-untyped-call]

    if auto_inject:
        _inject_routes(app.router.routes, inject_decorator)
        for blueprint in app.blueprints.values():
            _inject_routes(blueprint.routes, inject_decorator)
