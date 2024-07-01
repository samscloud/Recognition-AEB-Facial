from typing import Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from src.recorgnition.object_detections import ObjectDetection


class Processor:
    def __init__(self):
        self.yolo_model = YOLO("src/recorgnition/models/weapons.pt")
        self.confidence_level = 0.6

    def weapon_processor(self, frame: np.ndarray) -> Tuple[np.ndarray, list[str]]:
        """
        Process single frame and try to find a weapon.
        If weapon is found, notify main backend server
        :param frame: video frame np.ndarray
        :return: updated frame np.ndarray
        """

        results = self.yolo_model(frame)
        labels = []
        for result in results:
            classes = result.names
            cls = result.boxes.cls
            conf = result.boxes.conf
            detections = result.boxes.xyxy

            for pos, detection in enumerate(detections):
                if conf[pos] >= self.confidence_level:
                    xmin, ymin, xmax, ymax = detection
                    label = f"{classes[int(cls[pos])]} {conf[pos]:.2f}"
                    labels.append(label)
                    color = (0, int(cls[pos]), 255)
                    cv2.rectangle(
                        frame, (int(xmin), int(ymin)), (int(xmax), int(ymax)), color, 2
                    )
                    cv2.putText(
                        frame,
                        label,
                        (int(xmin), int(ymin) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
        return frame, labels

    def face_processor(self, frame: np.ndarray):
        pass
