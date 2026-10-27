"""Marketing automation engine.

A workflow is a trigger-to-action rule. When a domain event is emitted, every
*active* workflow whose trigger matches is executed once per (entity, context).
Each execution performs a single action against the contact that owns the event.

Supported triggers:
  contact_created      -> fires when a contact is created (context = '')
  lifecycle_changed    -> fires when a contact's lifecycle stage changes (context = new stage)
  form_submitted       -> fires when a form is submitted (context = form slug)
  deal_stage_changed   -> fires when a deal moves stage (context = stage name)
  campaign_sent        -> fires when a campaign email is sent (context = campaign id)

Supported actions:
  send_email           -> email the contact (action_value = subject; body appended)
  add_campaign         -> enroll the contact in campaign (action_value = campaign id)
  enroll_sequence      -> enroll the contact in sequence (action_value = sequence id)
  change_lifecycle     -> set the contact's lifecycle stage (action_value = stage name)
  create_task          -> create a follow-up task (action_value = task title)
"""
from __future__ import annotations

from typing import Any

from .. import db
from . import mailer

TRIGGERS = {
    "contact_created": "When a contact is created",
    "lifecycle_changed": "When a contact's lifecycle stage changes",
    "form_submitted": "When a form is submitted",
    "deal_stage_changed": "When a deal moves to a stage",
    "campaign_sent": "When a campaign email is sent to a contact",
}
ACTIONS = {
    "send_email": "Send an email to the contact",
    "add_campaign": "Enroll the contact in a campaign",
    "enroll_sequence": "Enroll the contact in a sequence",
    "change_lifecycle": "Change the contact's lifecycle stage",
    "create_task": "Create a follow-up task",
}

CONTACT_TRIGGERS = {"contact_created", "lifecycle_changed", "form_submitted", "campaign_sent"}


def log_activity(atype: str, entity_type: str, entity_id: int | None, detail: str) -> None:
    db.execute(
        "INSERT INTO activities (type, entity_type, entity_id, detail) VALUES (?, ?, ?, ?)",
        (atype, entity_type, entity_id, detail),
    )


def _contact_for(entity_type: str, entity_id: int) -> dict[str, Any] | None:
    if entity_type == "contact":
        return db.query_one("SELECT * FROM contacts WHERE id = ?", (entity_id,))
    if entity_type == "deal":
        deal = db.query_one("SELECT * FROM deals WHERE id = ?", (entity_id,))
        if deal and deal.get("contact_id"):
            return db.query_one("SELECT * FROM contacts WHERE id = ?", (deal["contact_id"],))
    if entity_type == "submission":
        sub = db.query_one("SELECT * FROM form_submissions WHERE id = ?", (entity_id,))
        if sub:
            data = json_loads(sub.get("data_json"))
            email = (data or {}).get("email") or (data or {}).get("Email")
            if email:
                return db.query_one("SELECT * FROM contacts WHERE email = ?", (email,))
    return None


def json_loads(value: str | None) -> Any:
    import json

    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:  # noqa: BLE001
        return {}


def _execute_action(workflow: dict[str, Any], contact: dict[str, Any]) -> str:
    """Run one action, return a human-readable summary."""
    atype = workflow["action_type"]
    value = workflow["action_value"] or ""
    cid = contact["id"]

    if atype == "send_email":
        subject = value or f"Message from OpenReach"
        body = f"Hi {contact['first_name']},\n\n{subject}\n\n— OpenReach"
        mailer.send_email(contact["email"] or "", subject, body, contact_id=cid)
        return f"Emailed {contact.get('email')}: {subject}"

    if atype == "add_campaign":
        try:
            campaign_id = int(value)
        except ValueError:
            campaign_id = 0
        if campaign_id:
            db.execute(
                "INSERT OR IGNORE INTO campaign_contacts (campaign_id, contact_id) VALUES (?, ?)",
                (campaign_id, cid),
            )
            return f"Enrolled contact {cid} in campaign {campaign_id}"

    if atype == "enroll_sequence":
        try:
            seq_id = int(value)
        except ValueError:
            seq_id = 0
        if seq_id:
            exists = db.query_one(
                "SELECT id FROM sequence_enrollments WHERE sequence_id = ? AND contact_id = ?",
                (seq_id, cid),
            )
            if not exists:
                db.execute(
                    "INSERT INTO sequence_enrollments (sequence_id, contact_id) VALUES (?, ?)",
                    (seq_id, cid),
                )
            return f"Enrolled contact {cid} in sequence {seq_id}"

    if atype == "change_lifecycle":
        db.execute("UPDATE contacts SET lifecycle_stage = ?, updated_at = datetime('now') WHERE id = ?", (value, cid))
        return f"Set lifecycle to {value}"

    if atype == "create_task":
        db.execute(
            "INSERT INTO tasks (contact_id, title) VALUES (?, ?)",
            (cid, value or "Follow up"),
        )
        return f"Created task: {value or 'Follow up'}"

    return f"No-op ({atype})"


def emit(event_type: str, entity_type: str, entity_id: int, context: str = "") -> list[dict[str, Any]]:
    """Emit a domain event; run every matching workflow exactly once per context."""
    runs: list[dict[str, Any]] = []
    contact = None
    if event_type in CONTACT_TRIGGERS or event_type == "deal_stage_changed":
        contact = _contact_for(entity_type, entity_id)
        if contact is None:
            return runs

    workflows = db.query(
        "SELECT * FROM workflows WHERE active = 1 AND trigger_type = ?",
        (event_type,),
    )
    for wf in workflows:
        if event_type == "lifecycle_changed" and wf["trigger_value"] and wf["trigger_value"] != context:
            continue
        if event_type == "form_submitted" and wf["trigger_value"] and wf["trigger_value"] != context:
            continue
        if event_type == "deal_stage_changed" and wf["trigger_value"] and wf["trigger_value"] != context:
            continue
        if event_type == "campaign_sent" and wf["trigger_value"] and wf["trigger_value"] != str(context):
            continue

        try:
            already = db.query_one(
                "SELECT id FROM workflow_runs WHERE workflow_id = ? AND entity_type = ? AND entity_id = ? AND context = ?",
                (wf["id"], entity_type, entity_id, context),
            )
            if already:
                continue
            detail = _execute_action(wf, contact) if contact else "No contact"
            db.execute(
                "INSERT INTO workflow_runs (workflow_id, entity_type, entity_id, context) VALUES (?, ?, ?, ?)",
                (wf["id"], entity_type, entity_id, context),
            )
            log_activity("workflow", "workflow", wf["id"], f"{wf['name']}: {detail}")
            runs.append({"workflow": wf["name"], "detail": detail})
        except Exception as exc:  # noqa: BLE001 - one bad workflow must not break the request
            runs.append({"workflow": wf["name"], "detail": f"Error: {exc}"})
    return runs
