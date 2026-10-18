import sys

"""Verified local backup before schema upgrades. Run from backend/ with the app stopped.

Uses pg_dump on PATH or the project's postgres container. Never prints connection secrets.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../backups") / datetime.now().strftime("workbench-%Y%m%d-%H%M%S"),
    )
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    with engine.connect() as connection:
        counts = {
            name: connection.execute(
                text('SELECT count(*) FROM "' + name.replace('"', '""') + '"')
            ).scalar()
            for name in inspect(connection).get_table_names()
        }
    env = dict(os.environ)
    if shutil.which("pg_dump"):
        url = engine.url
        env["PGPASSWORD"] = url.password or ""
        command = [
            "pg_dump",
            "-h",
            url.host or "localhost",
            "-p",
            str(url.port or 5432),
            "-U",
            url.username or "postgres",
            "-d",
            url.database,
            "-Fc",
        ]
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            engine.url.username or "postgres",
            "-d",
            engine.url.database,
            "-Fc",
        ]
    with (root / "database.dump").open("wb") as output:
        subprocess.run(command, stdout=output, check=True, env=env)
    storage = settings.get_storage_path()
    # APFS clone is an independent copy-on-write backup without duplicating 8 GB.
    if os.uname().sysname == "Darwin":
        subprocess.run(["cp", "-cR", str(storage), str(root / "storage")], check=True)
    else:
        shutil.copytree(storage, root / "storage")
    dump = root / "database.dump"
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "tables": counts,
                "database_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                "storage": str(storage),
            },
            indent=2,
        )
    )
    print("Backup complete:", root)


if __name__ == "__main__":
    main()
