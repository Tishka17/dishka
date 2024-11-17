__all__ = [
    "FromDishka",
    "inject",
    "setup_dishka",
]

from collections.abc import Callable
from typing import Final, TypeVar

from click import (
    Command,
    Context,
    Group,
    get_current_context,
)

from dishka import Container, FromDishka
from .base import InjectDecorator, is_dishka_injected, wrap_injection

T = TypeVar("T")
CONTAINER_NAME: Final = "dishka_container"


def inject(func: Callable[..., T]) -> Callable[..., T]:
    return wrap_injection(
        func=func,
        container_getter=lambda _, __: get_current_context().meta[
            CONTAINER_NAME
        ],
        remove_depends=True,
        is_async=False,
    )


def _inject_commands(
    context: Context,
    command: Command | None,
    inject_decorator: InjectDecorator,
) -> None:
    if isinstance(command, Command) and not is_dishka_injected(
        command.callback,  # type: ignore[arg-type]
    ):
        command.callback = inject_decorator(command.callback)   # type: ignore[arg-type]

    if isinstance(command, Group):
        for command_name in command.list_commands(context):
            child_command = command.get_command(context, command_name)
            _inject_commands(context, child_command, inject_decorator)


def setup_dishka(
    container: Container,
    context: Context,
    *,
    finalize_container: bool = True,
    auto_inject: bool = False,
    inject_decorator: InjectDecorator = inject,
) -> None:
    context.meta[CONTAINER_NAME] = container

    if finalize_container:
        context.call_on_close(container.close)

    if auto_inject:
        _inject_commands(context, context.command, inject_decorator)
