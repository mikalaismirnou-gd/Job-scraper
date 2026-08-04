import json
from pathlib import Path

import psycopg
import yaml
from dotenv import load_dotenv

from db.connection import connect

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "clients"


def load_client_files() -> list[dict]:
    profiles = []
    for path in sorted(CLIENTS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue  # skip _template.yaml
        with open(path, encoding="utf-8") as f:
            profiles.append(yaml.safe_load(f))
    return profiles


def upsert_profile(conn: psycopg.Connection, profile: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO client (name, email, status, schedule)
            VALUES (%(name)s, %(email)s, %(status)s, %(schedule)s)
            ON CONFLICT (email) DO UPDATE SET
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                schedule = EXCLUDED.schedule
            RETURNING id;
            """,
            profile,
        )
        client_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO search_profile (client_id, structured_filters, free_text_criteria)
            VALUES (%s, %s, %s)
            ON CONFLICT (client_id) DO UPDATE SET
                structured_filters = EXCLUDED.structured_filters,
                free_text_criteria = EXCLUDED.free_text_criteria,
                updated_at = now();
            """,
            (
                client_id,
                json.dumps(profile["structured_filters"]),
                profile.get("free_text_criteria"),
            ),
        )

    return client_id


def main() -> None:
    load_dotenv()
    profiles = load_client_files()

    with connect() as conn:
        for profile in profiles:
            client_id = upsert_profile(conn, profile)
            print(f"Loaded client_id={client_id}: {profile['name']} <{profile['email']}>")
        conn.commit()


if __name__ == "__main__":
    main()
