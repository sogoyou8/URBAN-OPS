"""Audit P4 coverage without pretending a single snapshot is a time series."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path


def moment(v):return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(timezone.utc)

def audit(folder:Path,now:datetime|None=None,expected_minutes=5):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    runs=int(manifest['unique_collections'])
    start=moment(manifest['from_utc']) if manifest['from_utc'] else None
    end=moment(manifest['through_utc']) if manifest['through_utc'] else None
    now=now or datetime.now(timezone.utc)
    gap_stats=[]
    with (folder/'fact_capture_intervals.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['gap_minutes'] not in ('',None):gap_stats.append(float(row['gap_minutes']))
    expected=1+int((end-start).total_seconds()//(expected_minutes*60)) if runs>=2 else None
    count=len(gap_stats)
    out={
        'captures':runs,'from_utc':manifest['from_utc'],'through_utc':manifest['through_utc'],
        'expected_slots_within_observed_period':expected,
        'coverage_within_observed_period':round(min(1,runs/expected),4) if expected else None,
        'max_observed_gap_minutes':round(max(gap_stats),3) if count else None,
        'gaps_over_10_minutes':sum(x>10 for x in gap_stats),
        'capture_age_minutes':round((now-end).total_seconds()/60,2) if end else None,
        'enough_captures_for_trend':runs>=12 and bool(gap_stats) and max(gap_stats)<=20,
    }
    # If no samples or no history, do not mark as 100% coverage.
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--csv-dir',required=True,type=Path);a=p.parse_args()
    print(json.dumps(audit(a.csv_dir),ensure_ascii=False,indent=2))
if __name__=='__main__':main()