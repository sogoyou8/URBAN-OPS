"""P6.9 packaging tests; ALL fixtures here are synthetic and ephemeral."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.package_p6_public import prepare, verify


def fixture(tmp_path):
    src = tmp_path / 'web'
    for d in ('src', 'data'):
        (src / d).mkdir(parents=True)
    (src / 'index.html').write_text('''<!doctype html><html><head><meta charset="utf-8"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<script defer src="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
</head><body>Fixture only, not publishable</body></html>''', encoding='utf8')
    for path in ('src/main.js', 'src/core.js', 'src/history.js', 'src/style.css'):
        (src / path).write_text('body{}' if path.endswith('.css') else 'export const test=true;', encoding='utf8')
    captured = datetime.now(timezone.utc) - timedelta(minutes=15)
    d = {
        'schema_version': 1, 'dataset_type': 'archived_p3_observations',
        'source': "Vélib' Métropole open data (ODbL) via URBAN-OPS P3",
        'source_url': 'https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole',
        'run_id': '2026-10-20T034500-collect-r1', 'captured_at': captured.isoformat(),
        'generated_at': captured.isoformat(), 'metrics': {'stations': 1200, 'capture_count': 1},
        'stations': [{'id': i, 'lat': 48.85, 'lon': 2.35} for i in range(1200)],
        'history': [{'at': captured.isoformat()}], 'forecast': {'status': 'unavailable'}
    }
    (src / 'data/network.json').write_text(json.dumps(d), encoding='utf8')
    replay = tmp_path/'replay.json'
    replay.write_text(json.dumps([{'run_id': d['run_id'], 'status': 'success', 'asset': 'data/p6-captures/capture-01.tar.gz'}]))
    vendor = tmp_path / 'vendor'
    vendor.mkdir()
    for fn in ('maplibre-gl.js', 'maplibre-gl.css'):
        (vendor / fn).write_bytes(b'/* vendored fixture, never deploy */' * 10)
    return src, replay, vendor, d


def test_p69_bundle_has_verified_digests_and_no_remote_scripts(tmp_path):
    src, replay, vendor, d = fixture(tmp_path)
    out = tmp_path/'dist'
    m = prepare(src, out, vendor, replay)
    assert m['status']=='publication_ready_not_deployed'
    assert verify(out)['validated']
    assert (out/'data/network.json').exists()
    assert (out/'src/history.js').is_file()
    assert 'src/history.js' in m['files_sha256']
    assert (out/'src/history.js').read_text() == 'export const test=true;'

    index = (out/'index.html').read_text()
    assert 'script-src \'self\'' in index
    assert 'src="./vendor/maplibre-gl.js"' in index
    assert 'src="https://cdn' not in index
    assert not (out/'.env').exists()
    assert set(p.name for p in out.iterdir()) == {'index.html','src','vendor','data','manifest.json','provenance.json','.nojekyll'}
    (out/'src/main.js').write_text('tampering')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        verify(out)


def test_p69_refuses_mismatched_replay_and_stale_data(tmp_path):
    src, replay, vendor, d = fixture(tmp_path)
    out = tmp_path/'dist'
    replay.write_text(json.dumps([{'run_id':'different', 'asset':'capture-x.tar.gz','status':'success'}]))
    with pytest.raises(ValueError,match='replay'):
        prepare(src,out,vendor,replay)
    replay.write_text(json.dumps([{'run_id':d['run_id'], 'asset':'capture-x.tar.gz','status':'success'}]))
    d['captured_at'] = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat()
    (src/'data/network.json').write_text(json.dumps(d))
    with pytest.raises(ValueError,match='fresh enough'):
        prepare(src,out,vendor,replay)


def test_p69_refuses_model_predictions_and_fixture(tmp_path):
    src, replay, vendor, d = fixture(tmp_path)
    out = tmp_path/'dist'
    d['forecast']['status']='available'
    (src/'data/network.json').write_text(json.dumps(d))
    with pytest.raises(ValueError,match='P5 predictions'):
        prepare(src,out,vendor,replay)
    d['forecast']['status']='unavailable'
    d['run_id']='TEST_BROWSERS_ONLY'
    replay.write_text(json.dumps([{'run_id':d['run_id'], 'asset':'capture-test.tar.gz','status':'success'}]))
    (src/'data/network.json').write_text(json.dumps(d))
    with pytest.raises(ValueError,match='test fixture'):
        prepare(src,out,vendor,replay)


def test_p69_refuses_extra_files_in_public_package(tmp_path):
    src, replay, vendor, d = fixture(tmp_path)
    out=tmp_path/'dist'
    prepare(src,out,vendor,replay)
    (out/'.env').write_text('forbidden=true')
    with pytest.raises(ValueError,match='release files'):
        verify(out)

def test_p69_requires_history_module_before_packaging(tmp_path):
    src, replay, vendor, _ = fixture(tmp_path)
    (src / 'src/history.js').unlink()
    with pytest.raises(ValueError, match='Missing app source'):
        prepare(src, tmp_path/'dist', vendor, replay)
