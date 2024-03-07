from typing import Optional, Dict

import requests
from aiohttp import ClientSession

from src.config import settings


class Shinobi:
    def __init__(self, auth_key: str, group_key: str):
        self.auth_key = auth_key
        self.group_key = group_key
        self.base_url = settings.SHINOBI_URL

    async def get_monitor_stream_url(self, monitor_id: str) -> str:
        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}"
        response = await self._send_request(url)
        if not response:
            return ""

        stream_url = response[0]["streams"][0]
        return f"{self.base_url}{stream_url}"

    async def start_monitor_recording(self, monitor_id: str) -> bool:
        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/record"
        response = await self._send_request(url)
        return response is not None

    async def stop_monitor_recording(self, monitor_id: str) -> bool:
        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/start"
        response = await self._send_request(url)
        return response is not None

    async def _send_request(self, url: str) -> Optional[Dict]:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    response_body = await response.json()
                    return response_body

                return None

    def start_monitor_recording_sync(self, monitor_id: str) -> bool:
        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/record"
        response = requests.get(url)
        if response.status_code == 200:
            return True

        print(response.json())
        return False

    def stop_monitor_recording_sync(self, monitor_id: str) -> bool:
        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/start"
        response = requests.get(url)
        if response.status_code == 200:
            return True

        print(response.json())
        return False
