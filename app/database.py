# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from dotenv import load_dotenv

load_dotenv()

class Base(DeclarativeBase):
    pass

engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine)

def init_db():
    from app.models import __init__  # ensures all models are imported before create_all
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        from app.services.materials import seed_materials
        seed_materials(session)

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()