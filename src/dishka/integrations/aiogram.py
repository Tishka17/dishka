__all__ = [
    "AutoInjectMiddleware",
    "AiogramProvider",
    "CONTAINER_NAME",
    "FromDishka",
    "inject",
    "setup_dishka",
]

from collections.abc import Awaitable, Callable, Container
from inspect import Parameter, signature
from typing import Any, Final, ParamSpec, TypeVar, cast

from aiogram import BaseMiddleware, Router
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.types import TelegramObject

from dishka import AsyncContainer, FromDishka, Provider, Scope, from_context
from .base import InjectDecorator, is_dishka_injected, wrap_injection

P = ParamSpec("P")
T = TypeVar("T")
CONTAINER_NAME: Final = "dishka_container"


def inject(func: Callable[P, T]) -> Callable[P, T]:
    if CONTAINER_NAME in signature(func).parameters:
        additional_params = []
    else:
        additional_params = [Parameter(
            name=CONTAINER_NAME,
            annotation=Container,
            kind=Parameter.KEYWORD_ONLY,
        )]

    return wrap_injection(
        func=func,
        is_async=True,
        additional_params=additional_params,
        container_getter=lambda args, kwargs: kwargs[CONTAINER_NAME],
    )


class AiogramProvider(Provider):
    event = from_context(TelegramObject, scope=Scope.REQUEST)


class ContainerMiddleware(BaseMiddleware):
    def __init__(self, container: AsyncContainer) -> None:
        self.container = container

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.container({TelegramObject: event}) as sub_container:
            data[CONTAINER_NAME] = sub_container
            return await handler(event, data)


class AutoInjectMiddleware(BaseMiddleware):
    def __init__(self, inject_decorator: InjectDecorator = inject) -> None:
        self.inject_decorator = inject_decorator

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        old_handler = cast(HandlerObject, data["handler"])
        if is_dishka_injected(old_handler.callback):
            return await handler(event, data)

        new_handler = HandlerObject(
            callback=self.inject_decorator(old_handler.callback),
            filters=old_handler.filters,
            flags=old_handler.flags,
        )
        old_handler.callback = new_handler.callback
        old_handler.params = new_handler.params
        old_handler.varkw = new_handler.varkw
        old_handler.awaitable = new_handler.awaitable
        return await handler(event, data)


def setup_dishka(
    container: AsyncContainer,
    router: Router,
    *,
    auto_inject: bool = False,
) -> None:
    middleware = ContainerMiddleware(container)
    auto_inject_middleware = AutoInjectMiddleware()

    for observer in router.observers.values():
        observer.outer_middleware(middleware)
        if auto_inject and observer.event_name != "update":
            observer.middleware(auto_inject_middleware)
