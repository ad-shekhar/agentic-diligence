from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# SQLite specific connect args: disable same-thread restriction and configure 30s lock timeout
connect_args = {"check_same_thread": False, "timeout": 30.0} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Ensure SQLite backward compatibility with dynamic column migrations and WAL mode
    with engine.connect() as conn:
        try:
            from sqlalchemy import text
            if settings.DATABASE_URL.startswith("sqlite") and ":memory:" not in settings.DATABASE_URL:
                conn.execute(text("PRAGMA journal_mode=WAL;"))
                conn.execute(text("PRAGMA synchronous=NORMAL;"))
                conn.commit()
            result = conn.execute(text("PRAGMA table_info(traces)")).fetchall()
            cols = [r[1] for r in result]
            if cols and "provenance_hash" not in cols:
                conn.execute(text("ALTER TABLE traces ADD COLUMN provenance_hash VARCHAR(64)"))
                conn.commit()
        except Exception:
            pass
