import io
import json
import logging
import threading
import uuid
from queue import Queue
from typing import Any
from datetime import datetime

import boto3
import face_recognition
import numpy as np
import requests
from PIL import Image
from numpy import ndarray
from pydantic import BaseModel
from sqlalchemy import select

from sqlalchemy.orm import Session, Query

from src.database import SessionLocal

from src.config import settings
from src.models import DetectedUser
from src.services.shinobi import Shinobi

log = logging.getLogger("uvicorn")


class RecognizedUser(BaseModel):
    user_id: str
    match_score: float
    face_location: Any
    face_image: Any = None
    tracking_enabled: bool = True


class UnknownUser(BaseModel):
    user_id: str
    face_location: Any
    face_encoding: Any
    face_image: Any = None
    tracking_enabled: bool = True


class FaceTracker:
    def __init__(self, wss_queue: Queue, shinobi: Shinobi):
        self.faces_dataset = self.__read_user_datasets()
        self.lock = threading.Lock()
        self.wss_queue = wss_queue
        self.shinobi = shinobi
        self.tracking_changed_status: dict = {}

    def __read_user_datasets(self) -> dict:
        url = f"https://api.samscloud.io/api/v2/organizations/{settings.ORGANIZATION_SLUG}/cctv/user-tracking/"

        response = requests.get(url)
        if response is None:
            raise Exception("cant get tracking users")

        users = {user["id"]: user["tracking_enabled"] for user in response.json()}

        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        faces: dict = {
            str(user["id"]): {"tracking_enabled": user["tracking_enabled"]}
            for user in response.json()
        }

        self.faces_dataset = faces

        for user_id, tracking_enabled in users.items():
            prefix = f"{settings.ORGANIZATION_SLUG}/{user_id}"
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

            faces[str(user_id)]["dataset"] = encoded_data

        users_under_tracking = len([user for user in faces.values() if user["tracking_enabled"]])
        users_not_tracking = len([user for user in faces.values() if not user["tracking_enabled"]])
        log.info(f"users under tracking: {users_under_tracking} | users not tracking: {users_not_tracking}")
        return faces

    def change_tracking_status(self, message: dict):
        log.error(f"change tracking status: {message}")
        user = self.faces_dataset.get(message.get("id"))
        if not user:
            log.warning(f"user {message.get('id')} not found")
            return
        with self.lock:
            user["tracking_enabled"] = message["tracking_enabled"]
            self.tracking_changed_status[message["id"]] = message["tracking_enabled"]

        log.info(f"user {len([user for user in self.faces_dataset.values() if user['tracking_enabled']])} tracking enabled")

    def track(self, message: dict):
        print(f"event_type: {message.get('event')}")
        event_type = message.get('event')

        if event_type == 'face_detection':
            self.face_detection(message.get("frame"), message.get("monitor_id"))
        elif event_type == 'detect_shooter':
            self._recognize_shooters(
                frame=message.get("frame"),
                monitor_id=message.get("monitor_id"),
                gun_boxes=message.get("gun_boxes"),
                incident_id=message.get("incident_id"),
            )

    def face_detection(self, frame: ndarray, monitor_id: str):
        log.info("start processing face detection event with frame")

        face_locations, face_encodings = self._identify_faces_location(frame)
        if len(face_locations) == 0:
            return

        log.info(f"total faces find: {len(face_locations)}. Start matching process")
        known_users, unknown_users = self._recognize_faces(face_locations, face_encodings)
        self.manage_findings(frame, monitor_id, known_users, unknown_users)

    def _identify_faces_location(self, frame: ndarray) -> tuple[tuple, tuple]:
        face_locations = face_recognition.face_locations(frame)
        face_encodings = face_recognition.face_encodings(frame, face_locations)

        return face_locations, face_encodings

    def _recognize_faces(self, face_locations: tuple, face_encodings: tuple):
        known_users: list[RecognizedUser] = []
        unknown_users: list[UnknownUser] = []

        for face_location, face_encoding in zip(face_locations, face_encodings):
            recognized_user: RecognizedUser | None = self._compare_face(face_location, face_encoding)
            if recognized_user:
                known_users.append(recognized_user)
            else:
                unknown_users.append(
                    UnknownUser(user_id=str(uuid.uuid4()), face_location=face_location, face_encoding=face_encoding, tracking_enabled=False)
                )

        log.info(f"recognition process finished. total known users: {len(known_users)}. total unknown users: {len(unknown_users)}")
        return known_users, unknown_users

    def _compare_face(self, face_location: ndarray, face_encoding: ndarray) -> RecognizedUser | None:
        sorted_ds = self.sort_dict_keys(self.faces_dataset)
        log.info(f"data: {sorted_ds.keys()}")
        for user_id, dataset in sorted_ds.items():
            matches = face_recognition.compare_faces(
                dataset["dataset"], face_encoding
            )
            face_distances = face_recognition.face_distance(
                dataset["dataset"], face_encoding
            )

            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                log.info(
                    f"Found: {user_id} with distance: {face_distances[best_match_index]}\n"
                )

                return RecognizedUser(
                    user_id=str(user_id),
                    match_score=face_distances[best_match_index],
                    face_location=face_location,
                    tracking_enabled=dataset["tracking_enabled"],
                )

        return None

    def sort_dict_keys(self, d):
        def sorting_key(key):
            try:
                return (0, int(key))  # (0, integer value) for keys that can be converted to integers
            except ValueError:
                return (1, key)  # (1, string value) for keys that cannot be converted to integers

        sorted_keys = sorted(d.keys(), key=sorting_key)
        sorted_dict = {k: d[k] for k in sorted_keys}
        return sorted_dict

    def _recognize_shooters(self, frame: ndarray, monitor_id: str, gun_boxes: list[tuple], incident_id: int):
        log.info("start processing shooter recognition")

        face_locations = face_recognition.face_locations(frame)
        if len(face_locations) == 0:
            log.info("no shooters on frame")
            return

        shooter_face_boxes = []
        face_boxes = {(left, top, right, bottom): None for top, right, bottom, left in face_locations}

        min_distance = None
        shooter = None

        for gun_box in gun_boxes:
            for face_box, threshold in face_boxes.items():
                is_near, distance = self._is_near_boxes(gun_box, face_box)
                log.warning(f"Is near: {is_near}, distance: {distance}")
                if is_near:
                    if min_distance is not None:
                        if min_distance > distance:
                            min_distance = distance
                            shooter = face_box
                    else:
                        min_distance = distance
                        shooter = face_box
            if shooter is not None:
                shooter_face_boxes.append(shooter)

        face_encodings = []
        if len(shooter_face_boxes) > 0:
            face_encodings = face_recognition.face_encodings(frame, shooter_face_boxes)

        log.warning(f"face ended. shooters: {len(face_encodings)}")

        known_users = []
        unknown_users = []
        for face_location, face_encoding in zip(face_locations, face_encodings):
            recognized_user: RecognizedUser | None = self._compare_face(face_location, face_encoding)
            # by default we enable tracking for known shooter
            if recognized_user:
                recognized_user.tracking_enabled = True
                known_users.append(recognized_user)
            else:
                unknown_users.append(
                    UnknownUser(
                        user_id=str(uuid.uuid4()),
                        face_location=face_location,
                        face_encoding=face_encoding,
                        tracking_enabled=True,
                    )
                )

        log.warning(f"incident shooters. known: {len(known_users)}, unknown: {len(unknown_users)}")

        with self.lock:
            for unknown_user in unknown_users:
                log.warning(f"unknown user: {unknown_user.face_location}")
                self.faces_dataset[unknown_user.user_id] = {
                    "dataset": [unknown_user.face_encoding],
                    "tracking_enabled": True,
                }

                log.warning(f"total uses under tracking: {len([user for user in self.faces_dataset.values() if user['tracking_enabled']])}")
        if len(known_users) + len(unknown_users) > 0:
            self.manage_findings(frame, monitor_id, known_users, unknown_users, incident_id)

    def manage_findings(self, frame: ndarray, monitor_id: str, known_users: list[RecognizedUser], unknown_users: list[UnknownUser], incident_id: int = None) -> None:
        stmt: Query = select(DetectedUser)
        db: Session = SessionLocal()
        users_under_tracking = db.execute(stmt).scalars().all()
        users_under_tracking_map = {
            user.id: user
            for user in users_under_tracking
        } if users_under_tracking else {}

        user_for_notification = []
        user_for_register = []
        for known_user in known_users:
            if not known_user.tracking_enabled and not self.tracking_changed_status.get(known_user.user_id):
                continue
            under_tracking = users_under_tracking_map.get(known_user.user_id)
            if under_tracking:
                under_tracking.last_update = datetime.now()

                if not under_tracking.incident_id and incident_id is not None:
                    user_for_notification.append(under_tracking)
                    under_tracking.incident_id = incident_id
                if under_tracking.monitor_id != monitor_id:
                    # TODO: stop shinoby prev camera here!
                    under_tracking.monitor_id = monitor_id
                    user_for_notification.append(under_tracking)
                if self.tracking_changed_status.get(known_user.user_id):
                    user_for_notification.append(under_tracking)
                    del self.tracking_changed_status[known_user.user_id]
            else:
                user_for_register.append(
                    DetectedUser(
                        id=known_user.user_id,
                        is_known=True,
                        monitor_id=monitor_id,
                        s3_img_url=self._face_image(known_user.user_id, frame, known_user.face_location),
                        last_update=datetime.now(),
                        incident_id=incident_id,
                        match_score=known_user.match_score,
                    )
                )

        for unknown_user in unknown_users:
            user_for_register.append(
                DetectedUser(
                    id=unknown_user.user_id,
                    is_known=False,
                    monitor_id=monitor_id,
                    s3_img_url=self._face_image(unknown_user.user_id, frame, unknown_user.face_location),
                    last_update=datetime.now(),
                    incident_id=incident_id,
                    match_score=0,
                )
            )

        db.add_all(user_for_register)
        db.commit()

        user_for_notification = list(set(user_for_notification))
        user_for_register = list(set(user_for_register))
        unknown_user_for_tracking = [unknown_user for unknown_user in unknown_users if unknown_user.tracking_enabled]

        log.warning(f"users for send to main BE: {len(user_for_notification) + len(user_for_register)}")
        if len(user_for_notification) + len(user_for_register) > 0:
            user_for_notification.extend(user_for_register)
            self._request(user_for_notification)
            if incident_id:
                shooters = ",".join(str(u.id) for u in user_for_notification)
                self.incident_finding(monitor_id, incident_id, shooters)

        if len(user_for_notification) + len(unknown_user_for_tracking) > 0:
            log.warning(f"trigger shinobi recording: {len(user_for_notification) + len(user_for_register)}")
            self.shinobi.start_monitor_recording_sync(monitor_id)

    def _face_image(self, user_id, frame, face_location):
        top, right, bottom, left = face_location
        face_image = frame[top:bottom, left:right]
        pil_image = Image.fromarray(face_image)
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format="JPEG")
        img_byte_arr = img_byte_arr.getvalue()

        image_filename = f"{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"

        return self.upload_face_to_s3(img_byte_arr, image_filename)

    def upload_face_to_s3(self, face_image, key):
        session = boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )

        client = session.client("s3")

        # Upload the object
        try:
            client.put_object(
                Bucket="located-faces",
                Key=key,
                Body=face_image,
                ContentType='image/jpeg'
            )
            return f"https://located-faces.s3.us-west-2.amazonaws.com/{key}"
        except Exception as e:
            print(f"Failed to upload {key} to S3: {e}")
            raise

    def incident_finding(self, monitor_id: str, incident_id: int, shooters: str):
        payload = {"zone_cctv_id": monitor_id, "shooters": shooters}

        url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/incidents/cctv-incidents/{incident_id}/history/"
        response = requests.post(url, json=payload)
        log.error(f"bad request: {response.text}")

    def _request(self, users: list):
        payload = {
            "new_users": [],
        }

        for user in users:
            user_id = None
            try:
                user_id = int(user.id)
            except ValueError:
                pass

            payload["new_users"].append(
                {
                    "id": user.id,
                    "user_id": user_id,
                    "recognition_img": user.s3_img_url,
                    "incident": user.incident_id,
                    "match_score": user.match_score,
                    "monitor_id": user.monitor_id,
                }
            )

        log.warning(f"payload: {payload}")

        url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/face-recognitions/log-findings/"
        response = requests.post(url, json=payload)
        if response.status_code != 201:
            log.error(f"cant send video detection request: {response.content}")

    @staticmethod
    def _is_near_boxes(box1, box2, threshold=400):
        """
        Check if box1 is near box2 within a given threshold.
        """
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2

        # Calculate the center points of both boxes
        x1_center = (x1_min + x1_max) / 2
        y1_center = (y1_min + y1_max) / 2
        x2_center = (x2_min + x2_max) / 2
        y2_center = (y2_min + y2_max) / 2

        # Calculate the Euclidean distance between the centers
        distance = ((x2_center - x1_center) ** 2 + (y2_center - y1_center) ** 2) ** 0.5

        return distance < threshold, distance

