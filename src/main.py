import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocket, WebSocketDisconnect

from src.config import settings, app_configs
from src.main_server import MainServer
from src.monitor import MonitorProcessor
from src.api.monitor.router import router as api_router
from src.api.files.router import router as file_router
from src.recorgnition.face_detections import FaceRecognition
from src.services.shinobi import Shinobi

# from src.recorgnition.face_detections import FaceRecognition

logger = logging.getLogger("uvicorn")

# from src.recorgnition.face import FaceRecognitionProcessor
# from src.recorgnition.objects_detections import ObjectDetectionModel
# from src.schema import ManageUserTrackingStatusSchema, NewCameraRequestSchema, NewCameraResponseSchema, MonitorSchema, \
#     CCTVCamera, MonitorRegisterSchema, VideoSchema, MonitorStreamSchema
# from src.utils.shinobi import Shinobi

app = FastAPI(**app_configs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
# shinobi = Shinobi(settings.SHINOBI_USER, settings.SHINOBI_PASSWORD, settings.SHINOBI_API_KEY)
# processor = FaceRecognitionProcessor(shinobi=shinobi)
# detection_model = ObjectDetectionModel()
# init_service = FaceRecognitionInit(
#             organization_slug=settings.ORGANIZATION_SLUG,
#             be_api_key=settings.BACKEND_API_KEY,
#             be_url=settings.BACKEND_API_URL,
#             shinobi=shinobi,
#         )
# camera_processor = Processor(shinobi=shinobi, object_detection_model=detection_model)

main_server = MainServer()
monitor_processor = MonitorProcessor(main_server)
shinobi = Shinobi(
    settings.SHINOBI_USER, settings.SHINOBI_PASSWORD, settings.SHINOBI_API_KEY
)


@app.on_event("startup")
async def startup():
    logger.info("start")
    try:
        logger.info("read monitors info")
        organization_monitors = await main_server.get_monitors()
        tracking_users = await main_server.get_tracking_users()
        logger.info(f"organization monitors: {organization_monitors}")
        logger.info(f"tracking_users: {tracking_users}")

        logger.info("register shinobi monitors")
        shinobi.register_monitors(organization_monitors)

        logger.info(f"initialize face recognition service")
        face_recognition_service = FaceRecognition(tracking_users)
        # print(face_recognition_service.faces_dataset)

        monitor_processor.set_face_detection_model(face_recognition_service)
        monitor_processor.set_shinobi_client = shinobi
        monitor_processor.set_monitors(organization_monitors)
        monitor_processor.run_monitors()

        # active_monitors = await init_service.execute()
        # logging.info(f"active monitors: {active_monitors}")
        #
        # logging.info("start camera")
        # camera_processor.set_monitors(monitors=active_monitors)
    except Exception as e:
        logger.info(f"Server start failed: {e}")


# @app.on_event("shutdown")
# async def shutdown():
#     return processor.stop()


# @router.get("/healthcheck")
# async def health_check(_=Depends(get_api_key)) -> Dict:
#     return {"status": "OK"}


# @router.get("monitor/{monitor_id}/streams")
# async def get_monitor_stream(monitor_id: str) -> MonitorStreamSchema:
#     monitor = monitor_processor.get_monitor(monitor_id)
#     if not monitor:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")
#     return MonitorStreamSchema(
#         monitor_id=monitor.monitor_id,
#         stream_url=monitor.stream_playlist,
#     )
#
#
# @router.get("/monitor/{monitor_id}/streams/{filename}")
# async def get_stream_playlist(monitor_id: str, filename: str):
#     monitor = monitor_processor.get_monitor(monitor_id)
#     if not monitor:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")
#
#     return FileResponse(f"src/streams/{monitor.monitor_id}/{filename}")


# @router.get("/available-users")
# async def get_available_users(_=Depends(get_api_key)) -> Dict:
#     print(processor.monitors)
#     return {"status": "OK"}
#
#
# @router.post("/{user_id}/track")
# async def get_available_users(user_id: int, payload: ManageUserTrackingStatusSchema, _=Depends(get_api_key)) -> Dict:
#     processor.change_user_tracking_status(user_id, payload.status)
#     return {"status": "OK"}
#
#
# @router.post("/{user_id}")
# def get_available_users(user_id: int, background_tasks: BackgroundTasks, _=Depends(get_api_key)) -> Dict:
#     # background_tasks.add_task(add_new_user, user_id)
#     dataset = init_service.read_user_datasets([user_id])
#     if dataset:
#         processor.add_new_user(user_id, dataset)
#     return {"status": "OK"}
#
#
# @router.get("/monitors")
# def get_monitors_info(_=Depends(get_api_key)) -> List[MonitorSchema]:
#     return shinobi.get_monitors_info()
#
#
# @router.post("/monitors/create")
# def create_new_monitor(payload: NewCameraRequestSchema, _=Depends(get_api_key)) -> NewCameraResponseSchema:
#     print(processor.shinobi)
#     monitor_id = shinobi.manage_monitor(payload)
#     if not monitor_id:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create monitor")
#
#     return NewCameraResponseSchema(monitor_id=monitor_id)
#
#
# @router.post("/monitors/{monitor_id}/register")
# def register_new_monitor(payload: MonitorRegisterSchema, _=Depends(get_api_key)):
#     users = []
#     live_tracking = dict()
#     face_tracking = dict()
#     if processor.monitors and len(processor.monitors) > 0:
#         users = processor.monitors[0].users
#         live_tracking = processor.monitors[0].live_tracking
#         face_tracking = processor.monitors[0].face_tracking
#
#     # Check monitor status?
#
#     monitor = CCTVCamera(
#         monitor_id=payload.monitor_id,
#         monitor_stream_url=shinobi.get_monitor_stream_url(payload.monitor_id),
#         location_id=payload.location_id,
#
#         organization_id=payload.organization_id,
#         organization_slug=payload.organization_slug,
#
#         shinobi_email=settings.SHINOBI_USER,
#         shinobi_password=settings.SHINOBI_PASSWORD,
#
#         users=users,
#         live_tracking=live_tracking,
#         face_tracking=face_tracking
#     )
#
#     processor.register_monitor(monitor)
#     return {"status": "OK"}
#
#
# @router.put("/monitors/{monitor_id}")
# def update_monitor(monitor_id: str, payload: NewCameraRequestSchema, _=Depends(get_api_key)):
#     print(processor.shinobi)
#     monitor_id = shinobi.manage_monitor(payload, monitor_id)
#     if not monitor_id:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to update monitor")
#     return NewCameraResponseSchema(monitor_id=monitor_id)
#
#
# @router.delete("/monitors/{monitor_id}")
# def delete_monitor(monitor_id: str, _=Depends(get_api_key)):
#     print(processor.shinobi)
#     monitor_id = shinobi.delete_monitor(monitor_id)
#     if not monitor_id:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete monitor")
#
#     processor.delete_monitor(monitor_id)
#     return Response(status_code=status.HTTP_204_NO_CONTENT)
#
#
# @router.post("/monitors/{monitor_id}/recording/{monitor_status}")
# def change_monitor_recording_status(monitor_id: str, monitor_status: str, _=Depends(get_api_key)):
#     if monitor_status == "start":
#         shinobi.stop_monitor_recording_sync(monitor_id)
#     elif monitor_status == "record":
#         shinobi.start_monitor_recording_sync(monitor_id)
#     else:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid monitor status")
#
#     return Response(status_code=status.HTTP_200_OK)
#
#
# @router.post("/monitors/{monitor_id}/snapshot")
# def create_monitor_snapshot(monitor_id: str, _=Depends(get_api_key)):
#     img_byte_arr = shinobi.create_snapshot(monitor_id)
#     if not monitor_id:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create snapshot")
#     return Response(content=img_byte_arr, media_type="image/png")
#
#
# @router.get("/monitors/{monitor_id}/video")
# def monitor_video(monitor_id: str, start: str = None, end: str = None, _=Depends(get_api_key)) -> List[VideoSchema]:
#     return shinobi.monitor_video(monitor_id, start, end)
#
#
# @router.get("/monitors/video")
# def list_video(_=Depends(get_api_key)) -> List[VideoSchema]:
#     return shinobi.video()
#
#
# @router.delete("/monitors/{monitor_id}/video/{record_id}")
# def delete_video(monitor_id: str, record_id: str, _=Depends(get_api_key)):
#     monitor_id = shinobi.delete_video(monitor_id, record_id)
#     if not monitor_id:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete video")
#     return Response(status_code=status.HTTP_200_OK)
#
#
# @app.websocket("/ws/{monitor_id}")
# async def websocket_endpoint(websocket: WebSocket, monitor_id: str):
#     await websocket.accept()
#     print(monitor_id)
#     camera_processor.register_connection(websocket, monitor_id)
#     try:
#         while True:
#             frame = camera_processor.get_frame(monitor_id)
#             if frame is not None:
#                 ret, buffer = cv2.imencode('.jpg', frame)
#                 frame = buffer.tobytes()
#                 await websocket.send_bytes(frame)
#             await asyncio.sleep(0.03)  # Control frame rate (30 FPS)
#     except WebSocketDisconnect as e:
#         print(e)
#         # TODO: remove connection
#         # active_connections[camera_index].remove(websocket)
#     except Exception as e:
#         print(e)


@app.websocket("/ws/{monitor_id}")
async def websocket_endpoint(websocket: WebSocket, monitor_id: str):
    print(monitor_id)
    logging.info(monitor_id)
    await websocket.accept()
    print(monitor_id)

    monitor_processor.set_wss_connection(monitor_id, websocket)
    print(monitor_processor.wss_connections)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)
    except WebSocketDisconnect as e:
        logging.error(e)
        # TODO: remove connection
        # active_connections[camera_index].remove(websocket)
    except Exception as e:
        logging.error(e)


app.include_router(api_router, prefix="/api", tags=["Monitors API"])
app.include_router(file_router, prefix="", tags=["Streaming"])
