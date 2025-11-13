#!/usr/bin/env python3
# ABOUTME: CLI tool to query clinical trials and prepare data for Synthyra PPI analysis

import os
import argparse
import json
import csv
from typing import List, Dict, Optional
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


class TrialsQuery:
    """Query clinical trials database for machine learning preparation."""

    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('AACT_DB_HOST'),
            port=os.getenv('AACT_DB_PORT'),
            database=os.getenv('AACT_DB_NAME'),
            user=os.getenv('AACT_DB_USER'),
            password=os.getenv('AACT_DB_PASSWORD')
        )

    def check_phase_progression(self, from_phase: str) -> Dict:
        """Check which trials progressed to next phase vs terminated."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Map phase to next phase
        next_phase_map = {
            'PHASE1': 'PHASE2',
            'PHASE2': 'PHASE3',
            'PHASE3': 'PHASE4'
        }

        if from_phase not in next_phase_map:
            raise ValueError(f"Invalid phase: {from_phase}")

        print(f"\n=== Analyzing {from_phase} → {next_phase_map[from_phase]} Progression ===\n")

        # Get all drugs tested in from_phase
        query = """
        WITH phase_drugs AS (
            SELECT DISTINCT
                i.name as drug_name,
                s.nct_id,
                s.phase,
                s.overall_status,
                s.why_stopped
            FROM ctgov.studies s
            JOIN ctgov.interventions i ON s.nct_id = i.nct_id
            WHERE s.phase = %s
              AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
        )
        SELECT
            drug_name,
            nct_id,
            overall_status,
            why_stopped
        FROM phase_drugs;
        """

        cursor.execute(query, (from_phase,))
        results = cursor.fetchall()

        cursor.close()
        return results

    def get_phase_trials(self, phase: str, intervention_types: List[str] = None) -> List[Dict]:
        """Get trials for a specific phase, filtered to terminated/suspended for efficiency."""
        if intervention_types is None:
            intervention_types = ['DRUG', 'BIOLOGICAL']

        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # OPTIMIZED: Filter to terminated/suspended first to reduce dataset size
        # Original approach queried ALL trials, this only gets failed trials
        query = """
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
          AND i.intervention_type = ANY(%s)
          AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
        ORDER BY s.start_date DESC;
        """

        cursor.execute(query, (phase, intervention_types))
        results = cursor.fetchall()

        cursor.close()

        # Convert to list of dicts
        return [dict(row) for row in results]

    def check_drug_progression(self, drug_name: str, from_phase: str) -> Dict:
        """Check if a specific drug progressed to next phase."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        next_phase_map = {
            'PHASE1': 'PHASE2',
            'PHASE2': 'PHASE3',
            'PHASE3': 'PHASE4'
        }

        next_phase = next_phase_map.get(from_phase)
        if not next_phase:
            return {'progressed': False, 'reason': 'No next phase'}

        # Check if drug appears in next phase
        query = """
        SELECT DISTINCT
            s.nct_id,
            s.phase,
            s.overall_status
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE LOWER(i.name) = LOWER(%s)
          AND s.phase = %s;
        """

        cursor.execute(query, (drug_name, next_phase))
        next_phase_trials = cursor.fetchall()

        cursor.close()

        return {
            'progressed': len(next_phase_trials) > 0,
            'next_phase_trials': len(next_phase_trials),
            'trials': [dict(t) for t in next_phase_trials]
        }

    def export_for_ml(self, phase: str, output_file: str = 'trials_export.json'):
        """Export trials with success/failure labels for ML."""
        print(f"\n=== Exporting {phase} trials for ML ===")
        print(f"Note: Filtering to terminated/suspended/withdrawn trials only for efficiency")

        trials = self.get_phase_trials(phase)
        print(f"Found {len(trials)} terminated/suspended {phase} trials with drug/biological interventions")

        # Check progression for each drug
        labeled_data = []
        processed_drugs = set()

        for i, trial in enumerate(trials):
            drug_name = trial['intervention_name']

            # Skip duplicates (same drug in multiple trials)
            if drug_name in processed_drugs:
                continue
            processed_drugs.add(drug_name)

            if (i + 1) % 100 == 0:
                print(f"  Processed {i+1}/{len(trials)} trials...")

            # Check if drug progressed
            progression = self.check_drug_progression(drug_name, phase)

            # Determine label
            if progression['progressed']:
                label = 'SUCCESS'
                label_reason = f"Progressed to next phase ({progression['next_phase_trials']} trials)"
            elif trial['overall_status'] in ['TERMINATED', 'SUSPENDED', 'WITHDRAWN']:
                # Will need LLM to classify efficacy vs adverse effects
                label = 'FAILURE'
                label_reason = trial['why_stopped'] or 'Unknown'
            else:
                # Still ongoing or completed but no next phase yet
                label = 'UNKNOWN'
                label_reason = trial['overall_status']

            labeled_data.append({
                'nct_id': trial['nct_id'],
                'drug_name': drug_name,
                'intervention_type': trial['intervention_type'],
                'intervention_description': trial['intervention_description'],
                'phase': phase,
                'label': label,
                'label_reason': label_reason,
                'overall_status': trial['overall_status'],
                'why_stopped': trial['why_stopped'],
                'title': trial['brief_title'],
                'start_date': str(trial['start_date']) if trial['start_date'] else None,
                'completion_date': str(trial['completion_date']) if trial['completion_date'] else None,
                'progressed_to_next_phase': progression['progressed']
            })

        # Save to file
        with open(output_file, 'w') as f:
            json.dump(labeled_data, f, indent=2)

        # Print summary
        print(f"\n=== Summary ===")
        success_count = sum(1 for d in labeled_data if d['label'] == 'SUCCESS')
        failure_count = sum(1 for d in labeled_data if d['label'] == 'FAILURE')
        unknown_count = sum(1 for d in labeled_data if d['label'] == 'UNKNOWN')

        print(f"Total drugs: {len(labeled_data)}")
        print(f"  SUCCESS (progressed): {success_count}")
        print(f"  FAILURE (terminated): {failure_count}")
        print(f"  UNKNOWN (ongoing/other): {unknown_count}")
        print(f"\nExported to: {output_file}")
        print(f"\nNext steps:")
        print(f"  1. Use ChEMBL/DrugBank to get UniProt targets for each drug")
        print(f"  2. Filter to only drugs with known targets")
        print(f"  3. Use LLM to classify FAILURE reasons into Efficacy vs Adverse Effects")

        return labeled_data

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Query clinical trials for Synthyra PPI analysis'
    )
    parser.add_argument(
        '--phase',
        type=str,
        required=True,
        choices=['PHASE1', 'PHASE2', 'PHASE3'],
        help='Clinical trial phase to analyze'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='trials_export.json',
        help='Output file path (default: trials_export.json)'
    )

    args = parser.parse_args()

    query = TrialsQuery()

    try:
        query.export_for_ml(args.phase, args.output)
    finally:
        query.close()


if __name__ == "__main__":
    main()
