#!/usr/bin/env python3
# ABOUTME: FAST clinical trials query - single SQL query with progression check

import os
import argparse
import json
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


def export_trials_fast(phase: str, output_file: str):
    """Ultra-fast export using single SQL query with LEFT JOIN for progression."""

    conn = psycopg2.connect(
        host=os.getenv('AACT_DB_HOST'),
        port=os.getenv('AACT_DB_PORT'),
        database=os.getenv('AACT_DB_NAME'),
        user=os.getenv('AACT_DB_USER'),
        password=os.getenv('AACT_DB_PASSWORD')
    )

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Map phases
    next_phase_map = {
        'PHASE1': 'PHASE2',
        'PHASE2': 'PHASE3',
        'PHASE3': 'PHASE4'
    }
    next_phase = next_phase_map.get(phase)

    print(f"\n=== Exporting {phase} FAILED trials (optimized) ===")
    print(f"Filtering to: TERMINATED, SUSPENDED, WITHDRAWN only")
    print(f"Checking progression to: {next_phase}\n")

    # SINGLE QUERY with LEFT JOIN to check progression
    query = """
    WITH failed_trials AS (
        -- Get all terminated/suspended trials for this phase
        SELECT DISTINCT
            s.nct_id,
            s.brief_title,
            s.phase,
            s.overall_status,
            s.why_stopped,
            s.start_date,
            s.completion_date,
            i.intervention_type,
            i.name as intervention_name,
            i.description as intervention_description
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.phase = %s
          AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
          AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
    ),
    progression_check AS (
        -- Check if any of these drugs progressed to next phase
        SELECT DISTINCT
            i.name as drug_name,
            s.nct_id as next_phase_nct_id
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.phase = %s
          AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
    )
    SELECT
        ft.*,
        CASE
            WHEN pc.next_phase_nct_id IS NOT NULL THEN true
            ELSE false
        END as progressed_to_next_phase
    FROM failed_trials ft
    LEFT JOIN progression_check pc
        ON LOWER(ft.intervention_name) = LOWER(pc.drug_name)
    ORDER BY ft.start_date DESC;
    """

    print("Executing optimized query...")
    cursor.execute(query, (phase, next_phase))

    results = cursor.fetchall()
    print(f"✓ Found {len(results)} failed trials\n")

    # Convert to labeled format
    labeled_data = []
    success_count = 0
    failure_count = 0

    for row in results:
        trial = dict(row)

        # Determine label
        if trial['progressed_to_next_phase']:
            label = 'SUCCESS'
            label_reason = f"Drug progressed to {next_phase}"
            success_count += 1
        else:
            label = 'FAILURE'
            label_reason = trial.get('why_stopped') or 'Unknown'
            failure_count += 1

        labeled_data.append({
            'nct_id': trial['nct_id'],
            'drug_name': trial['intervention_name'],
            'intervention_type': trial['intervention_type'],
            'intervention_description': trial['intervention_description'],
            'phase': phase,
            'label': label,
            'label_reason': label_reason,
            'overall_status': trial['overall_status'],
            'why_stopped': trial.get('why_stopped'),
            'title': trial['brief_title'],
            'start_date': str(trial['start_date']) if trial['start_date'] else None,
            'completion_date': str(trial['completion_date']) if trial['completion_date'] else None,
            'progressed_to_next_phase': trial['progressed_to_next_phase']
        })

    # Save
    with open(output_file, 'w') as f:
        json.dump(labeled_data, f, indent=2)

    # Summary
    print(f"=== Summary ===")
    print(f"Total failed trials: {len(labeled_data)}")
    print(f"  SUCCESS (drug progressed elsewhere): {success_count}")
    print(f"  FAILURE (drug did not progress): {failure_count}")
    print(f"\nSaved to: {output_file}")

    cursor.close()
    conn.close()

    return labeled_data


def main():
    parser = argparse.ArgumentParser(
        description='Fast clinical trials export (optimized single query)'
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
        default='trials_export.json',
        help='Output file'
    )

    args = parser.parse_args()
    export_trials_fast(args.phase, args.output)


if __name__ == "__main__":
    main()
