import face_recognition


class FaceRecognition:
    def __init__(self):
        pass

    def process(self, frame):
        face_locations = face_recognition.face_locations(frame)
        face_encodings = face_recognition.face_encodings(frame, face_locations)

        face_matched = []
        for face_encoding, face_location in zip(face_encodings, face_locations):
            pass