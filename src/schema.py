from datetime import datetime
from enum import Enum
from typing import Dict

from pydantic import BaseModel


class MonitorStateEnum(str, Enum):
    """Enum for monitor state"""

    start = "start"
    record = "record"


class CCTVCamera(BaseModel):
    monitor_id: str
    monitor_stream_url: str
    location_id: int

    organization_id: int
    organization_slug: str

    shinobi_authkey: str
    shinobi_group_key: str
    state: MonitorStateEnum = MonitorStateEnum.start

    users: Dict

    live_tracking: Dict
    face_tracking: Dict


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

