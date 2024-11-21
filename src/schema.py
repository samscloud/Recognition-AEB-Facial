from datetime import datetime, timedelta
from enum import Enum
from typing import Dict

from pydantic import BaseModel


class MonitorStateEnum(str, Enum):
    """Enum for monitor state"""

    start = "start"
    record = "record"


class OrganizationCameraSchema(BaseModel):
    id: int
    name: str
    monitor_id: str
    user_name: str
    password: str
    ip_address: str
    port: int
    path: str

    stream_playlist: str = None


class TrackingUsersSchema(BaseModel):
    id: int
    tracking_enabled: bool


class MonitorStreamSchema(BaseModel):
    monitor_id: str
    stream_url: str
    wss_url: str


class CCTVCamera(BaseModel):
    monitor_id: str
    username: str
    password: str
    ip: str
    stream: str
    monitor_stream_url: str
    location_id: int

    organization_id: int
    organization_slug: str

    shinobi_email: str
    shinobi_password: str
    state: MonitorStateEnum = MonitorStateEnum.start

    users: Dict

    live_tracking: Dict
    face_tracking: Dict

    is_deleted: bool = False


class ManageUserTrackingStatusSchema(BaseModel):
    status: bool = False


class RegisteredUserCache(BaseModel):
    user: int
    camera: int
    monitor_id: str
    match_score: float
    image_url: str
    appeared_at: datetime
    disappeared_at: datetime = None
    is_saved: bool = False


class UserLiveTrackingRecordSchema(BaseModel):
    user: int
    camera: int
    monitor_id: str
    start_time: datetime
    end_time: datetime = None


class NewCameraRequestSchema(BaseModel):
    name: str
    host: str
    port: int
    path: str
    username: str
    password: str


class NewCameraResponseSchema(BaseModel):
    monitor_id: str


class MonitorSchema(BaseModel):
    id: str
    group_id: str
    type: str
    ext: str
    protocol: str
    host: str
    path: str
    port: int
    fps: int
    mode: str
    width: int
    height: int
    currently_watching: int
    status: str
    code: str
    sub_stream_active: bool
    snapshot: str
    streams: list[str]


class MonitorRegisterSchema(BaseModel):
    location_id: int
    monitor_id: str
    organization_id: int
    organization_slug: str


class VideoSchema(BaseModel):
    monitor_id: str
    filename: str
    start: str
    end: str
    video_url: str

    @property
    def validate_duration(self) -> bool:
        start = datetime.strptime(self.start, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(self.end, "%Y-%m-%dT%H:%M:%SZ")

        return end - start < timedelta(seconds=2)
