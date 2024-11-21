import json
from typing import Any

import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime as dt, datetime

from src.config import settings
from src.services.shinobi import Shinobi


class OngoingIncidentRequest(BaseModel):
    type: str = "gun"
    datetime: dt = Field(default_factory=dt.now)
    camera_id: int
    camera_stream_url: str = Field(default="https://google.com")
    payload: dict = Field(default={"hello": "world"})


class NewIncidentCameraRequest(BaseModel):
    zone_cctv_id: int


class IncidentService:
    def __init__(self, shinobi_client: Shinobi):
        self.shinobi_client = shinobi_client

        self.ongoing_incident: int | None = None
        self.start_datetime: datetime | None = None
        self.last_event_datetime: datetime | None = None
        self.active_camera: int | None = None
        self.creation_in_progress: bool = False

        self.incident_url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/emergency-notification/"

        self.ws_connections = None

    async def track_incident(self, monitor_id: str, camera_id: int, message: str):
        print(json.loads(message))

        if message:
            payload_data = json.loads(message)
            if payload_data["event"] == "INCIDENT_END":
                return await self.end_ongoing_incident(monitor_id, message)

        if not self.ongoing_incident and not self.creation_in_progress:
            self.creation_in_progress = True
            await self.create_new_alert(monitor_id, camera_id, message)
            self.creation_in_progress = False

        elif self.ongoing_incident and camera_id == self.active_camera:
            await self.update_ongoing_alert(monitor_id, camera_id)
            self.active_camera = camera_id

        print("Ongoing incident! Nothing to do")

    async def create_new_alert(self, monitor_id: str, camera_id: int, message: str):
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        payload = OngoingIncidentRequest(
            camera_id=camera_id,
        )

        response_data = await self._request(
            self.incident_url, payload.model_dump(mode="json")
        )
        if not response_data:
            print("cant create alert record in DB")
            return

        self.ongoing_incident = response_data.get("id")
        self.start_datetime = payload.datetime
        self.active_camera = camera_id

        try:
            self.shinobi_client.start_monitor_recording_sync(monitor_id)
        except Exception as e:
            print(f"monitor recording start: {e}")

        msg = json.dumps(
            {
                "event": "OBJECT_DETECTED",
                "objects_detected": True,
                "payload": {
                    "object_type": "gun",
                    "camera_id": camera_id,
                    "incident_id": self.ongoing_incident,
                    "camera_status_changed": "record",
                },
            }
        )

        wss = self.ws_connections.get(monitor_id)
        if wss:
            print("send websocket about new incident")
            await wss[0].send_text(msg)

    async def update_ongoing_alert(self, monitor_id: str, camera_id: int):
        print(f"Add new camera: send and send ws notification")
        try:
            payload = NewIncidentCameraRequest(
                zone_cctv_id=camera_id,
            )
            url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/incidents/cctv-incidents/{self.ongoing_incident}/history/"
            await self._request(url, payload.model_dump(mode="json"))

            try:
                self.shinobi_client.start_monitor_recording_sync(monitor_id)
            except Exception as e:
                print(f"monitor recording start: {e}")
        except Exception as e:
            print(e)

    async def end_ongoing_incident(self, monitor_id: str, message: str):
        url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/incidents/cctv-incidents/{self.ongoing_incident}/end/"
        await self._request(url, {})
        wss = self.ws_connections.get(monitor_id)

        try:
            self.shinobi_client.stop_monitor_recording_sync(monitor_id)
        except Exception as e:
            print(f"monitor recording start: {e}")
        self.ongoing_incident = None

    async def _request(self, url: str, json_payload: dict[str, Any]) -> dict | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=json_payload) as response:
                    if response.status < 202:
                        return await response.json()
                    return None
        except Exception as e:
            print(e)
