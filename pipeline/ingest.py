import hashlib
import json
import re

import psycopg
from dotenv import load_dotenv

from connectors import adzuna, ashby, greenhouse, lever, personio, remoteok, smartrecruiters, wwr
from connectors.common import Vacancy
from db.connection import connect

FETCH_DAYS = 3

# Workday omitted for now: its WAF needs more validation at full scale before
# running unattended in the daily job (see connectors/workday.py).
CONNECTORS = (remoteok, wwr, adzuna, greenhouse, lever, smartrecruiters, personio, ashby)

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def fuzzy_key(company: str, title: str, location: str, remote_flag: bool) -> str:
    # Companies often repost the same remote role once per city for local-search
    # visibility, so location is excluded from the key when the role is remote.
    parts = f"{company}|{title}" if remote_flag else f"{company}|{title}|{location}"
    normalized = _NORMALIZE_RE.sub("", parts.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fetch_all(days: int = FETCH_DAYS) -> list[Vacancy]:
    vacancies: list[Vacancy] = []
    for connector in CONNECTORS:
        name = connector.__name__.rsplit(".", 1)[-1]
        try:
            fetched = connector.fetch(days=days)
        except Exception as e:
            # One source's outage (e.g. Adzuna 503s) shouldn't take down ingestion
            # for every other source too.
            print(f"{name}: FAILED ({e})")
            continue
        print(f"{name}: fetched {len(fetched)}")
        vacancies.extend(fetched)
    return vacancies


def store(conn: psycopg.Connection, vacancies: list[Vacancy]) -> tuple[int, int]:
    inserted = 0
    fuzzy_skipped = 0
    seen_fuzzy_keys: set[str] = set()

    with conn.cursor() as cur:
        cur.execute("SELECT company, title, location, remote_flag FROM vacancy;")
        for company, title, location, remote_flag in cur.fetchall():
            seen_fuzzy_keys.add(fuzzy_key(company or "", title or "", location or "", remote_flag))

        for vacancy in vacancies:
            key = fuzzy_key(vacancy["company"], vacancy["title"], vacancy["location"], vacancy["remote_flag"])
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

    with connect() as conn:
        inserted, fuzzy_skipped = store(conn, vacancies)
        conn.commit()

    print(f"Inserted: {inserted}, skipped as fuzzy duplicates: {fuzzy_skipped}")


if __name__ == "__main__":
    main()
