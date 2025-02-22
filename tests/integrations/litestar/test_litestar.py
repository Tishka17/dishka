from contextlib import asynccontextmanager
from unittest.mock import Mock

import litestar
import pytest
from asgi_lifespan import LifespanManager
from litestar import Request, get, websocket_listener
from litestar.contrib.htmx.request import HTMXRequest
from litestar.testing import TestClient

from dishka import make_async_container
from dishka.integrations.litestar import (
    FromDishka,
    inject,
    setup_dishka,
    DishkaRouter
)
from ..common import (
    APP_DEP_VALUE,
    REQUEST_DEP_VALUE,
    AppDep,
    AppProvider,
    RequestDep,
)


@asynccontextmanager
async def dishka_app(
        view,
        provider,
        request_class: type[Request] = Request,
) -> TestClient:
    dishka_router = DishkaRouter('', route_handlers=[])
    dishka_router.register(get("/")(view))

    app = litestar.Litestar(route_handlers=[dishka_router], request_class=request_class)
    # app.register(get("/")(inject(view)))
    app.register(websocket_listener("/ws")(websocket_handler))
    container = make_async_container(provider)
    setup_dishka(container, app)
    async with LifespanManager(app):
        yield litestar.testing.TestClient(app)
    await container.close()


async def websocket_handler(data: str):
    pass


def get_with_app(request_class: type[Request]):
    async def handler(
            request: request_class,
            a: FromDishka[AppDep],
            mock: FromDishka[Mock],
    ) -> None:
        mock(a)

    return handler


def get_with_request(request_class: type[Request]):
    async def handler(
            request: request_class,
            a: FromDishka[RequestDep],
            mock: FromDishka[Mock],
    ) -> None:
        mock(a)

    return handler


@pytest.mark.parametrize("request_class", [Request, HTMXRequest])
@pytest.mark.asyncio
async def test_app_dependency(request_class, app_provider: AppProvider):
    async with dishka_app(get_with_app(request_class), app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(APP_DEP_VALUE)
        app_provider.app_released.assert_not_called()
    app_provider.app_released.assert_called()


@pytest.mark.parametrize("request_class", [Request, HTMXRequest])
@pytest.mark.asyncio
async def test_request_dependency(request_class, app_provider: AppProvider):
    async with dishka_app(
            get_with_request(request_class),
            app_provider,
            request_class,
    ) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()


@pytest.mark.parametrize("request_class", [Request, HTMXRequest])
@pytest.mark.asyncio
async def test_request_dependency2(request_class, app_provider: AppProvider):
    async with dishka_app(
            get_with_request(request_class),
            app_provider,
            request_class,
    ) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.mock.reset_mock()
        app_provider.request_released.assert_called_once()
        app_provider.request_released.reset_mock()
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()


@pytest.mark.asyncio
async def test_request_middleware(app_provider: AppProvider):
    async with dishka_app(
            get_with_request(Request),
            app_provider,
            Request,
    ) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send("test")
