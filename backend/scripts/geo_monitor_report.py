from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.services.geo_monitor import read_geo_access_records
from app.services.geo_monitor import summarize_geo_access


REPO_DIR = PROJECT_DIR.parent
DEFAULT_LOG_FILE = REPO_DIR / "runtime" / "geo-access.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize SaveAny GEO crawler and landing-page access logs.")
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
    args = parser.parse_args()

    records = read_geo_access_records(args.log_file)
    print(json.dumps(summarize_geo_access(records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
