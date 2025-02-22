import pytest

from dishka import FromDishka, Provider, Scope, make_container
from dishka.integrations.pytest import dishka_fixture, inject


@pytest.fixture(scope="session")
def dishka_container():
    provider = Provider(scope=Scope.APP)
    provider.provide(source=lambda: 42, provides=int)
    container = make_container(provider)
    yield container
    container.close()


@inject
def test_inject_test(value: FromDishka[int]) -> None:
    assert value == 42


@pytest.fixture()
@inject
def some_fixture(value: FromDishka[int]):
    return value


def test_inject_fixture(some_fixture) -> None:
    assert some_fixture == 42


explicit_fixture = dishka_fixture("explicit_fixture", int)


def test_explicit_fixture(explicit_fixture) -> None:
    assert explicit_fixture == 42
