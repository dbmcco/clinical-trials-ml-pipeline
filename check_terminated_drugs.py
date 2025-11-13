#!/usr/bin/env python3
# ABOUTME: Check if we can get drug/biological data from terminated trials

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def check_data():
    """Check data availability."""
    conn = psycopg2.connect(
        host=os.getenv('AACT_DB_HOST'),
        port=os.getenv('AACT_DB_PORT'),
        database=os.getenv('AACT_DB_NAME'),
        user=os.getenv('AACT_DB_USER'),
        password=os.getenv('AACT_DB_PASSWORD')
    )

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Count terminated studies with drug/biological interventions
    print("=== COUNTING TERMINATED TRIALS BY INTERVENTION TYPE ===")
    cursor.execute("""
        SELECT
            i.intervention_type,
            COUNT(DISTINCT s.nct_id) as study_count
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.overall_status IN ('TERMINATED', 'SUSPENDED', 'WITHDRAWN')
        GROUP BY i.intervention_type
        ORDER BY study_count DESC;
    """)

    for row in cursor.fetchall():
        print(f"  {row['intervention_type']}: {row['study_count']:,} studies")

    # Get specific examples
    print("\n=== SAMPLE TERMINATED TRIALS WITH DRUGS ===")
    cursor.execute("""
        SELECT DISTINCT
            s.nct_id,
            s.brief_title,
            s.overall_status,
            s.phase,
            s.why_stopped,
            i.intervention_type,
            i.name as intervention_name
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.overall_status = 'TERMINATED'
          AND i.intervention_type IN ('DRUG', 'BIOLOGICAL')
        LIMIT 20;
    """)

    results = cursor.fetchall()
    print(f"Found {len(results)} examples:\n")

    for row in results:
        print(f"{row['nct_id']} [{row['phase']}] - {row['overall_status']}")
        print(f"  Intervention: {row['intervention_type']} - {row['intervention_name']}")
        print(f"  Title: {row['brief_title'][:70]}...")
        if row['why_stopped']:
            print(f"  Why stopped: {row['why_stopped'][:80]}")
        print()

    # Check what data points are available
    print("\n=== CHECKING FOR DOSING/IC50 DATA ===")
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'ctgov'
          AND (column_name LIKE '%dose%'
               OR column_name LIKE '%ic50%'
               OR column_name LIKE '%concentration%'
               OR column_name LIKE '%dosage%')
        ORDER BY table_name, column_name;
    """)

    dosing_cols = cursor.fetchall()
    if dosing_cols:
        print("Found dosing-related columns:")
        for col in dosing_cols:
            print(f"  - {col['column_name']}")
    else:
        print("❌ No IC50 or dosing columns found in database")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_data()
