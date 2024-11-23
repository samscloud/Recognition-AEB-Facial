import subprocess
from queue import Queue

import cv2
import numpy as np

from src.processor.gun_detector import detect_guns


def process_monitor(
    monitor_id: str,
    rtsp_url: str,
    output_playlist: str,
    segment_files_pattern: str,
    incident_queue: Queue,
    face_queue: Queue
):

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Error: Cannot open RTSP stream")
        return

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

    process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            new_frame, gun_findings, gun_boxes = detect_guns(np.copy(frame))
            if gun_findings and cap.get(cv2.CAP_PROP_POS_FRAMES) % 5 == 0:
                print(f"is catch something: {len(gun_findings)}")
                incident_queue.put({"event": "gun_detected", "monitor_id": monitor_id, "frame": np.copy(frame), "gun_boxes": gun_boxes})

            if cap.get(cv2.CAP_PROP_POS_FRAMES) % 50 == 0:
                face_queue.put({"frame": np.copy(frame), "event": "face_detection", "monitor_id": monitor_id})

            process.stdin.write(frame.tobytes())
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Release resources
        cap.release()
        process.stdin.close()
        process.wait()


