"""Generate the update JSON file for Tauri's updater.

Usage:
    python scripts/generate-update-json.py --version 0.2.0 --notes "Bug fixes" \
        --nsis-url https://example.com/MoldGen_0.2.0_x64-setup.exe \
        --nsis-sig path/to/setup.exe.sig

This creates a `latest.json` file compatible with Tauri 2 updater plugin.
Host this file where your updater endpoint points to.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Tauri updater JSON")
    parser.add_argument("--version", required=True, help="New version (e.g. 0.2.0)")
    parser.add_argument("--notes", default="", help="Release notes")
    parser.add_argument("--nsis-url", help="URL to the Windows NSIS installer")
    parser.add_argument("--nsis-sig", help="Path to .sig file for NSIS installer")
    parser.add_argument("--msi-url", help="URL to the Windows MSI installer")
    parser.add_argument("--msi-sig", help="Path to .sig file for MSI installer")
    parser.add_argument("--output", default="latest.json", help="Output file path")
    args = parser.parse_args()

    platforms: dict = {}

    if args.nsis_url and args.nsis_sig:
        sig = Path(args.nsis_sig).read_text().strip()
        platforms["windows-x86_64"] = {
            "signature": sig,
            "url": args.nsis_url,
        }

    if args.msi_url and args.msi_sig:
        sig = Path(args.msi_sig).read_text().strip()
        if "windows-x86_64" not in platforms:
            platforms["windows-x86_64"] = {
                "signature": sig,
                "url": args.msi_url,
            }

    if not platforms:
        print("ERROR: At least one platform URL and signature required", file=sys.stderr)
        sys.exit(1)

    update_json = {
        "version": args.version if args.version.startswith("v") else f"v{args.version}",
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }

    output = Path(args.output)
    output.write_text(json.dumps(update_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {output} for version {args.version}")
    print(json.dumps(update_json, indent=2))


if __name__ == "__main__":
    main()
