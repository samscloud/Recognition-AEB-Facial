import io
import logging
from typing import List, Dict

import boto3
import face_recognition
import numpy as np
from PIL import Image

from src.config import settings
from src.schema import TrackingUsersSchema

logger = logging.getLogger("uvicorn")


class FaceRecognition:
    def __init__(self, users: List[TrackingUsersSchema]):
        logger.info("fetching users dataset")
        self.faces_dataset = self.__read_user_datasets(users)

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

    def process(self, frame):
        face_locations = face_recognition.face_locations(frame)
        face_encodings = face_recognition.face_encodings(frame, face_locations)

        face_matched = []
        face_unmatched = []
        for face_encoding, face_location in zip(face_encodings, face_locations):
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
                        f"Found: {user_id} with distance: {face_distances[best_match_index]}"
                    )
                    face_matched.append(user_id)
                    continue
            face_unmatched.append(face_encoding)

        return face_matched, face_unmatched
