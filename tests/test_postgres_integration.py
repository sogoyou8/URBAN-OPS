"""Integration test: only runs when a real test PostgreSQL service is provided.

The Github Actions CI workflow starts an ephemeral PostgreSQL 16 service.
This is NOT a 24/7 data collection instance and contains synthetic fixtures only.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from urban_ops.config import Config
from urban_ops.pipeline import ingest
from urban_ops.storage import make_engine


@pytest.mark.skipif(not os.getenv("URBAN_OPS_TEST_DATABASE_URL"), reason="No PostgreSQL test service")
def test_real_postgresql_bronze_silver_gold(tmp_path):
    root = Path(__file__).parent / "fixtures"
    url = os.environ["URBAN_OPS_TEST_DATABASE_URL"]
    engine = make_engine(url)
    assert engine.dialect.name == "postgresql"
    engine.dispose()
    run_id = f"postgres-smoke-{uuid4()}"
    config = Config(database_url=url, bronze_dir=tmp_path / "bronze")
    result = ingest(
        (root / "station_information.json").read_bytes(),
        (root / "station_status.json").read_bytes(),
        config,
        run_id=run_id,
        captured_at=datetime(2026, 10, 19, 11, 19, tzinfo=timezone.utc),
    )
    assert result["status"] == "success"
    assert result["stations"] == result["status_samples"] == 3
    assert result["usable_samples"] == 1
    assert result["quality_issues"] == 2
    engine = make_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT count(*) FROM fact_station_status WHERE run_id=:r"), {"r": run_id}
        ).scalar_one()
        assert rows == 3
        day_rows = conn.execute(
            text("SELECT count(*) FROM gold_station_daily WHERE day_utc=CAST(:d AS DATE)"),
            {"d": "2026-10-19"},
        ).scalar_one()
        assert day_rows == 3
    engine.dispose()

@pytest.mark.skipif(not os.getenv("URBAN_OPS_TEST_DATABASE_URL"), reason="No PostgreSQL test service")
def test_p4_postgres_analytics_views_and_csv(tmp_path):
    from importlib.resources import files
    from urban_ops.analytics import build_export
    url = os.environ["URBAN_OPS_TEST_DATABASE_URL"]
    engine = make_engine(url)
    script = files("urban_ops").joinpath("sql", "p4_postgres_views.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        # Top-level comments are fine: each CREATE VIEW starts after preceding semicolon.
        for sql in script.split(";"):
            if sql.strip():
                conn.exec_driver_sql(sql.strip())
        n = conn.execute(text("SELECT count(*) FROM vw_p4_hourly_station")).scalar_one()
        assert n >= 3
        n_2 = conn.execute(text("SELECT count(*) FROM vw_p4_network_hourly")).scalar_one()
        assert n_2 >= 1
    engine.dispose()
    manifest = build_export(url, tmp_path / "postgres-p4")
    assert manifest["unique_stations_observed"] >= 3
    assert manifest["tables"]["fact_station_hourly"]["rows"] >= 3