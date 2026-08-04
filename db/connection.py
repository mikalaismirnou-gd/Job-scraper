import os

import psycopg


def connect() -> psycopg.Connection:
    # prepare_threshold=None disables server-side prepared statements, which
    # aren't supported reliably over Supabase's transaction-mode PgBouncer
    # pooler (each transaction can land on a different backend connection).
    return psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None)
