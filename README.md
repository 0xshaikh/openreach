# OpenReach

<p align="center">
  <img src="icon.svg" alt="OpenReach" width="120">
</p>

**OpenReach** is a self-hosted, open-source alternative to HubSpot CRM + Marketing Hub. It bundles a working CRM core — contacts, companies, a visual drag-and-drop deals pipeline — with the marketing automation features that make HubSpot expensive at scale: email campaigns and sequences, embeddable web forms, landing pages, and trigger-to-action automation workflows.

Everything runs on **FastAPI + SQLite**. **Zero API keys, zero paid services, zero per-contact fees.** One process, one file, fully yours.

> Differentiates from [openpipe](https://github.com/0xshaikh/openpipe) (a Salesforce-style sales pipeline CRM) by leaning into the *marketing* half of HubSpot — campaigns, sequences, forms, landing pages, and automation — while still shipping a complete CRM.

## Features

- **Contacts & CRM database** — full CRUD, search, lifecycle stages (`Lead → MQL → SQL → Customer → Churned`), link to companies.
- **Companies** — accounts with domain, industry, city, size, plus contact/deal rollups.
- **Deals pipeline** — a real drag-and-drop kanban board. Move a deal between stages (Appointment Scheduled, Qualified, Proposal Sent, Negotiation, Closed Won/Lost) with a single API call; every move is logged and can trigger automation.
- **Email campaigns** — create a campaign, enroll contacts, send. Messages go to a persistent **outbox** (viewable in-app). If you set SMTP env vars, they're delivered for real; otherwise they're spooled — so it works with zero external services.
- **Email sequences** — multi-step follow-ups (step 1 sends on enroll, "Advance day" sends the next step), with per-step subject/body and delay.
- **Embeddable web forms** — hosted at `/f/{slug}`, renderable in any page via an iframe. Submissions upsert a contact and fire automation.
- **Landing pages** — publish raw-HTML pages at `/p/{slug}` with one click.
- **Marketing automation** — a workflow engine that runs *trigger → action* rules:
  - **Triggers:** contact created, lifecycle changed, form submitted, deal stage changed, campaign sent.
  - **Actions:** send email, add to campaign, enroll in sequence, change lifecycle, create task.
  - Each rule fires **once per entity** (idempotent) and is logged to the activity feed.
- **Dashboard** — pipeline value, open deals, emails sent, submissions, activity feed.

## Quickstart

```bash
# 1. Create a virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run it
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000**. The database is created and seeded with a default pipeline and a demo company/contact/deal on first run.

### Try it end-to-end

```bash
# Contacts + automation
curl -X POST localhost:8000/api/contacts -H 'Content-Type: application/json' \
  -d '{"first_name":"Sam","last_name":"Lee","email":"sam@acme.dev","lifecycle_stage":"Lead"}'

# Deals
curl -X POST localhost:8000/api/deals -H 'Content-Type: application/json' \
  -d '{"name":"Acme expansion","value":12000}'
# move it
curl -X PATCH localhost:8000/api/deals/1/stage -H 'Content-Type: application/json' -d '{"stage_id":2}'

# Campaign
curl -X POST localhost:8000/api/campaigns -H 'Content-Type: application/json' \
  -d '{"name":"Welcome","subject":"Hello","body":"Thanks for signing up!"}'
curl -X POST localhost:8000/api/campaigns/1/enroll -H 'Content-Type: application/json' -d '{"contact_id":1}'
curl -X POST localhost:8000/api/campaigns/1/send

# Automation: when a deal hits "Closed Won", email the contact
curl -X POST localhost:8000/api/workflows -H 'Content-Type: application/json' \
  -d '{"name":"Won deal","trigger_type":"deal_stage_changed","trigger_value":"Closed Won","action_type":"send_email","action_value":"Congrats on the deal!"}'
```

## Architecture

```
app/
  main.py          FastAPI app + startup (init db, seed)
  db.py            SQLite layer (schema, query/execute helpers)
  seed.py          Default pipeline + demo records (idempotent)
  routers/
    pages.py       HTML: SPA shell, embeddable forms (/f/{slug}), landing pages (/p/{slug})
    api.py         JSON API: contacts, companies, deals, campaigns, sequences, forms, workflows
  services/
    mailer.py      Email delivery — SMTP if configured, otherwise spool to outbox table
    engine.py      Automation engine — emits events, matches workflows, executes actions
  templates/       Jinja2 views (app shell, form embed, thank-you)
  static/          Vanilla JS SPA + CSS (no build step, no deps)
openreach.db       SQLite file (created at runtime)
```

**Design choices**

- **Single SQLite file** — one process, zero infra, trivially portable. `OPENREACH_DB` overrides the location.
- **Outbox email model** — without SMTP config, mail is written to the `emails` table and shown in the UI's Email Outbox. Set `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` to deliver for real. Either way every message is retained and inspectable.
- **Event-driven automation** — the app never checks "if this then that" inline. Domain actions (`engine.emit`) fire events that the workflow engine matches against active rules, so automation is declarative and easy to audit.
- **Idempotent runs** — a workflow executes at most once per (entity, context), so re-firing an event never double-emails.

## License

MIT — see [LICENSE](LICENSE). Free to use, fork, and self-host.
