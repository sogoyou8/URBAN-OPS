"""P6 SQL fixture integration; constructed station values are TEST DATA ONLY."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.export_p6 import export


def create_db(path):
    db = sqlite3.connect(path)
    db.executescript('''
    CREATE TABLE ingestion_runs (run_id TEXT PRIMARY KEY, started_at TEXT, status TEXT, station_status_count INT);
    CREATE TABLE dim_stations (station_id INT PRIMARY KEY, station_code TEXT, station_name TEXT, latitude REAL, longitude REAL, capacity INT);
    CREATE TABLE fact_station_status (station_id INT, run_id TEXT, collected_at TEXT, station_reported_at TEXT,
        num_bikes_available INT, num_docks_available INT, mechanical_bikes INT, electric_bikes INT,
        reported_lag_seconds INT, is_usable INT, is_installed INT, is_renting INT, is_returning INT);
    CREATE TABLE data_quality_issues (run_id TEXT,station_id INT,issue_code TEXT,severity TEXT);
    ''')
    db.executemany('INSERT INTO dim_stations VALUES (?,?,?,?,?,?)',[
        (1,'001','A & <B>',48.85,2.34,20), (2,'002','Without observation',48.86,2.35,12),
        (3,'003','Invalid station',48.86,2.36,18),
    ])
    db.executemany('INSERT INTO ingestion_runs VALUES (?,?,?,?)', [
        ('a','2026-10-20T08:00:00+00:00','success',2),
        ('b','2026-10-20T08:45:00+00:00','success',2),
        ('c','2026-10-20T08:55:00+00:00','failed',1),
    ])
    db.executemany('INSERT INTO fact_station_status VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',[
        (1,'a','2026-10-20T08:00:00+00:00','2026-10-20T07:59:20+00:00',5,15,3,2,40,1,1,1,1),
        (3,'a','2026-10-20T08:00:00+00:00',None,3,15,2,1,None,0,0,0,0),
        (1,'b','2026-10-20T08:45:00+00:00','2026-10-20T08:44:00+00:00',0,20,0,0,60,1,1,1,1),
        (3,'b','2026-10-20T08:45:00+00:00',None,99,0,90,9,None,0,0,0,0),
    ])
    db.execute("INSERT INTO data_quality_issues VALUES ('b',3,'stale_station_report','warning')")
    db.commit();db.close()


def test_empty_history_rejected(tmp_path):
    p=tmp_path/'empty.sqlite';create_db(p)
    with sqlite3.connect(p) as db:db.execute('DELETE FROM ingestion_runs');db.commit()
    with pytest.raises(ValueError,match='No real successful'):
        export('sqlite:///'+str(p))


def test_snapshot_is_one_latest_run_without_mixing_ages(tmp_path):
    p=tmp_path/'x.sqlite';create_db(p)
    d=export('sqlite:///'+str(p), now=datetime(2026,10,20,9,tzinfo=timezone.utc))
    assert d['run_id']=='b'
    assert d['captured_at']=='2026-10-20T08:45:00Z'
    assert d['metrics']=={'stations':3,'observed':2,'usable':1,'unusable':1,'bikes':0,'docks':20,'empty':1,'capture_count':2}
    a,b,c=d['stations']
    assert a['condition']=='empty' and a['bikes']==0 and a['docks']==20
    assert b['condition']=='unknown' and b['bikes'] is None and not b['observed']
    assert c['condition']=='unknown' and c['bikes'] is None and c['lag_seconds'] is None
    assert d['forecast']['status']=='unavailable'
    assert d['issues']==[{'code':'stale_station_report','count':1}]
    assert d['quality_diagnostics']=={
        'not_observed':1, 'observed_but_unusable':1,
        'observed_non_operational':1, 'stations_with_multiple_issue_events':0,
        'limitation':'Issue events overlap; an issue count is not a distinct station count.'
    }
    assert d['stations'][2]['issues']==[{'code':'stale_station_report','severity':'warning'}]
    assert d['stations'][1]['issues']==[]
    assert d['p5_readiness']['status']=='unavailable'
    assert d['history'][1]['gap_minutes']==45 and not d['history'][1]['connected_to_previous']


def test_history_limit_and_no_stations(tmp_path):
    p=tmp_path/'x.sqlite';create_db(p)
    with pytest.raises(ValueError):export('sqlite:///'+str(p),history_limit=97)
    assert export('sqlite:///'+str(p),history_limit=1)['metrics']['capture_count']==1
    with sqlite3.connect(p) as db:db.execute('DELETE FROM dim_stations');db.commit()
    with pytest.raises(ValueError,match='Missing real station'):
        export('sqlite:///'+str(p))
def test_readiness_is_only_repository_filename_inventory(tmp_path):
    import json
    from scripts.export_p6 import main
    p=tmp_path/'capture.sqlite';create_db(p)
    f=tmp_path/'inventory.json'
    d={"source":"GitHub Release asset names (not P3 revalidated content)",
       "readiness":{"ready":False,"captures":13,"span_days":0.2,
                    "coverage_estimate":0.3,"reason":"insufficient_calendar_span",
                    "from_utc":"2026-10-20T01:00:00+00:00",
                    "through_utc":"2026-10-20T05:00:00+00:00"}}
    f.write_text(json.dumps(d),encoding='utf-8')
    out=tmp_path/'network.json'
    main(['--db-url','sqlite:///'+str(p),'--output',str(out),'--p5-inventory',str(f)])
    x=json.loads(out.read_text(encoding='utf-8'))
    assert x['p5_readiness']['status']=='insufficient_history'
    assert x['p5_readiness']['captures']==13
    assert 'NOT checksum' in x['p5_readiness']['limitation']
    d['source']='fabricated certainty'
    f.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ValueError,match='Unverified P5 inventory'):
        main(['--db-url','sqlite:///'+str(p),'--output',str(out),'--p5-inventory',str(f)])

def test_latest_success_with_zero_usable_is_not_zero_available(tmp_path):
    p=tmp_path/'zero.sqlite';create_db(p)
    with sqlite3.connect(p) as db:
        db.execute("UPDATE fact_station_status SET is_usable=0 WHERE run_id='b'")
        db.commit()
    d=export('sqlite:///'+str(p))
    assert d['metrics']['observed']==2
    assert d['metrics']['usable']==0
    assert d['metrics']['bikes'] is None
    assert d['metrics']['docks'] is None
    assert d['metrics']['empty'] is None
    assert d['capture_quality']['status']=='no_usable_stations'
    last=d['history'][-1]
    assert last['usable']==0 and last['bikes'] is None and last['empty'] is None
    assert last['at']==d['captured_at']  # Keep the actual 0-usable capture
    assert all(station['bikes'] is None for station in d['stations'])
    assert d['history'][0]['bikes']==5  # Preserve earlier valid history

def test_sql_forensic_anomaly_neighbors_do_not_invent_cause(tmp_path):
    from scripts.diagnose_p3_capture import diagnose
    p=tmp_path/'audit.sqlite';create_db(p)
    with sqlite3.connect(p) as db:
        db.execute("ALTER TABLE ingestion_runs ADD COLUMN station_information_count INT")
        db.execute("ALTER TABLE ingestion_runs ADD COLUMN inserted_status_count INT")
        db.execute("ALTER TABLE fact_station_status ADD COLUMN feed_updated_at TEXT")
        db.execute("UPDATE fact_station_status SET is_usable=0 WHERE run_id='b'")
        db.commit()
    audit=diagnose('sqlite:///'+str(p))
    assert audit['status']=='anomalies_detected'
    assert audit['runs_examined']==2
    assert len(audit['anomalies'])==1
    problem=audit['anomalies'][0]
    assert problem['usable']==0 and problem['observed']==2
    assert problem['previous_run']['usable']==1
    assert problem['following_run'] is None
    assert problem['diagnostic_factors_not_mutually_exclusive']['recorded']==2
    assert problem['diagnostic_factors_not_mutually_exclusive']['missing_total_bikes']==0
    assert problem['diagnostic_factors_not_mutually_exclusive']['missing_total_docks']==0
    assert problem['diagnostic_factors_not_mutually_exclusive']['missing_mechanical_bikes']==0
    assert problem['diagnostic_factors_not_mutually_exclusive']['missing_electric_bikes']==0
    assert problem['issue_counts_not_distinct_station_counts'][0]['code']=='stale_station_report'
