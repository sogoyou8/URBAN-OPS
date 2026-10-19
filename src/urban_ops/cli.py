"""CLI: one shot collection, no daemon silently running."""
import argparse
import json
import gzip
from pathlib import Path

from .config import Config
from .fetch import fetch_pair
from .pipeline import ingest
from .storage import init_schema, make_engine, query_summary


def main(argv=None):
    defaults = Config.from_env()
    parser = argparse.ArgumentParser(prog="urban-ops", description="Urban Ops P3 data engineering")
    parser.add_argument("--database-url", default=defaults.database_url)
    parser.add_argument("--bronze-dir", type=Path, default=defaults.bronze_dir)
    parser.add_argument("--max-lag-seconds", type=int, default=defaults.max_lag_seconds)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create Bronze/Silver/Gold database schema")
    collect = sub.add_parser("collect", help="Fetch both public JSON feeds and ingest one snapshot")
    collect.add_argument("--information-file", type=Path)
    collect.add_argument("--status-file", type=Path)
    collect.add_argument("--run-id", help="Optional stable UUID-like text for idempotent replays")
    sub.add_parser("report", help="Show counts from the local database")
    args = parser.parse_args(argv)
    if args.max_lag_seconds < 0:
        parser.error("--max-lag-seconds must be >= 0")
    config = Config(database_url=args.database_url, bronze_dir=args.bronze_dir,
                    max_lag_seconds=args.max_lag_seconds, timeout_seconds=defaults.timeout_seconds)
    if args.command == "init":
        engine = make_engine(config.database_url)
        init_schema(engine)
        engine.dispose()
        print(json.dumps({"status": "initialized", "db_url_driver": config.database_url.split(":", 1)[0]}))
    elif args.command == "collect":
        if bool(args.information_file) != bool(args.status_file):
            parser.error("--information-file and --status-file must be used together")
        if args.information_file:
            def read_fixture_or_archive(path):
                return gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
            info, status = read_fixture_or_archive(args.information_file), read_fixture_or_archive(args.status_file)
        else:
            info, status = fetch_pair(config.timeout_seconds)
        print(json.dumps(ingest(info, status, config, args.run_id), ensure_ascii=False, sort_keys=True))
    elif args.command == "report":
        engine = make_engine(config.database_url)
        init_schema(engine)
        print(json.dumps(query_summary(engine), ensure_ascii=False, sort_keys=True))
        engine.dispose()


if __name__ == "__main__":
    main()
