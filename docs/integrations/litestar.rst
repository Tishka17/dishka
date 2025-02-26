.. _litestar:

Litestar
===========================================

Though it is not required, you can use dishka-litestar integration. It features:

* automatic REQUEST scope management using middleware
* passing ``Request`` object as a context data to providers for **HTTP** requests
* injection of dependencies into handler function using decorator


How to use
****************

1. Import

..  code-block:: python

    from dishka.integrations.litestar import (
        FromDishka,
        LitestarProvider,
        inject,
        setup_dishka,
        DishkaRouter,
    )
    from dishka import make_async_container, Provider, provide, Scope

2. Create provider. You can use ``litestar.Request`` as a factory parameter to access on REQUEST-scope

.. code-block:: python

    class YourProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def create_x(self, request: Request) -> X:
             ...


3. Mark those of your handlers parameters which are to be injected with ``FromDishka[]`` and decorate them using ``@inject``

.. code-block:: python

    @router.get('/')
    @inject
    async def endpoint(
        request: str, gateway: FromDishka[Gateway],
    ) -> Response:
        ...

3a. *(optional)* Set route class to each of your fastapi routers to enable automatic injection (it works only for HTTP, not for websockets)

.. code-block:: python

    @router.get('/')
    async def endpoint(
        request: str, gateway: FromDishka[Gateway],
    ) -> Response:
        ...

    r = DishkaRouter('', route_handlers=[endpoint])
    app = Litestar(route_handlers=[r])


4. *(optional)* Use ``LitestarProvider()`` when creating container if you are going to use ``litestar.Request`` in providers.

.. code-block:: python

    container = make_async_container(YourProvider(), LitestarProvider())


5. *(optional)* Setup lifespan to close container on app termination

.. code-block:: python

    @asynccontextmanager
    async def lifespan(app: Litestar):
        yield
        await app.state.dishka_container.close()

    app = Litestar([endpoint], lifespan=[lifespan])


6. Setup dishka integration.

.. code-block:: python

    setup_dishka(container=container, app=app)


Websockets
**********************

.. include:: _websockets.rst

In litestar, your view function is called once per event,
and there is no way to determine if it is an http or websocket handler.
Therefore, you should use the special ``inject_websocket`` decorator for websocket handlers.
Also decorator can be only used to retrieve SESSION-scoped objects.
To achieve REQUEST-scope you can enter in manually:

.. code-block:: python

    @websocket_listener("/")
    @inject_websocket
    async def get_with_request(
        a: FromDishka[A],  # object with Scope.SESSION
        container: FromDishka[AsyncContainer],  # container for Scope.SESSION
        data: dict[str, str]
    ) -> dict[str, str]:
        # enter the nested scope, which is Scope.REQUEST
        async with container() as request_container:
            b = await request_container.get(B)  # object with Scope.REQUEST
        return {"key": "value"}

or with class-based handler:

.. code-block:: python

    class Handler(WebsocketListener):
        path = "/"

        @inject_websocket
        async def on_receive(
            a: FromDishka[A],  # object with Scope.SESSION
            container: FromDishka[AsyncContainer],  # container for Scope.SESSION
            data: dict[str, str]
        ) -> dict[str, str]:
            async with container() as request_container:
                b = await request_container.get(B)  # object with Scope.REQUEST
            return {"key": "value"}
