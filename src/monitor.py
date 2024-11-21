import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Optional
from queue import Queue

import cv2
from starlette.websockets import WebSocket

from src.main_server import MainServer
from src.recorgnition.face_detections import FaceRecognition
from src.recorgnition.object_detections import ObjectDetection
from src.schema import OrganizationCameraSchema
from src.services.incidents import IncidentService
from src.services.shinobi import Shinobi


class MonitorProcessor:

    def __init__(self, main_server: MainServer):
        self.main_server = main_server
        self.monitors: dict[str, OrganizationCameraSchema] = {}
        self.wss_connections = defaultdict(list)
        self.loop = asyncio.new_event_loop()
        self.message_queues = {}
        threading.Thread(target=self._start_asyncio_loop, daemon=True).start()

        self.stop_event = threading.Event()

        self.object_detection_model = ObjectDetection()
        self.face_detection_model: FaceRecognition | None = None
        self.ongoing = None

        self.shinobi_client: Shinobi | None = None
        self.incident_service: IncidentService | None = None

        self.gun_detected_frames_count = 0
        self.max_frames_for_trigger = 5
        self.process_every_nth_frame = 25

    def _start_asyncio_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def set_monitors(self, monitors: List[OrganizationCameraSchema]):
        for monitor in monitors:
            self.monitors[monitor.monitor_id] = monitor
            self.wss_connections[monitor.monitor_id] = []
            self.message_queues[monitor.monitor_id] = Queue()
        self.incident_service.ws_connections = self.wss_connections

    def register_minitor(self, monitor: OrganizationCameraSchema):
        self.monitors[monitor.monitor_id] = monitor
        self.wss_connections[monitor.monitor_id] = []
        self.message_queues[monitor.monitor_id] = Queue()

        self.run_stream(monitor)

    def set_face_detection_model(self, model_obj: FaceRecognition):
        self.face_detection_model = model_obj

    def set_shinobi_client(self, client: Shinobi):
        self.shinobi_client = client
        self.incident_service = IncidentService(client)

    def set_wss_connection(self, monitor_id: str, wss_connection: WebSocket):
        self.wss_connections[monitor_id].append(wss_connection)
        self.incident_service.ws_connections = self.wss_connections

    def get_monitor(self, monitor_id: str) -> Optional[OrganizationCameraSchema]:
        return self.monitors.get(monitor_id)

    def get_monitors(self) -> List[OrganizationCameraSchema]:
        return [item for item in self.monitors.values()]

    @staticmethod
    def __add_watermark(frame, watermark_text=f"samscloud", position=(10, 50)):
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (255, 255, 255)  # White color
        thickness = 2
        watermark_text += f": {datetime.now().isoformat()}"
        cv2.putText(
            frame,
            watermark_text,
            position,
            font,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
        return frame

    def __facial_recognition(self, monitor_id: str, rtsp_url: str):
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print("Error: Cannot open RTSP stream")
            return

        try:
            while not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                if cap.get(cv2.CAP_PROP_POS_FRAMES) % self.process_every_nth_frame == 0:
                    self.face_detection_model.process(frame, monitor_id)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Release resources
            cap.release()

    def __generate_hls_stream(
        self,
        monitor_id: str,
        rtsp_url: str,
        output_playlist: str,
        segment_files_pattern: str,
    ):
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print("Error: Cannot open RTSP stream")
            return

        process_every_nth_frame = 25

        # FFmpeg command to handle HLS streaming
        ffmpeg_command = [
            "ffmpeg",
            "-y",  # Overwrite output files
            "-f",
            "rawvideo",  # Input format
            "-pix_fmt",
            "bgr24",  # Pixel format
            "-s",
            f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",  # Frame size
            "-r",
            str(cap.get(cv2.CAP_PROP_FPS)),  # Frame rate
            "-i",
            "-",  # Input from stdin
            "-c:v",
            "libx264",  # Video codec
            "-f",
            "hls",  # Output format
            "-hls_time",
            "10",  # Segment length
            "-hls_list_size",
            "0",  # Keep all segments in playlist
            "-hls_segment_filename",
            segment_files_pattern,  # Segment file naming pattern
            output_playlist,
        ]

        # ffmpeg_command = [
        #     "ffmpeg",
        #     "-y",  # Overwrite output files
        #     "-f", "rawvideo",  # Input format
        #     "-pix_fmt", "bgr24",  # Pixel format
        #     "-s", f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",  # Frame size
        #     "-thread_queue_size", "1024",  # Increase thread queue size
        #     "-i", "-",  # Input from stdin
        #     "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",  # Add silent audio track
        #     "-c:v", "libx264",  # Video codec
        #     "-c:a", "aac",  # Audio codec
        #     "-b:a", "128k",  # Audio bitrate
        #     "-shortest",  # Match video duration to audio
        #     "-f", "hls",  # Output format
        #     "-hls_time", "10",  # Segment length
        #     "-hls_list_size", "0",  # Keep all segments in playlist
        #     "-hls_segment_filename", segment_files_pattern,  # Segment file naming pattern
        #     output_playlist  # Output playlist file
        # ]

        # Start FFmpeg
        process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)

        last_detection_time = None
        detection_timeout = 30

        try:
            while not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                frame, findings, shooter_faces = self.object_detection_model.process(frame)
                if shooter_faces:
                    print(f"matched faces: {len(shooter_faces)}")
                current_time = time.time()

                if findings:
                    self.gun_detected_frames_count += 1
                    last_detection_time = current_time

                else:
                    self.gun_detected_frames_count = 0

                if self.gun_detected_frames_count == self.max_frames_for_trigger:
                    print("send notification!")
                    msg = json.dumps(
                        {
                            "event": "OBJECT_DETECTED",
                            "objects_detected": True,
                            "payload": {
                                "object_type": "gun",
                                "camera_id": self.monitors.get(monitor_id).id,
                                "shooters": [i.tolist() for i in shooter_faces],
                            },
                        }
                    )
                    self.message_queues[monitor_id].put(msg)
                    self.gun_detected_frames_count = 0

                if (
                    last_detection_time
                    and self.incident_service.ongoing_incident
                    and (current_time - last_detection_time) >= detection_timeout
                ):
                    print("No findings for 30 seconds, end incident!")
                    msg = json.dumps(
                        {
                            "event": "INCIDENT_END",
                            "objects_detected": False,
                            "payload": {
                                "camera_id": self.monitors.get(monitor_id).id,
                            },
                        }
                    )
                    self.message_queues[monitor_id].put(msg)
                    last_detection_time = None

                # Write the frame to FFmpeg's stdin
                process.stdin.write(frame.tobytes())
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Release resources
            cap.release()
            process.stdin.close()
            process.wait()

    async def _send_message(self, monitor_id: str, message: str):
        await self.incident_service.track_incident(
            monitor_id, self.monitors[monitor_id].id, message
        )

    def _handle_messages(self, monitor_id: str):
        queue = self.message_queues[monitor_id]
        while True:
            message = queue.get()
            if message is None:
                break

            asyncio.run_coroutine_threadsafe(
                self._send_message(monitor_id, message), self.loop
            )

    def run_stream(self, monitor: OrganizationCameraSchema) -> str:
        output_dir = os.path.join("src/streams", monitor.monitor_id)
        rtsp_url = f"rtsp://{monitor.user_name}:{monitor.password}@{monitor.ip_address}:{monitor.port}/{monitor.path}"
        segment_files_pattern = os.path.join(output_dir, "segment_%03d.ts")

        print(output_dir)
        print(rtsp_url)
        print(segment_files_pattern)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            threading.Thread(
                target=self._handle_messages, args=(monitor.monitor_id,), daemon=True
            ).start()
            thread = threading.Thread(
                target=self.__generate_hls_stream,
                args=(
                    monitor.monitor_id,
                    rtsp_url,
                    os.path.join(output_dir, "output.m3u8"),
                    segment_files_pattern,
                ),
            )
            thread.start()
        except Exception as e:
            print(f"Error: {e}")
            shutil.rmtree(output_dir)

        monitor.stream_playlist = f"/streams/{monitor.monitor_id}/output.m3u8"

        return monitor.stream_playlist

    def run_face_detection(self, monitor: OrganizationCameraSchema):
        rtsp_url = f"rtsp://{monitor.user_name}:{monitor.password}@{monitor.ip_address}:{monitor.port}/{monitor.path}"

        try:
            threading.Thread(
                target=self._handle_messages, args=(monitor.monitor_id,), daemon=True
            ).start()
            thread = threading.Thread(
                target=self.__facial_recognition,
                args=(
                    monitor.monitor_id,
                    rtsp_url,
                ),
            )
            thread.start()
        except Exception as e:
            print(f"Error: {e}")

    def run_monitors(self):
        for monitor in self.monitors.values():
            self.run_stream(monitor)
            self.run_face_detection(monitor)
