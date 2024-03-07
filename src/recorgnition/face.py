import asyncio
import io
import threading
import time
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
        asyncio.run_coroutine_threadsafe(self.upload_face_to_s3_async(face_image, key), self.loop)

    def check_user_cache(self, user_id, monitor_id):
        with self.lock:
            if self.faces_cache.get(user_id):
                print(f"user {user_id} in cache")
                payload = self.faces_cache.get(user_id)
                if payload.monitor_id == monitor_id:
                    return None
                else:
                    print(f"send notification that user located on another camera")
                    del self.faces_cache[user_id]
                    return True
            return True

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
        print(payload)
        requests.post(url, data=payload)
        # asyncio.run_coroutine_threadsafe(self.send_history_record_async(payload), self.loop)

    def send_video_history_record(self, payload: Dict):
        url = f"{settings.BACKEND_API_URL}/{self.organization_slug}/face-recognitions/history"
        print(payload)
        response = requests.post(url, data=payload)
        print(f"response: {response.content}")

    def update_cache(self, user_id, monitor_id):
        payload = None
        with self.lock:
            if self.faces_cache.get(user_id):
                payload = self.faces_cache.get(user_id)
                print(payload)
                if payload.monitor_id == monitor_id:
                    del self.faces_cache[user_id]
                    payload.disappeared_at = datetime.now()

        if payload:
            self.send_history_record(payload.dict())

    def add_new_user_to_cache(self, user_id, monitor_id, location_id, distance, face_image):
        image_filename = f"{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"

        self.upload_face_to_s3(face_image, image_filename)
        payload = RegisteredUserCache(
            user=user_id,
            camera=location_id,
            monitor_id=monitor_id,
            match_score=distance,
            appeared_at=datetime.now(),
            image_url=f"https://located-faces.s3.us-west-2.amazonaws.com/{image_filename}"
        )
        with self.lock:
            self.faces_cache[user_id] = payload

        self.send_history_record(payload.dict())

    def process_video_stream(self, monitor: CCTVCamera):
        video_capture = cv2.VideoCapture(monitor.monitor_stream_url)
        process_every_nth_frame = 50

        while True:
            try:
                ret, frame = video_capture.read()
                if not ret:
                    print(f"Failed to capture frame from {monitor.monitor_id}")
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
                                print(f"Found: {user_id} with distance: {face_distances[best_match_index]}")

                                cache_new_user = self.check_user_cache(user_id, monitor.monitor_id)
                                print(cache_new_user)
                                face_matched.append(user_id)
                                if cache_new_user:
                                    top, right, bottom, left = face_location
                                    face_image = frame[top:bottom, left:right]
                                    pil_image = Image.fromarray(face_image)
                                    img_byte_arr = io.BytesIO()
                                    pil_image.save(img_byte_arr, format='JPEG')
                                    img_byte_arr = img_byte_arr.getvalue()
                                    self.add_new_user_to_cache(user_id, monitor.monitor_id, monitor.location_id, best_match_index, img_byte_arr)

                    # Check users that gone from camera
                    print(f"finded user: {face_matched}")
                    print(f"finded user: {monitor.users.keys()}")
                    for known_user_id in monitor.users.keys():
                        if known_user_id not in face_matched:
                            self.update_cache(known_user_id, monitor.monitor_id)

                    reconnect_stream = self.manage_live_tracking(face_matched, monitor.users.keys(), monitor)
                    if reconnect_stream:
                        video_capture = cv2.VideoCapture(monitor.monitor_stream_url)
            except Exception as e:
                print(e)
        # video_capture.release()

    def manage_live_tracking(self, find_users, known_users, monitor):
        if not monitor.live_tracking:
            print("no active tracking users")
            return False

        reconnect_stream = False

        print(f"total find users: {len(find_users)}")
        print(f"total known users: {len(known_users)}")
        print(f"monitor_id: {monitor.monitor_id}")
        print(f"monitor state: {monitor.state}")

        print("processing find users")
        for user_id in find_users:
            if user_id in monitor.live_tracking.keys():
                print("user required tracking!!!!!")
                print(f"monitor recording status: {monitor.state}")
                if monitor.state != MonitorStateEnum.record:
                    self.shinobi.start_monitor_recording_sync(monitor.monitor_id)
                    monitor.state = MonitorStateEnum.record
                    reconnect_stream = True

                print("check if not tracking this user")
                tracking_status = monitor.live_tracking.get(user_id)
                if tracking_status:
                    print(tracking_status)
                    if not tracking_status["start"]:
                        tracking_status["start"] = datetime.now()
                        print("send BE request")

        print("missing users")
        missing_users = set(known_users) - set(find_users)
        print(f"missing users: {len(missing_users)}")
        for missing_user_id in missing_users:
            if missing_user_id in monitor.live_tracking.keys():
                print("user stop tracking!!!!!")
                tracking_payload = monitor.live_tracking[missing_user_id]
                print(f"missing user tracking payload: {tracking_payload}")
                if tracking_payload.get("start"):
                    tracking_payload["end"] = datetime.now()
                    self.send_video_history_record(
                        payload={
                            "user_id": missing_user_id,
                            "camera_id": monitor.location_id,
                            "appeared_at": tracking_payload["start"],
                            "disappeared_at": tracking_payload["end"],
                        }
                    )
                monitor.live_tracking[missing_user_id] = {"start": None, "end": None}

        print("check if we steel need to record monitor")
        if len(missing_users) == len(known_users) and monitor.state == MonitorStateEnum.record:
            print("stop recording!")
            self.shinobi.stop_monitor_recording_sync(monitor.monitor_id)
            monitor.state = MonitorStateEnum.start
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
                        monitor.live_tracking = {user_id: {"start": None, "end": None}}

    def start(self):
        threading.Thread(target=self.start_async_loop, daemon=True).start()

        for monitor in self.monitors:
            self.executor.submit(self.process_video_stream, monitor)

    def stop(self):
        # Properly stop your threads and the asyncio loop
        self.loop.call_soon_threadsafe(self.loop.stop)
