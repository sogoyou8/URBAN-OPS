CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
    info_sha256 TEXT,
    status_sha256 TEXT,
    station_information_count INTEGER,
    station_status_count INTEGER,
    inserted_status_count INTEGER,
    issue_count INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS raw_snapshots (
    run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    source_name TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes_uncompressed INTEGER NOT NULL,
    PRIMARY KEY(run_id,source_name)
);
CREATE TABLE IF NOT EXISTS dim_stations (
    station_id BIGINT PRIMARY KEY,
    station_code TEXT NOT NULL,
    station_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    capacity INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_station_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    station_id BIGINT NOT NULL REFERENCES dim_stations(station_id),
    collected_at TEXT NOT NULL,
    feed_updated_at TEXT NOT NULL,
    station_reported_at TEXT,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    mechanical_bikes INTEGER,
    electric_bikes INTEGER,
    is_installed INTEGER,
    is_renting INTEGER,
    is_returning INTEGER,
    reported_lag_seconds INTEGER,
    is_usable INTEGER NOT NULL DEFAULT 0,
    UNIQUE(run_id, station_id)
);
CREATE INDEX IF NOT EXISTS idx_status_station_collected ON fact_station_status(station_id,collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_status_collected ON fact_station_status(collected_at);
CREATE TABLE IF NOT EXISTS data_quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    station_id BIGINT,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('warning','error')),
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_issue_run ON data_quality_issues(run_id,issue_code);
CREATE TABLE IF NOT EXISTS quarantined_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    station_id BIGINT,
    reason TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gold_station_daily (
    station_id BIGINT NOT NULL REFERENCES dim_stations(station_id),
    day_utc TEXT NOT NULL,
    total_samples INTEGER NOT NULL,
    usable_samples INTEGER NOT NULL,
    empty_samples INTEGER NOT NULL,
    full_samples INTEGER NOT NULL,
    avg_available_bikes REAL,
    avg_available_docks REAL,
    refreshed_at TEXT NOT NULL,
    PRIMARY KEY(station_id,day_utc)
);
CREATE VIEW IF NOT EXISTS vw_station_latest AS
    SELECT * FROM (
       SELECT f.*, ROW_NUMBER() OVER(PARTITION BY station_id ORDER BY collected_at DESC,id DESC) AS row_position
       FROM fact_station_status f
    ) ranked WHERE row_position=1;
