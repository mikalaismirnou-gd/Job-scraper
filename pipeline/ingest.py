import hashlib
import json
import os
import re

import psycopg
from dotenv import load_dotenv

from connectors import adzuna, remoteok, wwr
from connectors.common import Vacancy

FETCH_DAYS = 3

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def fuzzy_key(company: str, title: str, location: str) -> str:
    raw = f"{company}|{title}|{location}".lower()
    normalized = _NORMALIZE_RE.sub("", raw)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fetch_all(days: int = FETCH_DAYS) -> list[Vacancy]:
    vacancies: list[Vacancy] = []
    for connector in (remoteok, wwr, adzuna):
        fetched = connector.fetch(days=days)
        print(f"{connector.__name__.rsplit('.', 1)[-1]}: fetched {len(fetched)}")
        vacancies.extend(fetched)
    return vacancies


def store(conn: psycopg.Connection, vacancies: list[Vacancy]) -> tuple[int, int]:
    inserted = 0
    fuzzy_skipped = 0
    seen_fuzzy_keys: set[str] = set()

    with conn.cursor() as cur:
        cur.execute("SELECT company, title, location FROM vacancy;")
        for company, title, location in cur.fetchall():
            seen_fuzzy_keys.add(fuzzy_key(company or "", title or "", location or ""))

        for vacancy in vacancies:
            key = fuzzy_key(vacancy["company"], vacancy["title"], vacancy["location"])
            if key in seen_fuzzy_keys:
                fuzzy_skipped += 1
                continue

            cur.execute(
                """
                INSERT INTO vacancy
                    (source, source_id, title, company, location, salary, description, remote_flag, raw_payload)
                VALUES (%(source)s, %(source_id)s, %(title)s, %(company)s, %(location)s,
                        %(salary)s, %(description)s, %(remote_flag)s, %(raw_payload)s)
                ON CONFLICT (source, source_id) DO NOTHING
                RETURNING id;
                """,
                {**vacancy, "raw_payload": json.dumps(vacancy["raw_payload"])},
            )
            row = cur.fetchone()
            if row is not None:
                inserted += 1
                seen_fuzzy_keys.add(key)

    return inserted, fuzzy_skipped


def main() -> None:
    load_dotenv()
    vacancies = fetch_all()
    print(f"Total fetched across sources: {len(vacancies)}")

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        inserted, fuzzy_skipped = store(conn, vacancies)
        conn.commit()

    print(f"Inserted: {inserted}, skipped as fuzzy duplicates: {fuzzy_skipped}")


if __name__ == "__main__":
    main()
