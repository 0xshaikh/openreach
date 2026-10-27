"""Seed the database with a default deal pipeline and demo records."""
from __future__ import annotations

from . import db

DEFAULT_STAGES = [
    ("Appointment Scheduled", "#f59e0b"),
    ("Qualified", "#3b82f6"),
    ("Proposal Sent", "#8b5cf6"),
    ("Negotiation", "#ec4899"),
    ("Closed Won", "#10b981"),
    ("Closed Lost", "#ef4444"),
]


def seed_if_empty() -> None:
    """Idempotent: only seeds when the stages table is empty."""
    if db.query_one("SELECT COUNT(*) AS c FROM stages")["c"] > 0:
        return
    with db.tx() as conn:
        for i, (name, color) in enumerate(DEFAULT_STAGES, start=1):
            conn.execute(
                "INSERT INTO stages (name, order_index, color) VALUES (?, ?, ?)",
                (name, i, color),
            )

        # A starter company, contact and deal so the UI isn't empty.
        conn.execute(
            "INSERT INTO companies (name, domain, industry, city, size) VALUES (?, ?, ?, ?, ?)",
            ("Acme Robotics", "acmerobotics.example", "Manufacturing", "Austin", "51-200"),
        )
        conn.execute(
            "INSERT INTO contacts (first_name, last_name, email, job_title, lifecycle_stage, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Ava", "Chen", "ava@acmerobotics.example", "VP Operations", "Lead", 1),
        )
        conn.execute(
            "INSERT INTO deals (name, value, stage_id, contact_id, company_id) VALUES (?, ?, ?, ?, ?)",
            ("Robotics platform renewal", 24000, 1, 1, 1),
        )


def seed() -> None:
    seed_if_empty()
