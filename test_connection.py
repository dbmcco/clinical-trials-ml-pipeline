#!/usr/bin/env python3
# ABOUTME: Test script to connect to AACT database and explore schema

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("psycopg2 not installed. Installing...")
    os.system("pip3 install psycopg2-binary python-dotenv")
    import psycopg2
    from psycopg2 import sql

def test_connection():
    """Test connection to AACT database and list tables."""
    conn_params = {
        'host': os.getenv('AACT_DB_HOST'),
        'port': os.getenv('AACT_DB_PORT'),
        'database': os.getenv('AACT_DB_NAME'),
        'user': os.getenv('AACT_DB_USER'),
        'password': os.getenv('AACT_DB_PASSWORD')
    }

    print(f"Connecting to {conn_params['host']}:{conn_params['port']}/{conn_params['database']}...")

    try:
        conn = psycopg2.connect(**conn_params)
        print("✅ Connection successful!\n")

        cursor = conn.cursor()

        # List all tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"Found {len(tables)} tables in the database:\n")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()
