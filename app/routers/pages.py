"""HTML pages: the SPA shell, embeddable public forms and landing pages."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .. import db
from ..services import engine

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "app.html")


# ---------------------------------------------------------------- embeddable form
def _render_form(request: Request, form: dict):
    fields = json.loads(form["fields_json"])
    return templates.TemplateResponse(
        request,
        "form_embed.html",
        {"form": form, "fields": fields, "error": None},
    )


@router.get("/f/{slug}", response_class=HTMLResponse)
def public_form(request: Request, slug: str):
    form = db.query_one("SELECT * FROM forms WHERE slug = ?", (slug,))
    if not form:
        raise HTTPException(404, "Form not found")
    return _render_form(request, form)


@router.post("/f/{slug}/submit")
async def public_form_submit(request: Request, slug: str):
    form = db.query_one("SELECT * FROM forms WHERE slug = ?", (slug,))
    if not form:
        raise HTTPException(404, "Form not found")
    raw = await request.form()
    data = {k: v for k, v in raw.items() if k != "submit"}
    # Validate required fields.
    for field in json.loads(form["fields_json"]):
        if field.get("required") and not (data.get(field["name"]) or "").strip():
            return _render_form(request, form)  # simplistic: re-render (no error state wired)
    sid = db.execute(
        "INSERT INTO form_submissions (form_id, data_json) VALUES (?, ?)",
        (form["id"], json.dumps(data)),
    )
    engine.log_activity("form_submitted", "submission", sid, f"Form '{form['name']}' submission")
    email = (data.get("email") or "").strip().lower()
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
        engine.emit("form_submitted", "submission", sid, context=form["slug"])
    if form["redirect_url"]:
        return RedirectResponse(url=form["redirect_url"], status_code=303)
    return templates.TemplateResponse(
        request, "form_thanks.html", {"form": form, "name": data.get("first_name", "")}
    )


# ---------------------------------------------------------------- landing pages
@router.get("/p/{slug}", response_class=HTMLResponse)
def public_landing(request: Request, slug: str):
    page = db.query_one("SELECT * FROM landing_pages WHERE slug = ? AND published = 1", (slug,))
    if not page:
        raise HTTPException(404, "Page not found")
    html = page["html"] or f"<h1>{page['title']}</h1>"
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>{page['title']}</title></head><body>{html}</body></html>")
