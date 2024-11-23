from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, Query, joinedload

from src.database import SessionLocal
from src.models import Incident, DetectedUser


def create_incident(incident_id: int, active_monitor: str, gun_detected: bool, num_detected_shooters: int) -> Incident:
    incident: Incident = Incident(
        id=incident_id,
        active_monitor=active_monitor,
        gun_detected=gun_detected,
        number_active_shooters=num_detected_shooters,
        is_active=True,
        last_update=datetime.now(),
    )

    db: Session = SessionLocal()

    db.add(incident)
    db.commit()
    db.refresh(incident)

    return incident


def get_active_incident() -> Incident | None:
    stmt: Query = select(Incident).where(Incident.is_active == True)

    db: Session = SessionLocal()
    return db.execute(stmt).scalars().first()


def update_incident_catching_time(incident_id: int):
    incident: Incident = get_active_incident()
    incident.last_update = datetime.now()
    db: Session = SessionLocal()
    db.commit()


def get_detected_users() -> list[DetectedUser]:
    stmt: Query = select(DetectedUser)
    db: Session = SessionLocal()
    return db.execute(stmt).scalars().first()



