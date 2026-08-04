from dotenv import load_dotenv

from db.connection import connect

load_dotenv()

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), version();")
        db, version = cur.fetchone()
        print(f"Connected to database: {db}")
        print(f"Server version: {version.split(',')[0]}")

        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """
        )
        tables = [row[0] for row in cur.fetchall()]
        print(f"Tables in public schema: {tables}")
