CREATE TABLE client (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    schedule TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE search_profile (
    client_id INTEGER PRIMARY KEY REFERENCES client(id),
    structured_filters JSONB NOT NULL,
    free_text_criteria TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE vacancy (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    salary TEXT,
    description TEXT,
    remote_flag BOOLEAN NOT NULL DEFAULT false,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_id)
);

CREATE TABLE delivery (
    client_id INTEGER NOT NULL REFERENCES client(id),
    vacancy_id INTEGER NOT NULL REFERENCES vacancy(id),
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'sent',
    PRIMARY KEY (client_id, vacancy_id)
);
