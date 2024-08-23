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
        auth_call_id = next(self._call_id)
        auth_request = await self.map_commands("00000000000000000000000000000000", [
            {
                "id": auth_call_id,
                "path": "session",
                "procedure": "login",
                "params": {
                    "username": self._username,
                    "password": self._password,
                    "timeout": 600
                }
            }
        ])

        auth_response = await self.send_request(auth_request)

        auth_result = await self.map_response(auth_response)

        result_code = auth_result[auth_call_id]["status"]

        if result_code == 6:
            raise BadCredentialsError

        self._session_id = auth_result[auth_call_id]["result"]["ubus_rpc_session"]
        self._token_expiry = int(time.time()) + auth_result[auth_call_id]["result"]["expires"]

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

        await self.check_token_expiry()

        request = await self.map_commands(self._session_id, self._commands)

        response = await self.send_request(request)

        return await self.map_response(response)

    async def check_token_expiry(self):
        # Strictly speaking, the timeout is refreshed per request, but we'll get a fresh one anyway.
        if self._token_expiry - int(time.time()) < 15:
            await self.refresh_session()

    async def send_request(self, request):
        async with httpx.AsyncClient() as client:
            raw_response = await client.post(self._url, json=request, headers=self._headers)
        response = raw_response.json()

        return response

    @staticmethod
    async def map_commands(session_id, commands):
        def convert(c):
            return {
                "jsonrpc": "2.0",
                "id": c["id"],
                "method": "call",
                "params": [
                    session_id,
                    c["path"],
                    c["procedure"],
                    c["params"]
                ]
            }

        request = list(map(convert, commands))
        commands.clear()
        return request

    @staticmethod
    async def map_response(response):
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
