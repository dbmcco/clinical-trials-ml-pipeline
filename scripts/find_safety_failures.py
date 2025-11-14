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
    "sae",
    "death",
    "fatal",
    "hepatotoxic",
    "liver",
    "cardiac",
    "qt prolongation",
    "dose limiting",
    "dlt",
    "hold",
    "pause",
    "risk",
    "review of safety",
    "safety review",
    "irb",
]


def fetch_safety_trials(
    limit: int = 100,
    phases: list[str] | None = None,
    require_keywords: bool = True,
) -> list[dict]:
    """Query AACT for terminated/suspended/withdrawn trials citing safety-related reasons."""
    where_clauses = [
        "s.overall_status IN ('TERMINATED','SUSPENDED','WITHDRAWN')",
        "s.why_stopped IS NOT NULL",
    ]
    params: list[str | int] = []

    if require_keywords:
        placeholders = " OR ".join(["s.why_stopped ILIKE %s" for _ in SAFETY_KEYWORDS])
        where_clauses.append(f"({placeholders})")
        params.extend(SAFETY_KEYWORDS)

    if phases:
        phase_clauses = []
        for phase in phases:
            phase_clauses.append("s.phase ILIKE %s")
            params.append(f"%{phase.upper()}%")
        where_clauses.append(f"({' OR '.join(phase_clauses)})")

    where_sql = " AND ".join(where_clauses)

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
        WHERE {where_sql}
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
    cur.execute(sql, params + [limit])

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
    parser.add_argument(
        "--phase",
        action="append",
        help="Phase filter (can specify multiple, e.g., --phase PHASE1 --phase PHASE2)",
    )
    parser.add_argument(
        "--no-keywords",
        action="store_true",
        help="Do not require safety keywords in why_stopped",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    rows = fetch_safety_trials(
        limit=args.limit,
        phases=args.phase,
        require_keywords=not args.no_keywords,
    )
    save_csv(rows, args.output)

    print(f"✅ Found {len(rows)} safety-related terminated trials")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
