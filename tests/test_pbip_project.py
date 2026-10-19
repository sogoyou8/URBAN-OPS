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
    report=json.loads((project/'UrbanOps.Report/definition/report.json').read_text())
    assert 'themeCollection' in report
    assert (project/'UrbanOps.Report/StaticResources/RegisteredResources/UrbanOpsTheme.json').is_file()
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

def test_desktop_visual_corrections(tmp_path):
    export=synthetic_export(tmp_path)
    info=build(export,tmp_path/'corrected')
    project=Path(info['project'])
    pagefiles=list((project/'UrbanOps.Report/definition/pages').rglob('visual.json'))
    records={}
    for f in pagefiles:
        v=json.loads(f.read_text(encoding='utf-8'))
        label=v['visual']['visualContainerObjects']['title'][0]['properties']['text']['expr']['Literal']['Value'][1:-1]
        records[label]=v['visual']
    scatter=records['Stations — longitude / latitude']['query']['queryState']
    assert set(scatter)=={'X','Y','Tooltips'}
    assert scatter['X']['projections'][0]['field']['Column']['Property']=='longitude'
    assert scatter['Y']['projections'][0]['field']['Column']['Property']=='latitude'
    daily=records['Résumé par jour local']['query']['queryState']['Values']['projections']
    assert daily[0]['field']['Column']['Expression']['SourceRef']['Entity']=='dim_date'
    assert daily[0]['field']['Column']['Property']=='local_date'
    assert len(daily)==5
    assert records['Stations observées']['objects']['value'][0]['properties']['labelDisplayUnits']['expr']['Literal']['Value']=='1L'
    assert records['Stations observées']['objects']['label'][0]['properties']['show']['expr']['Literal']['Value']=='false'
    assert records['Cadence (> 10 min, si 2+ captures)']['query']['queryState']['Data']['projections'][0]['field']['Measure']['Property']=='Cadence verifiable'
    measures=(project/'UrbanOps.SemanticModel/definition/tables/_Measures.tmdl').read_text()
    assert '"Non mesurable"' in measures
    assert "COALESCE(CALCULATE(COUNTROWS('fact_runs')" in measures
