#!/usr/bin/env python3
# ABOUTME: Explore terminated/suspended trials with protein/drug targets

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def explore_trials():
    """Explore terminated/suspended trials."""
    conn = psycopg2.connect(
        host=os.getenv('AACT_DB_HOST'),
        port=os.getenv('AACT_DB_PORT'),
        database=os.getenv('AACT_DB_NAME'),
        user=os.getenv('AACT_DB_USER'),
        password=os.getenv('AACT_DB_PASSWORD')
    )

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # First, understand studies table structure
    print("=== STUDIES TABLE COLUMNS ===")
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'ctgov'
          AND table_name = 'studies'
        ORDER BY ordinal_position;
    """)
    for col in cursor.fetchall():
        print(f"  {col['column_name']}: {col['data_type']}")

    # Check what status values exist
    print("\n=== STUDY STATUS VALUES ===")
    cursor.execute("""
        SELECT overall_status, COUNT(*) as count
        FROM ctgov.studies
        GROUP BY overall_status
        ORDER BY count DESC;
    """)
    for row in cursor.fetchall():
        print(f"  {row['overall_status']}: {row['count']:,}")

    # Sample terminated studies
    print("\n=== SAMPLE TERMINATED STUDIES ===")
    cursor.execute("""
        SELECT nct_id, brief_title, overall_status, why_stopped, phase
        FROM ctgov.studies
        WHERE overall_status IN ('Terminated', 'Suspended', 'Withdrawn')
        LIMIT 5;
    """)
    for row in cursor.fetchall():
        print(f"\nNCT: {row['nct_id']}")
        print(f"  Title: {row['brief_title'][:80]}")
        print(f"  Status: {row['overall_status']}")
        print(f"  Reason: {row['why_stopped']}")
        print(f"  Phase: {row['phase']}")

    # Check interventions table
    print("\n\n=== INTERVENTIONS TABLE COLUMNS ===")
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'ctgov'
          AND table_name = 'interventions'
        ORDER BY ordinal_position;
    """)
    for col in cursor.fetchall():
        print(f"  {col['column_name']}: {col['data_type']}")

    # Check intervention types
    print("\n=== INTERVENTION TYPES ===")
    cursor.execute("""
        SELECT intervention_type, COUNT(*) as count
        FROM ctgov.interventions
        GROUP BY intervention_type
        ORDER BY count DESC;
    """)
    for row in cursor.fetchall():
        print(f"  {row['intervention_type']}: {row['count']:,}")

    # Sample drug/biological interventions from terminated studies
    print("\n=== SAMPLE DRUG/BIOLOGICAL INTERVENTIONS (Terminated Studies) ===")
    cursor.execute("""
        SELECT DISTINCT
            s.nct_id,
            s.brief_title,
            s.overall_status,
            s.why_stopped,
            i.intervention_type,
            i.name as intervention_name,
            i.description
        FROM ctgov.studies s
        JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        WHERE s.overall_status IN ('Terminated', 'Suspended', 'Withdrawn')
          AND i.intervention_type IN ('Drug', 'Biological', 'Combination Product')
        LIMIT 10;
    """)

    for row in cursor.fetchall():
        print(f"\n{row['nct_id']} - {row['overall_status']}")
        print(f"  Title: {row['brief_title'][:70]}")
        print(f"  Intervention: {row['intervention_type']} - {row['intervention_name']}")
        if row['why_stopped']:
            print(f"  Reason: {row['why_stopped'][:70]}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    explore_trials()
