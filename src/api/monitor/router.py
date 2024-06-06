from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from src.dependencies import get_api_key
from src.schema import MonitorStreamSchema

router = APIRouter()


@router.get("/healthcheck")
async def health_check(_=Depends(get_api_key)) -> Dict:
    """Server heart beat status"""
    return {"status": "OK"}


@router.get("/monitors")
async def get_monitor_info() -> List[MonitorStreamSchema]:
    """Get info about available monitors"""

    from src.main import monitor_processor

    monitors = monitor_processor.get_monitors()
    if not monitors:
        return []
    return [
        MonitorStreamSchema(
            monitor_id=monitor.monitor_id,
            stream_url=monitor.stream_playlist,
            wss_url=f"ws/{monitor.monitor_id}",
        )
        for monitor in monitors
    ]


@router.get("/monitors/{minitor_id}")
async def get_monitor_info(monitor_id: str) -> MonitorStreamSchema:
    """Get info about monitor"""

    from src.main import monitor_processor

    monitor = monitor_processor.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")
    return MonitorStreamSchema(
        monitor_id=monitor.monitor_id,
        stream_url=monitor.stream_playlist,
        wss_url=f"ws/{monitor_id}",
    )
