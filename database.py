import os
import json
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Setup SQLite Database
DATABASE_URL = "sqlite:///./carousel.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(String, default="free")
    credits_remaining = Column(Integer, default=3)
    
    brand_kits = relationship("BrandKit", back_populates="user", cascade="all, delete-orphan")
    writer_profiles = relationship("WriterProfile", back_populates="user", cascade="all, delete-orphan")
    carousels = relationship("Carousel", back_populates="user", cascade="all, delete-orphan")

class BrandKit(Base):
    __tablename__ = "brand_kits"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    logo_url = Column(Text, nullable=True) # Holds file path, S3 URL, or Base64 logo data
    primary_color = Column(String, default="#1f6e7c")
    secondary_color = Column(String, default="#f4f7f6")
    accent_color = Column(String, default="#e27d60")
    font_header = Column(String, default="Big Shoulders Display")
    font_body = Column(String, default="Plus Jakarta Sans")
    handle_cta = Column(String, default="")
    is_default = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="brand_kits")
    carousels = relationship("Carousel", back_populates="brand_kit")

class WriterProfile(Base):
    __tablename__ = "writer_profiles"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    tone_description = Column(Text, nullable=False)
    sample_text = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="writer_profiles")
    carousels = relationship("Carousel", back_populates="writer_profile")

class Carousel(Base):
    __tablename__ = "carousels"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    brand_kit_id = Column(String, ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True)
    writer_profile_id = Column(String, ForeignKey("writer_profiles.id", ondelete="SET NULL"), nullable=True)
    topic = Column(String, nullable=False)
    aspect_ratio = Column(String, default="1080x1440")
    design_system = Column(String, default="e2e_premium")
    state_json = Column(Text, nullable=False) # JSON-serialized state dictionary
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="carousels")
    brand_kit = relationship("BrandKit", back_populates="carousels")
    writer_profile = relationship("WriterProfile", back_populates="carousels")

def init_db():
    Base.metadata.create_all(bind=engine)

def seed_default_data():
    init_db()
    db = SessionLocal()
    try:
        # Seed User if not exists
        admin = db.query(User).filter(User.id == "admin").first()
        if not admin:
            admin = User(
                id="admin",
                email="admin@e2e.house",
                subscription_status="pro",
                credits_remaining=999
            )
            db.add(admin)
            db.commit()

        # Seed Brand Kit if not exists
        default_brand = db.query(BrandKit).filter(BrandKit.id == "e2e_brand").first()
        if not default_brand:
            logo_base64 = ""
            logo_path = os.path.join(os.path.dirname(__file__), "logo_base64.txt")
            if os.path.exists(logo_path):
                try:
                    with open(logo_path, "r", encoding="utf-8") as f:
                        logo_base64 = f.read().strip()
                except Exception:
                    pass
            default_brand = BrandKit(
                id="e2e_brand",
                user_id="admin",
                name="E2E Brand",
                logo_url=logo_base64,
                primary_color="#1f6e7c",
                secondary_color="#f4f7f6",
                accent_color="#e27d60",
                font_header="Big Shoulders Display",
                font_body="Plus Jakarta Sans",
                handle_cta="e2e.house",
                is_default=True
            )
            db.add(default_brand)
            db.commit()

        # Seed Writer Profile if not exists
        default_profile = db.query(WriterProfile).filter(WriterProfile.id == "e2e_house_voice").first()
        if not default_profile:
            tone_description = ""
            voice_path = os.path.join(os.path.dirname(__file__), "voice_profile.txt")
            if os.path.exists(voice_path):
                try:
                    with open(voice_path, "r", encoding="utf-8") as f:
                        tone_description = f.read().strip()
                except Exception:
                    pass
            default_profile = WriterProfile(
                id="e2e_house_voice",
                user_id="admin",
                name="E2E House Voice",
                tone_description=tone_description,
                is_default=True
            )
            db.add(default_profile)
            db.commit()
    finally:
        db.close()
