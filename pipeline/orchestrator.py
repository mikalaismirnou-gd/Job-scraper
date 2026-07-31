import logging
import os

import psycopg
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from psycopg.rows import dict_row

from delivery import digest
from pipeline import ingest, ranking

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("orchestrator")

INGESTION_SCHEDULE = "0 6 * * *"  # daily at 06:00, ahead of any client's digest time


def ingestion_job() -> None:
    logger.info("Starting shared ingestion run")
    vacancies = ingest.fetch_all()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        inserted, fuzzy_skipped = ingest.store(conn, vacancies)
        conn.commit()
    logger.info("Ingestion done: inserted=%d, fuzzy_skipped=%d", inserted, fuzzy_skipped)


def client_digest_job(client_id: int, client_name: str, client_email: str) -> None:
    logger.info("Building digest for client_id=%d (%s)", client_id, client_name)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        matches = ranking.rank_for_client(conn, client_id)
        if not matches:
            logger.info("client_id=%d (%s): no matches, skipping send", client_id, client_name)
            return

        email_id = digest.send_digest(client_email, client_name, matches)
        digest.log_delivery(conn, client_id, matches)
        conn.commit()

    logger.info("client_id=%d (%s): sent %d matches (email_id=%s)", client_id, client_name, len(matches), email_id)


def load_active_clients() -> list[dict]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name, email, schedule FROM client WHERE status = 'active';")
            return cur.fetchall()


def register_jobs(scheduler) -> None:
    scheduler.add_job(
        ingestion_job,
        CronTrigger.from_crontab(INGESTION_SCHEDULE),
        id="shared_ingestion",
        name="Shared ingestion (RemoteOK/WWR/Adzuna)",
    )

    for client in load_active_clients():
        scheduler.add_job(
            client_digest_job,
            CronTrigger.from_crontab(client["schedule"]),
            args=[client["id"], client["name"], client["email"]],
            id=f"digest_client_{client['id']}",
            name=f"Digest for {client['name']}",
        )


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Europe/Warsaw")
    register_jobs(scheduler)
    return scheduler


def main() -> None:
    load_dotenv()
    scheduler = build_scheduler()
    for job in scheduler.get_jobs():
        logger.info("Registered job: %s (next run: %s)", job.name, job.next_run_time)
    scheduler.start()


if __name__ == "__main__":
    main()
