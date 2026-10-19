import csv,hashlib,json
from pathlib import Path
import pytest
from scripts.build_pbip import build,MEASURES
from scripts.audit_history import audit
from urban_ops.analytics import build_export,TABLES
from urban_ops.config import Config
from urban_ops.pipeline import ingest

ROOT=Path(__file__).parent/'fixtures'

def synthetic_export(tmp_path):
    cfg=Config(database_url=f"sqlite:///{tmp_path/'db.sqlite'}",bronze_dir=tmp_path/'bronze')
    ingest((ROOT/'station_information.json').read_bytes(),(ROOT/'station_status.json').read_bytes(),cfg,run_id='test-fixture')
    out=tmp_path/'export'; build_export(cfg.database_url,out)
    return out

def test_pbip_four_pages_and_query_fields(tmp_path):
    dataset=synthetic_export(tmp_path)
    info=build(dataset,tmp_path/'report')
    assert info['pages']==4 and info['visuals']>=20 and info['tables']==9
    project=Path(info['project'])
    pages=(project/'UrbanOps.Report/definition/pages')
    order=json.loads((pages/'pages.json').read_text())['pageOrder']
    assert len(order)==4
    found=set()
    for name in order:
        d=json.loads((pages/name/'page.json').read_text())
        assert d['height']==720 and d['width']==1280
        found.add(d['displayName'])
        for p in (pages/name/'visuals').rglob('visual.json'):
            v=json.loads(p.read_text())
            for role in v['visual']['query']['queryState'].values():
                for ref in role['projections']:
                    f=ref['field']; kind,obj=next(iter(f.items()))
                    entity=obj['Expression']['SourceRef']['Entity']; prop=obj['Property']
                    assert prop in (MEASURES if entity=='_Measures' else TABLES[entity])
    assert found=={'01 · Réseau','02 · Territoires','03 · Stations','04 · Fiabilité'}
    assert len(list((project/'UrbanOps.SemanticModel/definition/tables').glob('*.tmdl')))==10
    assert 'fictif' not in (project/'README_OUVERTURE.md').read_text().lower()


def test_pbip_refuses_modified_data_or_missing_history(tmp_path):
    export=synthetic_export(tmp_path)
    f=export/'dim_station.csv'
    f.write_text('malicious',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA-256'):build(export,tmp_path/'report')


def test_coverage_single_capture_is_unknown(tmp_path):
    export=synthetic_export(tmp_path)
    stats=audit(export)
    assert stats['captures']==1
    assert stats['coverage_within_observed_period'] is None
    assert stats['enough_captures_for_trend'] is False