import asyncio
import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Dict

import aioboto3
import cv2
import face_recognition
import numpy as np
import requests
from PIL import Image
from aiohttp import ClientSession

from src.config import settings
from src.schema import CCTVCamera, RegisteredUserCache, MonitorStateEnum
from src.utils.shinobi import Shinobi


logger = logging.getLogger(__name__)


class NotRegisteredMonitorsException(Exception):
    pass


class FaceRecognitionProcessor:

    def __init__(self):
        self.monitors = None
        self.s3_bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.executor = None
        self.loop = asyncio.new_event_loop()
        self.lock = threading.Lock()

        self.notification_timeout = settings.USER_NOTIFICATION_DELAY_SECONDS

        self.organization_slug = None

        self.faces_cache = {}
        self.live_tracking_cache = {}

        self.shinobi = None
        self.stop_event = threading.Event()

    def set_monitors(self, monitors: List[CCTVCamera]):
        self.monitors = monitors
        self.executor = ThreadPoolExecutor(max_workers=len(monitors))
        self.organization_slug = monitors[0].organization_slug

    def set_shinobi_client(self, shinobi: Shinobi):
        self.shinobi = shinobi

    def start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def upload_face_to_s3_async(self, face_image, key):
        session = aioboto3.Session()
        async with session.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        ) as s3:

            await s3.put_object(
                Bucket="located-faces", Key=key, Body=face_image
            )

        return f"https://located-faces.s3.us-west-2.amazonaws.com/{key}"

    def upload_face_to_s3(self, face_image, key):
        # Schedule the async upload function to run in the asyncio loop
        return asyncio.run_coroutine_threadsafe(self.upload_face_to_s3_async(face_image, key), self.loop)

    async def send_history_record_async(self, payload: Dict):
        url = f"{settings.BACKEND_API_URL}/{self.organization_slug}/cctv-info"

        async with ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"cant send request")

    def send_history_record(self, payload: Dict):
        url = f"{settings.BACKEND_API_URL}/{self.organization_slug}/cctv-info"
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"cant send request: {response.content}")
        # asyncio.run_coroutine_threadsafe(self.send_history_record_async(payload), self.loop)

    def send_video_history_record(self, payload: Dict):
        url = f"{settings.BACKEND_API_URL}/{self.organization_slug}/face-recognitions/history"
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logging.error(f"cant send video detection request: {response.content}")

    def process_video_stream(self, monitor: CCTVCamera):
        video_capture = cv2.VideoCapture(monitor.monitor_stream_url)
        process_every_nth_frame = 25

        while not self.stop_event.is_set():
            try:
                ret, frame = video_capture.read()
                if not ret:
                    logging.warning(f"Failed to capture frame from {monitor.monitor_id}")
                    video_capture = cv2.VideoCapture(monitor.monitor_stream_url)
                    continue

                if video_capture.get(cv2.CAP_PROP_POS_FRAMES) % process_every_nth_frame == 0:
                    face_locations = face_recognition.face_locations(frame)
                    face_encodings = face_recognition.face_encodings(frame, face_locations)

                    face_matched = []
                    for face_encoding, face_location in zip(face_encodings, face_locations):
                        for user_id, dataset in monitor.users.items():
                            matches = face_recognition.compare_faces(dataset, face_encoding)
                            face_distances = face_recognition.face_distance(dataset, face_encoding)

                            best_match_index = np.argmin(face_distances)
                            if matches[best_match_index]:
                                logging.info(f"Found: {user_id} with distance: {face_distances[best_match_index]}")
                                face_matched.append(user_id)

                                if user_id in monitor.face_tracking.keys() and not monitor.face_tracking.get(user_id):
                                    monitor.face_tracking[user_id] = RegisteredUserCache(
                                        user=user_id,
                                        camera=monitor.location_id,
                                        monitor_id=monitor.monitor_id,
                                        match_score=best_match_index,
                                        appeared_at=datetime.now(),
                                        image_url=self.save_user_face_to_s3(user_id, frame, face_location)
                                    )

                    self.check_face_detection_cache(monitor, face_matched)
                    reconnect_stream = self.check_live_tracking_cache(monitor, face_matched)
                    if reconnect_stream:
                        logging.warning(f"reconnection to {monitor.monitor_id}")
                        video_capture = cv2.VideoCapture(monitor.monitor_stream_url)
            except Exception as e:
                print(e)
        # video_capture.release()

    def save_user_face_to_s3(self, user_id, frame, face_location) -> str:
        top, right, bottom, left = face_location
        face_image = frame[top:bottom, left:right]
        pil_image = Image.fromarray(face_image)
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='JPEG')
        img_byte_arr = img_byte_arr.getvalue()

        image_filename = f"{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"

        self.upload_face_to_s3(img_byte_arr, image_filename)
        return f"https://located-faces.s3.us-west-2.amazonaws.com/{image_filename}"

    def check_face_detection_cache(self, monitor: CCTVCamera, face_matched: List[int]):
        """
        Check face detection cache.
        If user in cache but not saved in db then create new history record.
        If user disappeared from monitor then wait 30 second before trying to update history record.
        This 30 seconds delay is needed for handle situation when user disappeared and then appeared again.

        :param monitor: CCTVCamera minotor record
        :param face_matched: matched face ndarray
        """
        missing_users = set(monitor.users.keys()) - set(face_matched)

        # Manage find not processed users
        for user_id in face_matched:
            payload = monitor.face_tracking[user_id]
            if not payload.is_saved:
                # Save new record
                self.send_history_record(payload.dict())
                payload.is_saved = True
            # is user is already registered and appear again then reset time
            if payload.disappeared_at:
                payload.disappeared_at = None
            monitor.face_tracking[user_id] = payload

        # Manage missing users
        for user_id in missing_users:
            payload = monitor.face_tracking.get(user_id)
            if payload and not payload.disappeared_at:
                # Register missing datetime
                monitor.face_tracking[user_id].disappeared_at = datetime.now()
            elif payload and payload.disappeared_at + timedelta(seconds=30) < datetime.now():
                # send update history
                payload.disappeared_at = datetime.now()
                self.send_history_record(payload.dict())
                # and reset history cache
                monitor.face_tracking[user_id] = {}

    def check_live_tracking_cache(self, monitor: CCTVCamera, matched_users: List[int]):
        if not monitor.live_tracking:
            logging.info("no active tracking users")
            return False

        reconnect_stream = False

        logging.info(f"find users: {matched_users}")
        missing_users = set(monitor.users.keys()) - set(matched_users)
        logging.info(f"missing users: {missing_users}")

        # First check if matched users is tracking
        for user_id in matched_users:
            if user_id not in monitor.live_tracking.keys():
                # User not required tracking
                continue

            # User required tracking
            payload = monitor.live_tracking[user_id]
            if not payload:
                monitor.live_tracking[user_id] = {
                    "appeared_at": datetime.now()
                }

            if payload.get("disappeared_at"):
                # If user back to camera then reset disappeared_at timestamp
                payload["disappeared_at"] = None

        # Check missing users
        for user_id in missing_users:
            missing_user_payload = monitor.live_tracking.get(user_id)
            if not missing_user_payload:
                continue

            disappeared_at = missing_user_payload.get("disappeared_at")
            if disappeared_at and disappeared_at + timedelta(seconds=30) < datetime.now():
                missing_user_payload["disappeared_at"] = datetime.now()
                missing_user_payload["user_id"] = user_id
                missing_user_payload["camera_id"] = monitor.location_id
                self.send_video_history_record(missing_user_payload)
                monitor.live_tracking[user_id] = {}
            elif not disappeared_at:
                missing_user_payload["disappeared_at"] = datetime.now()
            logging.info(f"missing user payload: {missing_user_payload}")

        user_under_tracking = [user_id for user_id, payload in monitor.live_tracking.items() if payload]
        logging.info(f"user under tracking: {user_under_tracking}")

        # Do we need enable recording?
        if monitor.state == MonitorStateEnum.start and user_under_tracking:
            logging.info(f"enable monitor recording {monitor.monitor_id}")
            self.shinobi.start_monitor_recording_sync(monitor.monitor_id)
            monitor.state = MonitorStateEnum.record
            reconnect_stream = True
        elif monitor.state == MonitorStateEnum.record and not user_under_tracking:
            logging.info(f"no user under tracking {monitor.monitor_id}. stop record")
            monitor.state = MonitorStateEnum.start
            self.shinobi.stop_monitor_recording_sync(monitor.monitor_id)
            reconnect_stream = True

        return reconnect_stream

    def change_user_tracking_status(self, user_id: int, tracking_status: bool):
        if not self.monitors:
            raise NotRegisteredMonitorsException

        for monitor in self.monitors:
            if monitor.users.get(user_id):
                if monitor.live_tracking:
                    if tracking_status:
                        monitor.live_tracking[user_id] = {"start": None, "end": None}
                    else:
                        del monitor.live_tracking[user_id]
                else:
                    if tracking_status:
                        monitor.live_tracking = {user_id: {}}

    def start(self):
        threading.Thread(target=self.start_async_loop, daemon=True).start()

        for monitor in self.monitors:
            self.executor.submit(self.process_video_stream, monitor)

    def stop(self):
        # Ensure proper cleanup
        if self.executor:
            self.stop_event.set()
            self.executor.shutdown(wait=True)
            logging.info("processor id down")
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
