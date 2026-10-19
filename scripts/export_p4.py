"""Export a P3 SQLite or PostgreSQL database to Power BI ready analytic CSV tables."""
import argparse
import json
from datetime import date
from pathlib import Path
from urban_ops.analytics import build_export


def main(argv=None):
    p = argparse.ArgumentParser(description="P4 reproducible Power BI CSV export")
    p.add_argument("--db-url", default="sqlite:///./data/replayed.sqlite")
    p.add_argument("--output", type=Path, default=Path("data/p4-export"))
    p.add_argument("--start", type=date.fromisoformat, help="UTC inclusive YYYY-MM-DD")
    p.add_argument("--end", type=date.fromisoformat, help="UTC inclusive YYYY-MM-DD")
    p.add_argument("--include-samples", action="store_true", help="Large row-level optional CSV")
    a = p.parse_args(argv)
    result = build_export(a.db_url, a.output, start=a.start, end=a.end, include_samples=a.include_samples)
    print(json.dumps({"status": "success", "output": str(a.output),
                      "from_utc": result["from_utc"], "through_utc": result["through_utc"],
                      "tables": {k: v["rows"] for k, v in result["tables"].items()}}, sort_keys=True))

if __name__ == "__main__":
    main()