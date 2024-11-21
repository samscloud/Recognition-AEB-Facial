import asyncio
import io
import json
import logging
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from typing import List, Dict

import aioboto3
import boto3
import face_recognition

import numpy as np
import requests
from PIL import Image
from pydantic import BaseModel

from src.config import settings
from src.schema import TrackingUsersSchema
from src.services.shinobi import Shinobi

logger = logging.getLogger("uvicorn")


class Findings(BaseModel):
    user_id: int | None = None
    unknown_user_id: str | None = None
    match_score: float
    monitor_id: str
    s3_face_image_url: str | None = None
    last_seen: datetime


class FaceRecognition:
    def __init__(self, users: List[TrackingUsersSchema], shinobi: Shinobi, organization_slug) -> None:
        logger.info("fetching users dataset")
        self.faces_dataset = self.__read_user_datasets(users)
        self.shinobi = shinobi

        self.lock = threading.Lock()
        self.loop = asyncio.new_event_loop()

        self.findings: list[Findings] = []

        self.missing_delta = timedelta(seconds=30)
        self.organization_slug = organization_slug

    def __read_user_datasets(self, users: List[TrackingUsersSchema]) -> Dict:
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        faces = {}

        for user in users:
            prefix = f"{settings.ORGANIZATION_SLUG}/{user.id}"
            result = s3.list_objects_v2(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME, Prefix=prefix
            )
            if "Contents" not in result.keys():
                continue

            encoded_data = []
            for obj in result["Contents"]:
                blob = io.BytesIO()
                s3.download_fileobj(
                    settings.AWS_STORAGE_BUCKET_NAME, obj.get("Key"), blob
                )

                blob.seek(0)
                image = Image.open(blob).convert("RGB")
                image_np = np.array(image)
                encoded_data.append(face_recognition.face_encodings(image_np)[0])
                blob.close()

            faces[user.id] = {
                "dataset": encoded_data,
                "tracking_enabled": user.tracking_enabled,
            }

        return faces

    def upload_face_to_s3_async(self, face_image, key):
        session = boto3.Session()
        client = session.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        client.put_object(Bucket="located-faces", Key=key, Body=face_image)
        return f"https://located-faces.s3.us-west-2.amazonaws.com/{key}"

    def upload_face_to_s3(self, face_image, key):
        session = boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )

        client = session.client("s3")

        # Upload the object
        try:
            response = client.put_object(
                Bucket="located-faces",
                Key=key,
                Body=face_image,
                ContentType='image/jpeg'
            )
            return f"https://located-faces.s3.us-west-2.amazonaws.com/{key}"
        except Exception as e:
            print(f"Failed to upload {key} to S3: {e}")
            raise

    def _face_image(self, user_id, face_location, frame):
        top, right, bottom, left = face_location
        face_image = frame[top:bottom, left:right]
        pil_image = Image.fromarray(face_image)
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format="JPEG")
        img_byte_arr = img_byte_arr.getvalue()

        image_filename = f"{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"

        return self.upload_face_to_s3(img_byte_arr, image_filename)

    def _face_encoding(self, face_location, frame):
        top, right, bottom, left = face_location
        face_image = frame[top:bottom, left:right]
        pil_image = Image.fromarray(face_image).convert("RGB")
        image_np = np.array(pil_image)

        data = face_recognition.face_encodings(image_np)

        return data[0] if len(data) > 0 else None

    def _handle_finding(self, monitor_id, frame, location, match_score, user_id):
        with self.lock:
            unknown_user_id = None
            if user_id is None:
                print("unknown user")
                unknown_user_id = uuid.uuid4()
            elif isinstance(user_id, str):
                print("registered user id")
                unknown_user_id = user_id
                user_id = None

            under_tracking = next(
                (
                    item
                    for item in self.findings
                    if item.user_id == user_id
                    and item.unknown_user_id == unknown_user_id
                    and item.monitor_id == monitor_id
                ),
                None,
            )
            if under_tracking:
                logger.warning(f"known user\n")
                under_tracking.last_seen = datetime.now()
                if monitor_id != under_tracking.monitor_id:
                    under_tracking.s3_face_image_url = self._face_image(
                            user_id or unknown_user_id, location, frame
                        )
                    under_tracking.monitor_id = monitor_id
                    under_tracking.match_score = match_score

                    return under_tracking
            else:
                logger.warning("new user\n")
                if unknown_user_id:
                    dataset = self._face_encoding(location, frame)
                    if dataset is None:
                        return
                    self.faces_dataset[unknown_user_id] = {
                        "dataset": [dataset],
                        "tracking_enabled": True,
                    }

                tracking_user = Findings(
                    user_id=user_id,
                    unknown_user_id=unknown_user_id,
                    s3_face_image_url=self._face_image(
                        user_id or unknown_user_id, location, frame
                    ),
                    match_score=match_score,
                    monitor_id=monitor_id,
                    last_seen=datetime.now(),
                )
                self.findings.append(tracking_user)
                return tracking_user

    def _filter_missing_users(self, monitor_id):
        with self.lock:
            missing_users = [
                user
                for user in self.findings if user.last_seen + self.missing_delta < datetime.now() and user.monitor_id == monitor_id
            ]

            for user in missing_users:
                try:
                    self.findings.remove(user)
                except ValueError:
                    pass
        logger.info(f"users for remove: {missing_users}")
        return missing_users

    def identify_faces(self, frame, monitor_id):
        face_locations = face_recognition.face_locations(frame)
        face_encodings = face_recognition.face_encodings(frame, face_locations)

        logger.warning(f"found {len(face_locations)} faces\n")

        new_users = []

        for face_encoding, face_location in zip(face_encodings, face_locations):
            matched = False
            for user_id, dataset in self.faces_dataset.items():
                matches = face_recognition.compare_faces(
                    dataset["dataset"], face_encoding
                )
                face_distances = face_recognition.face_distance(
                    dataset["dataset"], face_encoding
                )

                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    logger.info(
                        f"Found: {user_id} with distance: {face_distances[best_match_index]}\n"
                    )
                    obj = self._handle_finding(
                        monitor_id,
                        frame,
                        face_location,
                        face_distances[best_match_index],
                        user_id,
                    )
                    if obj:
                        new_users.append(obj)
                    matched = True
                    break
            if not matched:
                logger.info(len(face_location))
                new_users.append(self._handle_finding(
                    monitor_id=monitor_id,
                    frame=frame,
                    location=face_location,
                    match_score=0,
                    user_id=str(uuid.uuid4()),
                ))

            return new_users

    def video_recording(self, monitor_id):
        monitor_tracking_users = 0
        for user in self.findings:
            if user.monitor_id == monitor_id:
                monitor_tracking_users += 1

        monitor_recording_status = self.shinobi.recorded_monitor_register.get(monitor_id)
        if monitor_recording_status > 0 and monitor_tracking_users == 0:
            logger.info(f"Monitor {monitor_id} is recording")
            logger.info(f"Monitor {monitor_id} has no tracking users. stop monitoring")
            self.shinobi.stop_monitor_recording_sync(monitor_id)
        elif monitor_recording_status == 0 and monitor_tracking_users > 0:
            logger.info(f"Monitor {monitor_id} is not recording. Start recording")
            self.shinobi.start_monitor_recording_sync(monitor_id)

    def _request(self, new_findings: list[Findings], for_remove: list[Findings]):
        payload = {
            "new_users": [],
            "remove_user": [],
        }

        if new_findings:
            payload["new_users"] = [
                {
                    "unknown_user_id": user.unknown_user_id,
                    "user_id": user.user_id,
                    "monitor_id": user.monitor_id,
                    "s3_face_image_url": user.s3_face_image_url,
                    "match_score": user.match_score,
                }
                for user in new_findings
            ]

        if for_remove:
            payload["remove_user"] = [
                {
                    "unknown_user_id": user.unknown_user_id,
                    "user_id": user.user_id,
                    "monitor_id": user.monitor_id,
                    "s3_face_image_url": user.s3_face_image_url,
                    "match_score": user.match_score,
                }
                for user in for_remove]

        logger.warning(f"payload: {payload}")

        url = f"{settings.BACKEND_API_URL}/{self.organization_slug}/face-recognitions/log-findings/"
        response = requests.post(url, json=payload)
        if response.status_code != 201:
            logging.error(f"cant send video detection request: {response.content}")

    def process(self, frame, monitor_id):
        try:
            new_findings = self.identify_faces(frame, monitor_id)
            logger.info(new_findings)
            print(f"total matched users: {len(self.findings)}")
            for_remove = self._filter_missing_users(monitor_id)
            logger.info(for_remove)
            self.video_recording(monitor_id)

            if new_findings or for_remove:
                self._request(new_findings, for_remove)

        except Exception as e:
            traceback.print_exc()
