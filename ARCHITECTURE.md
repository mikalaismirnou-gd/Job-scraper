# Job Search AI Agent — Architecture Brief

Multi-agent pipeline: discovers vacancies from multiple sources, ranks them against a search profile, delivers a digest, and collects feedback to refine future ranking. Runs on a schedule every 1–2 days.

## Target market

**Priority: Poland OR remote.** Caveat — the `remote: true` flag from APIs doesn't guarantee eligibility from Poland (timezone/region restrictions usually only exist as free text, e.g. "Remote — US only"). The Ranking agent must verify this from the description text, not just trust the flag.

## Pipeline (5 stages)

1. **Discovery/Connector agents** — one connector per source, deterministic code (not autonomous LLM agents; reliability matters more than flexibility here)
2. **Normalizer & Dedup** — unify schema across sources, dedupe by `source+source_id` (exact) and embedding similarity on `company+title+location` (fuzzy — the same vacancy often appears on a job board AND a company's ATS AND a Telegram repost)
3. **Ranking agent** — LLM + embeddings vs. `search_profile`; outputs a score + short reasoning (reasoning goes straight into the digest)
4. **Distribution agent** — formats the digest, sends via channel adapters
5. **Feedback agent** — collects reactions, feeds back into Ranking (loop)

**Orchestrator**: cron / APScheduler / Celery Beat, runs every 24–48h, tracks an "already sent" fingerprint table so nothing gets resent on the next run.

## Data sources, by phase

### Phase 1 — start here (no auth, or instant free key)

| Source | Endpoint | Notes |
|---|---|---|
| RemoteOK | `GET remoteok.com/api` | Free, no auth, filter via `?tags=` |
| We Work Remotely | `GET weworkremotely.com/remote-jobs.rss` | Free RSS; per-category feeds exist (backend/frontend/full-stack) |
| Remotive | `GET remotive.com/api/remote-jobs` | Free, but must attribute/link back to Remotive or access gets revoked; data is 24h delayed (irrelevant for a daily digest) |
| Adzuna | `GET api.adzuna.com/v1/api/jobs/pl/search/1?app_id=&app_key=` | Free key, Poland + wider Europe in one API |

### Phase 2 — ATS aggregation (naturally covers Poland *and* remote — both fields are in the payload)

- Greenhouse: `boards-api.greenhouse.io/v1/boards/{token}/jobs` — open, no auth
- Lever: `api.lever.co/v0/postings/{company}` — open, supports filters (team/location/commitment)
- Ashby, Workable, SmartRecruiters — same pattern, open JSON per company
- Personio: `{company}.jobs.personio.de/xml` — open XML feed, strong in DACH region

### Phase 3 — Telegram + Polish niche boards

- Polish IT Telegram channels — via **Telethon** (MTProto/userbot), *not* the Bot API (can't read channel history unless the bot is admin of that channel). Register an app at my.telegram.org.
- NoFluffJobs / JustJoinIT — best density/quality for Polish IT specifically, but **no free official API** — scraping only; check robots.txt/ToS before building this connector.

### Phase 4 — broaden

- Jooble — partner REST API (apply for a key), 66+ countries, aggregates LinkedIn/Indeed under the hood
- Email delivery channel
- Feedback-driven ranking weight adjustments become real (not just logged)

### Avoid

- **LinkedIn** scraping/automation — explicitly prohibited (User Agreement §8.2), aggressively detected and banned. Use only official partner APIs if ever needed, or skip it entirely — not worth the account risk.

## Data model (minimal)

```
vacancy(source, source_id, title, company, location, salary, description, remote_flag, embedding, raw_payload)
search_profile(structured_filters, free_text_criteria, updated_by_feedback)
match(vacancy_id, profile_id, score, reasoning, status)
delivery(match_id, channel, sent_at, status)
feedback(match_id, reaction, comment, created_at)
```

Storage: **Postgres + pgvector** (relational + semantic search in one DB — no separate vector store needed at this scale).

## Search profile logic

```sql
location ILIKE '%poland%' OR remote = true
```

→ then an LLM pass on the remote subset to confirm actual geographic/timezone eligibility from the job description text (see caveat above).

## Tech stack

- **Connectors**: Python + `httpx` — deterministic, not "agentic"
- **Telegram**: Telethon
- **LLM layer used for**: parsing unstructured Telegram posts into schema, semantic ranking + remote-eligibility check, digest generation, interpreting free-text feedback
- **Orchestration**: cron/APScheduler is enough for one linear pipeline; LangGraph if you want a stateful graph with retries out of the box. A heavier agent framework (CrewAI/AutoGen/Microsoft Agent Framework) is likely overkill for this shape of pipeline — it's one sequential process, not a crowd of autonomous agents negotiating.
- **No-code MVP alternative**: n8n has ready templates for scrape → AI filter → notify, useful for validating the concept before writing custom code
- **Delivery**: aiogram/python-telegram-bot (Telegram), Postmark/SendGrid/Resend (email)
- **Feedback**: Telegram inline buttons (👍 / 👎 / "не по профилю")

## Feedback loop

Dislike on a specific company → downweight that company going forward. Systematic dislike pattern (grade, location) → adjust that criterion's weight. Later: feed liked/disliked examples as few-shot examples into the ranking prompt, or train a lightweight reranker.

## MVP roadmap

1. **Phase 1** (1–2 weeks): RemoteOK + WWR + Adzuna(`/pl/`) → Telegram bot delivery + inline-button feedback. SQLite/Postgres, daily cron.
2. **Phase 2**: + Greenhouse/Lever/Ashby/Personio aggregation, LLM normalization + dedup
3. **Phase 3**: + Polish Telegram channels via Telethon, LLM parsing of unstructured posts
4. **Phase 4**: + Jooble, email channel, feedback-driven ranking, possibly NoFluffJobs/JustJoinIT scraping
