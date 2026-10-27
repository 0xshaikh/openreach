"""JSON API for OpenReach."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from .. import db
from ..services import engine, mailer

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers
def _json_dumps(data) -> str:
    return json.dumps(data)


def _contact_or_404(contact_id: int) -> dict:
    row = db.query_one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if not row:
        raise HTTPException(404, "Contact not found")
    return row


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "page"


def _unique_slug(table: str, base: str) -> str:
    slug = base
    n = 1
    while db.query_one(f"SELECT id FROM {table} WHERE slug = ?", (slug,)):
        n += 1
        slug = f"{base}-{n}"
    return slug


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard():
    counts = {
        "contacts": db.query_one("SELECT COUNT(*) c FROM contacts")["c"],
        "companies": db.query_one("SELECT COUNT(*) c FROM companies")["c"],
        "deals": db.query_one("SELECT COUNT(*) c FROM deals")["c"],
        "open_deals": db.query_one(
            "SELECT COUNT(*) c FROM deals d JOIN stages s ON d.stage_id=s.id "
            "WHERE s.name NOT IN ('Closed Won','Closed Lost')"
        )["c"],
        "pipeline_value": db.query_one(
            "SELECT COALESCE(SUM(d.value),0) v FROM deals d JOIN stages s ON d.stage_id=s.id "
            "WHERE s.name NOT IN ('Closed Won','Closed Lost')"
        )["v"],
        "campaigns": db.query_one("SELECT COUNT(*) c FROM campaigns")["c"],
        "emails_sent": db.query_one("SELECT COUNT(*) c FROM emails WHERE status='Sent'")["c"],
        "submissions": db.query_one("SELECT COUNT(*) c FROM form_submissions")["c"],
        "workflows": db.query_one("SELECT COUNT(*) c FROM workflows WHERE active=1")["c"],
        "tasks_open": db.query_one("SELECT COUNT(*) c FROM tasks WHERE done=0")["c"],
    }
    activities = db.query("SELECT * FROM activities ORDER BY id DESC LIMIT 12")
    recent_contacts = db.query(
        "SELECT c.*, co.name AS company_name FROM contacts c "
        "LEFT JOIN companies co ON c.company_id = co.id ORDER BY c.id DESC LIMIT 5"
    )
    return {"counts": counts, "activities": activities, "recent_contacts": recent_contacts}


# ---------------------------------------------------------------- contacts
@router.get("/contacts")
def list_contacts(q: str = ""):
    if q:
        like = f"%{q}%"
        return db.query(
            "SELECT c.*, co.name AS company_name FROM contacts c LEFT JOIN companies co ON c.company_id=co.id "
            "WHERE c.first_name LIKE ? OR c.last_name LIKE ? OR c.email LIKE ? ORDER BY c.id DESC",
            (like, like, like),
        )
    return db.query(
        "SELECT c.*, co.name AS company_name FROM contacts c LEFT JOIN companies co ON c.company_id=co.id "
        "ORDER BY c.id DESC"
    )


@router.post("/contacts")
def create_contact(payload: dict = Body(...)):
    email = (payload.get("email") or "").strip().lower() or None
    if email and db.query_one("SELECT id FROM contacts WHERE email = ?", (email,)):
        raise HTTPException(400, "A contact with this email already exists")
    cid = db.execute(
        """INSERT INTO contacts (first_name, last_name, email, phone, job_title, website, lifecycle_stage, company_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload.get("first_name", "").strip(),
            (payload.get("last_name") or "").strip(),
            email,
            (payload.get("phone") or "").strip(),
            (payload.get("job_title") or "").strip(),
            (payload.get("website") or "").strip(),
            (payload.get("lifecycle_stage") or "Lead"),
            payload.get("company_id"),
        ),
    )
    engine.log_activity("contact_created", "contact", cid, f"Created contact #{cid}")
    engine.emit("contact_created", "contact", cid)
    return {"id": cid, "ok": True}


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: int):
    c = _contact_or_404(contact_id)
    c["deals"] = db.query("SELECT * FROM deals WHERE contact_id = ? ORDER BY id DESC", (contact_id,))
    c["tasks"] = db.query("SELECT * FROM tasks WHERE contact_id = ? ORDER BY id DESC", (contact_id,))
    c["emails"] = db.query("SELECT * FROM emails WHERE contact_id = ? ORDER BY id DESC", (contact_id,))
    c["company"] = db.query_one("SELECT * FROM companies WHERE id = ?", (c["company_id"],)) if c.get("company_id") else None
    return c


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: int, payload: dict = Body(...)):
    _contact_or_404(contact_id)
    allowed = {"first_name", "last_name", "email", "phone", "job_title", "website", "lifecycle_stage", "company_id"}
    old = db.query_one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    sets, params = [], []
    for key, value in payload.items():
        if key in allowed and value is not None:
            sets.append(f"{key} = ?")
            params.append(value)
    if sets:
        params.append(contact_id)
        db.execute(
            f"UPDATE contacts SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?",
            tuple(params),
        )
    new = db.query_one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if new["lifecycle_stage"] != old["lifecycle_stage"]:
        engine.log_activity(
            "lifecycle_changed", "contact", contact_id,
            f"#{contact_id} lifecycle: {old['lifecycle_stage']} -> {new['lifecycle_stage']}",
        )
        engine.emit("lifecycle_changed", "contact", contact_id, context=new["lifecycle_stage"])
    return {"id": contact_id, "ok": True}


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int):
    db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    return {"id": contact_id, "ok": True}


# ---------------------------------------------------------------- companies
@router.get("/companies")
def list_companies():
    return db.query(
        "SELECT co.*, (SELECT COUNT(*) FROM contacts c WHERE c.company_id=co.id) AS contact_count, "
        "(SELECT COUNT(*) FROM deals d WHERE d.company_id=co.id) AS deal_count "
        "FROM companies co ORDER BY co.id DESC"
    )


@router.post("/companies")
def create_company(payload: dict = Body(...)):
    cid = db.execute(
        "INSERT INTO companies (name, domain, industry, city, size) VALUES (?, ?, ?, ?, ?)",
        (
            payload.get("name", "").strip(),
            (payload.get("domain") or "").strip(),
            (payload.get("industry") or "").strip(),
            (payload.get("city") or "").strip(),
            (payload.get("size") or "").strip(),
        ),
    )
    return {"id": cid, "ok": True}


# ---------------------------------------------------------------- deals / pipeline
@router.get("/stages")
def list_stages():
    return db.query("SELECT * FROM stages ORDER BY order_index")


@router.get("/deals")
def list_deals():
    return db.query(
        "SELECT d.*, s.name AS stage_name, s.color AS stage_color, s.order_index, "
        "c.first_name || ' ' || COALESCE(c.last_name,'') AS contact_name, co.name AS company_name "
        "FROM deals d JOIN stages s ON d.stage_id=s.id "
        "LEFT JOIN contacts c ON d.contact_id=c.id LEFT JOIN companies co ON d.company_id=co.id "
        "ORDER BY s.order_index, d.id DESC"
    )


@router.post("/deals")
def create_deal(payload: dict = Body(...)):
    stage_id = payload.get("stage_id")
    if not stage_id:
        first = db.query_one("SELECT id FROM stages ORDER BY order_index LIMIT 1")
        stage_id = first["id"] if first else 1
    did = db.execute(
        "INSERT INTO deals (name, value, stage_id, contact_id, company_id, close_date) VALUES (?, ?, ?, ?, ?, ?)",
        (
            payload.get("name", "").strip() or "Untitled deal",
            float(payload.get("value") or 0),
            stage_id,
            payload.get("contact_id"),
            payload.get("company_id"),
            payload.get("close_date"),
        ),
    )
    return {"id": did, "ok": True}


@router.patch("/deals/{deal_id}/stage")
def move_deal(deal_id: int, payload: dict = Body(...)):
    deal = db.query_one("SELECT * FROM deals WHERE id = ?", (deal_id,))
    if not deal:
        raise HTTPException(404, "Deal not found")
    stage = db.query_one("SELECT * FROM stages WHERE id = ?", (payload["stage_id"],))
    if not stage:
        raise HTTPException(400, "Stage not found")
    db.execute("UPDATE deals SET stage_id = ? WHERE id = ?", (payload["stage_id"], deal_id))
    engine.log_activity(
        "deal_stage_changed", "deal", deal_id, f"Deal #{deal_id} -> {stage['name']}"
    )
    engine.emit("deal_stage_changed", "deal", deal_id, context=stage["name"])
    return {"id": deal_id, "stage": stage["name"], "ok": True}


@router.delete("/deals/{deal_id}")
def delete_deal(deal_id: int):
    db.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    return {"id": deal_id, "ok": True}


# ---------------------------------------------------------------- campaigns
def _enroll_campaign(campaign_id: int, contact_id: int) -> bool:
    added = db.execute(
        "INSERT OR IGNORE INTO campaign_contacts (campaign_id, contact_id) VALUES (?, ?)",
        (campaign_id, contact_id),
    )
    return bool(added)


@router.get("/campaigns")
def list_campaigns():
    return db.query(
        "SELECT cam.*, (SELECT COUNT(*) FROM campaign_contacts cc WHERE cc.campaign_id=cam.id) AS enrolled, "
        "(SELECT COUNT(*) FROM campaign_contacts cc WHERE cc.campaign_id=cam.id AND cc.sent_at IS NOT NULL) AS sent "
        "FROM campaigns cam ORDER BY cam.id DESC"
    )


@router.post("/campaigns")
def create_campaign(payload: dict = Body(...)):
    cid = db.execute(
        "INSERT INTO campaigns (name, subject, body, status) VALUES (?, ?, ?, ?)",
        (
            payload.get("name", "").strip() or "Untitled campaign",
            payload.get("subject", ""),
            payload.get("body", ""),
            payload.get("status") or "Draft",
        ),
    )
    return {"id": cid, "ok": True}


@router.post("/campaigns/{campaign_id}/enroll")
def enroll_campaign(campaign_id: int, payload: dict = Body(...)):
    added = _enroll_campaign(campaign_id, payload["contact_id"])
    return {"enrolled": added, "ok": True}


@router.post("/campaigns/{campaign_id}/send")
def send_campaign(campaign_id: int):
    campaign = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    enrolled = db.query(
        "SELECT cc.id AS cc_id, c.* FROM campaign_contacts cc JOIN contacts c ON cc.contact_id=c.id "
        "WHERE cc.campaign_id = ? AND cc.sent_at IS NULL",
        (campaign_id,),
    )
    sent = 0
    for row in enrolled:
        body = campaign["body"] or ""
        mailer.send_email(
            row["email"] or "", campaign["subject"] or "", body,
            contact_id=row["id"], campaign_id=campaign_id,
        )
        db.execute("UPDATE campaign_contacts SET sent_at = datetime('now') WHERE id = ?", (row["cc_id"],))
        engine.log_activity("campaign_sent", "campaign", campaign_id, f"Sent '{campaign['name']}' to {row['email']}")
        engine.emit("campaign_sent", "contact", row["id"], context=str(campaign_id))
        sent += 1
    if campaign["status"] == "Draft":
        db.execute("UPDATE campaigns SET status = 'Sent' WHERE id = ?", (campaign_id,))
    return {"sent": sent, "ok": True}


# ---------------------------------------------------------------- sequences
@router.get("/sequences")
def list_sequences():
    return db.query(
        "SELECT s.*, (SELECT COUNT(*) FROM sequence_steps ss WHERE ss.sequence_id=s.id) AS steps, "
        "(SELECT COUNT(*) FROM sequence_enrollments se WHERE se.sequence_id=s.id AND se.status='Active') AS active "
        "FROM sequences s ORDER BY s.id DESC"
    )


@router.get("/sequences/{sequence_id}")
def get_sequence(sequence_id: int):
    seq = db.query_one("SELECT * FROM sequences WHERE id = ?", (sequence_id,))
    if not seq:
        raise HTTPException(404, "Sequence not found")
    seq["steps"] = db.query(
        "SELECT * FROM sequence_steps WHERE sequence_id = ? ORDER BY step_order", (sequence_id,)
    )
    seq["enrollments"] = db.query(
        "SELECT se.*, c.first_name || ' ' || COALESCE(c.last_name,'') AS contact_name, c.email "
        "FROM sequence_enrollments se JOIN contacts c ON se.contact_id=c.id "
        "WHERE se.sequence_id = ? ORDER BY se.id DESC",
        (sequence_id,),
    )
    return seq


def _send_step(sequence_id: int, contact_id: int, step_num: int) -> bool:
    step = db.query_one(
        "SELECT * FROM sequence_steps WHERE sequence_id = ? AND step_order = ?", (sequence_id, step_num)
    )
    if not step:
        return False
    contact = _contact_or_404(contact_id)
    mailer.send_email(
        contact["email"] or "", step["subject"] or "", step["body"] or "",
        contact_id=contact_id,
    )
    engine.log_activity("sequence_step", "sequence", sequence_id, f"Step {step_num} -> {contact['email']}")
    return True


@router.post("/sequences")
def create_sequence(payload: dict = Body(...)):
    sid = db.execute("INSERT INTO sequences (name) VALUES (?)", (payload.get("name", "").strip() or "Untitled sequence",))
    for i, step in enumerate(payload.get("steps") or [], start=1):
        db.execute(
            "INSERT INTO sequence_steps (sequence_id, step_order, subject, body, delay_days) VALUES (?, ?, ?, ?, ?)",
            (sid, i, step.get("subject", ""), step.get("body", ""), int(step.get("delay_days") or 0)),
        )
    return {"id": sid, "ok": True}


@router.post("/sequences/{sequence_id}/enroll")
def enroll_sequence(sequence_id: int, payload: dict = Body(...)):
    contact_id = payload["contact_id"]
    exists = db.query_one(
        "SELECT id FROM sequence_enrollments WHERE sequence_id = ? AND contact_id = ?",
        (sequence_id, contact_id),
    )
    if exists:
        return {"ok": True, "already": True}
    db.execute(
        "INSERT INTO sequence_enrollments (sequence_id, contact_id, current_step, status) VALUES (?, ?, 1, 'Active')",
        (sequence_id, contact_id),
    )
    total = db.query_one("SELECT COUNT(*) c FROM sequence_steps WHERE sequence_id = ?", (sequence_id,))["c"]
    _send_step(sequence_id, contact_id, 1)
    if total <= 1:
        db.execute(
            "UPDATE sequence_enrollments SET status='Completed' WHERE sequence_id = ? AND contact_id = ?",
            (sequence_id, contact_id),
        )
    return {"ok": True, "total_steps": total}


@router.post("/sequences/{sequence_id}/advance")
def advance_sequence(sequence_id: int):
    """Simulate the next day: send the next step for every active enrollment."""
    enrollments = db.query(
        "SELECT * FROM sequence_enrollments WHERE sequence_id = ? AND status = 'Active'", (sequence_id,)
    )
    total = db.query_one("SELECT COUNT(*) c FROM sequence_steps WHERE sequence_id = ?", (sequence_id,))["c"]
    progressed = 0
    for enr in enrollments:
        nxt = enr["current_step"] + 1
        if nxt > total:
            db.execute("UPDATE sequence_enrollments SET status='Completed' WHERE id = ?", (enr["id"],))
            continue
        if _send_step(sequence_id, enr["contact_id"], nxt):
            db.execute("UPDATE sequence_enrollments SET current_step = ? WHERE id = ?", (nxt, enr["id"]))
            progressed += 1
    return {"progressed": progressed, "ok": True}


# ---------------------------------------------------------------- forms
@router.get("/forms")
def list_forms():
    return db.query(
        "SELECT f.*, (SELECT COUNT(*) FROM form_submissions fs WHERE fs.form_id=f.id) AS submissions "
        "FROM forms f ORDER BY f.id DESC"
    )


@router.post("/forms")
def create_form(payload: dict = Body(...)):
    slug = _unique_slug("forms", _slugify(payload.get("name", "")))
    fid = db.execute(
        "INSERT INTO forms (name, slug, fields_json, redirect_url, submit_label) VALUES (?, ?, ?, ?, ?)",
        (
            payload.get("name", "").strip() or "Untitled form",
            slug,
            _json_dumps(payload.get("fields") or []),
            payload.get("redirect_url"),
            payload.get("submit_label") or "Submit",
        ),
    )
    return {"id": fid, "slug": slug, "ok": True}


@router.get("/forms/{form_id}")
def get_form(form_id: int):
    f = db.query_one("SELECT * FROM forms WHERE id = ?", (form_id,))
    if not f:
        raise HTTPException(404, "Form not found")
    f["fields"] = json.loads(f["fields_json"])
    f["submissions"] = db.query(
        "SELECT * FROM form_submissions WHERE form_id = ? ORDER BY id DESC LIMIT 25", (form_id,)
    )
    for s in f["submissions"]:
        s["data"] = json.loads(s["data_json"])
    return f


@router.post("/forms/{form_id}/submit")
def submit_form(form_id: int, payload: dict = Body(...)):
    """Public form submission: record it, upsert a contact, fire automation."""
    f = db.query_one("SELECT * FROM forms WHERE id = ?", (form_id,))
    if not f:
        raise HTTPException(404, "Form not found")
    data = payload.get("data") or {}
    sid = db.execute(
        "INSERT INTO form_submissions (form_id, data_json) VALUES (?, ?)",
        (form_id, _json_dumps(data)),
    )
    engine.log_activity("form_submitted", "submission", sid, f"Form '{f['name']}' submission")

    email = (data.get("email") or "").strip().lower()
    contact_id = None
    if email:
        existing = db.query_one("SELECT id FROM contacts WHERE email = ?", (email,))
        if existing:
            contact_id = existing["id"]
        else:
            contact_id = db.execute(
                "INSERT INTO contacts (first_name, last_name, email, lifecycle_stage) VALUES (?, ?, ?, 'Lead')",
                (data.get("first_name") or email.split("@")[0].title(), data.get("last_name") or "", email),
            )
            engine.log_activity("contact_created", "contact", contact_id, f"Created from form #{sid}")
            engine.emit("contact_created", "contact", contact_id)
        engine.emit("form_submitted", "submission", sid, context=f["slug"])
    return {"id": sid, "contact_id": contact_id, "ok": True}


@router.delete("/forms/{form_id}")
def delete_form(form_id: int):
    db.execute("DELETE FROM forms WHERE id = ?", (form_id,))
    return {"id": form_id, "ok": True}


# ---------------------------------------------------------------- landing pages
@router.get("/landing-pages")
def list_landing_pages():
    return db.query("SELECT * FROM landing_pages ORDER BY id DESC")


@router.post("/landing-pages")
def create_landing_page(payload: dict = Body(...)):
    slug = _unique_slug("landing_pages", _slugify(payload.get("title", "")))
    pid = db.execute(
        "INSERT INTO landing_pages (title, slug, html, published) VALUES (?, ?, ?, ?)",
        (
            payload.get("title", "").strip() or "Untitled page",
            slug,
            payload.get("html", ""),
            1 if payload.get("published") else 0,
        ),
    )
    return {"id": pid, "slug": slug, "ok": True}


@router.patch("/landing-pages/{page_id}")
def update_landing_page(page_id: int, payload: dict = Body(...)):
    fields = []
    params = []
    for key in ("title", "html", "slug"):
        if key in payload:
            fields.append(f"{key} = ?")
            params.append(payload[key])
    if "published" in payload:
        fields.append("published = ?")
        params.append(1 if payload["published"] else 0)
    if fields:
        params.append(page_id)
        db.execute(f"UPDATE landing_pages SET {', '.join(fields)} WHERE id = ?", tuple(params))
    return {"id": page_id, "ok": True}


@router.delete("/landing-pages/{page_id}")
def delete_landing_page(page_id: int):
    db.execute("DELETE FROM landing_pages WHERE id = ?", (page_id,))
    return {"id": page_id, "ok": True}


# ---------------------------------------------------------------- workflows
@router.get("/workflows")
def list_workflows():
    return db.query(
        "SELECT w.*, (SELECT COUNT(*) FROM workflow_runs wr WHERE wr.workflow_id=w.id) AS runs "
        "FROM workflows w ORDER BY w.id DESC"
    )


@router.post("/workflows")
def create_workflow(payload: dict = Body(...)):
    wid = db.execute(
        "INSERT INTO workflows (name, trigger_type, trigger_value, action_type, action_value, active) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            payload.get("name", "").strip() or "Untitled workflow",
            payload["trigger_type"],
            payload.get("trigger_value") or "",
            payload["action_type"],
            payload.get("action_value") or "",
            1 if payload.get("active", True) else 0,
        ),
    )
    return {"id": wid, "ok": True}


@router.patch("/workflows/{workflow_id}")
def toggle_workflow(workflow_id: int, payload: dict = Body(...)):
    if "active" in payload:
        db.execute("UPDATE workflows SET active = ? WHERE id = ?", (1 if payload["active"] else 0, workflow_id))
    return {"id": workflow_id, "ok": True}


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int):
    db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
    return {"id": workflow_id, "ok": True}


# ---------------------------------------------------------------- tasks / outbox / misc
@router.get("/tasks")
def list_tasks():
    return db.query(
        "SELECT t.*, c.first_name || ' ' || COALESCE(c.last_name,'') AS contact_name "
        "FROM tasks t LEFT JOIN contacts c ON t.contact_id=c.id ORDER BY t.done, t.id DESC"
    )


@router.post("/tasks")
def create_task(payload: dict = Body(...)):
    tid = db.execute(
        "INSERT INTO tasks (contact_id, title, due_date) VALUES (?, ?, ?)",
        (payload.get("contact_id"), payload.get("title", "Task"), payload.get("due_date")),
    )
    return {"id": tid, "ok": True}


@router.patch("/tasks/{task_id}/toggle")
def toggle_task(task_id: int):
    t = db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not t:
        raise HTTPException(404, "Task not found")
    db.execute("UPDATE tasks SET done = ? WHERE id = ?", (0 if t["done"] else 1, task_id))
    return {"id": task_id, "done": not t["done"], "ok": True}


@router.get("/outbox")
def outbox():
    return db.query("SELECT * FROM emails ORDER BY id DESC LIMIT 50")


@router.get("/activities")
def activities():
    return db.query("SELECT * FROM activities ORDER BY id DESC LIMIT 50")


@router.get("/options")
def options():
    return {
        "stages": db.query("SELECT * FROM stages ORDER BY order_index"),
        "companies": db.query("SELECT id, name FROM companies ORDER BY name"),
        "contacts": db.query("SELECT id, first_name, last_name, email FROM contacts ORDER BY id DESC"),
        "campaigns": db.query("SELECT id, name FROM campaigns ORDER BY name"),
        "sequences": db.query("SELECT id, name FROM sequences ORDER BY name"),
        "lifecycle": ["Lead", "Marketing Qualified", "Sales Qualified", "Customer", "Churned"],
    }
