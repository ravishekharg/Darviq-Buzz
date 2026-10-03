import datetime
import os

from sqlalchemy import Column, DateTime, String, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

BUSINESS_CATEGORIES = [
    "Restaurant", "Retail Store", "Professional Service", "Local Business",
    "Health & Wellness", "Beauty & Personal Care", "Home Services", "Other",
]


class User(Base):
    __tablename__ = "users"

    username = Column(String(32), primary_key=True)
    password_hash = Column(String(255), nullable=False)
    bio = Column(String(300))
    avatar_url = Column(String(500))
    cover_url = Column(String(500))
    work = Column(String(100))
    education = Column(String(100))
    current_city = Column(String(100))
    hometown = Column(String(100))
    relationship_status = Column(String(32))
    website = Column(String(200))
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Account type is chosen once at sign-up (like Instagram/Twitter's
    # business-account toggle) rather than a separate ownable Page entity
    # with multiple admins (Facebook's actual Pages model) -- deliberately
    # simpler scope, but genuinely functional: a business account is just a
    # User with these fields set, so it reuses every existing follow/post/
    # feed/discover code path for free instead of needing a parallel system.
    account_type = Column(String(16), nullable=False, default="personal")
    business_category = Column(String(64))
    business_phone = Column(String(32))
    business_address = Column(String(200))

    def to_public_dict(self):
        return {
            "username": self.username,
            "bio": self.bio,
            "avatar_url": self.avatar_url,
            "cover_url": self.cover_url,
            "work": self.work,
            "education": self.education,
            "current_city": self.current_city,
            "hometown": self.hometown,
            "relationship_status": self.relationship_status,
            "website": self.website,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "account_type": self.account_type,
            "business_category": self.business_category,
            "business_phone": self.business_phone,
            "business_address": self.business_address,
        }


engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# Columns added after the table's first deploy. Base.metadata.create_all()
# only creates missing *tables*, never adds columns to one that already
# exists, so a plain redeploy against the live "users" table would silently
# keep the old schema and every new field would 500 on first use.
_NEW_COLUMNS = {
    "cover_url": "VARCHAR(500)",
    "account_type": "VARCHAR(16) NOT NULL DEFAULT 'personal'",
    "business_category": "VARCHAR(64)",
    "business_phone": "VARCHAR(32)",
    "business_address": "VARCHAR(200)",
}


def init_db():
    Base.metadata.create_all(engine)
    existing = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        for name, ddl_type in _NEW_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl_type}"))
