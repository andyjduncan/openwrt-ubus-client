import asyncio
import json
import os

from openwrt_ubus_client.client import OpenWrtUbusClient


async def main():
    host = os.environ["HOST"]

    client = OpenWrtUbusClient(host, os.environ["USERNAME"], os.environ["PASSWORD"])

    board_id = client.add_command(path="system", procedure="board") # returns system board info
    info_id = client.add_command(path="system", procedure="info") # returns os info
    wifi_id = client.add_command("luci-rpc", "getNetworkDevices") # returns all network devices
    session_id = client.add_command(path="session", procedure="list") # returns error due to ubus permissions

    result = await client.send_commands()

    print(json.dumps(result[board_id], indent=2))
    print(json.dumps(result[info_id], indent=2))
    print(json.dumps(result[wifi_id], indent=2))
    print(json.dumps(result[session_id], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
