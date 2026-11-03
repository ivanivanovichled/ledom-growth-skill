#!/usr/bin/env python3
"""Describe a lead-created cohort from a local CSV snapshot; no network.

Required columns: lead_id,created_at,source,medium,is_test,qualification,deal_status
One snapshot row per lead. qualification: qualified|unqualified|pending|unknown.
deal_status: won|lost|open|unknown. is_test: true|false (or 1|0).
created_at must include a timezone. Dates --start/--end are Moscow local dates;
start inclusive, end exclusive. Current statuses are as of the snapshot, not
necessarily historical end-date statuses. Test rows never enter business counts.

Example: python funnel_report.py leads.csv --start 2026-10-01 --end 2026-11-01
Output is aggregate JSON; lead identifiers are not emitted. source/medium must
contain no personal data. Missing/ambiguous input fails instead of
silently turning an unknown into a zero. No spend, revenue or ROI is inferred.
"""
import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys

MOSCOW = timezone(timedelta(hours=3), name="Europe/Moscow")
REQUIRED = {"lead_id", "created_at", "source", "medium", "is_test", "qualification", "deal_status"}
QUALIFICATIONS = {"qualified", "unqualified", "pending", "unknown"}
DEALS = {"won", "lost", "open", "unknown"}


def new_counts():
    return {"leads": 0, "qualified": 0, "unqualified": 0,
            "qualification_pending": 0, "qualification_unknown": 0,
            "won": 0, "lost": 0, "open": 0, "deal_unknown": 0}


def report(path, start, end):
    start_dt = datetime.combine(date.fromisoformat(start), time.min, MOSCOW)
    end_dt = datetime.combine(date.fromisoformat(end), time.min, MOSCOW)
    if end_dt <= start_dt:
        raise ValueError("end must be after start")
    groups, seen = {}, set()
    totals = new_counts()
    tested = outside = read = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers) or not REQUIRED.issubset(headers):
            raise ValueError("CSV must have unique headers and all required columns")
        for line, raw in enumerate(reader, 2):
            if None in raw or any(raw.get(key) is None for key in REQUIRED):
                raise ValueError(f"row {line}: malformed CSV row")
            row = {key: raw[key].strip() for key in REQUIRED}
            lead_id = row["lead_id"]
            if not lead_id or lead_id in seen:
                raise ValueError(f"row {line}: blank or duplicate lead_id; supply one snapshot row per lead")
            seen.add(lead_id)
            read += 1
            try:
                created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"row {line}: invalid created_at") from exc
            if created.tzinfo is None:
                raise ValueError(f"row {line}: created_at requires timezone")
            q, deal, test = row["qualification"], row["deal_status"], row["is_test"].lower()
            if q not in QUALIFICATIONS or deal not in DEALS or test not in {"true", "false", "1", "0"}:
                raise ValueError(f"row {line}: unsupported status or is_test value")
            if deal == "won" and q != "qualified":
                raise ValueError(f"row {line}: won lead must be qualified; reconcile source statuses")
            if not row["source"] or not row["medium"]:
                raise ValueError(f"row {line}: source/medium required; use explicit unknown when unavailable")
            if not start_dt <= created < end_dt:
                outside += 1
                continue
            if test in {"true", "1"}:
                tested += 1
                continue
            key = (row["source"], row["medium"])
            group = groups.setdefault(key, new_counts())
            qkey = q if q in {"qualified", "unqualified"} else "qualification_" + q
            dkey = "deal_unknown" if deal == "unknown" else deal
            for count in (group, totals):
                count["leads"] += 1
                count[qkey] += 1
                count[dkey] += 1
    # Independent reconciliation over disjoint groups; fail if totals drift.
    for metric in totals:
        if sum(group[metric] for group in groups.values()) != totals[metric]:
            raise ValueError("internal reconciliation failed")
    return {"cohort": {"created_from_inclusive": start, "created_to_exclusive": end,
                       "timezone": "Europe/Moscow", "statuses": "current CSV snapshot"},
            "rows_read": read, "outside_cohort": outside, "test_rows_excluded": tested,
            "totals": totals,
            "by_source": [{"source": key[0], "medium": key[1], **groups[key]} for key in sorted(groups)],
            "limitations": ["not website conversion rate", "not ROI or causal attribution",
                            "pending/open outcomes are unresolved, not failures"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    try:
        result = report(args.csv_file, args.start, args.end)
    except (OSError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
