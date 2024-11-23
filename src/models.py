from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from src.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    active_monitor = Column(String, index=True)
    gun_detected = Column(Boolean)
    number_active_shooters = Column(Integer)
    is_active = Column(Boolean)
    last_update = Column(DateTime)

    shooters = relationship("DetectedUser", back_populates="incident")


class DetectedUser(Base):
    __tablename__ = "detected_users"

    id = Column(String, primary_key=True, index=True)
    is_known = Column(Boolean)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    monitor_id = Column(String, index=True)
    s3_img_url = Column(String)
    match_score = Column(Float, default=0)
    last_update = Column(DateTime)

    incident = relationship("Incident", back_populates="shooters")
