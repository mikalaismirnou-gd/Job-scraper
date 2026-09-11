import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from db.connection import connect


def score_vacancy(vacancy: dict, filters: dict) -> tuple[int, list[str]] | None:
    """Rule-based Phase 1 scorer. Returns (score, reasons) or None if excluded."""
    title = (vacancy["title"] or "").lower()
    text = f"{title} {(vacancy['description'] or '').lower()}"
    reasons: list[str] = []
    score = 0

    for term in filters.get("tech_exclude", []):
        if term.lower() in text:
            return None
    for company in filters.get("company_blocklist", []):
        if company.lower() == (vacancy["company"] or "").lower():
            return None
    for industry in filters.get("industries_exclude", []):
        if industry.lower() in text:
            return None

    role_keywords = filters.get("role_keywords", [])
    matched_roles = [kw for kw in role_keywords if kw.lower() in title]
    if role_keywords and not matched_roles:
        return None
    if matched_roles:
        score += 3 * len(matched_roles)
        reasons.append(f"role match: {', '.join(matched_roles)}")

    location_pref = (filters.get("location") or "").lower()
    remote_ok = filters.get("remote_ok", False)
    vacancy_location = (vacancy["location"] or "").lower()
    is_remote = vacancy["remote_flag"]
    location_match = (remote_ok and is_remote) or (location_pref and location_pref in vacancy_location)
    if (location_pref or remote_ok) and not location_match:
        return None
    if location_match:
        reasons.append("remote" if is_remote else f"location: {vacancy['location']}")
        score += 2

    matched_seniority = [s for s in filters.get("seniority", []) if s.lower() in title]
    if matched_seniority:
        score += len(matched_seniority)
        reasons.append(f"seniority: {', '.join(matched_seniority)}")

    # Informational only, never excludes: Adzuna salary figures mix incompatible units
    # (monthly/annual/daily) with no reliable way to normalize them in Phase 1.
    if vacancy["salary"]:
        reasons.append(f"salary: {vacancy['salary']}")

    return score, reasons


def rank_for_client(conn: psycopg.Connection, client_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT structured_filters FROM search_profile WHERE client_id = %s;", (client_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"No search_profile for client_id={client_id}")
        filters = row["structured_filters"]

        # raw_payload is excluded here (and fetched separately, only for the final
        # matches below) since it's the largest field per row by far and the
        # undelivered backlog can be tens of thousands of rows - pulling it for
        # every candidate is what was OOM-killing this on the 1GB VPS.
        cur.execute(
            """
            SELECT v.id, v.source, v.source_id, v.title, v.company, v.location,
                   v.salary, v.description, v.remote_flag, v.created_at
            FROM vacancy v
            LEFT JOIN delivery d ON d.vacancy_id = v.id AND d.client_id = %s
            WHERE d.vacancy_id IS NULL;
            """,
            (client_id,),
        )
        candidates = cur.fetchall()

        matches = []
        for vacancy in candidates:
            result = score_vacancy(vacancy, filters)
            if result is None:
                continue
            score, reasons = result
            matches.append({**vacancy, "score": score, "reasoning": "; ".join(reasons)})

        matches.sort(key=lambda m: m["score"], reverse=True)

        if matches:
            cur.execute(
                "SELECT id, raw_payload FROM vacancy WHERE id = ANY(%s);",
                ([m["id"] for m in matches],),
            )
            payloads = {row["id"]: row["raw_payload"] for row in cur.fetchall()}
            for m in matches:
                m["raw_payload"] = payloads.get(m["id"])

    return matches


def main() -> None:
    load_dotenv()
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name FROM client WHERE status = 'active';")
            clients = cur.fetchall()

        for client in clients:
            matches = rank_for_client(conn, client["id"])
            print(f"\n{client['name']}: {len(matches)} matches")
            for m in matches[:10]:
                print(f"  [{m['score']}] {m['title']} @ {m['company']} ({m['source']}) - {m['reasoning']}")


if __name__ == "__main__":
    main()
