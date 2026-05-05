#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from local_results import DAG_PATH, ROOT, TRAIN_ORIG_PATH, TRAIN_PATH, restore_workspace_from_current_master


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore train.py from the current promoted local master and rebuild live metadata."
    )
    parser.add_argument(
        "--fetch-dag",
        action="store_true",
        help="kept for compatibility; rebuilds research/live/dag.json locally",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite local train.py even if it diverged from train_orig.py",
    )
    args = parser.parse_args()

    try:
        snapshot = restore_workspace_from_current_master(force=args.force)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    val_bpb = snapshot.get("val_bpb", "unknown")
    print(f"restored local master {snapshot['hash']} (val_bpb={val_bpb})")
    print(f"wrote {TRAIN_PATH.relative_to(ROOT)}")
    print(f"wrote {TRAIN_ORIG_PATH.relative_to(ROOT)}")
    print("wrote research/live/master.json")
    print("wrote research/live/master_detail.json")
    if args.fetch_dag:
        print(f"wrote {DAG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
