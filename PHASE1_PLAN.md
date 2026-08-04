# Phase 1 Plan — MVP

Operating model: **internal ops tool**, not a self-serve product. There is no in-app authentication or client-facing onboarding UI — the operator runs pipelines on behalf of clients and configures everything manually. Clients receive results by email.

## Goal

A working pipeline that pulls jobs from three free sources, stores them in Postgres, ranks them per client, and emails each client a digest on their own schedule.

## Scope (in / out)

**In**: RemoteOK, We Work Remotely, Adzuna (`/pl/`) connectors; Postgres storage; per-client scheduling; email delivery via Resend; rule-based ranking; per-client dedup/fingerprinting; YAML-based client intake.

**Out** (deferred to later phases): ATS aggregation (Greenhouse/Lever/etc.), Telegram-source scraping, LLM-based ranking and remote-eligibility verification, embeddings/pgvector, automated feedback-driven weight adjustment, NoFluffJobs/JustJoinIT scraping, structured feedback UI.

## Architecture

Ingestion is decoupled from delivery, since clients run on independent schedules and the same job pool serves all of them:

- **Ingestion job** (shared, runs once daily): connectors → normalize → dedup → populate a shared `vacancy` pool. Client-agnostic — avoids redundant API calls (and Adzuna rate limits) that per-client fetching would cause.
- **Per-client digest job** (runs on each client's own cadence, via `client.schedule`): rank the current pool against that client's `search_profile` → filter out anything already in their `delivery` log → send email digest.

Fingerprinting (`delivery` table) is tracked **per client**, not globally, since the same vacancy can be relevant to multiple clients and get sent to each on a different schedule.

## Data model

```
client(id, name, email, status, schedule, created_at)
search_profile(client_id FK, structured_filters JSONB, free_text_criteria, updated_at)
vacancy(id, source, source_id, title, company, location, salary, description, remote_flag, raw_payload, created_at)
delivery(client_id FK, vacancy_id FK, sent_at, status)
```

- `structured_filters` (JSONB): role keywords, seniority, location, salary_min, tech_include/exclude, employment_type — the answerable-in-SQL criteria.
- `free_text_criteria`: prose dealbreakers/preferences that don't fit structured fields (used by later LLM ranking phases; for Phase 1, informs manual review only).
- `client.schedule`: cron expression (or `frequency_days` + `send_hour` if full cron flexibility isn't needed).

Storage: Postgres (hosted, e.g. Supabase or Neon) from the start — avoids a later migration once pgvector is introduced in Phase 2+.

## Client intake

No in-app questionnaire for Phase 1. The operator runs the fixed generic questionnaire (role, seniority, must-have/avoid tech, employment type, work arrangement, salary floor, visa needs, company size/industry preferences, exclusions, language requirements, dealbreakers) with each client directly, then fills in a YAML file per client (e.g. `clients/jane_doe.yaml`). A loader script parses these into `search_profile` rows. Editing a client's filters later is a direct YAML edit.

## Ranking (Phase 1, simplified)

No LLM yet. Rule-based score against `structured_filters`:
- Keyword match on title/description against role/tech filters
- `location ILIKE '%poland%' OR remote_flag = true`
- Salary floor filter where salary data is present

Reasoning stored as a short static string (e.g. "matched: remote + backend + Python"). LLM-based ranking and remote-eligibility text verification are deferred to Phase 2+.

## Delivery

Email via **Resend**. One digest email per client per scheduled run, listing matched vacancies (title, company, location, salary if available, link, match reasoning). No structured feedback UI in Phase 1 — digest includes a line inviting clients to reply with feedback, which the operator reviews manually and reflects back into the client's YAML profile. Automated feedback capture/parsing is deferred to a later phase.

## Tech stack

- **Connectors**: Python + `httpx` — deterministic, not agentic
- **Orchestration**: APScheduler — one shared ingestion job, dynamic per-client jobs loaded from `client.schedule`
- **Storage**: Postgres (hosted: Supabase or Neon)
- **Email**: Resend
- **Compute**: small VPS (e.g. Hetzner), chosen over serverless so the same host can later run Telethon's persistent session in Phase 3 without re-architecting

## Task breakdown (~1.5–2 weeks)

1. Scaffolding + Postgres setup (Supabase/Neon) — 0.5 day
2. Schema: `client`, `search_profile`, `vacancy`, `delivery` — 0.5 day
3. Connectors: RemoteOK, WWR, Adzuna — 2–3 days
4. Normalizer + dedup (shared pool) — 1 day
5. Rule-based ranking against `structured_filters` — 1 day
6. Orchestrator: APScheduler, shared ingestion job + dynamic per-client jobs — 1 day
7. Email delivery via Resend (digest template + send) — 1 day
8. Client intake: YAML file per client → loader into `search_profile` — 0.5 day
9. End-to-end test with 1–2 real client profiles — 1 day

## Open items for later phases

- Automated feedback capture and ranking-weight adjustment
- LLM-based ranking + remote-eligibility verification from description text
- ATS aggregation:
  - Tech-native platforms (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Personio) — mostly startups/scale-ups, clean public per-company job-board APIs
  - Enterprise platforms (Workday, SuccessFactors, Taleo) — needed to cover large (500+ headcount) IT employers with a Poland presence, since these typically don't use the tech-native platforms above. Workday exposes a fairly consistent unofficial JSON endpoint (CXS API) behind its public career sites; SuccessFactors and Taleo are less standardized and may require HTML scraping rather than a clean API — expect more per-target integration effort here
  - Neither category has a global search API: requires a curated target company list (name → ATS platform → board/company slug) rather than one broad query like Adzuna's
- Telegram source scraping (Telethon) and Polish niche boards (NoFluffJobs, JustJoinIT)
- pgvector-based fuzzy dedup (embedding similarity), replacing the simpler string-hash dedup used in Phase 1
