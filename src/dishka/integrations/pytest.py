from inspect import Parameter
from typing import Any

import pytest

from dishka import Container
from .base import wrap_injection

CONTAINER_NAME = "dishka_container"


def dishka_fixture(name: str, cls: Any):
    def temp_fixture(dishka_container):
        return dishka_container.get(cls)

    temp_fixture.__name__ = name
    return pytest.fixture(temp_fixture)


def inject(func):
    additional_params = [Parameter(
        name=CONTAINER_NAME,
        annotation=Container,
        kind=Parameter.KEYWORD_ONLY,
    )]
    return wrap_injection(
        func=func,
        remove_depends=True,
        container_getter=lambda _, p: p[CONTAINER_NAME],
        additional_params=additional_params,
        is_async=False,
    )
