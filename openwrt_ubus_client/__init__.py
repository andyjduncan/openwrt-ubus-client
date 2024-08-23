import time

import httpx


class OpenWrtUbusClient:

    def __init__(self, host: str, username: str, password: str):
        self._headers = {'content-type': 'application/json'}
        self._host = host
        self._url = f"http://{host}/ubus"
        self._username = username
        self._password = password
        self._call_id = (i for i in range(1, 10 ** 100))
        self._commands = []
        self._token_expiry = int(time.time())
        self._session_id = None

    async def refresh_session(self):
        auth_payload = {
            "jsonrpc": "2.0",
            "id": next(self._call_id),
            "method": "call",
            "params": [
                "00000000000000000000000000000000",
                "session",
                "login",
                {
                    "username": self._username,
                    "password": self._password,
                    "timeout": 600
                }
            ]
        }
        async with httpx.AsyncClient() as client:
            raw_auth_response = await client.post(self._url, json=auth_payload, headers=self._headers)

        auth_response = raw_auth_response.json()

        result_code = auth_response["result"][0]

        if result_code == 6:
            raise BadCredentialsError

        self._session_id = auth_response["result"][1]["ubus_rpc_session"]
        self._token_expiry = int(time.time()) + auth_response["result"][1]["expires"]

    def add_command(self, path, procedure, params={}) -> int:
        command_id = next(self._call_id)
        self._commands.append({
            "id": command_id,
            "path": path,
            "procedure": procedure,
            "params": params
        })
        return command_id

    async def send_commands(self) -> dict:
        if not self._commands:
            return {}
        # Strictly speaking, the timeout is refreshed per request, but we'll get a fresh one anyway.
        if self._token_expiry - int(time.time()) < 15:
            await self.refresh_session()

        def convert(c):
            return {
                "jsonrpc": "2.0",
                "id": c["id"],
                "method": "call",
                "params": [
                    self._session_id,
                    c["path"],
                    c["procedure"],
                    c["params"]
                ]
            }

        request = list(map(convert, self._commands))

        self._commands.clear()

        async with httpx.AsyncClient() as client:
            raw_response = await client.post(self._url, json=request, headers=self._headers)

        response = raw_response.json()

        def map_result(res: dict):
            if "result" in res:
                success_result = None
                if len(res["result"]) > 1:
                    success_result = res["result"][1]
                return {
                    "status": res["result"][0],
                    "result": success_result
                }
            else:
                return {
                    "status": res["error"]["code"],
                    "error": res["error"]["message"]
                }

        result = {}

        for r in response:
            result[r["id"]] = map_result(r)

        return result


class BadCredentialsError(Exception):
    pass
