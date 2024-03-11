import base64
import io
from typing import Optional, Dict, List

import aioboto3
import boto3
import face_recognition
import numpy as np
from aiohttp import ClientSession
from PIL import Image

from src.config import settings
from src.schema import CCTVCamera
from src.utils.shinobi import Shinobi


class FaceRecognitionInit:
    """
    Get all required info for face recognition process:
    - list of available monitors with stream url
    - users with datasets
    """

    def __init__(self, organization_slug: str, be_api_key: str, be_url: str):
        self.organization_slug = organization_slug
        self.be_api_key = be_api_key
        self.be_url = be_url

        self.shinobi_client = None

    async def fetch_organization_info(self) -> Optional[Dict]:
        url = f"{self.be_url}/{self.organization_slug}/cctv-info"

        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()

    def read_user_datasets(self, users_id: List[int]) -> Dict:
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        faces = {}

        for user_id in users_id:
            prefix = f"{self.organization_slug}/{user_id}"
            result = s3.list_objects_v2(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Prefix=prefix)
            if "Contents" not in result.keys():
                continue

            encoded_data = []
            for obj in result["Contents"]:
                blob = io.BytesIO()
                s3.download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, obj.get("Key"), blob)

                blob.seek(0)
                image = Image.open(blob).convert("RGB")
                image_np = np.array(image)
                encoded_data.append(
                    face_recognition.face_encodings(image_np)[0]
                )
                blob.close()

            faces[user_id] = encoded_data

        return faces

    async def get_monitors_info(self, monitors: List[Dict]):
        for monitor in monitors:
            monitor["stram_url"] = await self.shinobi_client.get_monitor_stream_url(monitor.get("monitor_id"))

    async def execute(self) -> List[CCTVCamera]:
        organization_info = await self.fetch_organization_info()
        if not organization_info:
            raise Exception("Organization not found")

        print(f"organization: {organization_info}")

        faces = {}
        if organization_info.get("users"):
            faces = self.read_user_datasets([item.get("id") for item in organization_info["users"]])

        # Stream urls from shinobi
        self.shinobi_client = Shinobi(organization_info["shinobi_authkey"], organization_info["shinobi_group_key"])
        await self.get_monitors_info(organization_info.get("cctv"))

        print(f'monitor info: {organization_info.get("cctv")}')

        # Build response
        return [
            CCTVCamera(
                monitor_id=monitor.get("monitor_id"),
                monitor_stream_url=monitor.get("stram_url"),
                location_id=monitor.get("id"),

                organization_id=organization_info.get("id"),
                organization_slug=self.organization_slug,
                shinobi_authkey=organization_info.get("shinobi_authkey"),
                shinobi_group_key=organization_info.get("shinobi_group_key"),

                users=faces,
                live_tracking={},
                face_tracking={
                    user_id: {} for user_id in faces.keys()
                }
            )
            for monitor in organization_info["cctv"]
        ]

