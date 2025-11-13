#!/usr/bin/env python3
# ABOUTME: Fast sampling query - gets N trials quickly without progression checks

import os
import argparse
import json
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


def sample_terminated_trials(phase: str, output_file: str, limit: int = 10):
    """
    Quick sample of terminated trials WITHOUT progression checking.
    Perfect for testing enrichment pipeline.

    FAST because:
    - No CTE with ARRAY_AGG
    - No progression checks
    - Direct LIMIT on query
    - Uses indexes on phase + overall_status
    """

    conn = psycopg2.connect(
        host=os.getenv('AACT_DB_HOST'),
        port=os.getenv('AACT_DB_PORT'),
        database=os.getenv('AACT_DB_NAME'),
        user=os.getenv('AACT_DB_USER'),
        password=os.getenv('AACT_DB_PASSWORD')
    )

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    print(f"\n=== Fast Sampling: {limit} {phase} Terminated Trials ===")
    print(f"Note: NOT checking progression (use query_trials_correct.py for that)")
    print(f"Purpose: Quick data for testing enrichment pipeline\n")

    # FAST QUERY: Just get terminated trials with drugs, no progression check
    query = """
    SELECT
        s.nct_id,
        s.brief_title,
        s.phase,
        s.overall_status,
        s.why_stopped,
        s.start_date,
        s.completion_date,
        i.name as drug_name,
        i.intervention_type,
        i.description as drug_description
    FROM ctgov.studies s
    JOIN ctgov.interventions i ON s.nct_id = i.nct_id
    WHERE s.phase = %s
      AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
      AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
    ORDER BY s.start_date DESC
    LIMIT %s;
    """

    print(f"Executing fast sample query (should be <5 seconds)...")
    import time
    start = time.time()

    cursor.execute(query, (phase, limit))
    results = cursor.fetchall()

    elapsed = time.time() - start
    print(f"✓ Retrieved {len(results)} trials in {elapsed:.2f} seconds\n")

    # Convert to standard format
    trials = []
    for row in results:
        trials.append({
            'nct_id': row['nct_id'],
            'drug_name': row['drug_name'],
            'intervention_type': row['intervention_type'],
            'drug_description': row['drug_description'],
            'phase': phase,
            'label': 'FAILURE',  # All are terminated
            'label_reason': row['why_stopped'] or 'Unknown',
            'overall_status': row['overall_status'],
            'why_stopped': row['why_stopped'],
            'title': row['brief_title'],
            'start_date': str(row['start_date']) if row['start_date'] else None,
            'completion_date': str(row['completion_date']) if row['completion_date'] else None,
            'progressed_to_next_phase': None  # Not checked in sampling mode
        })

    # Save
    with open(output_file, 'w') as f:
        json.dump(trials, f, indent=2)

    # Summary
    print(f"=== Summary ===")
    print(f"Total trials sampled: {len(trials)}")
    print(f"All labeled: FAILURE (terminated trials)")
    print(f"\nUnique drugs in sample:")
    unique_drugs = set(t['drug_name'] for t in trials)
    for i, drug in enumerate(sorted(unique_drugs)[:10], 1):
        print(f"  {i}. {drug}")
    if len(unique_drugs) > 10:
        print(f"  ... and {len(unique_drugs) - 10} more")

    print(f"\nSaved to: {output_file}")
    print(f"\nReady for enrichment:")
    print(f"  python enrich_targets.py --input {output_file} --output data/phase1_enriched.json --limit 10")

    cursor.close()
    conn.close()

    return trials


def main():
    parser = argparse.ArgumentParser(
        description='Fast sampling of terminated trials (no progression checks)'
    )
    parser.add_argument(
        '--phase',
        type=str,
        required=True,
        choices=['PHASE1', 'PHASE2', 'PHASE3'],
        help='Clinical trial phase'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='trials_sample.json',
        help='Output file'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Number of trials to sample (default: 10)'
    )

    args = parser.parse_args()
    sample_terminated_trials(args.phase, args.output, args.limit)


if __name__ == "__main__":
    main()
