from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette import status

router = APIRouter()


@router.get("/streams/{monitor_id}/{filename}")
async def get_stream_playlist(monitor_id: str, filename: str):
    """
    Return file for streaming
    :param monitor_id: id of monitor
    :param filename: name of file
    :return: FileResponse
    """
    from src.main import monitor_processor

    monitor = monitor_processor.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")

    return FileResponse(f"src/streams/{monitor.monitor_id}/{filename}")
