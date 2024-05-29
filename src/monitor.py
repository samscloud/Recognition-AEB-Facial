import os
import shutil
import subprocess
import threading
from typing import List, Dict, Optional

import cv2

from src.main_server import MainServer
from src.schema import OrganizationCameraSchema


class MonitorProcessor:

    def __init__(self, main_server: MainServer):
        self.main_server = main_server
        self.monitors = {}

    def set_monitors(self, monitors: List[OrganizationCameraSchema]):
        self.monitors = {monitor.monitor_id: monitor for monitor in monitors}

    def get_monitor(self, monitor_id: str) -> Optional[OrganizationCameraSchema]:
        return self.monitors.get(monitor_id)

    @staticmethod
    def __add_watermark(frame, watermark_text="samscloud", position=(10, 50)):
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (255, 255, 255)  # White color
        thickness = 2
        cv2.putText(frame, watermark_text, position, font, font_scale, color, thickness, cv2.LINE_AA)
        return frame

    def __generate_hls_stream(self, rtsp_url: str, output_playlist: str, segment_files_pattern: str):
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print("Error: Cannot open RTSP stream")
            return

        # FFmpeg command to handle HLS streaming
        ffmpeg_command = [
            "ffmpeg",
            "-y",  # Overwrite output files
            "-f", "rawvideo",  # Input format
            "-pix_fmt", "bgr24",  # Pixel format
            "-s", f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",  # Frame size
            "-r", str(cap.get(cv2.CAP_PROP_FPS)),  # Frame rate
            "-i", "-",  # Input from stdin
            "-c:v", "libx264",  # Video codec
            "-hls_flags", "delete_segments",
            "-f", "hls",  # Output format
            "-hls_time", "10",  # Segment length
            "-hls_list_size", "0",  # Keep all segments in playlist
            "-hls_segment_filename", segment_files_pattern,  # Segment file naming pattern
            output_playlist
        ]

        # Start FFmpeg process
        process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Apply watermark
                frame = self.__add_watermark(frame)

                # Write the frame to FFmpeg's stdin
                process.stdin.write(frame.tobytes())
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Release resources
            cap.release()
            process.stdin.close()
            process.wait()

    def run_stream(self, monitor: OrganizationCameraSchema) -> str:
        output_dir = os.path.join("src/streams", monitor.monitor_id)
        rtsp_url = f"rtsp://{monitor.user_name}:{monitor.password}@{monitor.ip_address}:{monitor.port}/{monitor.path}"
        segment_files_pattern = os.path.join(output_dir, "segment_%03d.ts")

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            thread = threading.Thread(target=self.__generate_hls_stream, args=(rtsp_url, os.path.join(output_dir, "output.m3u8"), segment_files_pattern))
            thread.start()
        except Exception as e:
            print(f"Error: {e}")
            shutil.rmtree(output_dir)

        monitor.stream_playlist = f"/streams/{monitor.monitor_id}/output.m3u8"

        return monitor.stream_playlist

    def run_monitors(self):
        for monitor in self.monitors.values():
            self.run_stream(monitor)

