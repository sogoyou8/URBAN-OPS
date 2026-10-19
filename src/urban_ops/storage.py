"""Database backend: SQLite for local validation, PostgreSQL for production."""
from pathlib import Path
from importlib.resources import files
from sqlalchemy import create_engine, event, text


def make_engine(database_url: str):
    if database_url.startswith("sqlite:///"):
        path = database_url[len("sqlite:///"):]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    elif not database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        raise ValueError("URBAN_OPS_DATABASE_URL must be sqlite:/// or postgresql+psycopg://")
    url = ("postgresql+psycopg://" + database_url[len("postgresql://"):]
           if database_url.startswith("postgresql://") else database_url)
    engine = create_engine(url, pool_pre_ping=True, future=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_pragmas(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA busy_timeout=5000")
    return engine


def init_schema(engine):
    script_name = "postgres.sql" if engine.dialect.name == "postgresql" else "sqlite.sql"
    script = files("urban_ops").joinpath("sql", script_name).read_text(encoding="utf-8")
    commands = [x.strip() for x in script.split(";") if x.strip()]
    with engine.begin() as conn:
        for cmd in commands:
            conn.exec_driver_sql(cmd)


def get_run(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status FROM ingestion_runs WHERE run_id=:run_id"), {"run_id": run_id}).first()
    return row[0] if row else None


def query_summary(engine):
    queries = {
        "runs_succeeded": "SELECT count(*) FROM ingestion_runs WHERE status='success'",
        "runs_failed": "SELECT count(*) FROM ingestion_runs WHERE status='failed'",
        "stations": "SELECT count(*) FROM dim_stations",
        "status_samples": "SELECT count(*) FROM fact_station_status",
        "usable_samples": "SELECT count(*) FROM fact_station_status WHERE is_usable=1",
        "quality_issues": "SELECT count(*) FROM data_quality_issues",
        "quarantined": "SELECT count(*) FROM quarantined_records",
        "gold_rows": "SELECT count(*) FROM gold_station_daily",
    }
    with engine.connect() as conn:
        return {name: conn.execute(text(query)).scalar_one() for name, query in queries.items()}
