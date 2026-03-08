#!/usr/bin/env python3
"""CLI wrapper for snapshot build — use outside the orchestrator.

Usage:
    python3 build_cli.py --domain palo_alto --profile civic
    python3 build_cli.py --domain palo_alto --db /path/to/palo_alto.db
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from workers.snapshot.worker import build_snapshot, test_snapshot


def main():
    parser = argparse.ArgumentParser(
        description="Build a Loom knowledge snapshot",
    )
    parser.add_argument(
        "--domain", required=True,
        help="Domain identifier (e.g. community ID)",
    )
    parser.add_argument(
        "--db", default=None,
        help="Path to source evidence graph DB "
             "(default: LOOM_DB_PATH env var)",
    )
    parser.add_argument(
        "--profile", default=None,
        help="Domain profile name (default: same as domain)",
    )
    parser.add_argument(
        "--snapshots-dir", default=None,
        help="Output snapshots directory "
             "(default: LOOM_SNAPSHOTS_DIR env var)",
    )
    parser.add_argument(
        "--previous-version", default=None,
        help="Previous version for changelog diff",
    )
    parser.add_argument(
        "--skip-test", action="store_true",
        help="Skip quality gate tests after build",
    )
    parser.add_argument(
        "--promote", action="store_true",
        help="Promote snapshot to current after build+test",
    )

    args = parser.parse_args()

    # Build.
    print(f"Building snapshot for domain={args.domain}...")
    result = build_snapshot(
        domain_id=args.domain,
        db_path=args.db,
        profile_name=args.profile,
        previous_version=args.previous_version,
        snapshots_dir=args.snapshots_dir,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"  Built {result['version']}: "
          f"{result['claim_count']} claims, "
          f"{result['evidence_count']} evidence")
    print(f"  Path: {result['snapshot_path']}")

    # Test.
    if not args.skip_test:
        print("Running quality gates...")
        test_result = test_snapshot(
            snapshot_path=result["snapshot_path"],
            domain_id=args.domain,
            profile_name=args.profile,
        )
        for gate, info in test_result.get("gate_results", {}).items():
            status = "PASS" if info["passed"] else "FAIL"
            print(f"  [{status}] {gate}: {info['details']}")

        if not test_result.get("passed"):
            print("Quality gates FAILED — not promoting.",
                  file=sys.stderr)
            sys.exit(1)
        print("All quality gates passed.")

    # Promote.
    if args.promote:
        from workers.snapshot.worker import SnapshotWorker
        snap_dir = args.snapshots_dir or os.environ.get(
            "LOOM_SNAPSHOTS_DIR",
            os.path.join(os.path.expanduser("~"), "loom", "data", "snapshots"),
        )
        domain_dir = os.path.join(snap_dir, args.domain)
        current_link = os.path.join(domain_dir, "current")
        version_name = os.path.basename(result["snapshot_path"])

        import shutil
        if os.path.islink(current_link):
            os.unlink(current_link)
        elif os.path.isdir(current_link):
            shutil.rmtree(current_link)
        os.symlink(version_name, current_link)
        print(f"  Promoted {version_name} -> current")

    # Summary.
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
