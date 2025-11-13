#!/usr/bin/env python3
# ABOUTME: CORRECT clinical trials query - per-trial with drug aggregation (research-backed approach)

import os
import argparse
import json
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


def export_trials_correct(phase: str, output_file: str):
    """
    Export trials using CORRECT per-trial aggregation approach.

    Based on research findings:
    - Unit of analysis: ONE ROW PER TRIAL (not per drug-trial pair)
    - Aligns with TrialBench (Nature 2025) methodology
    - Avoids cartesian products through ARRAY_AGG aggregation
    - Checks if ANY drug progressed (trial-level success)

    Expected output: ~4,900 Phase 1 terminated trials (not 5.3M rows)
    """

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

    print(f"\n=== Exporting {phase} TERMINATED Trials (Per-Trial Aggregation) ===")
    print(f"Approach: One row per trial with aggregated drug information")
    print(f"Checking progression: ANY drug → {next_phase}\n")

    # RESEARCH-BACKED QUERY: Aggregation-first approach
    query = """
    WITH terminated_trials AS (
        -- Step 1: Get terminated trials with aggregated drugs
        SELECT
            s.nct_id,
            s.brief_title,
            s.phase,
            s.overall_status,
            s.why_stopped,
            s.start_date,
            s.completion_date,
            ARRAY_AGG(DISTINCT i.name) FILTER (WHERE i.intervention_type IN ('DRUG', 'BIOLOGICAL')) as drug_names,
            STRING_AGG(DISTINCT i.name, '; ') FILTER (WHERE i.intervention_type IN ('DRUG', 'BIOLOGICAL')) as drug_list,
            ARRAY_AGG(DISTINCT i.intervention_type) as intervention_types
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.phase = %s
          AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
          AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
        GROUP BY s.nct_id, s.brief_title, s.phase, s.overall_status,
                 s.why_stopped, s.start_date, s.completion_date
    ),
    next_phase_drugs AS (
        -- Step 2: Get all drugs that appear in next phase
        SELECT DISTINCT LOWER(i.name) as drug_name_lower
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.phase = %s
          AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
    )
    SELECT
        t.*,
        EXISTS(
            SELECT 1
            FROM UNNEST(t.drug_names) as drug
            WHERE LOWER(drug) IN (SELECT drug_name_lower FROM next_phase_drugs)
        ) as any_drug_progressed
    FROM terminated_trials t
    ORDER BY t.start_date DESC;
    """

    print("Executing query (this should be fast now)...")
    cursor.execute(query, (phase, next_phase))

    results = cursor.fetchall()
    print(f"✓ Found {len(results)} terminated {phase} trials\n")

    # Convert to labeled format
    labeled_data = []
    success_count = 0
    failure_count = 0

    for row in results:
        # Determine label
        if row['any_drug_progressed']:
            label = 'SUCCESS'
            label_reason = f"At least one drug progressed to {next_phase}"
            success_count += 1
        else:
            label = 'FAILURE'
            label_reason = row['why_stopped'] or 'Unknown'
            failure_count += 1

        labeled_data.append({
            'nct_id': row['nct_id'],
            'drug_names': row['drug_names'],  # Array of all drugs
            'drug_list': row['drug_list'],     # Semicolon-separated string
            'drug_count': len(row['drug_names']) if row['drug_names'] else 0,
            'primary_drug': row['drug_names'][0] if row['drug_names'] else None,
            'is_combination_therapy': len(row['drug_names']) > 1 if row['drug_names'] else False,
            'intervention_types': row['intervention_types'],
            'phase': phase,
            'label': label,
            'label_reason': label_reason,
            'overall_status': row['overall_status'],
            'why_stopped': row['why_stopped'],
            'title': row['brief_title'],
            'start_date': str(row['start_date']) if row['start_date'] else None,
            'completion_date': str(row['completion_date']) if row['completion_date'] else None,
            'progressed_to_next_phase': row['any_drug_progressed']
        })

    # Save
    with open(output_file, 'w') as f:
        json.dump(labeled_data, f, indent=2)

    # Summary
    print(f"=== Summary ===")
    print(f"Total trials: {len(labeled_data)}")
    print(f"  SUCCESS (drug progressed): {success_count}")
    print(f"  FAILURE (no progression): {failure_count}")

    print(f"\nDrug statistics:")
    single_drug = sum(1 for d in labeled_data if d['drug_count'] == 1)
    multi_drug = sum(1 for d in labeled_data if d['drug_count'] > 1)
    max_drugs = max((d['drug_count'] for d in labeled_data), default=0)

    print(f"  Single-drug trials: {single_drug}")
    print(f"  Multi-drug trials: {multi_drug}")
    print(f"  Max drugs in one trial: {max_drugs}")

    print(f"\nSaved to: {output_file}")

    cursor.close()
    conn.close()

    return labeled_data


def main():
    parser = argparse.ArgumentParser(
        description='Clinical trials export (CORRECT per-trial aggregation)'
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
    export_trials_correct(args.phase, args.output)


if __name__ == "__main__":
    main()
