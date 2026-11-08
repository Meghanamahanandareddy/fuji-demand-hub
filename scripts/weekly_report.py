"""Generate the weekly PDF and Excel report for every business with one command.

Usage:
    python scripts/weekly_report.py               # week ending on the latest data date
    python scripts/weekly_report.py --end 2026-10-25
"""
import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import reporting
from app.db import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end", type=date.fromisoformat,
                        help="last day of the 7-day period, YYYY-MM-DD")
    args = parser.parse_args()
    end = args.end or reporting.latest_data_date()
    out_dir = ROOT / "reports"

    started = time.perf_counter()
    for code in reporting.BUSINESSES:
        pdf, xlsx = reporting.generate(code, end, out_dir)
        with engine.begin() as conn:
            reporting.record(conn, code, end, [pdf, xlsx], ROOT)
        print(f"{code}: {pdf.name} and {xlsx.name}")
    print(f"Done in {time.perf_counter() - started:.1f} seconds. "
          f"Files are in {out_dir}")


if __name__ == "__main__":
    main()