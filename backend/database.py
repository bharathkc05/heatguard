import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _resolve_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    # Default to SQLite for local/dev runs unless explicitly disabled.
    use_sqlite = os.getenv("DB_USE_SQLITE", "1") == "1"
    if use_sqlite:
        return "sqlite:///./heatguard.db"

    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER", r"localhost\SQLEXPRESS")
    database = os.getenv("DB_NAME", "heatguard")
    username = os.getenv("DB_USERNAME", "")
    password = os.getenv("DB_PASSWORD", "")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "yes")
    trust_cert = os.getenv("DB_TRUST_SERVER_CERT", "yes")

    if username and password:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate={trust_cert};"
        )
    else:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection={trusted};"
            f"TrustServerCertificate={trust_cert};"
        )

    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc)


DATABASE_URL = _resolve_database_url()

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Tables
class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Worker")
    age = Column(Integer)
    work_type = Column(String)
    activity_level = Column(String, default="moderate")
    acclimatized = Column(Boolean, default=False)
    supervisor_phone = Column(String, nullable=True)
    fcm_token = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer)
    # Environmental inputs
    tdb = Column(Float)
    rh = Column(Float)
    v = Column(Float)
    wbgt = Column(Float)
    heat_index = Column(Float)
    # Worker inputs
    hours_worked = Column(Float)
    hydration_status = Column(String)
    # Outputs
    risk_score = Column(Float)
    risk_label = Column(String)
    risk_label_int = Column(Integer)
    # Metadata
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    climate_zone = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SOSLog(Base):
    __tablename__ = "sos_logs"

    id = Column(Integer, primary_key=True)
    worker_id = Column(Integer)
    lat = Column(Float)
    lon = Column(Float)
    risk_score = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
