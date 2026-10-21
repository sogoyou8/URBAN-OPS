"""Structural verification of a P4 Power BI PBIP, NOT Power BI Desktop rendering.

Never asserts that Windows Power BI Desktop actually opened or rendered the
PBIP. The CSV hashes in the real P4 manifest must match their contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_PAGES=("01 · Réseau","02 · Territoires","03 · Stations","04 · Fiabilité")

def verify_pbip(project: Path) -> dict:
    from urban_ops.analytics import TABLES
    root=project/"UrbanOps.Report"/"definition"/"pages"
    pages=json.loads((root/"pages.json").read_text(encoding="utf-8"))
    ids=pages["pageOrder"]
    if len(ids)!=4 or len(set(ids))!=4:
        raise ValueError("Expected exactly four uniquely identified pages")
    names=[];visual_count=0
    for pid in ids:
        record=json.loads((root/pid/"page.json").read_text(encoding="utf-8"))
        names.append(record["displayName"])
        visuals=list((root/pid/"visuals").glob("*/visual.json"))
        if len(visuals)<3:
            raise ValueError("PBIP missing visuals on "+record["displayName"])
        for path in visuals:
            item=json.loads(path.read_text(encoding="utf-8"))
            if "visualType" not in item.get("visual",{}):
                raise ValueError("Visual contract incomplete: "+str(path))
        visual_count+=len(visuals)
    if tuple(names)!=EXPECTED_PAGES:
        raise ValueError(f"Unexpected pages or order: {names}")
    manifest=json.loads((project/"data/manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("has_usable_history") or manifest.get("unique_collections",0)<1:
        raise ValueError("No real qualified P4 history to check")
    for name in TABLES:
        path=project/"data"/(name+".csv")
        if not path.is_file() or name not in manifest["tables"]:
            raise ValueError("PBIP missing P4 data mart "+name)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=manifest["tables"][name]["sha256"]:
            raise ValueError("P4 source CSV SHA-256 mismatch: "+name)
    if not (project/"UrbanOps.pbip").is_file():
        raise ValueError("Missing PBIP project entrypoint")
    if not (project/"UrbanOps.SemanticModel"/"definition"/"model.tmdl").is_file():
        raise ValueError("Missing editable Power BI semantic model")
    if not (project/"UrbanOps.Report"/"definition.pbir").is_file():
        raise ValueError("Missing editable Power BI report")
    return {
        "status":"structural_pbip_ok_desktop_qa_pending",
        "pages":names,"visuals":visual_count,"verified_csv_tables":len(TABLES),
        "verified_p3_captures":manifest["unique_collections"],
        "power_bi_desktop_rendered":False,
        "action_needed":"Open UrbanOps.pbip in Power BI Desktop on Windows; set DataFolder; refresh and inspect all four pages."
    }

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--project",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("data/p4-pbip-qa.json"))
    args=p.parse_args()
    result=verify_pbip(args.project)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
