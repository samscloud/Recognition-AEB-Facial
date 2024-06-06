import logging
from typing import Optional, Dict, List
from urllib.parse import urljoin

from aiohttp import ClientSession

from src.config import settings
from src.schema import OrganizationCameraSchema, TrackingUsersSchema


class MainBEException(Exception):
    pass


class MainServer:
    def __init__(self):
        self.organization_id = settings.ORGANIZATION_ID
        self.organization_slug = settings.ORGANIZATION_SLUG

        self.api_base_url = settings.BACKEND_API_URL
        self.api_key = settings.BACKEND_API_KEY

    @staticmethod
    async def __send_get_request(url: str) -> Optional[Dict]:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logging.error(f"Error fetching: {await response.text()}")

    async def get_monitors(self) -> List[OrganizationCameraSchema]:
        url = f"https://api.samscloud.io/api/v2/organizations/{self.organization_slug}/cctv/monitors/"

        response = await self.__send_get_request(url)
        if response is None:
            raise MainBEException

        return [OrganizationCameraSchema(**obj) for obj in response]

    async def get_tracking_users(self) -> List[TrackingUsersSchema]:
        url = f"https://api.samscloud.io/api/v2/organizations/{self.organization_slug}/cctv/user-tracking/"

        response = await self.__send_get_request(url)
        if response is None:
            raise MainBEException

        return [TrackingUsersSchema(**obj) for obj in response]
