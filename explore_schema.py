#!/usr/bin/env python3
# ABOUTME: Explore AACT database schema more thoroughly

import os
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

def explore_schema():
    """Explore AACT database schema in detail."""
    conn_params = {
        'host': os.getenv('AACT_DB_HOST'),
        'port': os.getenv('AACT_DB_PORT'),
        'database': os.getenv('AACT_DB_NAME'),
        'user': os.getenv('AACT_DB_USER'),
        'password': os.getenv('AACT_DB_PASSWORD')
    }

    print(f"Connecting to {conn_params['host']}...")

    try:
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()

        # List all schemas
        print("\n=== SCHEMAS ===")
        cursor.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            ORDER BY schema_name;
        """)
        schemas = cursor.fetchall()
        for schema in schemas:
            print(f"  - {schema[0]}")

        # Try ctgov schema (common for clinical trials data)
        print("\n=== TABLES IN CTGOV SCHEMA ===")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'ctgov'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        if tables:
            print(f"Found {len(tables)} tables:\n")
            for table in tables[:20]:  # Show first 20
                print(f"  - {table[0]}")
            if len(tables) > 20:
                print(f"\n  ... and {len(tables) - 20} more tables")
        else:
            print("No tables found in ctgov schema")

        # Look for tables related to studies, interventions, outcomes
        print("\n=== SEARCHING FOR KEY TABLES ===")
        cursor.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_name LIKE '%stud%'
               OR table_name LIKE '%intervention%'
               OR table_name LIKE '%outcome%'
               OR table_name LIKE '%condition%'
               OR table_name LIKE '%browse%'
            ORDER BY table_schema, table_name;
        """)
        key_tables = cursor.fetchall()

        if key_tables:
            print(f"Found {len(key_tables)} relevant tables:")
            for schema, table in key_tables[:30]:
                print(f"  - {schema}.{table}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    explore_schema()
