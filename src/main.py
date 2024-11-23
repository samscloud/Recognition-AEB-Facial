import logging
from queue import Queue

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from src.config import settings, app_configs
from src.dependencies import get_api_key
from src.main_server import MainServer
from src.monitor import MonitorProcessor
from src.api.files.router import router as file_router
from src.processor.wss_notificator import WSSNotificator
from src.recorgnition.face_detections import FaceRecognition
from src.schema import (
    NewCameraRequestSchema,
    NewCameraResponseSchema,
    OrganizationCameraSchema,
    MonitorRegisterSchema,
    MonitorStreamSchema,
    VideoSchema, TrackingUsersSchema, ManageUserTrackingStatusSchema,
)
from src.services.shinobi import Shinobi

# from src.recorgnition.face_detections import FaceRecognition

logger = logging.getLogger("uvicorn")
user_sync_queue: Queue = Queue()

app = FastAPI(**app_configs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
api_router = APIRouter()
video_api_router = APIRouter()

main_server = MainServer()
monitor_processor = MonitorProcessor(main_server)
shinobi = Shinobi(
    settings.SHINOBI_USER, settings.SHINOBI_PASSWORD, settings.SHINOBI_API_KEY
)
wss_notificator = WSSNotificator()


@app.on_event("startup")
async def startup():
    logger.info("start")
    from src.processor.service import start

    try:
        logger.info("read monitors info")
        organization_monitors = await main_server.get_monitors()
        tracking_users: list[TrackingUsersSchema] = await main_server.get_tracking_users()
        logger.info(f"organization monitors: {organization_monitors}")
        logger.info(f"tracking_users: {tracking_users}")

        logger.info("register shinobi monitors")
        shinobi.register_monitors(organization_monitors)

        start(shinobi, user_sync_queue)

    #
    #     logger.info(f"initialize face recognition service")
    #     face_recognition_service = FaceRecognition(tracking_users, shinobi, settings.ORGANIZATION_SLUG)
    #     # print(face_recognition_service.faces_dataset)
    #
    #     monitor_processor.set_face_detection_model(face_recognition_service)
    #     monitor_processor.set_shinobi_client(shinobi)
    #     monitor_processor.set_monitors(organization_monitors)
    #     monitor_processor.run_monitors()
    except Exception as e:
        logger.info(f"Server start failed: {e}")


# @app.on_event("shutdown")
# async def shutdown():
#     return processor.stop()


@api_router.get("/healthcheck")
async def health_check(_=Depends(get_api_key)) -> dict:
    return {"status": "OK"}


@api_router.post("/monitors")
async def create_monitor(payload: NewCameraRequestSchema) -> NewCameraResponseSchema:
    monitor_id = shinobi.manage_monitor(payload)
    if not monitor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create monitor"
        )

    print(f"monitor id: {monitor_id}")

    return NewCameraResponseSchema(monitor_id=monitor_id)


@api_router.post("/monitors/{monitor_id}/register")
async def register_monitor(monitor_id: str, payload: MonitorRegisterSchema):
    monitor_info: OrganizationCameraSchema = await main_server.get_monitor_by_id(
        monitor_id
    )

    if not monitor_info:
        print("no monitor found")
        return

    shinobi.register_monitor(monitor_info)
    monitor_processor.register_minitor(monitor_info)


@api_router.get("/monitors")
async def get_monitor_info() -> list[MonitorStreamSchema]:
    """Get info about available monitors"""

    monitors = monitor_processor.get_monitors()
    if not monitors:
        return []
    return [
        # TODO: add monitor recording status
        MonitorStreamSchema(
            monitor_id=monitor.monitor_id,
            stream_url=monitor.stream_playlist,
            wss_url=f"ws/{monitor.monitor_id}",
        )
        for monitor in monitors
    ]


@api_router.get("/monitors/{minitor_id}")
async def get_monitor_info(monitor_id: str) -> MonitorStreamSchema:
    """Get info about monitor"""

    monitor = monitor_processor.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found"
        )
    return MonitorStreamSchema(
        monitor_id=monitor.monitor_id,
        stream_url=monitor.stream_playlist,
        wss_url=f"ws/{monitor_id}",
    )


@api_router.get("/streams/{monitor_id}/{filename}")
async def get_stream_playlist(monitor_id: str, filename: str):
    """
    Return file for streaming
    :param monitor_id: id of monitor
    :param filename: name of file
    :return: FileResponse
    """

    return FileResponse(f"src/streams/{monitor_id}/{filename}")


@api_router.post("/{user_id}/track")
async def get_available_users(user_id: str, payload: ManageUserTrackingStatusSchema, _=Depends(get_api_key)) -> dict:
    logging.error(f"user tracking status: {user_id}")
    user_sync_queue.put({"id": str(user_id), "tracking_enabled": payload.status})
    return {"status": "OK"}


@api_router.post("/monitors/{monitor_id}/snapshot")
def create_monitor_snapshot(monitor_id: str, _=Depends(get_api_key)):
    img_byte_arr = shinobi.create_snapshot(monitor_id)
    if not monitor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create snapshot")
    return Response(content=img_byte_arr, media_type="image/png")


@api_router.get("/video/")
def list_video() -> list[VideoSchema]:
    print("here")
    return shinobi.video()


@api_router.get("/video/{monitor_id}/")
def monitor_video(
    monitor_id: str, start: str = None, end: str = None, _=Depends(get_api_key)
) -> list[VideoSchema]:
    return shinobi.monitor_video(monitor_id, start, end)


@app.websocket("/ws/{monitor_id}")
async def websocket_endpoint(websocket: WebSocket, monitor_id: str):
    print(monitor_id)
    logging.info(monitor_id)
    await websocket.accept()
    print(monitor_id)

    wss_notificator.register_wss_connection(monitor_id, websocket)
    print(monitor_processor.wss_connections)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)
    except WebSocketDisconnect as e:
        logging.error(e)
        wss_notificator.unregister_wss_connection(monitor_id, websocket)
    except Exception as e:
        logging.error(e)


app.include_router(api_router, prefix="/api", tags=["Monitors API"])
app.include_router(file_router, prefix="", tags=["Streaming"])
