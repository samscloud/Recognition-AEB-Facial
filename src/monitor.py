import asyncio
import logging
from collections import defaultdict
from typing import List

import cv2
from starlette.websockets import WebSocket

from src.config import settings
from src.recorgnition.objects_detections import ObjectDetectionModel
from src.schema import CCTVCamera
from src.utils.shinobi import Shinobi


class Processor:
    def __init__(self, shinobi: Shinobi, object_detection_model: ObjectDetectionModel):
        self.shinobi = shinobi
        self.object_detection = object_detection_model
        self.s3_bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        self.notification_timeout = settings.USER_NOTIFICATION_DELAY_SECONDS

        self.organization_slug = settings.ORGANIZATION_SLUG
        self.organization_id = settings.ORGANIZATION_ID
        self.be_api_key = settings.BACKEND_API_KEY
        self.be_url = settings.BACKEND_API_URL

        self.tasks = []
        self.ws_connections = defaultdict(list)
        self.frames = None

        self.monitors = {}

    def set_monitors(self, monitors: List[CCTVCamera]):
        self.monitors = {monitor.monitor_id: monitor for monitor in monitors}
        self.frames = {monitor.monitor_id: None for monitor in monitors}

        for monitor in monitors:
            self.tasks.append(
                asyncio.create_task(self.capture_frames(monitor.monitor_id))
            )

    def register_connection(self, ws_connection: WebSocket, monitor_id: str):
        self.ws_connections[monitor_id].append(ws_connection)

    def get_frame(self, monitor_id: str):
        return self.frames.get(monitor_id)

    async def capture_frames(self, monitor_id: str):
        cap = None

        boxes, indexes, class_ids = [], [], []

        try:
            cap = cv2.VideoCapture(self.monitors[monitor_id].monitor_stream_url)
            if not cap.isOpened():
                raise Exception(f"Error: Could not open video stream {self.monitors[monitor_id]}")

            # TODO: implement reconnect
            while True:
                success, frame = cap.read()
                if not success:
                    logging.info(f"Failed to grab frame from {self.monitors[monitor_id]}")
                    await asyncio.sleep(0.1)
                    continue

                try:
                    if int(cap.get(cv2.CAP_PROP_POS_FRAMES)) % 30 == 0:
                        boxes, indexes, class_ids = self.object_detection.predict(frame)
                        if len(boxes) > 0 and len(indexes) > 0 and len(class_ids) > 0:
                            logging.info(boxes, indexes, class_ids)
                        # TODO: face detection
                except Exception as e:
                    logging.info(f"Failed to predict object detection model: {e}")

                if len(boxes) > 0 and len(indexes) > 0 and len(class_ids) > 0:
                    self.object_detection.draw_boxes(frame, boxes, indexes, class_ids)
                await asyncio.sleep(0.03)

                if self.ws_connections.get(monitor_id):
                    self.frames[monitor_id] = frame

                    await asyncio.sleep(0.03)  # Control frame rate (30 FPS)
                else:
                    await asyncio.sleep(1)
        except Exception as e:
            logging.info(f"Exception occurred while capturing frames from camera {monitor_id}: {e}")
        finally:
            if cap is not None:
                cap.release()
