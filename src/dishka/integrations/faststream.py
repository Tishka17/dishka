__all__ = (
    "FromDishka",
    "inject",
    "FastStreamProvider",
    "setup_dishka",
)

import warnings
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, ParamSpec, TypeVar, cast

from faststream import BaseMiddleware, FastStream, context
from faststream.__about__ import __version__
from faststream.broker.message import StreamMessage
from faststream.types import DecodedMessage
from faststream.utils.context import ContextRepo

from dishka import AsyncContainer, FromDishka, Provider, Scope, from_context
from dishka.integrations.base import InjectDecorator, wrap_injection

T = TypeVar("T")
P = ParamSpec("P")


class FastStreamProvider(Provider):
    context = from_context(ContextRepo, scope=Scope.REQUEST)
    message = from_context(StreamMessage, scope=Scope.REQUEST)


FASTSTREAM_OLD_MIDDLEWARES = __version__ < "0.5"


def inject(func: Callable[P, T]) -> Callable[P, T]:
    return wrap_injection(
        func=func,
        is_async=True,
        container_getter=lambda *_: context.get_local("dishka"),
    )


class _DishkaBaseMiddleware(BaseMiddleware):
    def __init__(self, container: AsyncContainer) -> None:
        self.container = container

    def __call__(self, msg: Any | None = None) -> "_DishkaBaseMiddleware":
        self.msg = msg
        return self


if FASTSTREAM_OLD_MIDDLEWARES:

    class DishkaMiddleware(_DishkaBaseMiddleware):
        @asynccontextmanager
        async def consume_scope(  # type: ignore[override]
                self,
                *args: Any,
                **kwargs: Any,
        ) -> AsyncIterator[DecodedMessage]:
            async with self.container() as request_container:
                with context.scope("dishka", request_container):
                    async with super().consume_scope(  # type: ignore[attr-defined]
                        *args,
                        **kwargs,
                    ) as result:
                        yield result

else:

    class DishkaMiddleware(_DishkaBaseMiddleware):  # type: ignore[no-redef]
        async def consume_scope(
                self,
                call_next: Callable[[Any], Awaitable[Any]],
                msg: StreamMessage[Any],
        ) -> AsyncIterator[DecodedMessage]:
            async with self.container(
                {
                    StreamMessage: msg,
                    ContextRepo: context,
                    type(msg): msg,
                },
            ) as request_container:
                with context.scope("dishka", request_container):
                    return cast(
                        AsyncIterator[DecodedMessage],
                        await call_next(msg),
                    )


def setup_dishka(
        container: AsyncContainer,
        app: FastStream,
        *,
        finalize_container: bool = True,
        auto_inject: bool = False,
        inject_decorator: InjectDecorator = inject,
) -> None:
    assert app.broker, "You can't patch FastStream application without broker"  # noqa: S101

    if finalize_container:
        app.after_shutdown(container.close)

    if FASTSTREAM_OLD_MIDDLEWARES:
        app.broker.middlewares = (  # type: ignore[attr-defined]
            DishkaMiddleware(container),
            *app.broker.middlewares,  # type: ignore[attr-defined]
        )

        if auto_inject:
            warnings.warn(
                """
Auto injection is not supported for FastStream version less than 0.5.0
Please, update your FastStream installation
or use @inject at each subscriber manually.
            """,
                category=RuntimeWarning,
                stacklevel=1,
            )

    else:
        app.broker._middlewares = (  # noqa: SLF001
            DishkaMiddleware(container),
            *app.broker._middlewares,  # noqa: SLF001
        )

        for subscriber in app.broker._subscribers.values():  # noqa: SLF001
            subscriber._broker_middlewares = (  # noqa: SLF001
                DishkaMiddleware(container),
                *subscriber._broker_middlewares,  # noqa: SLF001
            )

        for publisher in app.broker._publishers.values():  # noqa: SLF001
            publisher._broker_middlewares = (  # noqa: SLF001
                DishkaMiddleware(container),
                *publisher._broker_middlewares,  # noqa: SLF001
            )

        if auto_inject:
            app.broker._call_decorators = (  # noqa: SLF001
                inject_decorator,
                *app.broker._call_decorators,  # noqa: SLF001
            )
