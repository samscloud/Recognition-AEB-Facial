import os
from enum import Enum
from typing import Optional, List, Sequence

import boto3
import cv2
import numpy as np
import requests
from pydantic import BaseModel

from src.config import settings


class ObjectRectangleArea(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ObjectTypeEnum(str, Enum):
    WEAPON = 'Weapon'
    FIRE = 'Fire'
    GUN = 'Gun'
    RIFLE = 'Rifle'

    @staticmethod
    def from_str(label) -> Optional["ObjectTypeEnum"]:
        if label.lower() == "weapon":
            return ObjectTypeEnum.WEAPON
        elif label.lower() == "fire":
            return ObjectTypeEnum.FIRE
        elif label.lower() == "gun":
            return ObjectTypeEnum.GUN
        elif label.lower() == "rifle":
            return ObjectTypeEnum.RIFLE

        return None


class PredictedObject(BaseModel):
    object_type: ObjectTypeEnum
    box_area: ObjectRectangleArea


class ObjectDetectionModel:
    def __init__(self):
        self.model, self.classes, self.output_layer_names = self.__load_yolov()

    def __load_yolov(self):
        weights = "src/recorgnition/yolov3_testing.cfg"
        cfg = "src/recorgnition/yolov3_training_2000.weights"

        model = cv2.dnn.readNet(weights, cfg)
        model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        classes = ["Gun", "Fire", "Rifle"]
        output_layer_names = model.getUnconnectedOutLayersNames()

        return model, classes, output_layer_names

    def predict(self, frame: np.ndarray):
        height, width, channels = frame.shape

        # Resize frame for faster processing
        frame_resized = cv2.resize(frame, (416, 416))
        blob = cv2.dnn.blobFromImage(frame_resized, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
        self.model.setInput(blob)
        outs = self.model.forward(self.output_layer_names)

        class_ids = []
        confidences = []
        boxes = []
        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if confidence > 0.5:
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)

                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)

                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.3, 0.2)
        return boxes, indexes, class_ids

    def draw_boxes(self, frame, boxes, indexes, class_ids):
        for i in range(len(boxes)):
            if i in indexes:
                x, y, w, h = boxes[i]
                label = str(self.classes[class_ids[i]])
                color = (0, 255, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

