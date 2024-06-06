from pydantic import BaseModel


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


class MonitorStreamSchema(BaseModel):
    monitor_id: str
    stream_url: str
    wss_url: str
