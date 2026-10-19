"""P4 tests use synthetic fixtures, never claim network-level empirical findings."""
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from urban_ops.analytics import build_export
from urban_ops.config import Config
from urban_ops.pipeline import ingest

FIXTURES = Path(__file__).parent / "fixtures"

def ingest_twice(tmp_path):
    cfg = Config(database_url=f"sqlite:///{tmp_path/'history.sqlite'}", bronze_dir=tmp_path/'bronze')
    info = (FIXTURES/'station_information.json').read_bytes()
    status = (FIXTURES/'station_status.json').read_bytes()
    when = datetime(2026,10,19, 11,19, tzinfo=timezone.utc)
    ingest(info, status, cfg, captured_at=when, run_id='t1')
    doc = json.loads(status)
    row = doc['data']['stations'][0]
    row['num_bikes_available'] = row['numBikesAvailable'] = 1
    row['num_docks_available'] = row['numDocksAvailable'] = 9
    row['num_bikes_available_types'] = [{'mechanical':1},{'ebike':0}]
    # Set an updated report time within the upstream feed's time bounds.
    row['last_reported'] = doc['lastUpdatedOther']
    ingest(info, json.dumps(doc).encode(), cfg, captured_at=when+timedelta(minutes=5), run_id='t2')
    return cfg


def csv_rows(root, name):
    with (root/f'{name}.csv').open(encoding='utf-8-sig', newline='') as fp:
        return list(csv.DictReader(fp))


def test_p4_two_observations_and_weighted_values(tmp_path):
    cfg = ingest_twice(tmp_path)
    out = tmp_path/'exports'
    manifest = build_export(cfg.database_url, out)
    assert manifest['unique_collections']==2
    assert manifest['unique_stations_observed']==3
    hr = [r for r in csv_rows(out,'fact_station_hourly') if r['station_id']=='101']
    assert len(hr)==1
    x = hr[0]
    assert x['samples']=='2' and x['usable_samples']=='2'
    assert x['empty_samples']=='1' and x['full_samples']=='0'
    assert x['sum_bikes_available']=='1'
    assert x['avg_bikes_available']=='0.5'
    assert x['local_date']=='2026-10-19' and x['local_hour']=='13'
    assert x['utc_offset_minutes']=='120'
    assert csv_rows(out,'fact_station_daily')[0]['station_id']=='101'
    net = csv_rows(out,'fact_network_hourly')
    assert len(net)==1 and net[0]['samples']=='6'
    assert len(csv_rows(out,'fact_station_latest'))==3
    assert csv_rows(out,'fact_station_latest')[0]['num_bikes_available']=='1'
    assert len(csv_rows(out,'fact_issues'))==4
    assert all(len(v['sha256'])==64 for v in manifest['tables'].values())


def test_p4_utc_day_range_and_no_samples_outside(tmp_path):
    cfg = ingest_twice(tmp_path)
    out = tmp_path/'export'
    meta = build_export(cfg.database_url,out,start=date(2026,10,20),end=date(2026,10,20))
    assert meta['unique_collections']==0
    assert len(csv_rows(out,'dim_station'))==0
    assert len(csv_rows(out,'fact_station_hourly'))==0
    assert len(csv_rows(out,'fact_network_hourly'))==0
    assert meta['from_utc'] is None
    assert meta['has_usable_history'] is False


def test_p4_missing_date_endpoint_rejected(tmp_path):
    cfg=ingest_twice(tmp_path)
    with pytest.raises(ValueError,match='both'):
        build_export(cfg.database_url,tmp_path/'failed',start=date(2026,10,19))
    with pytest.raises(ValueError,match='<='):
        build_export(cfg.database_url,tmp_path/'failed',start=date(2026,10,20),end=date(2026,10,19))


def test_p4_optional_observations_and_idempotent_reexport(tmp_path):
    cfg=ingest_twice(tmp_path)
    out=tmp_path/'exports'
    m=build_export(cfg.database_url,out,include_samples=True)
    assert len(csv_rows(out,'fact_observations'))==6
    checksum=m['tables']['fact_station_hourly']['sha256']
    m2=build_export(cfg.database_url,out,include_samples=True)
    assert m2['tables']['fact_station_hourly']['sha256']==checksum


def test_dst_spring_clock_transition_is_unambiguous():
    from urban_ops.analytics import hour_start, PARIS
    first=datetime(2026,3,29,0,0,tzinfo=timezone.utc)
    second=first+timedelta(hours=1)
    assert first.astimezone(PARIS).hour==1
    assert second.astimezone(PARIS).hour==3
    assert hour_start(first)!=hour_start(second)


def test_dst_autumn_duplicate_hour_has_distinct_offsets():
    from urban_ops.analytics import PARIS
    a=datetime(2026,10,25,0,30,tzinfo=timezone.utc).astimezone(PARIS)
    b=datetime(2026,10,25,1,30,tzinfo=timezone.utc).astimezone(PARIS)
    assert a.hour==b.hour==2
    assert a.utcoffset()!=b.utcoffset()