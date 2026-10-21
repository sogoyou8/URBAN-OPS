"""P5 fixtures are synthetic, NEVER counted as real operating metrics."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from urban_ops.p5 import (
    FEATURE_NAMES, Observation, Reservoir, bounded, collect_splits, evaluate,
    examples_and_latest, features_for, fit_and_score, readiness, split_limits,
    stream_examples,
)
from scripts.p5_inventory import inventory_report

T = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def obs(n, *, sid=101, bikes=4, usable=True, shift=0):
    return Observation(sid, T + timedelta(minutes=5*n, seconds=shift), bikes,
                       8 - bikes, 8, mechanical=bikes, electric=0, latitude=48.86,
                       longitude=2.32, report_lag_seconds=80, usable=usable)


def test_target_is_actual_future_capture_not_filled_value():
    sequence = [obs(n, bikes=1 if n >= 6 else 4) for n in range(8)]
    examples, latest = examples_and_latest(sequence)
    assert examples[0].feature_at == obs(0).at
    assert examples[0].target_at == obs(6).at
    assert examples[0].target_bikes == 1
    assert latest[101].values[0] == 1
    assert len(examples) == 2


def test_hole_in_capture_history_yields_no_fabricated_label():
    examples, _ = examples_and_latest([obs(0), obs(12)])
    assert examples == []


def test_tolerance_accepts_real_observation_with_small_drift():
    examples, _ = examples_and_latest([obs(0), obs(6,shift=70)])
    assert len(examples) == 1
    assert examples[0].target_at == obs(6,shift=70).at


def test_invalid_targets_are_never_labeled():
    samples = [obs(0), obs(6,usable=False)]
    assert examples_and_latest(samples)[0] == []
    samples = [obs(0,usable=False), obs(6)]
    assert examples_and_latest(samples)[0] == []


def test_features_have_strict_past_only_lags():
    rows = [obs(0,bikes=3),obs(1,bikes=4),obs(2,bikes=5),obs(3,bikes=6)]
    _, latest = examples_and_latest(rows)
    f = latest[101]
    assert len(f.values) == len(FEATURE_NAMES)
    assert f.values[6] == 5  # 5-minute past
    assert f.values[7] == 3  # 15-minute past
    assert f.values[8] == 1  # change in previous 5 min
    assert f.values[9] == 3


def test_duplicate_capture_timestamp_not_reused():
    rows = [obs(0),obs(0,bikes=1),obs(6),obs(6,bikes=1)]
    assert len(examples_and_latest(rows)[0]) == 1


def test_unsorted_station_data_rejected():
    with pytest.raises(ValueError,match='Unsorted'):
        list(stream_examples([obs(1),obs(0)]))


def test_insufficient_real_capture_count_blocks_training():
    actual_count_like_now = [T, T+timedelta(hours=3), T+timedelta(hours=4)]
    report=readiness(actual_count_like_now)
    assert report['ready'] is False
    assert report['reason']=='insufficient_calendar_span'
    assert report['captures']==3


def test_weeklong_regular_fixture_is_eligible_but_not_real():
    series=[T + timedelta(minutes=n*5) for n in range(8*24*12+1)]
    report=readiness(series)
    assert report['ready'] is True
    assert report['coverage_estimate']==1


def test_sparse_weeklong_data_cannot_pass_coverage_gate():
    series=[T + timedelta(hours=n) for n in range(8*24+1)]
    report=readiness(series)
    assert not report['ready']
    assert report['coverage_estimate'] < 0.10


def test_training_labels_purged_across_temporal_boundaries():
    series=[obs(n) for n in range(8*24*12+1)]
    captures=[x.at for x in series]
    sets, last, (v,t) = collect_splits(series,captures,max_train=99999,max_eval=99999)
    assert sets['train'].seen > 0 and sets['validation'].seen > 0 and sets['test'].seen > 0
    assert all(x.target_at < v for x in sets['train'].items)
    assert all(v <= x.feature_at < t and x.target_at < t for x in sets['validation'].items)
    assert all(x.feature_at >= t for x in sets['test'].items)
    assert last[101].feature_at == series[-1].at


def test_no_trained_model_when_there_arent_enough_pairs():
    sets={key: Reservoir(10,1) for key in ('train','validation','test')}
    model, summary = fit_and_score(sets)
    assert model is None and summary['status']=='insufficient_labeled_pairs'


def test_clips_predictions_to_physical_station_capacity():
    from urban_ops.p5 import Example
    a=Example(101,T,T+timedelta(minutes=30), (4.,2.,8.) + (math.nan,)*13,4.)
    assert bounded([-2],[a]) == [0]
    assert bounded([150],[a]) == [8]


def test_inventory_gate_on_release_names():
    now=T + timedelta(days=1)
    asset={'name': 'capture-20261012T120000Z-1234abcd.tar.gz'}
    data=[{'tag_name':'velib-data-2026-10-12', 'assets':[asset]}]
    report=inventory_report(data,now)
    assert report['readiness']['captures']==1
    assert report['status']=='insufficient_history'


def test_p5_boundary_daylight_saving_not_nan():
    before=datetime(2026,10,25,0,30,tzinfo=timezone.utc)
    after=datetime(2026,10,25,1,30,tzinfo=timezone.utc)
    # Same local hour but different UTC instants; temporal source is UTC.
    a=Observation(101,before,4,4,8)
    b=Observation(101,after,4,4,8)
    assert features_for(a,[]).feature_at != features_for(b,[]).feature_at


def test_sql_reader_only_successful_runs_and_not_usable_as_labels(tmp_path):
    import sqlite3
    from urban_ops.p5 import sql_observations, successful_captures
    database = tmp_path/'tiny.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript('''
            CREATE TABLE ingestion_runs(run_id TEXT,started_at TEXT,status TEXT);
            CREATE TABLE dim_stations(station_id INTEGER,capacity INTEGER,latitude REAL,longitude REAL);
            CREATE TABLE fact_station_status(id INTEGER,run_id TEXT,station_id INTEGER,collected_at TEXT,
              num_bikes_available INTEGER,num_docks_available INTEGER,mechanical_bikes INTEGER,
              electric_bikes INTEGER,reported_lag_seconds INTEGER,is_usable INTEGER);
        ''')
        db.execute("INSERT INTO dim_stations VALUES (101,8,48.87,2.33)")
        for i,state in enumerate(('success','failed','success')):
            db.execute("INSERT INTO ingestion_runs VALUES (?,?,?)", (f'run{i}', (T+timedelta(minutes=30*i)).isoformat(),state))
            db.execute("INSERT INTO fact_station_status VALUES (?,?,?,?,?,?,?,?,?,?)",
                (i,f'run{i}',101,(T+timedelta(minutes=30*i)).isoformat(),4,4,4,0,10,1 if i == 0 else 0))
    path='sqlite:///'+str(database)
    captures=successful_captures(path)
    observations=list(sql_observations(path))
    assert len(captures)==2 and len(observations)==2
    assert observations[-1].usable is False
    assert examples_and_latest(observations)[0]==[]


def test_cli_rejects_thin_history_and_creates_no_model(tmp_path):
    import sqlite3
    from scripts.train_p5 import run
    from pathlib import Path
    dbfile=tmp_path/'thin.sqlite'
    with sqlite3.connect(dbfile) as db:
        db.execute('CREATE TABLE ingestion_runs(run_id TEXT, started_at TEXT, status TEXT)')
        db.execute('INSERT INTO ingestion_runs VALUES (?,?,?)',('one',T.isoformat(),'success'))
    result=run('sqlite:///'+str(dbfile),tmp_path/'output')
    assert result['status']=='not_ready'
    assert (tmp_path/'output'/'P5_STATUS.json').is_file()
    assert not (tmp_path/'output'/'model.joblib').exists()


def synthetic_paired_examples(count=1400, *, signal=True):
    """Model algorithm tests only. Fabricated examples never used as real evidence."""
    from urban_ops.p5 import Example
    for i in range(count):
        now = T + timedelta(minutes=5*i)
        current = i % 9
        target = (current + 3) % 9 if signal else current
        values = (float(current), float(8-current), 8., float(current), 0., 80.,
                  float((current-1)%9), float((current-3)%9), 1., 3.,
                  0.,1.,0.,1.,48.86,2.32)
        yield Example(101,now,now+timedelta(minutes=30),values,float(target))


def test_synthetic_model_training_and_evaluation_path():
    pytest.importorskip('sklearn')
    sets={key: Reservoir(3000,seed) for key,seed in [('train',1),('validation',2),('test',3)]}
    for key,count in [('train',1000),('validation',200),('test',200)]:
        for item in synthetic_paired_examples(count):
            sets[key].add(item)
    model, result=fit_and_score(sets,min_train=200,min_eval=100)
    assert result['status']=='validated_model'
    assert model is not None
    assert result['holdout']['ml_mae'] < result['holdout']['persistence_mae']


def test_perfect_persistence_baseline_blocks_fake_ml_skill():
    pytest.importorskip('sklearn')
    sets={key: Reservoir(2000,seed) for key,seed in [('train',1),('validation',2),('test',3)]}
    for key,count in [('train',1000),('validation',200),('test',200)]:
        for item in synthetic_paired_examples(count,signal=False):
            sets[key].add(item)
    model, result=fit_and_score(sets,min_train=200,min_eval=100)
    assert result['validation']['persistence_mae']==0
    assert result['holdout']['mae_skill_vs_persistence'] is None
    assert result['status']=='baseline_wins_or_uncertain'
    assert model is None


def test_many_captures_in_the_same_five_minute_slots_cannot_unlock_p5():
    # 935 unique UTC instants over >= 7 days, but only 85 distinct five-minute
    # bins. The previous len(times)/span calculation could report >40%.
    bursty = [
        T + timedelta(hours=2 * block, seconds=second)
        for block in range(85)
        for second in range(11)
    ]
    outcome = readiness(bursty)
    assert outcome["captures"] == 935
    assert outcome["span_days"] >= 7
    assert outcome["distinct_5m_slots"] == 85
    assert outcome["repeated_5m_slot_captures"] == 850
    assert outcome["coverage_estimate"] < 0.10
    assert outcome["reason"] == "insufficient_capture_coverage"
    assert outcome["ready"] is False


def test_readiness_explains_remaining_span_and_capture_requirements():
    samples = [T, T + timedelta(days=1)]
    info = readiness(samples)
    assert info["remaining_captures_to_min"] == 898
    assert info["hours_to_minimum_span"] == 144.0
    assert info["earliest_span_eligibility_utc"] == (T+timedelta(days=7)).isoformat()
    assert info["expected_5m_slots"] == 289
    assert info["distinct_5m_slots"] == 2


def test_empty_readiness_exposes_safe_nulls():
    report = readiness([])
    assert report["ready"] is False
    assert report["distinct_5m_slots"] == 0
    assert report["expected_5m_slots"] is None
    assert report["earliest_span_eligibility_utc"] is None
