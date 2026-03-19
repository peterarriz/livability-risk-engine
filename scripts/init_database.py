#!/usr/bin/env python3
"""
scripts/init_database.py
task: data-015
lane: data

Database initialization script for Railway Postgres+PostGIS deployment.
Reads db/schema.sql and executes it against the configured database.

Usage:
    python scripts/init_database.py

Environment variables:
    DATABASE_URL              (Railway format: postgresql://user:pass@host:port/db)
    or
    POSTGRES_HOST             Database hostname
    POSTGRES_PORT             Database port (default: 5432)
    POSTGRES_DB               Database name (default: livability)
    POSTGRES_USER             Database user (default: postgres)
    POSTGRES_PASSWORD         Database password
"""

import os
import sys
from pathlib import Path

# Add backend to path so we can import database connection logic
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from scoring.query import get_db_connection
except ImportError:
    print("Error: Could not import database connection from backend/scoring/query.py")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def main():
    """Initialize the database schema."""
    
    # Check if database is configured
    database_url = os.environ.get("DATABASE_URL")
    postgres_host = os.environ.get("POSTGRES_HOST")
    
    if not (database_url or postgres_host):
        print("Error: No database configuration found.")
        print("Set either:")
        print("  DATABASE_URL=postgresql://user:pass@host:port/db")
        print("or:")
        print("  POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD")
        sys.exit(1)
    
    # Read schema file
    schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}")
        sys.exit(1)
    
    print(f"Reading schema from: {schema_path}")
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Connect to database
    print("Connecting to database...")
    try:
        conn = get_db_connection()
        print("✅ Database connection successful!")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Execute schema
    print("Creating database schema...")
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("✅ Database schema created successfully!")
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to create schema: {e}")
        sys.exit(1)
    finally:
        conn.close()
    
    # Verify PostGIS extension
    print("Verifying PostGIS installation...")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT postgis_version();")
            postgis_version = cur.fetchone()[0]
            print(f"✅ PostGIS version: {postgis_version}")
        conn.close()
    except Exception as e:
        print(f"⚠️  PostGIS verification failed: {e}")
        print("You may need to enable PostGIS extension manually:")
        print("  psql \"$DATABASE_URL\" -c \"CREATE EXTENSION IF NOT EXISTS postgis;\"")
    
    # Check tables
    print("Verifying created tables...")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY tablename;
            """)
            tables = [row[0] for row in cur.fetchall()]
            
        conn.close()
        
        expected_tables = [
            'ingest_runs',
            'projects', 
            'raw_building_permits',
            'raw_street_closures'
        ]
        
        for table in expected_tables:
            if table in tables:
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table} (missing)")
        
        print(f"\nCreated {len(tables)} tables total.")
        
    except Exception as e:
        print(f"⚠️  Table verification failed: {e}")
    
    print("\n🎉 Database initialization complete!")
    print("\nNext steps:")
    print("1. Run data ingestion: python backend/ingest/building_permits.py")
    print("2. Run data ingestion: python backend/ingest/street_closures.py") 
    print("3. Test the API: curl http://localhost:8000/health")


if __name__ == "__main__":
    main()