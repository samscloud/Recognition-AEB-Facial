import json
from asyncio import Queue
from typing import Any

import requests
from numpy import ndarray
from pydantic import BaseModel, Field
from datetime import datetime as dt, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import settings
from src.database import SessionLocal
from src.models import Incident
from src.processor.repository import create_incident, get_active_incident
from src.services.shinobi import Shinobi


class OngoingIncidentRequest(BaseModel):
    type: str = "gun"
    datetime: dt = Field(default_factory=dt.now)
    camera_id: str
    camera_stream_url: str = Field(default="https://google.com")
    payload: dict = Field(default={"hello": "world"})


class NewIncidentCameraRequest(BaseModel):
    zone_cctv_id: int


class IncidentTracking:

    def __init__(self, wss_queue: Queue, shinobi: Shinobi):
        self.ongoing_incident: int | None = None
        self.start_datetime: dt | None = None
        self.last_event_datetime: dt | None = None
        self.active_camera: int | None = None
        self.creation_in_progress: bool = False

        self.incident_url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/emergency-notification/"

        self.incident: Incident | None = None

        self.ws_connections = None
        self.wss_queue: Queue = wss_queue
        self.shinobi = shinobi

    def track(self, monitor_id: str, event: str, shooters: list[ndarray] | None = None, frame=None) -> int:
        stmt = select(Incident).where(Incident.is_active == True)

        db: Session = SessionLocal()
        self.incident: Incident | None = db.execute(stmt).scalars().first()
        if self.incident is None:
            self._create_new_incident(monitor_id, event, shooters)
            self.shinobi.start_monitor_recording_sync(monitor_id)
        else:
            print(f"incident is active!")
            if self.incident.active_monitor != monitor_id:
                print(f"camera changed!")
                self.update_ongoing_alert(monitor_id)
                try:
                    self.shinobi.start_monitor_recording_sync(monitor_id)
                    self.shinobi.stop_monitor_recording(self.incident.active_monitor)
                except Exception as e:
                    print(e)
            self.incident.last_update = datetime.now()
            self.incident.active_monitor = monitor_id
            db.commit()

        return self.incident.id

        # if message:
        #     payload_data = json.loads(message)
        #     if payload_data["event"] == "INCIDENT_END":
        #         return await self.end_ongoing_incident(monitor_id, message)

        # if not self.ongoing_incident and not self.creation_in_progress:
        #     self.creation_in_progress = True
        #     await self.create_new_alert(monitor_id, camera_id, message)
        #     self.creation_in_progress = False
        #
        # elif self.ongoing_incident and camera_id == self.active_camera:
        #     await self.update_ongoing_alert(monitor_id, camera_id)
        #     self.active_camera = camera_id
        #
        # print("Ongoing incident! Nothing to do")

    def _create_new_incident(self, monitor_id: str, event: str, shooters: list[ndarray] | None = None):
        print("send BE request")

        payload = OngoingIncidentRequest(
            camera_id=monitor_id,
        )

        response_data = self._request(
            self.incident_url, payload.model_dump(mode="json")
        )
        if not response_data:
            print("cant create alert record in DB")
            return

        # Save incident to db:
        self.incident: Incident = create_incident(
            response_data.get("id"),
            active_monitor=monitor_id,
            gun_detected=True,
            num_detected_shooters=0
        )

        msg = json.dumps(
            {
                "event": "OBJECT_DETECTED",
                "objects_detected": True,
                "payload": {
                    "object_type": "gun",
                    "camera_id": monitor_id,
                    "incident_id": self.incident.id,
                    "camera_status_changed": "record",
                },
            }
        )
        self.wss_queue.put({"monitor_id": monitor_id, "msg": msg})

    def update_ongoing_alert(self, monitor_id: str):
        print(f"Add new camera")
        try:
            payload = NewIncidentCameraRequest(
                zone_cctv_id=monitor_id,
            )
            url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/incidents/cctv-incidents/{self.incident.id}/history/"
            self._request(url, payload.model_dump(mode="json"))

            # TODO: activate shinoby
            # try:
            #     self.shinobi_client.start_monitor_recording_sync(monitor_id)
            # except Exception as e:
            #     print(f"monitor recording start: {e}")
        except Exception as e:
            print(e)

    def _request(self, url: str, json_payload: dict[str, Any]) -> dict | None:
        try:
            response = requests.post(url, json=json_payload)
            if response.status_code < 202:
                return response.json()
            return None
        except Exception as e:
            print(e)


