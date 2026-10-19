-- P4: read-only analytic views, PostgreSQL 16.
-- Grain is a captured station status, not a trip or duration. Idempotent CREATE OR REPLACE.
-- UTC hour distinguishes both occurrences of 02:00 during Europe/Paris autumn DST.
CREATE OR REPLACE VIEW vw_p4_hourly_station AS
WITH valid AS (
    SELECT f.*, date_trunc('hour',f.collected_at) AS utc_hour
    FROM fact_station_status f
    JOIN ingestion_runs r ON r.run_id=f.run_id AND r.status='success'
)
SELECT station_id, utc_hour AS utc_hour_start,
       (utc_hour AT TIME ZONE 'Europe/Paris')::date AS local_date,
       EXTRACT(HOUR FROM (utc_hour AT TIME ZONE 'Europe/Paris'))::integer AS local_hour,
       COUNT(*)::bigint AS samples,
       COUNT(*) FILTER(WHERE is_usable=1)::bigint AS usable_samples,
       COUNT(*) FILTER(WHERE is_usable<>1)::bigint AS invalid_samples,
       COUNT(*) FILTER(WHERE is_usable=1 AND num_bikes_available=0)::bigint AS empty_samples,
       COUNT(*) FILTER(WHERE is_usable=1 AND num_docks_available=0)::bigint AS full_samples,
       SUM(num_bikes_available) FILTER(WHERE is_usable=1) AS sum_bikes_available,
       SUM(num_docks_available) FILTER(WHERE is_usable=1) AS sum_docks_available,
       AVG(num_bikes_available) FILTER(WHERE is_usable=1) AS avg_bikes_available,
       AVG(num_docks_available) FILTER(WHERE is_usable=1) AS avg_docks_available,
       COUNT(DISTINCT station_reported_at) FILTER(WHERE is_usable=1) AS distinct_station_reports
FROM valid GROUP BY station_id, utc_hour;

CREATE OR REPLACE VIEW vw_p4_daily_station AS
SELECT station_id, local_date,
       SUM(samples)::bigint AS samples,
       SUM(usable_samples)::bigint AS usable_samples,
       SUM(invalid_samples)::bigint AS invalid_samples,
       SUM(empty_samples)::bigint AS empty_samples,
       SUM(full_samples)::bigint AS full_samples,
       SUM(sum_bikes_available)::bigint AS sum_bikes_available,
       SUM(sum_docks_available)::bigint AS sum_docks_available,
       SUM(sum_bikes_available)::numeric / NULLIF(SUM(usable_samples), 0) AS avg_bikes_available,
       SUM(sum_docks_available)::numeric / NULLIF(SUM(usable_samples), 0) AS avg_docks_available
FROM vw_p4_hourly_station GROUP BY station_id, local_date;

CREATE OR REPLACE VIEW vw_p4_network_hourly AS
SELECT utc_hour_start, local_date, local_hour,
       COUNT(DISTINCT station_id)::integer AS observed_stations,
       SUM(samples)::bigint AS samples,
       SUM(usable_samples)::bigint AS usable_samples,
       SUM(invalid_samples)::bigint AS invalid_samples,
       SUM(empty_samples)::bigint AS empty_samples,
       SUM(full_samples)::bigint AS full_samples,
       SUM(sum_bikes_available)::numeric / NULLIF(SUM(usable_samples), 0) AS avg_bikes_available,
       SUM(sum_docks_available)::numeric / NULLIF(SUM(usable_samples), 0) AS avg_docks_available
FROM vw_p4_hourly_station
GROUP BY utc_hour_start, local_date, local_hour;

CREATE OR REPLACE VIEW vw_p4_quality_by_capture AS
SELECT r.run_id, r.started_at AS collected_at, r.status, r.inserted_status_count,
       r.issue_count,
       COUNT(f.id) AS station_rows,
       COUNT(f.id) FILTER(WHERE f.is_usable=1) AS usable_rows,
       COUNT(f.id) FILTER(WHERE f.is_usable<>1) AS invalid_rows
FROM ingestion_runs r
LEFT JOIN fact_station_status f ON f.run_id=r.run_id
GROUP BY r.run_id, r.started_at, r.status, r.inserted_status_count, r.issue_count;