import asyncio
import queue
import threading

from src.main import wss_notificator
from src.processor.face_tracking import FaceTracker
from src.processor.incidents_tracking import IncidentTracking
from src.processor.monitor import process_monitor
from src.processor.watchdog import watch_dog
from src.services.shinobi import Shinobi

loop = asyncio.get_event_loop()


def handle_incident(incident_q: queue.Queue, face_q: queue.Queue, wss_q: queue.Queue, shinobi: Shinobi):
    service = IncidentTracking(wss_q, shinobi)
    while True:
        try:
            message = incident_q.get(timeout=1)
            print("get gun incident")
            gun_boxes = message.pop("gun_boxes")
            incident_id: int = service.track(**message)
            print(f"incident id: {incident_id}, trigger face detection")
            face_q.put(
                {
                    "frame": message.get("frame"),
                    "incident_id": incident_id,
                    "monitor_id": message.get("monitor_id"),
                    "event": "detect_shooter",
                    "gun_boxes": gun_boxes,
                }
            )
        except queue.Empty:
            pass


def handle_face_tracking(q: queue.Queue, wss_q: queue.Queue, sync_users_q: queue.Queue, shinobi: Shinobi):
    service = FaceTracker(wss_q, shinobi)
    while True:
        try:
            message = q.get(timeout=1)
            service.track(message)
        except queue.Empty:
            pass
        try:
            sync_user_msg = sync_users_q.get(timeout=1)
            service.change_tracking_status(sync_user_msg)
        except queue.Empty:
            pass


def handle_wss(q: queue.Queue):
    while True:
        try:
            message = q.get(timeout=1)
            loop.call_soon_threadsafe(asyncio.create_task, wss_notificator.send_wss_notification(message))
        except queue.Empty:
            pass


def start(shinobi: Shinobi, sync_users_queue: queue.Queue):
    incident_queue = queue.Queue()
    face_queue = queue.Queue()
    wss_queue = queue.Queue()

    incident_thread = threading.Thread(target=handle_incident, args=(incident_queue, face_queue, wss_queue, shinobi,))
    incident_thread.start()

    face_thread = threading.Thread(target=handle_face_tracking, args=(face_queue, wss_queue, sync_users_queue, shinobi,))
    face_thread.start()

    watchdog_thread = threading.Thread(target=watch_dog, args=(wss_queue, shinobi,))
    watchdog_thread.start()

    wss_thread = threading.Thread(target=handle_wss, args=(wss_queue,))
    wss_thread.start()

    monitor_thread = threading.Thread(
        target=process_monitor,
        args=(
            "654f7de165494686b0f7f85294b0c555",
            "rtsp://Bohdan:zbi22121991@192.168.3.27:554//stream2",
            "src/streams/654f7de165494686b0f7f85294b0c555/output.m3u8",
            "src/streams/654f7de165494686b0f7f85294b0c555/segment_%03d.ts",
            incident_queue,
            face_queue
        ),
    )
    monitor_thread.start()
