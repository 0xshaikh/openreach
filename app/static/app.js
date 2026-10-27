/* OpenReach SPA — vanilla JS, no build step, no dependencies. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

let OPTIONS = { stages: [], companies: [], contacts: [], campaigns: [], sequences: [], lifecycle: [] };

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

async function loadOptions() {
  OPTIONS = await api("/options");
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

function modal(html, { onMount } = {}) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-backdrop"><div class="modal">${html}</div></div>`;
  const close = () => (root.innerHTML = "");
  $(".modal-backdrop", root).addEventListener("click", (e) => { if (e.target === $(".modal-backdrop", root)) close(); });
  $$(".x", root).forEach((b) => (b.onclick = close));
  if (onMount) onMount(root, close);
  return { close, root };
}

function modalFoot(close, onSave) {
  return `<div class="modal-foot">
    <button class="btn" id="m-cancel">Cancel</button>
    <button class="btn btn-primary" id="m-save">Save</button>
  </div>`;
}

/* ================================================================ ROUTER */
const VIEWS = {};
function navigate(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  const meta = VIEWS[view];
  $("#view-title").textContent = meta.title;
  $("#topbar-actions").innerHTML = meta.action ? meta.action() : "";
  $("#content").innerHTML = `<div class="empty">Loading…</div>`;
  meta.render();
}

document.addEventListener("click", (e) => {
  const item = e.target.closest(".nav-item");
  if (item) navigate(item.dataset.view);
});

/* ================================================================ DASHBOARD */
VIEWS.dashboard = {
  title: "Dashboard",
  async render() {
    const d = await api("/dashboard");
    const c = d.counts;
    $("#content").innerHTML = `
      <div class="stats">
        <div class="stat"><div class="k">Contacts</div><div class="v">${c.contacts}</div></div>
        <div class="stat"><div class="k">Companies</div><div class="v">${c.companies}</div></div>
        <div class="stat"><div class="k">Open deals</div><div class="v">${c.open_deals}</div></div>
        <div class="stat"><div class="k">Pipeline value</div><div class="v money">${money(c.pipeline_value)}</div></div>
        <div class="stat"><div class="k">Emails sent</div><div class="v">${c.emails_sent}</div></div>
        <div class="stat"><div class="k">Form submissions</div><div class="v">${c.submissions}</div></div>
        <div class="stat"><div class="k">Active workflows</div><div class="v">${c.workflows}</div></div>
      </div>
      <div class="form-row" style="grid-template-columns: 1fr 1fr; align-items:start;">
        <div class="card">
          <div class="card-head"><h3>Recent contacts</h3></div>
          <div class="card-body tight"><table>
            <thead><tr><th>Name</th><th>Email</th><th>Company</th><th>Stage</th></tr></thead>
            <tbody>${d.recent_contacts.map((r) => `
              <tr><td><strong>${esc(r.first_name)} ${esc(r.last_name || "")}</strong></td>
              <td class="muted">${esc(r.email || "")}</td>
              <td>${esc(r.company_name || "—")}</td>
              <td><span class="tag">${esc(r.lifecycle_stage)}</span></td></tr>`).join("") || `<tr><td colspan="4" class="empty">No contacts yet</td></tr>`}
            </tbody></table></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>Activity feed</h3></div>
          <div class="card-body"><ul class="activity-list">
            ${d.activities.map((a) => `<li><div>${esc(a.detail || a.type)}</div><div class="at">${esc(a.created_at)}</div></li>`).join("") || `<li class="muted">No activity yet</li>`}
          </ul></div>
        </div>
      </div>`;
  },
};

/* ================================================================ CONTACTS */
function contactForm(c = {}) {
  const coOpts = OPTIONS.companies.map((x) => `<option value="${x.id}" ${x.id === c.company_id ? "selected" : ""}>${esc(x.name)}</option>`).join("");
  const stOpts = OPTIONS.lifecycle.map((s) => `<option ${s === (c.lifecycle_stage || "Lead") ? "selected" : ""}>${esc(s)}</option>`).join("");
  return `
    <div class="modal-head"><h3>${c.id ? "Edit contact" : "New contact"}</h3><button class="x">×</button></div>
    <div class="modal-body">
      <div class="form-row">
        <label class="field"><span class="field-label">First name</span><input class="input" id="c-first" value="${esc(c.first_name || "")}"></label>
        <label class="field"><span class="field-label">Last name</span><input class="input" id="c-last" value="${esc(c.last_name || "")}"></label>
      </div>
      <div class="form-row">
        <label class="field"><span class="field-label">Email</span><input class="input" id="c-email" type="email" value="${esc(c.email || "")}"></label>
        <label class="field"><span class="field-label">Phone</span><input class="input" id="c-phone" value="${esc(c.phone || "")}"></label>
      </div>
      <div class="form-row">
        <label class="field"><span class="field-label">Job title</span><input class="input" id="c-title" value="${esc(c.job_title || "")}"></label>
        <label class="field"><span class="field-label">Company</span><select class="input" id="c-company"><option value="">—</option>${coOpts}</select></label>
      </div>
      <label class="field"><span class="field-label">Lifecycle stage</span><select class="input" id="c-stage">${stOpts}</select></label>
      <label class="field"><span class="field-label">Website</span><input class="input" id="c-web" value="${esc(c.website || "")}"></label>
    </div>
    ${modalFoot()}
  `;
}

VIEWS.contacts = {
  title: "Contacts",
  action: () => `<button class="btn btn-primary" id="add-contact">+ New contact</button>`,
  async render() {
    const rows = await api("/contacts");
    $("#content").innerHTML = `
      <div class="toolbar"><input class="input search" id="c-search" placeholder="Search name or email…"></div>
      <div class="card"><div class="card-body tight"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Company</th><th>Stage</th><th>Created</th><th></th></tr></thead>
        <tbody id="c-rows">${rowHtml(rows)}</tbody></table></div></div>`;
    const search = $("#c-search");
    search.oninput = () => {
      const q = search.value.toLowerCase();
      $$("#c-rows tr").forEach((tr) => (tr.style.display = tr.dataset.search.includes(q) ? "" : "none"));
    };
    $("#add-contact").onclick = () => modal(contactForm(), {
      onMount: (root, close) => {
        $("#m-save", root).onclick = async () => {
          const body = {
            first_name: $("#c-first", root).value, last_name: $("#c-last", root).value,
            email: $("#c-email", root).value, phone: $("#c-phone", root).value,
            job_title: $("#c-title", root).value, company_id: Number($("#c-company", root).value) || null,
            lifecycle_stage: $("#c-stage", root).value, website: $("#c-web", root).value,
          };
          try { await api("/contacts", { method: "POST", body }); close(); toast("Contact created"); loadOptions().then(() => navigate("contacts")); }
          catch (e) { toast(e.message); }
        };
        $("#m-cancel", root).onclick = close;
      },
    });
  },
};
function rowHtml(rows) {
  return rows.map((r) => `
    <tr data-search="${esc((r.first_name + " " + (r.last_name || "") + " " + (r.email || "")).toLowerCase())}">
      <td><strong>${esc(r.first_name)} ${esc(r.last_name || "")}</strong></td>
      <td class="muted">${esc(r.email || "—")}</td>
      <td>${esc(r.company_name || "—")}</td>
      <td><span class="tag">${esc(r.lifecycle_stage)}</span></td>
      <td class="muted">${esc((r.created_at || "").slice(0, 10))}</td>
      <td><button class="btn btn-sm" data-contact="${r.id}" data-act="open">Open</button></td>
    </tr>`).join("");
}

/* ================================================================ COMPANIES */
VIEWS.companies = {
  title: "Companies",
  action: () => `<button class="btn btn-primary" id="add-company">+ New company</button>`,
  async render() {
    const rows = await api("/companies");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Name</th><th>Domain</th><th>Industry</th><th>City</th><th>Size</th><th>Contacts</th><th>Deals</th></tr></thead>
      <tbody>${rows.map((r) => `
        <tr><td><strong>${esc(r.name)}</strong></td><td class="muted">${esc(r.domain || "—")}</td>
        <td>${esc(r.industry || "—")}</td><td>${esc(r.city || "—")}</td><td>${esc(r.size || "—")}</td>
        <td>${r.contact_count}</td><td>${r.deal_count}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No companies yet</td></tr>`}
      </tbody></table></div></div>`;
    $("#add-company").onclick = () => modal(`
      <div class="modal-head"><h3>New company</h3><button class="x">×</button></div>
      <div class="modal-body">
        <label class="field"><span class="field-label">Name</span><input class="input" id="co-name"></label>
        <div class="form-row">
          <label class="field"><span class="field-label">Domain</span><input class="input" id="co-domain"></label>
          <label class="field"><span class="field-label">Industry</span><input class="input" id="co-industry"></label>
        </div>
        <div class="form-row">
          <label class="field"><span class="field-label">City</span><input class="input" id="co-city"></label>
          <label class="field"><span class="field-label">Size</span><select class="input" id="co-size">
            <option>1-10</option><option>11-50</option><option>51-200</option><option>201-1000</option><option>1000+</option>
          </select></label>
        </div>
      </div>${modalFoot()}`,
      { onMount: (root, close) => {
        $("#m-save", root).onclick = async () => {
          await api("/companies", { method: "POST", body: {
            name: $("#co-name", root).value, domain: $("#co-domain", root).value,
            industry: $("#co-industry", root).value, city: $("#co-city", root).value, size: $("#co-size", root).value } });
          close(); toast("Company created"); loadOptions().then(() => navigate("companies"));
        };
        $("#m-cancel", root).onclick = close;
      } });
  },
};

/* ================================================================ DEALS (kanban) */
VIEWS.deals = {
  title: "Deals Pipeline",
  action: () => `<button class="btn btn-primary" id="add-deal">+ New deal</button>`,
  async render() {
    const [stages, deals] = await Promise.all([api("/stages"), api("/deals")]);
    const byStage = {};
    stages.forEach((s) => (byStage[s.id] = []));
    deals.forEach((d) => (byStage[d.stage_id] = byStage[d.stage_id] || []).push(d));
    $("#content").innerHTML = `<div class="kanban">
      ${stages.map((s) => `
        <div class="kanban-col" data-stage="${s.id}">
          <div class="kanban-head"><div><span class="dot" style="background:${s.color}"></span><strong>${esc(s.name)}</strong></div>
          <span class="kanban-count">${byStage[s.id].length}</span></div>
          <div class="kanban-drop">${byStage[s.id].map((d) => `
            <div class="deal-card" draggable="true" data-deal="${d.id}">
              <div class="dc-name">${esc(d.name)}</div>
              <div class="dc-val">${money(d.value)}</div>
              <div class="dc-sub">${esc(d.contact_name || d.company_name || "")}</div>
            </div>`).join("")}</div>
        </div>`).join("")}
    </div>`;

    // drag & drop
    let dragId = null;
    $$(".deal-card").forEach((el) => {
      el.addEventListener("dragstart", () => { dragId = el.dataset.deal; el.style.opacity = .5; });
      el.addEventListener("dragend", () => { el.style.opacity = 1; $$(".kanban-col").forEach((c) => c.classList.remove("drag-over")); });
    });
    $$(".kanban-col").forEach((col) => {
      col.addEventListener("dragover", (e) => { e.preventDefault(); col.classList.add("drag-over"); });
      col.addEventListener("dragleave", () => col.classList.remove("drag-over"));
      col.addEventListener("drop", async (e) => {
        e.preventDefault(); col.classList.remove("drag-over");
        if (!dragId) return;
        try {
          await api(`/deals/${dragId}/stage`, { method: "PATCH", body: { stage_id: Number(col.dataset.stage) } });
          toast("Deal moved"); navigate("deals");
        } catch (err) { toast(err.message); }
      });
    });

    $("#add-deal").onclick = () => {
      const coOpts = OPTIONS.companies.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join("");
      const ctOpts = OPTIONS.contacts.map((x) => `<option value="${x.id}">${esc(x.first_name)} ${esc(x.last_name || "")}</option>`).join("");
      const stOpts = stages.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
      modal(`
        <div class="modal-head"><h3>New deal</h3><button class="x">×</button></div>
        <div class="modal-body">
          <label class="field"><span class="field-label">Deal name</span><input class="input" id="d-name"></label>
          <div class="form-row">
            <label class="field"><span class="field-label">Value ($)</span><input class="input" id="d-value" type="number"></label>
            <label class="field"><span class="field-label">Stage</span><select class="input" id="d-stage">${stOpts}</select></label>
          </div>
          <div class="form-row">
            <label class="field"><span class="field-label">Contact</span><select class="input" id="d-contact"><option value="">—</option>${ctOpts}</select></label>
            <label class="field"><span class="field-label">Company</span><select class="input" id="d-company"><option value="">—</option>${coOpts}</select></label>
          </div>
          <label class="field"><span class="field-label">Close date</span><input class="input" id="d-close" type="date"></label>
        </div>${modalFoot()}`,
        { onMount: (root, close) => {
          $("#m-save", root).onclick = async () => {
            await api("/deals", { method: "POST", body: {
              name: $("#d-name", root).value, value: Number($("#d-value", root).value) || 0,
              stage_id: Number($("#d-stage", root).value), contact_id: Number($("#d-contact", root).value) || null,
              company_id: Number($("#d-company", root).value) || null, close_date: $("#d-close", root).value } });
            close(); toast("Deal created"); navigate("deals");
          };
          $("#m-cancel", root).onclick = close;
        } });
    };
  },
};

/* ================================================================ CAMPAIGNS */
VIEWS.campaigns = {
  title: "Campaigns",
  action: () => `<button class="btn btn-primary" id="add-campaign">+ New campaign</button>`,
  async render() {
    const [campaigns, contacts] = await Promise.all([api("/campaigns"), api("/contacts")]);
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Name</th><th>Status</th><th>Enrolled</th><th>Sent</th><th>Created</th><th></th></tr></thead>
      <tbody>${campaigns.map((c) => `
        <tr><td><strong>${esc(c.name)}</strong></td>
        <td><span class="tag">${esc(c.status)}</span></td><td>${c.enrolled}</td><td>${c.sent}</td>
        <td class="muted">${esc((c.created_at || "").slice(0, 10))}</td>
        <td><button class="btn btn-sm" data-camp="${c.id}" data-act="enroll">Enroll</button>
            <button class="btn btn-sm btn-primary" data-camp="${c.id}" data-act="send">Send</button></td></tr>`).join("") || `<tr><td colspan="6" class="empty">No campaigns yet</td></tr>`}
      </tbody></table></div></div>`;

    $("#add-campaign").onclick = () => modal(`
      <div class="modal-head"><h3>New campaign</h3><button class="x">×</button></div>
      <div class="modal-body">
        <label class="field"><span class="field-label">Name</span><input class="input" id="camp-name"></label>
        <label class="field"><span class="field-label">Subject</span><input class="input" id="camp-subject"></label>
        <label class="field"><span class="field-label">Body</span><textarea class="input" id="camp-body" rows="5"></textarea></label>
      </div>${modalFoot()}`,
      { onMount: (root, close) => {
        $("#m-save", root).onclick = async () => {
          await api("/campaigns", { method: "POST", body: {
            name: $("#camp-name", root).value, subject: $("#camp-subject", root).value, body: $("#camp-body", root).value } });
          close(); toast("Campaign created"); loadOptions().then(() => navigate("campaigns"));
        };
        $("#m-cancel", root).onclick = close;
      } });

    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      const cid = b.dataset.camp;
      if (b.dataset.act === "send") {
        const r = await api(`/campaigns/${cid}/send`, { method: "POST" });
        toast(`Sent to ${r.sent} contact${r.sent === 1 ? "" : "s"}`); navigate("campaigns");
      } else {
        const ctOpts = contacts.map((x) => `<option value="${x.id}">${esc(x.first_name)} ${esc(x.last_name || "")} (${esc(x.email || "")})</option>`).join("");
        modal(`
          <div class="modal-head"><h3>Enroll contact</h3><button class="x">×</button></div>
          <div class="modal-body"><label class="field"><span class="field-label">Contact</span><select class="input" id="e-contact">${ctOpts}</select></label></div>
          ${modalFoot()}`,
          { onMount: (root, close) => {
            $("#m-save", root).onclick = async () => {
              await api(`/campaigns/${cid}/enroll`, { method: "POST", body: { contact_id: Number($("#e-contact", root).value) } });
              close(); toast("Enrolled"); navigate("campaigns");
            };
            $("#m-cancel", root).onclick = close;
          } });
      }
    }));
  },
};

/* ================================================================ SEQUENCES */
VIEWS.sequences = {
  title: "Sequences",
  action: () => `<button class="btn btn-primary" id="add-seq">+ New sequence</button>`,
  async render() {
    const [seqs, contacts] = await Promise.all([api("/sequences"), api("/contacts")]);
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Name</th><th>Steps</th><th>Active</th><th></th></tr></thead>
      <tbody>${seqs.map((s) => `
        <tr><td><strong>${esc(s.name)}</strong></td><td>${s.steps}</td><td>${s.active}</td>
        <td><button class="btn btn-sm" data-seq="${s.id}" data-act="enroll">Enroll</button>
            <button class="btn btn-sm" data-seq="${s.id}" data-act="advance">Advance day</button></td></tr>`).join("") || `<tr><td colspan="4" class="empty">No sequences yet</td></tr>`}
      </tbody></table></div></div>`;

    $("#add-seq").onclick = () => modal(`
      <div class="modal-head"><h3>New sequence</h3><button class="x">×</button></div>
      <div class="modal-body">
        <label class="field"><span class="field-label">Name</span><input class="input" id="s-name"></label>
        <div id="s-steps">
          ${[1, 2, 3].map((n) => `
          <div class="card" style="padding:12px;margin-bottom:10px;">
            <div class="field-label">Step ${n}</div>
            <label class="field" style="margin-top:6px"><input class="input s-subj" placeholder="Subject (day ${n})" value="Step ${n} follow-up"></label>
            <label class="field"><textarea class="input s-body" rows="2" placeholder="Body">This is follow-up ${n}.</textarea></label>
          </div>`).join("")}
        </div>
      </div>${modalFoot()}`,
      { onMount: (root, close) => {
        $("#m-save", root).onclick = async () => {
          const steps = $$(".s-subj", root).map((el, i) => ({
            subject: el.value, body: $$(".s-body", root)[i].value, delay_days: 1 }));
          await api("/sequences", { method: "POST", body: { name: $("#s-name", root).value, steps } });
          close(); toast("Sequence created"); loadOptions().then(() => navigate("sequences"));
        };
        $("#m-cancel", root).onclick = close;
      } });

    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      const sid = b.dataset.seq;
      if (b.dataset.act === "advance") {
        const r = await api(`/sequences/${sid}/advance`, { method: "POST" });
        toast(`Advanced: ${r.progressed} email${r.progressed === 1 ? "" : "s"} sent`); navigate("sequences");
      } else {
        const ctOpts = contacts.map((x) => `<option value="${x.id}">${esc(x.first_name)} ${esc(x.last_name || "")} (${esc(x.email || "")})</option>`).join("");
        modal(`
          <div class="modal-head"><h3>Enroll contact</h3><button class="x">×</button></div>
          <div class="modal-body"><label class="field"><span class="field-label">Contact</span><select class="input" id="e-contact">${ctOpts}</select></label></div>
          ${modalFoot()}`,
          { onMount: (root, close) => {
            $("#m-save", root).onclick = async () => {
              await api(`/sequences/${sid}/enroll`, { method: "POST", body: { contact_id: Number($("#e-contact", root).value) } });
              close(); toast("Enrolled — step 1 sent"); navigate("sequences");
            };
            $("#m-cancel", root).onclick = close;
          } });
      }
    }));
  },
};

/* ================================================================ FORMS */
VIEWS.forms = {
  title: "Web Forms",
  action: () => `<button class="btn btn-primary" id="add-form">+ New form</button>`,
  async render() {
    const forms = await api("/forms");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Name</th><th>Slug</th><th>Submissions</th><th>Created</th><th></th></tr></thead>
      <tbody>${forms.map((f) => `
        <tr><td><strong>${esc(f.name)}</strong></td><td class="muted">${esc(f.slug)}</td><td>${f.submissions}</td>
        <td class="muted">${esc((f.created_at || "").slice(0, 10))}</td>
        <td><a class="btn btn-sm" href="/f/${esc(f.slug)}" target="_blank">Open</a>
            <button class="btn btn-sm" data-form="${f.id}" data-act="embed">Embed</button>
            <button class="btn btn-sm" data-form="${f.id}" data-act="subs">Submissions</button></td></tr>`).join("") || `<tr><td colspan="5" class="empty">No forms yet</td></tr>`}
      </tbody></table></div></div>`;

    $("#add-form").onclick = () => modal(`
      <div class="modal-head"><h3>New form</h3><button class="x">×</button></div>
      <div class="modal-body">
        <label class="field"><span class="field-label">Form name</span><input class="input" id="f-name" placeholder="e.g. Newsletter signup"></label>
        <div class="field-label">Fields</div>
        <div id="f-fields">
          <div class="form-row" style="margin-bottom:8px">
            <input class="input f-label" placeholder="Field label" value="Email">
            <input class="input f-type" placeholder="type" value="email">
          </div>
        </div>
        <button class="btn btn-sm" id="f-addfield">+ Add field</button>
        <label class="field" style="margin-top:12px"><span class="field-label">Submit label</span><input class="input" id="f-submit" value="Sign up"></label>
        <label class="field"><span class="field-label">Redirect URL (optional)</span><input class="input" id="f-redirect"></label>
      </div>${modalFoot()}`,
      { onMount: (root, close) => {
        $("#f-addfield", root).onclick = () => {
          const row = document.createElement("div");
          row.className = "form-row"; row.style.marginBottom = "8px";
          row.innerHTML = `<input class="input f-label" placeholder="Field label"><input class="input f-type" placeholder="type" value="text">`;
          $("#f-fields", root).append(row);
        };
        $("#m-save", root).onclick = async () => {
          const fields = $$("#f-fields .form-row", root).map((r) => ({
            label: $(".f-label", r).value || "Field", name: ($(".f-label", r).value || "field").toLowerCase().replace(/\s+/g, "_"),
            type: $(".f-type", r).value || "text", required: true }));
          const r = await api("/forms", { method: "POST", body: {
            name: $("#f-name", root).value, fields, submit_label: $("#f-submit", root).value,
            redirect_url: $("#f-redirect", root).value } });
          close(); toast(`Form created at /f/${r.slug}`); loadOptions().then(() => navigate("forms"));
        };
        $("#m-cancel", root).onclick = close;
      } });

    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      const fid = b.dataset.form;
      if (b.dataset.act === "embed") {
        navigator.clipboard?.writeText(`<iframe src="http://${location.host}/f/... "></iframe>`);
        toast(`Embed: <iframe src="${location.origin}/f/…" width="440" height="480"></iframe>`);
      } else {
        const f = await api(`/forms/${fid}`);
        modal(`
          <div class="modal-head"><h3>Submissions — ${esc(f.name)}</h3><button class="x">×</button></div>
          <div class="modal-body">${f.submissions.map((s) => `
            <div class="card" style="padding:10px;margin-bottom:8px">
              <div class="muted" style="font-size:12px">${esc(s.created_at)}</div>
              <div>${Object.entries(s.data || {}).map(([k, v]) => `<span class="tag">${esc(k)}: ${esc(v)}</span>`).join(" ")}</div>
            </div>`).join("") || `<div class="empty">No submissions yet</div>`}</div>`,
          { onMount: (root) => { $(".x", root).onclick = () => (root.remove()); } });
      }
    }));
  },
};

/* ================================================================ LANDING PAGES */
VIEWS.landing = {
  title: "Landing Pages",
  action: () => `<button class="btn btn-primary" id="add-page">+ New page</button>`,
  async render() {
    const pages = await api("/landing-pages");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Title</th><th>Slug</th><th>Published</th><th></th></tr></thead>
      <tbody>${pages.map((p) => `
        <tr><td><strong>${esc(p.title)}</strong></td><td class="muted">${esc(p.slug)}</td>
        <td>${p.published ? '<span class="tag">Published</span>' : '<span class="muted">Draft</span>'}</td>
        <td><a class="btn btn-sm" href="/p/${esc(p.slug)}" target="_blank">View</a>
            <button class="btn btn-sm" data-page="${p.id}" data-pub="${p.published}" data-act="toggle">${p.published ? "Unpublish" : "Publish"}</button></td></tr>`).join("") || `<tr><td colspan="4" class="empty">No pages yet</td></tr>`}
      </tbody></table></div></div>`;

    $("#add-page").onclick = () => modal(`
      <div class="modal-head"><h3>New landing page</h3><button class="x">×</button></div>
      <div class="modal-body">
        <label class="field"><span class="field-label">Title</span><input class="input" id="lp-title" placeholder="e.g. Spring webinar signup"></label>
        <label class="field"><span class="field-label">HTML</span><textarea class="input" id="lp-html" rows="10">&lt;h1&gt;Welcome!&lt;/h1&gt;&lt;p&gt;Build your landing page here.&lt;/p&gt;</textarea></label>
      </div>${modalFoot()}`,
      { onMount: (root, close) => {
        $("#m-save", root).onclick = async () => {
          const r = await api("/landing-pages", { method: "POST", body: {
            title: $("#lp-title", root).value, html: $("#lp-html", root).value, published: true } });
          close(); toast(`Page at /p/${r.slug}`); navigate("landing");
        };
        $("#m-cancel", root).onclick = close;
      } });

    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      await api(`/landing-pages/${b.dataset.page}`, { method: "PATCH", body: { published: b.dataset.pub !== "1" } });
      navigate("landing");
    }));
  },
};

/* ================================================================ WORKFLOWS */
VIEWS.workflows = {
  title: "Marketing Automation",
  action: () => `<button class="btn btn-primary" id="add-wf">+ New workflow</button>`,
  async render() {
    const wfs = await api("/workflows");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Name</th><th>Trigger</th><th>Action</th><th>Runs</th><th>Status</th><th></th></tr></thead>
      <tbody>${wfs.map((w) => `
        <tr><td><strong>${esc(w.name)}</strong></td>
        <td class="muted">${esc(w.trigger_type)}${w.trigger_value ? " → " + esc(w.trigger_value) : ""}</td>
        <td class="muted">${esc(w.action_type)}${w.action_value ? " → " + esc(w.action_value) : ""}</td>
        <td>${w.runs}</td>
        <td>${w.active ? '<span class="tag">Active</span>' : '<span class="muted">Off</span>'}</td>
        <td><button class="btn btn-sm" data-wf="${w.id}" data-active="${w.active}" data-act="toggle">${w.active ? "Deactivate" : "Activate"}</button></td></tr>`).join("") || `<tr><td colspan="6" class="empty">No workflows yet</td></tr>`}
      </tbody></table></div></div>`;

    $("#add-wf").onclick = () => {
      const trigOpts = Object.entries({ contact_created: "Contact created", lifecycle_changed: "Lifecycle changes", form_submitted: "Form submitted", deal_stage_changed: "Deal stage changes", campaign_sent: "Campaign email sent" })
        .map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
      const actOpts = Object.entries({ send_email: "Send email", add_campaign: "Add to campaign", enroll_sequence: "Enroll in sequence", change_lifecycle: "Change lifecycle", create_task: "Create task" })
        .map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
      modal(`
        <div class="modal-head"><h3>New workflow</h3><button class="x">×</button></div>
        <div class="modal-body">
          <label class="field"><span class="field-label">Name</span><input class="input" id="w-name" placeholder="e.g. New lead welcome"></label>
          <div class="form-row">
            <label class="field"><span class="field-label">When</span><select class="input" id="w-trigger">${trigOpts}</select></label>
            <label class="field"><span class="field-label">Match value (optional)</span><input class="input" id="w-trigval" placeholder="stage / form slug"></label>
          </div>
          <div class="form-row">
            <label class="field"><span class="field-label">Then</span><select class="input" id="w-action">${actOpts}</select></label>
            <label class="field"><span class="field-label">Value (subject / id / stage)</span><input class="input" id="w-actval"></label>
          </div>
          <label class="field" style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" id="w-active" checked> <span>Active immediately</span></label>
        </div>${modalFoot()}`,
        { onMount: (root, close) => {
          $("#m-save", root).onclick = async () => {
            await api("/workflows", { method: "POST", body: {
              name: $("#w-name", root).value, trigger_type: $("#w-trigger", root).value,
              trigger_value: $("#w-trigval", root).value, action_type: $("#w-action", root).value,
              action_value: $("#w-actval", root).value, active: $("#w-active", root).checked } });
            close(); toast("Workflow created"); navigate("workflows");
          };
          $("#m-cancel", root).onclick = close;
        } });
    };

    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      await api(`/workflows/${b.dataset.wf}`, { method: "PATCH", body: { active: b.dataset.active !== "1" } });
      navigate("workflows");
    }));
  },
};

/* ================================================================ TASKS & OUTBOX */
VIEWS.tasks = {
  title: "Tasks",
  async render() {
    const tasks = await api("/tasks");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>Done</th><th>Task</th><th>Contact</th><th>Due</th></tr></thead>
      <tbody>${tasks.map((t) => `
        <tr style="${t.done ? "opacity:.5" : ""}">
          <td><input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""}></td>
          <td>${esc(t.title)}</td><td>${esc(t.contact_name || "—")}</td><td class="muted">${esc(t.due_date || "—")}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">No tasks</td></tr>`}
      </tbody></table></div></div>`;
    $$("[data-task]").forEach((c) => (c.onchange = async () => {
      await api(`/tasks/${c.dataset.task}/toggle`, { method: "PATCH" }); navigate("tasks");
    }));
  },
};

VIEWS.outbox = {
  title: "Email Outbox",
  async render() {
    const emails = await api("/outbox");
    $("#content").innerHTML = `<div class="card"><div class="card-body tight"><table>
      <thead><tr><th>To</th><th>Subject</th><th>Status</th><th>Sent</th></tr></thead>
      <tbody>${emails.map((e) => `
        <tr><td>${esc(e.to_email)}</td><td>${esc(e.subject || "")}</td>
        <td><span class="tag">${esc(e.status)}</span></td><td class="muted">${esc(e.created_at)}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">Outbox empty</td></tr>`}
      </tbody></table></div></div>`;
  },
};

/* ================================================================ BOOT */
document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();
  navigate("dashboard");
  // Contact row "Open" action (delegated)
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act='open']");
    if (!btn) return;
    const c = await api(`/contacts/${btn.dataset.contact}`);
    modal(`
      <div class="modal-head"><h3>${esc(c.first_name)} ${esc(c.last_name || "")}</h3><button class="x">×</button></div>
      <div class="modal-body">
        <div class="muted" style="margin-bottom:12px">${esc(c.email || "")} · ${esc(c.job_title || "")} · ${esc((c.company || {}).name || "No company")}</div>
        <div class="field-label">Emails</div>
        <ul class="activity-list">${(c.emails || []).map((em) => `<li><strong>${esc(em.subject || "")}</strong><div class="at">${esc(em.created_at)}</div></li>`).join("") || '<li class="muted">No emails</li>'}</ul>
        <div class="field-label" style="margin-top:12px">Tasks</div>
        <ul class="activity-list">${(c.tasks || []).map((t) => `<li>${t.done ? "✅" : "⬜"} ${esc(t.title)}</li>`).join("") || '<li class="muted">No tasks</li>'}</ul>
      </div>`);
  });
});
