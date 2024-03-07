from typing import Dict

from fastapi import FastAPI, APIRouter, Depends

from src.dependencies import get_api_key
from src.intit.face_recognition import FaceRecognitionInit
from src.config import settings, app_configs
from src.recorgnition.face import FaceRecognitionProcessor
from src.schema import ManageUserTrackingStatusSchema

app = FastAPI(**app_configs)
processor = FaceRecognitionProcessor()
router = APIRouter()


@app.on_event("startup")
async def startup():
    print("start")
    try:
        print("read monitors data")
        init_service = FaceRecognitionInit(
            organization_slug=settings.ORGANIZATION_SLUG,
            be_api_key=settings.BACKEND_API_KEY,
            be_url=settings.BACKEND_API_URL,
        )

        active_monitors = await init_service.execute()

        print(active_monitors)
        print("start camera")
        processor.set_monitors(active_monitors)
        processor.set_shinobi_client(init_service.shinobi_client)
        processor.start()
    except Exception as e:
        print(f"Server start failed: {e}")


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
    print(user_id)
    print(payload)
    processor.change_user_tracking_status(user_id, payload.status)
    return {"status": "OK"}


app.include_router(router, prefix="/api")
