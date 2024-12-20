#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import random
import uuid

import pytest
import tornado.websocket
from unittest.mock import patch
from reactivex.scheduler.eventloop import IOLoopScheduler
from tornado import ioloop

from tests.protocols.helpers import \
    client_test_on_event, \
    client_test_read_property, \
    client_test_write_property, \
    client_test_invoke_action, \
    client_test_invoke_action_error, \
    client_test_on_property_change_error
from tests.utils import run_test_coroutine
from wotpy.protocols.exceptions import ProtocolClientException, ClientRequestTimeout
from wotpy.protocols.ws.client import WebsocketClient
from wotpy.wot.td import ThingDescription


def test_read_property(websocket_servient):
    """The Websockets client can read properties."""

    client_test_read_property(websocket_servient, WebsocketClient)


def test_read_property_unknown(websocket_servient):
    """The Websockets client raises an error when attempting to read an unknown property."""

    exposed_thing = next(websocket_servient.exposed_things)
    td = ThingDescription.from_thing(exposed_thing.thing)

    async def test_coroutine():
        ws_client = WebsocketClient()

        with pytest.raises(ProtocolClientException):
            await ws_client.read_property(td, uuid.uuid4().hex)

    run_test_coroutine(test_coroutine)


def test_write_property(websocket_servient):
    """The Websockets client can write properties."""

    client_test_write_property(websocket_servient, WebsocketClient)


def test_invoke_action(websocket_servient):
    """The Websockets client can invoke actions."""

    client_test_invoke_action(websocket_servient, WebsocketClient)


def test_invoke_action_error(websocket_servient):
    """Errors raised by Actions are propagated propertly by the WebSockets binding client."""

    client_test_invoke_action_error(websocket_servient, WebsocketClient)


def test_on_event(websocket_servient):
    """The Websockets client can observe events."""

    client_test_on_event(websocket_servient, WebsocketClient)


def test_on_property_change(websocket_servient):
    """The Websockets client can observe property changes."""

    exposed_thing = next(websocket_servient.exposed_things)
    td = ThingDescription.from_thing(exposed_thing.thing)

    async def test_coroutine():
        ws_client = WebsocketClient()

        prop_names = list(td.properties.keys())
        prop_name_01 = prop_names[0]
        prop_name_02 = prop_names[1]

        obsv_01 = ws_client.on_property_change(td, prop_name_01)
        obsv_02 = ws_client.on_property_change(td, prop_name_02)

        prop_values_01 = [uuid.uuid4().hex for _ in range(10)]
        prop_values_02 = [uuid.uuid4().hex for _ in range(90)]

        loop = asyncio.get_running_loop()
        future_values_01 = {key: loop.create_future() for key in prop_values_01}
        future_values_02 = {key: loop.create_future() for key in prop_values_02}

        future_conn_01 = loop.create_future()
        future_conn_02 = loop.create_future()

        def build_on_next(fut_conn, fut_vals):
            def on_next(ev):
                if not fut_conn.done():
                    fut_conn.set_result(True)

                if ev.data.value in fut_vals:
                    fut_vals[ev.data.value].set_result(True)

            return on_next

        on_next_01 = build_on_next(future_conn_01, future_values_01)
        on_next_02 = build_on_next(future_conn_02, future_values_02)

        loop = ioloop.IOLoop.current()
        scheduler = IOLoopScheduler(loop)
        subscription_01 = obsv_01.subscribe(on_next_01, scheduler=scheduler)
        subscription_02 = obsv_02.subscribe(on_next_02, scheduler=scheduler)

        while not future_conn_01.done() or not future_conn_02.done():
            await exposed_thing.write_property(prop_name_01, uuid.uuid4().hex)
            await exposed_thing.write_property(prop_name_02, uuid.uuid4().hex)
            await asyncio.sleep(0)

        assert len(prop_values_01) < len(prop_values_02)

        for idx in range(len(prop_values_01)):
            await exposed_thing.write_property(prop_name_01, prop_values_01[idx])
            await exposed_thing.write_property(prop_name_02, prop_values_02[idx])

        await asyncio.gather(*future_values_01.values())

        assert next(fut for fut in future_values_02.values() if not fut.done())

        subscription_01.dispose()

        for val in prop_values_02[len(prop_values_01):]:
            await exposed_thing.write_property(prop_name_02, val)

        await asyncio.gather(*future_values_02.values())
            
        subscription_02.dispose()

    run_test_coroutine(test_coroutine)


def test_on_property_change_error(websocket_servient):
    """Errors that arise in the middle of an ongoing Property
    observation are propagated to the subscription as expected."""

    client_test_on_property_change_error(websocket_servient, WebsocketClient)


# noinspection PyUnusedLocal
def _condition_coro(*args, **kwargs):
    """Coroutine mock side effect that returns a Condition that is never notified."""

    async def _coro():
        return asyncio.Condition()

    return _coro()


def test_timeout_read_property(websocket_servient):
    """Timeouts can be defined on Property reads."""

    # noinspection PyUnresolvedReferences
    with patch.object(WebsocketClient, '_send_message', _condition_coro):
        with pytest.raises(ClientRequestTimeout):
            client_test_read_property(websocket_servient, WebsocketClient, timeout=random.random())


def test_timeout_write_property(websocket_servient):
    """Timeouts can be defined on Property writes."""

    # noinspection PyUnresolvedReferences
    with patch.object(WebsocketClient, '_send_message', _condition_coro):
        with pytest.raises(ClientRequestTimeout):
            client_test_write_property(websocket_servient, WebsocketClient, timeout=random.random())


def test_timeout_invoke_action(websocket_servient):
    """Timeouts can be defined on Action invocations."""

    # noinspection PyUnresolvedReferences
    with patch.object(WebsocketClient, '_send_message', _condition_coro):
        with pytest.raises(ClientRequestTimeout):
            client_test_invoke_action(websocket_servient, WebsocketClient, timeout=random.random())
