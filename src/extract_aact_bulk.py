# ABOUTME: Stage 1 - Bulk extraction of Phase 1 terminated trials from AACT database to TinyDB

import os
import sys
import psycopg2
from datetime import datetime
from typing import List, Dict, Optional
from tinydb import TinyDB
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class AACTBulkExtractor:
    """Extract Phase 1 terminated trials from AACT database"""

    def __init__(self, db_path: str = "data/clinical_trials.json"):
        """
        Initialize extractor with database connection

        Args:
            db_path: Path to TinyDB database file
        """
        self.db_path = db_path
        self.db = TinyDB(db_path)
        self.trials_table = self.db.table('trials')

        # AACT database connection
        self.aact_conn = psycopg2.connect(
            host=os.getenv('AACT_DB_HOST', 'aact-db.ctti-clinicaltrials.org'),
            port=os.getenv('AACT_DB_PORT', '5432'),
            database=os.getenv('AACT_DB_NAME', 'aact'),
            user=os.getenv('AACT_DB_USER'),
            password=os.getenv('AACT_DB_PASSWORD')
        )

    def extract_all_trials(self, start_year: int = 2010, limit: Optional[int] = None) -> int:
        """
        Extract all Phase 1, 2, and 3 terminated trials from specified year

        Args:
            start_year: Starting year for trial extraction (default 2010)
            limit: Optional limit for testing (default None = all trials)

        Returns:
            Number of trials extracted
        """
        query = """
            SELECT DISTINCT
                s.nct_id,
                s.brief_title as title,
                s.phase,
                s.overall_status,
                s.why_stopped,
                s.start_date,
                s.completion_date,
                i.name as drug_name,
                i.intervention_type,
                i.description as drug_description,
                sp.name as sponsor
            FROM ctgov.studies s
            JOIN ctgov.interventions i ON s.nct_id = i.nct_id
            LEFT JOIN ctgov.sponsors sp ON s.nct_id = sp.nct_id
                AND sp.lead_or_collaborator = 'lead'
            WHERE s.phase IN ('PHASE1', 'PHASE2', 'PHASE3')
              AND s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
              AND s.start_date >= %s
              AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
            ORDER BY s.start_date DESC
        """

        # Add LIMIT clause if specified
        params = [f"{start_year}-01-01"]
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        print(f"Extracting Phase 1, 2, and 3 terminated trials from {start_year}+...")
        if limit:
            print(f"LIMITED TO {limit} trials for testing")

        cursor = self.aact_conn.cursor()
        cursor.execute(query, params)

        trials_extracted = 0
        for row in cursor.fetchall():
            trial = self._build_trial_document(row)
            self.trials_table.insert(trial)
            trials_extracted += 1

            if trials_extracted % 100 == 0:
                print(f"Extracted {trials_extracted} trials...")

        cursor.close()

        print(f"\n✅ Extraction complete: {trials_extracted} trials saved to {self.db_path}")
        return trials_extracted

    def _build_trial_document(self, row: tuple) -> Dict:
        """
        Build TinyDB trial document from AACT query result

        Args:
            row: Tuple from psycopg2 query result

        Returns:
            Trial document dictionary
        """
        nct_id, title, phase, overall_status, why_stopped, start_date, \
            completion_date, drug_name, intervention_type, drug_description, sponsor = row

        return {
            # Core AACT Data
            "nct_id": nct_id,
            "drug_name": drug_name,
            "intervention_type": intervention_type,
            "drug_description": drug_description,
            "phase": phase,
            "overall_status": overall_status,
            "why_stopped": why_stopped,
            "title": title,
            "start_date": start_date.isoformat() if start_date else None,
            "completion_date": completion_date.isoformat() if completion_date else None,
            "sponsor": sponsor,

            # Enrichment Status
            "enrichment_status": {
                "stage1_extracted": datetime.utcnow().isoformat(),
                "stage2_targets": "pending",
                "stage2_ppi": "pending",
                "stage2_failure_details": "pending",
                "stage3_llm_analysis": "pending",
                "last_updated": datetime.utcnow().isoformat(),
                "retry_count": 0
            }
        }

    def get_statistics(self) -> Dict:
        """
        Get extraction statistics

        Returns:
            Dictionary with database statistics
        """
        total_trials = len(self.trials_table.all())

        # Count by status
        status_counts = {}
        for trial in self.trials_table.all():
            status = trial.get('overall_status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1

        # Count by intervention type
        intervention_counts = {}
        for trial in self.trials_table.all():
            itype = trial.get('intervention_type', 'UNKNOWN')
            intervention_counts[itype] = intervention_counts.get(itype, 0) + 1

        return {
            "total_trials": total_trials,
            "by_status": status_counts,
            "by_intervention_type": intervention_counts
        }

    def close(self):
        """Close database connections"""
        self.aact_conn.close()
        self.db.close()


def main():
    """Main entry point for bulk extraction"""
    parser = argparse.ArgumentParser(
        description="Extract Phase 1, 2, and 3 terminated trials from AACT database"
    )
    parser.add_argument(
        '--output',
        default='data/clinical_trials.json',
        help='Output TinyDB database path (default: data/clinical_trials.json)'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=2010,
        help='Starting year for extraction (default: 2010)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of trials for testing (default: None = all trials)'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show database statistics after extraction'
    )

    args = parser.parse_args()

    # Create data directory if it doesn't exist
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Extract trials
    extractor = AACTBulkExtractor(db_path=args.output)

    try:
        count = extractor.extract_all_trials(
            start_year=args.start_year,
            limit=args.limit
        )

        if args.stats:
            print("\n" + "="*50)
            print("DATABASE STATISTICS")
            print("="*50)
            stats = extractor.get_statistics()
            print(f"\nTotal Trials: {stats['total_trials']}")
            print("\nBy Status:")
            for status, count in sorted(stats['by_status'].items()):
                print(f"  {status}: {count}")
            print("\nBy Intervention Type:")
            for itype, count in sorted(stats['by_intervention_type'].items()):
                print(f"  {itype}: {count}")

    finally:
        extractor.close()


if __name__ == "__main__":
    main()
