import logging
import time
from datetime import timedelta, datetime
from queue import Queue

import requests
from sqlalchemy.orm import Session, joinedload

from src.config import settings
from src.database import SessionLocal
from src.models import Incident, DetectedUser
from src.services.shinobi import Shinobi

log = logging.getLogger("uvicorn")


def watch_dog(wss_queue: Queue, shinobi: Shinobi):
    while True:
        log.warning("watch_dog started")
        end_expired_incidents(wss_queue)
        delete_missing_users()
        stop_inactive_monitors(shinobi)

        time.sleep(5)


def delete_missing_users():
    db: Session = SessionLocal()
    active_users = db.query(DetectedUser).filter(DetectedUser.incident_id.is_(None))
    users_for_delete = []
    for user in active_users:
        if user.last_update + timedelta(minutes=5) < datetime.now():
            log.warning(f"User {user.id} is inactive. Notify BE")
            users_for_delete.append(user)

    if len(users_for_delete) > 0:
        face_request(users_for_delete)
        for user in users_for_delete:
            db.delete(user)
        db.commit()


def end_expired_incidents(wss_queue: Queue):
    db: Session = SessionLocal()
    active_incidents = db.query(Incident).filter(Incident.is_active == True).options(
        joinedload(Incident.shooters)).all()

    for incident in active_incidents:
        if incident.last_update + timedelta(minutes=5) < datetime.now():
            log.warning(f'Dead incident {incident.id} has expired')

            no_shooters = 0
            for user in incident.shooters:
                log.warning(f'Shooter User {user.id}')
                if user.last_update + timedelta(minutes=5) < datetime.now():
                    no_shooters += 1
            if no_shooters == len(incident.shooters):
                for user in incident.shooters:
                    db.delete(user)
                end_ongoing_incident(incident.id)
                db.delete(incident)
    db.commit()


def face_request(for_remove: list):
    payload = {
        "new_users": [],
        "remove_user": [],
    }

    for user in for_remove:
        payload["remove_user"].append(
            {
                "id": user.id,
                "monitor_id": user.monitor_id,
            }
        )

    url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/face-recognitions/log-findings/"
    response = requests.post(url, json=payload)
    if response.status_code != 201:
        logging.error(f"cant send video detection request: {response.content}")


def end_ongoing_incident(incident_id: int):
    url = f"{settings.BACKEND_API_URL}/{settings.ORGANIZATION_SLUG}/incidents/cctv-incidents/{incident_id}/end/"
    requests.post(url, json={})


def stop_inactive_monitors(shinobi: Shinobi):
    db: Session = SessionLocal()

    for monitor in shinobi.recorded_monitor_register.keys():
        active_incidents_count = db.query(Incident).filter(Incident.active_monitor == monitor).count()
        active_users_count = db.query(DetectedUser).filter(DetectedUser.monitor_id == monitor).count()

        log.warning(f"total active events for monitor: {active_incidents_count + active_users_count}")

        if active_incidents_count + active_users_count == 0:
            shinobi.recorded_monitor_register[monitor] = 0
            shinobi.stop_monitor_recording_sync(monitor)
