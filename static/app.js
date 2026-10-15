"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const STATUS_LABEL = {
  live: "Verified · API",
  manual: "Verified · manual",
  stale: "Stale",
  unavailable: "Unavailable",
  unverified: "Not verified",
  error: "Refresh failed",
};
let manualAgeHours = 24;
let state = { products: [], manualListing: null, ambiguous: null };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function inr(v) {
  return v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
function when(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) + " IST";
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.data = data;
    err.status = res.status;
    throw err;
  }
  return data;
}

function showMessage(el, text, isError = false) {
  el.hidden = !text;
  el.className = "message" + (isError ? " error" : "");
  el.innerHTML = text || "";
}

async function loadStatus() {
  const s = await api("/api/status");
  manualAgeHours = s.manual_max_age_hours;
  $("#sources").innerHTML = s.sources
    .map((x) => `<span class="source ${x.mode}" title="${esc(x.detail)}">${esc(x.name)}: ${x.mode === "api" ? "live API" : "manual verification"}</span>`)
    .join("");
}

async function loadProducts() {
  state.products = await api("/api/products");
  render();
}

function priceCell(l) {
  const current = l.status === "live" || l.status === "manual";
  const badge = `<span class="badge b-${l.status}">${STATUS_LABEL[l.status] || l.status}</span>`;
  const lowest = l.is_lowest ? ` <span class="badge b-lowest">Lowest</span>` : "";
  let meta = "";
  if (l.verified_at) meta = `${current ? "Verified" : "Last verified"} ${when(l.verified_at)}`;
  if (l.status === "error" && l.price != null) meta = `Last verified ${inr(l.price)} on ${when(l.verified_at)}`;
  if (l.status === "stale") meta = `Checked ${when(l.verified_at)} (older than ${manualAgeHours}h)`;
  const note = l.note ? `<div class="meta">${esc(l.note)}</div>` : "";
  const value = current ? `<span class="price">${inr(l.price)}</span>` : `<span class="price strike">—</span>`;
  return `${value}${lowest}<div class="meta">${badge} ${esc(meta)}</div>${note}`;
}

function rowActions(p, l) {
  const out = [];
  if (l.match_state === "suggested") {
    out.push(`<button class="btn btn-small" data-act="confirm" data-id="${l.id}">Confirm match</button>`);
  }
  const apiBacked = l.source === "Amazon Creators API" && (l.status === "live" || l.status === "unavailable");
  if (!apiBacked) {
    out.push(`<button class="btn btn-small" data-act="manual" data-id="${l.id}" data-pid="${p.id}">Enter price</button>`);
  }
  if (l.role !== "source") {
    out.push(`<button class="btn btn-small" data-act="remove" data-id="${l.id}" title="Not the same product">Remove</button>`);
  }
  return `<div class="row-actions">${out.join("")}</div>`;
}

function renderProduct(p) {
  const rows = p.listings
    .map((l) => {
      const cls = [l.is_lowest ? "lowest" : "", l.match_state === "suggested" ? "suggested" : ""].join(" ");
      const matchInfo =
        l.role === "source"
          ? ""
          : `<div class="meta">${l.match_state === "suggested" ? '<span class="badge b-suggested">Suggested match</span> ' : "Matched "}${
              l.match_score != null ? `score ${l.match_score}%` : ""
            }${l.match_reasons.length ? " · " + esc(l.match_reasons.join(", ")) : ""}</div>`;
      return `<tr class="${cls}">
        <td>${l.title ? esc(l.title) : '<span class="muted">Name not verified yet</span>'}${l.variant ? `<div class="meta">${esc(l.variant)}</div>` : ""}${matchInfo}</td>
        <td>${esc(l.platform_name)}</td>
        <td><a class="link" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.platform_id)}</a><div class="meta">${esc(l.id_label)}</div></td>
        <td class="num">${l.status === "live" || l.status === "manual" ? inr(l.mrp) : "—"}</td>
        <td class="num">${priceCell(l)}</td>
        <td>${rowActions(p, l)}</td>
      </tr>`;
    })
    .join("");

  const missing = p.missing
    .map(
      (m) => `<div class="missing-row">
        <span class="plat">${esc(m.platform_name)}</span>
        ${m.search_url ? `<a class="link" href="${esc(m.search_url)}" target="_blank" rel="noopener">Search ↗</a>` : ""}
        ${m.can_search_api ? `<button class="btn btn-small" data-act="candidates" data-pid="${p.id}">Find via API</button>` : ""}
        <input placeholder="Paste the matching ${esc(m.platform_name)} URL or ${esc(m.id_label)}" data-platform="${m.platform}" data-pid="${p.id}">
        <button class="btn btn-small" data-act="add-listing" data-platform="${m.platform}" data-pid="${p.id}">Add</button>
      </div>`
    )
    .join("");

  const summary =
    p.verified_count > 1
      ? `Lowest verified price ${inr(p.lowest_price)} across ${p.verified_count} platforms`
      : p.verified_count === 1
      ? "Only one verified price so far"
      : "No verified prices yet";

  return `<section class="card" data-pid="${p.id}">
    <div class="product-head">
      <div>
        <div class="name">${p.name ? esc(p.name) : "Unnamed product (enter details to verify)"}</div>
        <div class="muted">${p.brand ? esc(p.brand) + " · " : ""}${summary}</div>
      </div>
      <div class="row-actions">
        <button class="btn btn-small" data-act="refresh" data-pid="${p.id}">Refresh</button>
        <button class="btn btn-small" data-act="delete" data-pid="${p.id}">Delete</button>
      </div>
    </div>
    <div class="table-scroll"><table>
      <thead><tr><th>Product Name</th><th>Platform</th><th>Platform Product ID</th><th class="num">MRP</th><th class="num">Current Selling Price</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    ${missing ? `<div class="missing"><div class="muted">Find this product on the other platforms${p.search_query ? "" : " (enter the product name first to get search links)"}:</div>${missing}</div>` : ""}
    <div class="message" hidden data-msg="${p.id}"></div>
  </section>`;
}

function render() {
  $("#products").innerHTML = state.products.map(renderProduct).join("");
  $("#empty").hidden = state.products.length > 0;
}

function replaceProduct(p) {
  const i = state.products.findIndex((x) => x.id === p.id);
  if (i >= 0) state.products[i] = p;
  else state.products.unshift(p);
  render();
}

function productMessage(pid, text, isError) {
  const el = document.querySelector(`[data-msg="${pid}"]`);
  if (el) showMessage(el, esc(text), isError);
}

// ----- add product ------------------------------------------------------

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#add-message");
  const input = $("#add-input").value.trim();
  const platform = $("#add-platform").value;
  showMessage(msg, "Looking up…");
  try {
    const res = await api("/api/products", { method: "POST", body: { input, platform } });
    replaceProduct(res.product);
    showMessage(msg, res.created ? "" : "Already tracked. Showing the existing product.");
    $("#add-input").value = "";
    $("#add-platform").value = "";
  } catch (err) {
    if (err.status === 409 && err.data.candidates) {
      const buttons = err.data.candidates
        .map((c) => `<button class="btn btn-small" data-pick="${c.platform}">${esc(c.name)}</button>`)
        .join(" ");
      showMessage(msg, `${esc(err.message)} ${buttons}`);
    } else {
      showMessage(msg, esc(err.message), true);
    }
  }
});

$("#add-message").addEventListener("click", (e) => {
  const pick = e.target.dataset.pick;
  if (!pick) return;
  $("#add-platform").value = pick;
  $("#add-form").requestSubmit();
});

// ----- per-product actions ----------------------------------------------

$("#products").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const { act, id, pid, platform } = btn.dataset;
  btn.disabled = true;
  try {
    if (act === "refresh") {
      const res = await api(`/api/products/${pid}/refresh?force=1`, { method: "POST" });
      replaceProduct(res.product);
      const s = res.summary;
      const parts = [];
      if (s.checked) parts.push(`Checked ${s.checked} Amazon listing(s) via API.`);
      if (s.reason) parts.push(s.reason + ".");
      if (s.error) parts.push("Amazon API error: " + s.error);
      if (s.manual_listings) parts.push(`${s.manual_listings} listing(s) need a manual check; use Enter price.`);
      productMessage(pid, parts.join(" "), !!s.error);
    } else if (act === "delete") {
      if (!confirm("Stop tracking this product and delete its price history?")) return;
      await api(`/api/products/${pid}`, { method: "DELETE" });
      state.products = state.products.filter((p) => String(p.id) !== pid);
      render();
    } else if (act === "confirm") {
      await api(`/api/listings/${id}/confirm`, { method: "POST" });
      await loadProducts();
    } else if (act === "remove") {
      await api(`/api/listings/${id}`, { method: "DELETE" });
      await loadProducts();
    } else if (act === "manual") {
      openManual(Number(pid), Number(id));
    } else if (act === "add-listing") {
      const input = document.querySelector(`input[data-platform="${platform}"][data-pid="${pid}"]`).value.trim();
      if (!input) throw new Error("Paste a URL or ID first.");
      replaceProduct(await api(`/api/products/${pid}/listings`, { method: "POST", body: { input, platform } }));
    } else if (act === "candidates") {
      await openCandidates(Number(pid));
    }
  } catch (err) {
    productMessage(pid || btn.closest("[data-pid]")?.dataset.pid, err.message, true);
  } finally {
    btn.disabled = false;
  }
});

// ----- manual verification ----------------------------------------------

function openManual(pid, lid) {
  const p = state.products.find((x) => x.id === pid);
  const l = p.listings.find((x) => x.id === lid);
  state.manualListing = { pid, lid };
  const f = $("#manual-form");
  f.reset();
  f.elements.title.value = l.title || "";
  f.elements.brand.value = l.brand || "";
  f.elements.variant.value = l.variant || "";
  $("#manual-help").textContent = `${l.platform_name} · ${l.id_label} ${l.platform_id}. Open the product page, check the price shown to you right now, and enter it here. It will be saved with the current time.`;
  $("#manual-link").href = l.url;
  showMessage($("#manual-error"), "");
  $("#manual-dialog").showModal();
}

$("#manual-cancel").addEventListener("click", () => $("#manual-dialog").close());

$("#manual-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = {
    title: f.elements.title.value, brand: f.elements.brand.value, variant: f.elements.variant.value,
    mrp: f.elements.mrp.value, price: f.elements.price.value, available: !f.elements.unavailable.checked, note: f.elements.note.value,
  };
  try {
    replaceProduct(await api(`/api/listings/${state.manualListing.lid}/manual`, { method: "POST", body }));
    $("#manual-dialog").close();
  } catch (err) {
    showMessage($("#manual-error"), esc(err.message), true);
  }
});

// ----- Amazon candidates -------------------------------------------------

async function openCandidates(pid) {
  const list = $("#candidates-list");
  list.innerHTML = '<p class="muted">Searching Amazon India…</p>';
  $("#candidates-dialog").showModal();
  try {
    const items = await api(`/api/products/${pid}/amazon-candidates`);
    if (!items.length) {
      list.innerHTML = '<p class="muted">No results from the API.</p>';
      return;
    }
    list.innerHTML = items
      .map(
        (c) => `<div class="cand">
          <div>
            <div>${esc(c.title)}</div>
            <div class="meta">${esc(c.brand || "")} · ASIN ${esc(c.platform_id)} · ${c.price != null ? inr(c.price) : "no offer"} ${c.mrp ? "(MRP " + inr(c.mrp) + ")" : ""}</div>
            <div class="meta"><span class="badge ${c.match.confidence === "high" ? "b-live" : c.match.confidence === "medium" ? "b-stale" : "b-error"}">${c.match.score}% ${c.match.confidence}</span> ${esc(c.match.reasons.join(", "))}</div>
          </div>
          <button class="btn btn-small" data-use="${esc(c.platform_id)}">Use this</button>
        </div>`
      )
      .join("");
    list.onclick = async (e) => {
      const asin = e.target.dataset.use;
      if (!asin) return;
      replaceProduct(await api(`/api/products/${pid}/listings`, { method: "POST", body: { input: asin, platform: "amazon" } }));
      $("#candidates-dialog").close();
    };
  } catch (err) {
    list.innerHTML = `<div class="message error">${esc(err.message)}</div>`;
  }
}
$("#candidates-close").addEventListener("click", () => $("#candidates-dialog").close());

// ----- global -----------------------------------------------------------

$("#refresh-all").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  try {
    const { summary } = await api("/api/refresh", { method: "POST" });
    await loadProducts();
    const parts = [];
    if (summary.checked) parts.push(`Checked ${summary.checked} Amazon listing(s) via API.`);
    if (summary.reason) parts.push(summary.reason + ".");
    if (summary.error) parts.push("Amazon API error: " + esc(summary.error));
    if (summary.manual_listings) parts.push(`${summary.manual_listings} Myntra/Nykaa/Tata CLiQ listing(s) are verified manually and were not changed.`);
    showMessage($("#add-message"), parts.join(" "), !!summary.error);
  } catch (err) {
    showMessage($("#add-message"), esc(err.message), true);
  } finally {
    btn.disabled = false;
  }
});

loadStatus();
loadProducts();
