from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": 30  # Timeout em segundos antes de levantar erro de bloqueio
    }

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

# Configura PRAGMAs do SQLite para alta performance e concorrência com WAL Mode
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # WAL (Write-Ahead Logging): Leitores não travam escritores e vice-versa
        cursor.execute("PRAGMA journal_mode=WAL;")
        # NORMAL otimiza sync no disco garantindo durabilidade com segurança no modo WAL
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # Espera até 10000ms antes de retornar OperationalError
        cursor.execute("PRAGMA busy_timeout=10000;")
        # Habilita integridade referencial de chaves estrangeiras
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
