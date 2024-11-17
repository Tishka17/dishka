from collections.abc import Awaitable, Callable, Sequence
from inspect import (
    Parameter,
    Signature,
    isasyncgenfunction,
    isgeneratorfunction,
    signature,
)
from typing import (
    Annotated,
    Any,
    Literal,
    ParamSpec,
    TypeAlias,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from dishka.async_container import AsyncContainer
from dishka.container import Container
from dishka.entities.component import DEFAULT_COMPONENT
from dishka.entities.depends_marker import FromDishka
from dishka.entities.key import DependencyKey, _FromComponent

T = TypeVar("T")
P = ParamSpec("P")
DependencyParser: TypeAlias = Callable[[Parameter, Any], DependencyKey | None]
ContainerGetter: TypeAlias = Callable[[tuple[Any, ...], dict[str, Any]], T]
DependsClass: TypeAlias = cast(
    type | Sequence[type],
    FromDishka | _FromComponent,
)
InjectDecorator: TypeAlias = Callable[[Callable[..., Any]], Any]


def default_parse_dependency(
        parameter: Parameter,
        hint: Any,
) -> DependencyKey | None:
    """Resolve dependency type or return None if it is not a dependency."""
    if get_origin(hint) is not Annotated:
        return None
    args = get_args(hint)
    dep = next(
        (arg for arg in args if isinstance(arg, DependsClass)),
        None,
    )
    if not dep:
        return None
    if isinstance(dep, FromDishka | _FromComponent):  # type: ignore[arg-type]
        return DependencyKey(args[0], dep.component)
    else:
        return DependencyKey(args[0], DEFAULT_COMPONENT)


@overload
def wrap_injection(
        *,
        func: Callable[P, T],
        container_getter: ContainerGetter[Container],
        is_async: Literal[False] = False,
        remove_depends: bool = True,
        additional_params: Sequence[Parameter] = (),
        parse_dependency: DependencyParser = default_parse_dependency,
) -> Callable[P, T]:
    ...


@overload
def wrap_injection(
        *,
        func: Callable[P, T],
        container_getter: ContainerGetter[AsyncContainer],
        is_async: Literal[True] = True,
        remove_depends: bool = True,
        additional_params: Sequence[Parameter] = (),
        parse_dependency: DependencyParser = default_parse_dependency,
) -> Callable[P, T]:
    ...


def wrap_injection(
        *,
        func: Callable[P, T],
        container_getter: ContainerGetter[Container | AsyncContainer],
        is_async: bool = False,
        remove_depends: bool = True,
        additional_params: Sequence[Parameter] = (),
        parse_dependency: DependencyParser = default_parse_dependency,
) -> Callable[P, T]:
    hints = get_type_hints(func, include_extras=True)
    func_signature = signature(func)

    dependencies = {}
    for name, param in func_signature.parameters.items():
        hint = hints.get(name, Any)
        dep = parse_dependency(param, hint)
        if dep is None:
            continue
        dependencies[name] = dep

    if remove_depends:
        new_annotations = {
            name: hint
            for name, hint in hints.items()
            if name not in dependencies
        }
        new_params = [
            param
            for name, param in func_signature.parameters.items()
            if name not in dependencies
        ]
    else:
        new_annotations = hints.copy()
        new_params = list(func_signature.parameters.copy().values())

    auto_injected_func: Callable[P, T | Awaitable[T]]
    if additional_params:
        new_params.extend(additional_params)
        for param in additional_params:
            new_annotations[param.name] = param.annotation

    if is_async:
        auto_injected_func = _async_injection_wrapper(
            # typing.cast is needed because the function must be async
            func=cast(Callable[P, Awaitable[T]],func),
            dependencies=dependencies,
            additional_params=additional_params,
            container_getter=cast(
                ContainerGetter[AsyncContainer], container_getter,
            ),
        )
    else:
        auto_injected_func = _sync_injection_wrapper(
            func=func,
            dependencies=dependencies,
            additional_params=additional_params,
            container_getter=cast(
                ContainerGetter[Container], container_getter,
            ),
        )

    auto_injected_func.__dishka_injected__ = True  # type: ignore[attr-defined]
    auto_injected_func.__name__ = func.__name__
    auto_injected_func.__qualname__ = func.__qualname__
    auto_injected_func.__doc__ = func.__doc__
    auto_injected_func.__annotations__ = new_annotations
    auto_injected_func.__signature__ = Signature(  # type: ignore[attr-defined]
        parameters=new_params,
        return_annotation=func_signature.return_annotation,
    )
    return cast(Callable[P, T], auto_injected_func)


def is_dishka_injected(func: Callable[..., Any]) -> bool:
    return hasattr(func, "__dishka_injected__")


def _async_injection_wrapper(
        container_getter: ContainerGetter[AsyncContainer],
        additional_params: Sequence[Parameter],
        dependencies: dict[str, DependencyKey],
        func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    if isasyncgenfunction(func):
        async def auto_injected_func(*args: P.args, **kwargs: P.kwargs) -> T:
            container = container_getter(args, kwargs)
            for param in additional_params:
                kwargs.pop(param.name)
            solved = {
                name: await container.get(
                    dep.type_hint, component=dep.component,
                )
                for name, dep in dependencies.items()
            }
            async for message in func(*args, **kwargs, **solved):
                yield message
    else:
        async def auto_injected_func(*args: P.args, **kwargs: P.kwargs) -> T:
            container = container_getter(args, kwargs)
            for param in additional_params:
                kwargs.pop(param.name)
            solved = {
                name: await container.get(
                    dep.type_hint, component=dep.component,
                )
                for name, dep in dependencies.items()
            }
            return await func(*args, **kwargs, **solved)

    return auto_injected_func


def _sync_injection_wrapper(
        container_getter: ContainerGetter[Container],
        additional_params: Sequence[Parameter],
        dependencies: dict[str, DependencyKey],
        func: Callable[P, T],
) -> Callable[P, T]:
    if isgeneratorfunction(func):
        def auto_injected_func(*args: P.args, **kwargs: P.kwargs) -> T:
            container = container_getter(args, kwargs)
            for param in additional_params:
                kwargs.pop(param.name)
            solved = {
                name: container.get(dep.type_hint, component=dep.component)
                for name, dep in dependencies.items()
            }
            yield from func(*args, **kwargs, **solved)
    else:
        def auto_injected_func(*args: P.args, **kwargs: P.kwargs) -> T:
            container = container_getter(args, kwargs)
            for param in additional_params:
                kwargs.pop(param.name)
            solved = {
                name: container.get(dep.type_hint, component=dep.component)
                for name, dep in dependencies.items()
            }
            return func(*args, **kwargs, **solved)

    return auto_injected_func
