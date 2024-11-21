import cv2
import face_recognition
from ultralytics import YOLO


class ObjectDetection:
    def __init__(self):
        self.yolo_model = YOLO("src/recorgnition/models/weapons.pt")
        self.confidence_level = 0.6

    def is_near(self, box1, box2, threshold=400):
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

        return distance < threshold, threshold

    def process(self, frame):
        results = self.yolo_model(frame)
        labels = []
        shooter_face_boxes = []
        for result in results:
            classes = result.names
            cls = result.boxes.cls
            conf = result.boxes.conf
            detections = result.boxes.xyxy

            face_locations = face_recognition.face_locations(frame)
            face_boxes = {(left, top, right, bottom): None for top, right, bottom, left in face_locations}
            print(f"total faces detected: {face_boxes}")

            for pos, detection in enumerate(detections):
                if conf[pos] >= self.confidence_level:
                    xmin, ymin, xmax, ymax = detection
                    gun_box = (int(xmin), int(ymin), int(xmax), int(ymax))
                    print(f"gun box: {gun_box}")
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

                    min_distance = None
                    shooter = None

                    for face_box, threshold in face_boxes.items():
                        is_near, distance = self.is_near(gun_box, face_box)
                        print(f"is_near: {is_near}, distance: {distance}")
                        if is_near:
                            if min_distance:
                                if min_distance > distance:
                                    min_distance = distance
                                    shooter = face_box
                            else:
                                min_distance = distance
                                shooter = face_box
                    print(min_distance)
                    if shooter is not None:
                        shooter_face_boxes.append(shooter)
        if len(shooter_face_boxes) > 0:
            face_encodings = face_recognition.face_encodings(frame, shooter_face_boxes)
        else:
            face_encodings = None
        return frame, labels, face_encodings
