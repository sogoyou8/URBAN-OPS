"""Immutable gzip Bronze archives, atomic fs rename, SHA-256 provenance."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import gzip
import os


def archive(bronze_dir: Path, run_id: str, name: str, raw: bytes, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    digest = sha256(raw).hexdigest()
    folder = Path(bronze_dir) / now.strftime("%Y/%m/%d") / run_id
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{name}-{digest[:16]}.json.gz"
    temporary = destination.with_suffix(".json.gz.tmp")
    with temporary.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
            compressed.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, destination)
    return {"run_id": run_id, "source_name": name, "path": str(destination),
            "sha256": digest, "bytes_uncompressed": len(raw)}
