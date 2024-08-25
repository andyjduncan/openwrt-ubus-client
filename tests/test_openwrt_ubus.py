import random
import string

import pytest
import time_machine
from pytest_httpx import HTTPXMock

from openwrt_ubus_client.client import OpenWrtUbusClient, BadCredentialsError


@pytest.fixture
def host():
    return random_string(10)


@pytest.fixture
def username():
    return random_string(10)


@pytest.fixture
def password():
    return random_string(10)


@pytest.fixture
def session_id():
    return random_string(10)


@pytest.fixture
def path():
    return random_string(5)


@pytest.fixture
def procedure():
    return random_string(5)


@pytest.mark.asyncio
async def test_creates_new_login_session(httpx_mock: HTTPXMock, host, username, password):
    httpx_mock.add_response(
        method="POST",
        url=f"http://{host}/ubus",
        match_headers={'content-type': 'application/json'},
        match_json=[login_params(1, username, password)],
        json=[login_response(1, random_string(10))]
    )

    client = OpenWrtUbusClient(host, username, password)

    await client.refresh_session()


@pytest.mark.asyncio
async def test_increments_command_id(httpx_mock: HTTPXMock, host, username, password):
    httpx_mock.add_response(
        match_json=[login_params(1, username, password)],
        json=[login_response(1, random_string(10))]
    )
    httpx_mock.add_response(
        match_json=[login_params(2, username, password)],
        json=[login_response(2, random_string(10))]
    )

    client = OpenWrtUbusClient(host, username, password)

    await client.refresh_session()
    await client.refresh_session()


@pytest.mark.asyncio
async def test_raises_an_error_on_bad_credentials(httpx_mock: HTTPXMock, host, username, password):
    httpx_mock.add_response(
        match_json=[login_params(1, username, password)],
        json=[{
            "jsonrpc": "2.0",
            "id": 1,
            "result": [
                6
            ]
        }]
    )

    client = OpenWrtUbusClient(host, username, password)

    with pytest.raises(BadCredentialsError):
        await client.refresh_session()


@pytest.mark.asyncio
async def test_sends_a_command_to_ubus(httpx_mock: HTTPXMock, host, username, password, session_id, path, procedure):
    auth_call = 2  # Queued commands get their ids before the token refresh
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    httpx_mock.add_response(
        method="POST",
        url=f"http://{host}/ubus",
        match_headers={'content-type': 'application/json'},
        match_json=[call_request(1, session_id, path, procedure)],
        json=[]
    )

    client = OpenWrtUbusClient(host, username, password)

    client.add_command(path, procedure)

    await client.send_commands()


@pytest.mark.asyncio
async def test_does_not_repeat_commands(httpx_mock: HTTPXMock, host, username, password, session_id, path, procedure):
    auth_call = 2  # Queued commands get their ids before the token refresh
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    httpx_mock.add_response(
        method="POST",
        url=f"http://{host}/ubus",
        match_headers={'content-type': 'application/json'},
        match_json=[call_request(1, session_id, path, procedure)],
        json=[]
    )

    client = OpenWrtUbusClient(host, username, password)

    client.add_command(path, procedure)

    await client.send_commands()
    await client.send_commands()


@pytest.mark.asyncio
async def test_command_responds_are_identified_by_id(httpx_mock: HTTPXMock, host, username, password, session_id):
    auth_call = 3  # Queued commands get their ids before the token refresh
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    path1 = random_string(5)
    procedure1 = random_string(5)
    path2 = random_string(5)
    procedure2 = random_string(5)

    httpx_mock.add_response(
        match_json=[
            call_request(1, session_id, path1, procedure1),
            call_request(2, session_id, path2, procedure2)
        ],
        json=[
            call_response(1, {
                "path": path1,
                "procedure": procedure1
            }),
            call_response(2, {
                "path": path2,
                "procedure": procedure2
            })
        ]
    )

    client = OpenWrtUbusClient(host, username, password)

    command_id1 = client.add_command(path1, procedure1)
    command_id2 = client.add_command(path2, procedure2)

    result = await client.send_commands()

    assert len(result) == 2
    assert result[command_id1] == {
        "status": 0,
        "result": {
            "path": path1,
            "procedure": procedure1
        }
    }
    assert result[command_id2] == {
        "status": 0,
        "result": {
            "path": path2,
            "procedure": procedure2
        }
    }


@pytest.mark.asyncio
async def test_maps_failed_commands_to_errors(httpx_mock: HTTPXMock, host, username, password, session_id, path,
                                              procedure):
    auth_call = 2
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    error_message = random_string(10)
    httpx_mock.add_response(
        match_json=[call_request(1, session_id, path, procedure)],
        json=[
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -1,
                    "message": error_message
                }
            }
        ]
    )

    client = OpenWrtUbusClient(host, username, password)

    command_id = client.add_command(path, procedure)

    result = await client.send_commands()

    assert result[command_id] == {
        "status": -1,
        "error": error_message
    }


@pytest.mark.asyncio
async def test_does_not_refresh_valid_token(httpx_mock: HTTPXMock, host, username, password, session_id, path,
                                            procedure):
    auth_call = 1
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    httpx_mock.add_response(
        match_json=[call_request(2, session_id, path, procedure)],
        json=[]
    )

    with time_machine.travel(0, tick=False) as traveller:
        client = OpenWrtUbusClient(host, username, password)

        await client.refresh_session()

        traveller.move_to(500)

        client.add_command(path, procedure)

        await client.send_commands()


@pytest.mark.asyncio
async def test_refreshes_expired_token(httpx_mock: HTTPXMock, host, username, password, session_id, path, procedure):
    auth_call = 1
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, session_id)]
    )

    auth_call = 3
    new_session_id = random_string(10)
    httpx_mock.add_response(
        match_json=[login_params(auth_call, username, password)],
        json=[login_response(auth_call, new_session_id)]
    )

    httpx_mock.add_response(
        match_json=[call_request(2, new_session_id, path, procedure)],
        json=[]
    )

    with time_machine.travel(0, tick=False) as traveller:
        client = OpenWrtUbusClient(host, username, password)

        await client.refresh_session()

        traveller.move_to(599)

        client.add_command(path, procedure)

        await client.send_commands()


def login_params(call_id, username, password):
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "call",
        "params": [
            "00000000000000000000000000000000",
            "session",
            "login",
            {
                "username": username,
                "password": password,
                "timeout": 600
            }
        ]
    }


def login_response(auth_call, session_id):
    return {
        "jsonrpc": "2.0",
        "id": auth_call,
        "result": [
            0,
            {
                "ubus_rpc_session": session_id,
                "expires": 600
            }
        ]
    }


def call_request(call, session_id, path, procedure, params={}):
    return {
        "jsonrpc": "2.0",
        "id": call,
        "method": "call",
        "params": [
            session_id,
            path,
            procedure,
            params
        ]
    }


def call_response(call_id, result):
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "result": [
            0,
            result
        ]
    }


def random_string(length):
    return ''.join(random.sample(string.ascii_lowercase, length))
