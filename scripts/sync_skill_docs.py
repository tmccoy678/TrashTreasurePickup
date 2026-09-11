"""Copy shared documents into the two portable skill folders, or check them."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
from sources import sync_documents


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        sync_documents(ROOT, check=args.check)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
    print("Shared skill documents: " + ("verified" if args.check else "updated"))
