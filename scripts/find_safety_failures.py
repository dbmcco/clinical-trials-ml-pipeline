# ABOUTME: Utility to list terminated trials citing safety/toxicity reasons

import os
import csv
import argparse
from datetime import datetime

import psycopg2


SAFETY_KEYWORDS = [
    "safety",
    "toxicity",
    "toxic",
    "adverse",
    "ae",
    "death",
    "fatal",
    "hepatotoxic",
    "liver",
    "cardiac",
    "qt prolongation",
    "dose limiting"
]


def fetch_safety_trials(limit: int = 100) -> list[dict]:
    """Query AACT for terminated/suspended/withdrawn trials citing safety-related reasons."""
    placeholders = " OR ".join(["why_stopped ILIKE %s" for _ in SAFETY_KEYWORDS])
    sql = f"""
        SELECT
            s.nct_id,
            s.brief_title,
            s.phase,
            s.overall_status,
            s.why_stopped,
            s.start_date,
            s.completion_date,
            sp.name AS sponsor
        FROM ctgov.studies s
        LEFT JOIN ctgov.sponsors sp
            ON s.nct_id = sp.nct_id
            AND sp.lead_or_collaborator = 'lead'
        WHERE s.overall_status IN ('TERMINATED','SUSPENDED','WITHDRAWN')
          AND s.why_stopped IS NOT NULL
          AND ({placeholders})
        ORDER BY s.completion_date DESC NULLS LAST
        LIMIT %s
    """

    conn = psycopg2.connect(
        host=os.environ["AACT_DB_HOST"],
        port=os.environ["AACT_DB_PORT"],
        database=os.environ["AACT_DB_NAME"],
        user=os.environ["AACT_DB_USER"],
        password=os.environ["AACT_DB_PASSWORD"],
    )
    cur = conn.cursor()
    cur.execute(sql, SAFETY_KEYWORDS + [limit])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        (
            nct_id,
            title,
            phase,
            status,
            why_stopped,
            start_date,
            completion_date,
            sponsor,
        ) = row
        results.append(
            {
                "nct_id": nct_id,
                "title": title,
                "phase": phase,
                "status": status,
                "why_stopped": why_stopped,
                "start_date": start_date.isoformat() if start_date else None,
                "completion_date": completion_date.isoformat() if completion_date else None,
                "sponsor": sponsor,
            }
        )

    return results


def save_csv(rows: list[dict], path: str) -> None:
    fieldnames = [
        "nct_id",
        "title",
        "phase",
        "status",
        "why_stopped",
        "start_date",
        "completion_date",
        "sponsor",
    ]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="List AACT trials terminated for safety/toxicity reasons"
    )
    parser.add_argument("--limit", type=int, default=100, help="Max trials to fetch (default 100)")
    parser.add_argument(
        "--output",
        default=f"data/safety_failures_{datetime.utcnow().date()}.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    rows = fetch_safety_trials(limit=args.limit)
    save_csv(rows, args.output)

    print(f"✅ Found {len(rows)} safety-related terminated trials")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
