from contextlib import asynccontextmanager
from typing import Annotated
from unittest.mock import Mock

import fastapi
import pytest
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient

from dishka import make_async_container, provide, Scope
from dishka.integrations.fastapi import (
    DishkaRoute,
    FromDishka,
    inject,
    setup_dishka,
)
from ..common import (
    APP_DEP_VALUE,
    REQUEST_DEP_VALUE,
    AppDep,
    AppProvider,
    RequestDep,
)


@asynccontextmanager
async def dishka_app(view, provider) -> TestClient:
    router = fastapi.APIRouter()
    router.get("/")(inject(view))
    app = fastapi.FastAPI()
    app.include_router(router)
    container = make_async_container(provider)
    setup_dishka(container, app)
    async with LifespanManager(app):
        yield fastapi.testclient.TestClient(app)
    await container.close()


@asynccontextmanager
async def dishka_auto_app(view, provider) -> TestClient:
    router = fastapi.APIRouter(route_class=DishkaRoute)
    router.get("/")(view)
    app = fastapi.FastAPI()
    app.include_router(router)
    container = make_async_container(provider)
    setup_dishka(container, app)
    async with LifespanManager(app):
        yield fastapi.testclient.TestClient(app)
    await container.close()


async def get_with_app(
        a: FromDishka[AppDep],
        mock: FromDishka[Mock],
) -> None:
    mock(a)


@pytest.mark.parametrize("app_factory", [
    dishka_app, dishka_auto_app,
])
@pytest.mark.asyncio
async def test_app_dependency(app_provider: AppProvider, app_factory):
    async with app_factory(get_with_app, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(APP_DEP_VALUE)
        app_provider.app_released.assert_not_called()
    app_provider.app_released.assert_called()


class Wrapper:
    a: AppDep
    mock: Mock

    async def get_with_app(
            self,
            a: FromDishka[AppDep],
            mock: FromDishka[Mock],
    ) -> None:
        mock(a)


class LocalProvider(AppProvider):
    scope = Scope.APP

    wrapper = provide(Wrapper)


@pytest.mark.parametrize("app_factory", [
    dishka_app, dishka_auto_app,
])
@pytest.mark.asyncio
async def test_app_dependency_method(app_factory):
    app_provider = LocalProvider()
    async with app_factory(Wrapper.get_with_app, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(APP_DEP_VALUE)
        app_provider.app_released.assert_not_called()
    app_provider.app_released.assert_called()


async def get_with_request(
        a: FromDishka[RequestDep],
        mock: FromDishka[Mock],
) -> None:
    mock(a)


@pytest.mark.asyncio
async def test_request_dependency(app_provider: AppProvider):
    async with dishka_app(get_with_request, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()

async def get_compat(
        a: FromDishka[RequestDep],
        mock: FromDishka[Mock],
) -> None:
    mock(a)


@pytest.mark.asyncio
async def test_compat(app_provider: AppProvider):
    async with dishka_app(get_compat, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()


@pytest.mark.asyncio
async def test_request_dependency2(app_provider: AppProvider):
    async with dishka_app(get_with_request, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.mock.reset_mock()
        app_provider.request_released.assert_called_once()
        app_provider.request_released.reset_mock()
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()


@inject
async def additional(
        a: FromDishka[RequestDep],
        mock: FromDishka[Mock],
):
    mock(a)


async def get_with_depends(
        a: Annotated[None, fastapi.Depends(additional)],
) -> None:
    pass


@pytest.mark.asyncio
async def test_fastapi_depends(app_provider: AppProvider):
    async with dishka_app(get_with_depends, app_provider) as client:
        client.get("/")
        app_provider.mock.assert_called_with(REQUEST_DEP_VALUE)
        app_provider.request_released.assert_called_once()
