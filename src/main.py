import logging
from typing import Dict

from fastapi import FastAPI, APIRouter, Depends, BackgroundTasks

from src.dependencies import get_api_key
from src.intit.face_recognition import FaceRecognitionInit
from src.config import settings, app_configs
from src.recorgnition.face import FaceRecognitionProcessor
from src.schema import ManageUserTrackingStatusSchema

app = FastAPI(**app_configs)
processor = FaceRecognitionProcessor()
init_service = FaceRecognitionInit(
            organization_slug=settings.ORGANIZATION_SLUG,
            be_api_key=settings.BACKEND_API_KEY,
            be_url=settings.BACKEND_API_URL,
        )
router = APIRouter()


async def add_new_user(user_id: int):
    dataset = init_service.read_user_datasets([user_id])
    if dataset:
        processor.add_new_user(user_id, dataset)


@app.on_event("startup")
async def startup():
    logging.info("start")
    try:
        logging.info("read monitors data")
        active_monitors = await init_service.execute()

        logging.info("start camera")
        processor.set_monitors(active_monitors)
        processor.set_shinobi_client(init_service.shinobi_client)
        processor.start()
    except Exception as e:
        logging.info(f"Server start failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    return processor.stop()


@router.get("/healthcheck")
async def health_check(_=Depends(get_api_key)) -> Dict:
    return {"status": "OK"}


@router.get("/available-users")
async def get_available_users(_=Depends(get_api_key)) -> Dict:
    print(processor.monitors)
    return {"status": "OK"}


@router.post("/{user_id}/track")
async def get_available_users(user_id: int, payload: ManageUserTrackingStatusSchema, _=Depends(get_api_key)) -> Dict:
    processor.change_user_tracking_status(user_id, payload.status)
    return {"status": "OK"}


@router.post("/{user_id}")
async def get_available_users(user_id: int, background_tasks: BackgroundTasks, _=Depends(get_api_key)) -> Dict:
    # background_tasks.add_task(add_new_user, user_id)
    dataset = init_service.read_user_datasets([user_id])
    if dataset:
        processor.add_new_user(user_id, dataset)
    return {"status": "OK"}


app.include_router(router, prefix="/api")
