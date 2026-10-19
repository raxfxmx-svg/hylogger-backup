from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import ETLError
from release_etl import transform


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transform one immutable NVCL raw package into an ETL3 release"
    )
    parser.add_argument("hole_id")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--release-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = transform(
            args.hole_id,
            args.raw_root,
            args.processed_root,
            args.release_id,
        )
    except ETLError as exc:
        print(f"ETL3 failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
