import datetime
import os
import uuid

from sqlalchemy import Boolean, Column, DateTime, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recipient_username = Column(String(32), nullable=False, index=True)
    actor_username = Column(String(32), nullable=False)
    notif_type = Column(String(32), nullable=False)  # follow | friend_request | friend_accept | like | comment | repost
    target_ref = Column(String(200), nullable=True)  # e.g. "alice:1789290776835" for a post
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "actor_username": self.actor_username,
            "notif_type": self.notif_type,
            "target_ref": self.target_ref,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
