"""Only structural fixture tests; not a claim that Microsoft Power BI rendered."""
import hashlib
import json

import pytest

from scripts.check_p4_pbip import verify_pbip, EXPECTED_PAGES
from urban_ops.analytics import TABLES

def create_fixture(tmp_path):
    project=tmp_path/"UrbanOps"
    project.mkdir()
    (project/"UrbanOps.pbip").write_text("{}")
    model=project/"UrbanOps.SemanticModel"/"definition"
    model.mkdir(parents=True)
    (model/"model.tmdl").write_text("model Model")
    report=project/"UrbanOps.Report"
    report.mkdir()
    (report/"definition.pbir").write_text("{}")
    pages=report/"definition"/"pages"
    pages.mkdir(parents=True)
    ids=["a","b","c","d"]
    (pages/"pages.json").write_text(json.dumps({"pageOrder":ids}))
    for pid,title in zip(ids,EXPECTED_PAGES):
        page=pages/pid
        page.mkdir()
        (page/"page.json").write_text(json.dumps({"displayName":title}))
        for v in range(3):
            visual=page/"visuals"/str(v)
            visual.mkdir(parents=True)
            (visual/"visual.json").write_text(json.dumps({"visual":{"visualType":"cardVisual"}}))
    dat=project/"data";dat.mkdir()
    table_hashes={}
    for name,columns in TABLES.items():
        raw=(",".join(columns)+"\n").encode()
        (dat/(name+".csv")).write_bytes(raw)
        table_hashes[name]={"sha256":hashlib.sha256(raw).hexdigest()}
    (dat/"manifest.json").write_text(json.dumps({
        "has_usable_history":True,
        "unique_collections":3,
        "tables":table_hashes
    }))
    return project

def test_pbip_check_requires_four_pages_and_hashed_csv(tmp_path):
    project=create_fixture(tmp_path)
    result=verify_pbip(project)
    assert result["pages"]==list(EXPECTED_PAGES)
    assert result["visuals"]==12
    assert result["power_bi_desktop_rendered"] is False
    assert result["status"]=="structural_pbip_ok_desktop_qa_pending"
    (project/"data/dim_station.csv").write_text("tampered\n")
    with pytest.raises(ValueError,match="SHA-256"):
        verify_pbip(project)

def test_pbip_check_rejects_missing_visuals(tmp_path):
    project=create_fixture(tmp_path)
    visual=project/"UrbanOps.Report"/"definition"/"pages"/"a"/"visuals"/"0"/"visual.json"
    visual.unlink()
    with pytest.raises(ValueError,match="missing visuals"):
        verify_pbip(project)
