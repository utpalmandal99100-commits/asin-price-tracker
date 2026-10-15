"""Tracking logic: add products, attach matches, verify and refresh prices."""

import json
from datetime import datetime, timezone

from . import amazon, config, matching
from .db import now
from .platforms import ID_LABELS, PLATFORMS, InputError, parse_input, product_url, search_url

PLATFORM_ORDER = list(PLATFORMS)
API_SOURCE = "Amazon Creators API"
MANUAL_SOURCE = "Manual check"


class NotFound(LookupError):
    pass


def _age_hours(ts):
    if not ts:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 3600


class Tracker:
    def __init__(self, conn, amazon_client=amazon):
        self.db = conn
        self.amazon = amazon_client

    # ----- reading -------------------------------------------------------

    def _listing_rows(self, product_id):
        return self.db.execute("SELECT * FROM listings WHERE product_id = ?", (product_id,)).fetchall()

    def _listing(self, listing_id):
        row = self.db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            raise NotFound("Listing not found.")
        return row

    def _reference(self, product_id):
        """Product identity used for matching: the source listing's details."""
        rows = sorted(self._listing_rows(product_id), key=lambda r: r["role"] != "source")
        for r in rows:
            if r["title"]:
                return {
                    "title": r["title"], "brand": r["brand"], "variant": r["variant"],
                    "eans": json.loads(r["eans"] or "[]"), "model": r["model"],
                }
        return None

    def display_status(self, row):
        status = row["status"]
        if status == "manual":
            age = _age_hours(row["verified_at"])
            if age is not None and age > config.manual_max_age_hours():
                return "stale"
        return status

    def serialize_listing(self, row):
        display = self.display_status(row)
        counts = (
            row["match_state"] == "confirmed"
            and display in ("live", "manual")
            and row["price"] is not None
        )
        return {
            "id": row["id"],
            "platform": row["platform"],
            "platform_name": PLATFORMS[row["platform"]],
            "id_label": ID_LABELS[row["platform"]],
            "platform_id": row["platform_id"],
            "url": row["url"] or product_url(row["platform"], row["platform_id"]),
            "title": row["title"],
            "brand": row["brand"],
            "variant": row["variant"],
            "mrp": row["mrp"],
            "price": row["price"],
            "currency": row["currency"],
            "status": display,
            "source": row["source"],
            "note": row["note"],
            "verified_at": row["verified_at"],
            "last_checked_at": row["last_checked_at"],
            "role": row["role"],
            "match_state": row["match_state"],
            "match_score": row["match_score"],
            "match_reasons": json.loads(row["match_reasons"] or "[]"),
            "counts_for_lowest": counts,
            "is_lowest": False,
        }

    def get_product(self, product_id):
        prod = self.db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not prod:
            raise NotFound("Product not found.")
        listings = [self.serialize_listing(r) for r in self._listing_rows(product_id)]
        listings.sort(key=lambda l: (l["role"] != "source", PLATFORM_ORDER.index(l["platform"])))
        eligible = [l["price"] for l in listings if l["counts_for_lowest"]]
        lowest = min(eligible) if eligible else None
        for l in listings:
            l["is_lowest"] = l["counts_for_lowest"] and lowest is not None and len(eligible) > 1 and l["price"] == lowest

        ref = self._reference(product_id)
        source = next((l for l in listings if l["role"] == "source"), listings[0] if listings else None)
        name = (ref or {}).get("title")
        query = matching.search_query(ref["brand"], ref["title"], ref.get("variant")) if ref else None
        present = {l["platform"] for l in listings}
        missing = [
            {
                "platform": p,
                "platform_name": PLATFORMS[p],
                "id_label": ID_LABELS[p],
                "search_url": search_url(p, query) if query else None,
                "can_search_api": p == "amazon" and self.amazon.configured() and bool(query),
            }
            for p in PLATFORM_ORDER if p not in present
        ]
        return {
            "id": prod["id"],
            "created_at": prod["created_at"],
            "name": name,
            "brand": (ref or {}).get("brand"),
            "source_platform": source["platform"] if source else None,
            "search_query": query,
            "lowest_price": lowest,
            "verified_count": len(eligible),
            "listings": listings,
            "missing": missing,
        }

    def list_products(self):
        ids = [r["id"] for r in self.db.execute("SELECT id FROM products ORDER BY id DESC")]
        return [self.get_product(i) for i in ids]

    def history(self):
        return self.db.execute(
            """SELECT h.*, l.platform, l.platform_id, l.title, l.product_id
               FROM history h JOIN listings l ON l.id = h.listing_id
               ORDER BY h.recorded_at DESC, h.id DESC"""
        ).fetchall()

    # ----- writing -------------------------------------------------------

    def _record(self, listing_id):
        r = self._listing(listing_id)
        self.db.execute(
            "INSERT INTO history (listing_id, mrp, price, status, source, recorded_at) VALUES (?,?,?,?,?,?)",
            (listing_id, r["mrp"], r["price"], r["status"], r["source"], now()),
        )

    def _insert_listing(self, product_id, parsed, role, match_state, score=None):
        cur = self.db.execute(
            """INSERT INTO listings (product_id, platform, platform_id, url, role, match_state, match_score, match_reasons)
               VALUES (?,?,?,?,?,?,?,?)""",
            (product_id, parsed.platform, parsed.platform_id, parsed.url, role, match_state,
             score["score"] if score else None, json.dumps(score["reasons"]) if score else None),
        )
        return cur.lastrowid

    def _apply_api_fields(self, listing_id, fields, ts):
        verified = fields["status"] in ("live", "unavailable")
        self.db.execute(
            """UPDATE listings SET title = COALESCE(?, title), brand = COALESCE(?, brand),
                   variant = COALESCE(?, variant), eans = ?, model = COALESCE(?, model),
                   url = COALESCE(url, ?), mrp = ?, price = ?, currency = ?, status = ?,
                   source = ?, note = ?, verified_at = ?, last_checked_at = ?
               WHERE id = ?""",
            (fields["title"], fields["brand"], fields["variant"], json.dumps(fields["eans"]), fields["model"],
             fields["url"], fields["mrp"], fields["price"], fields["currency"], fields["status"],
             API_SOURCE, fields["note"], ts if verified else None, ts, listing_id),
        )
        self._record(listing_id)

    def _mark_error(self, listing_id, message, ts):
        # Keep the last verified price (shown as such) but never as current.
        self.db.execute(
            "UPDATE listings SET status = 'error', note = ?, last_checked_at = ? WHERE id = ?",
            (message, ts, listing_id),
        )
        self._record(listing_id)

    def _fetch_amazon(self, rows, force=False):
        """Refresh Amazon listings in one batched API call. Returns a short summary."""
        if not rows:
            return {"checked": 0, "skipped": 0}
        if not self.amazon.configured():
            for r in rows:
                if r["status"] == "unverified":
                    self.db.execute(
                        "UPDATE listings SET note = ? WHERE id = ?",
                        ("Amazon API credentials not set; enter the price manually or add credentials.", r["id"]),
                    )
            return {"checked": 0, "skipped": len(rows), "reason": "Amazon API not configured"}

        min_age = config.min_refresh_minutes() / 60
        due = [r for r in rows if force or r["last_checked_at"] is None or _age_hours(r["last_checked_at"]) >= min_age]
        if not due:
            return {"checked": 0, "skipped": len(rows), "reason": "Refreshed recently"}
        ts = now()
        try:
            found = self.amazon.get_items([r["platform_id"] for r in due])
        except Exception as exc:
            for r in due:
                self._mark_error(r["id"], f"Amazon API error: {exc}", ts)
            return {"checked": len(due), "skipped": len(rows) - len(due), "error": str(exc)}
        for r in due:
            fields = found.get(r["platform_id"].upper())
            if fields:
                self._apply_api_fields(r["id"], fields, ts)
            else:
                self._mark_error(r["id"], "Amazon did not return this ASIN (it may be invalid or not available to your Associates account).", ts)
        return {"checked": len(due), "skipped": len(rows) - len(due)}

    def _rescore(self, product_id):
        ref = None
        rows = self._listing_rows(product_id)
        src = next((r for r in rows if r["role"] == "source"), None)
        if src and src["title"]:
            ref = {"title": src["title"], "brand": src["brand"], "variant": src["variant"],
                   "eans": json.loads(src["eans"] or "[]"), "model": src["model"]}
        for r in rows:
            if r["role"] == "source":
                continue
            if ref and r["title"]:
                s = matching.score(ref, {"title": r["title"], "brand": r["brand"], "variant": r["variant"],
                                         "eans": json.loads(r["eans"] or "[]"), "model": r["model"]})
                self.db.execute("UPDATE listings SET match_score = ?, match_reasons = ? WHERE id = ?",
                                (s["score"], json.dumps(s["reasons"]), r["id"]))

    def add_product(self, text, platform_hint=None, auto_match=True):
        parsed = parse_input(text, platform_hint)
        existing = self.db.execute(
            "SELECT product_id FROM listings WHERE platform = ? AND platform_id = ?",
            (parsed.platform, parsed.platform_id),
        ).fetchone()
        if existing:
            return self.get_product(existing["product_id"]), False

        with self.db:
            pid = self.db.execute("INSERT INTO products (created_at) VALUES (?)", (now(),)).lastrowid
            self._insert_listing(pid, parsed, "source", "confirmed")
        if parsed.platform == "amazon":
            with self.db:
                self._fetch_amazon(self._listing_rows(pid), force=True)
        if auto_match:
            self.suggest_amazon_match(pid)
        return self.get_product(pid), True

    def add_listing(self, product_id, text, platform_hint=None):
        """Attach a listing the user picked as the same product on another platform."""
        self.get_product(product_id)
        parsed = parse_input(text, platform_hint)
        clash = self.db.execute(
            "SELECT product_id FROM listings WHERE platform = ? AND platform_id = ?",
            (parsed.platform, parsed.platform_id),
        ).fetchone()
        if clash and clash["product_id"] != product_id:
            raise InputError(f"That {PLATFORMS[parsed.platform]} listing is already tracked under another product.")
        with self.db:
            current = self.db.execute(
                "SELECT * FROM listings WHERE product_id = ? AND platform = ?", (product_id, parsed.platform)
            ).fetchone()
            if current and current["role"] == "source":
                raise InputError(f"{PLATFORMS[parsed.platform]} is this product's source listing.")
            if current:
                self.db.execute("DELETE FROM listings WHERE id = ?", (current["id"],))
            lid = self._insert_listing(product_id, parsed, "match", "confirmed")
        if parsed.platform == "amazon":
            with self.db:
                self._fetch_amazon([self._listing(lid)], force=True)
        with self.db:
            self._rescore(product_id)
        return self.get_product(product_id)

    def amazon_candidates(self, product_id, limit=5):
        ref = self._reference(product_id)
        if not ref:
            raise InputError("Add the product name and brand first (enter the price details for the source listing).")
        if not self.amazon.configured():
            raise InputError("Amazon Creators API credentials are not set.")
        query = matching.search_query(ref["brand"], ref["title"], ref.get("variant"))
        results = self.amazon.search(query, brand=ref.get("brand"))
        scored = []
        for item in results:
            s = matching.score(ref, item)
            scored.append({**item, "match": s})
        scored.sort(key=lambda x: -x["match"]["score"])
        return scored[:limit]

    def suggest_amazon_match(self, product_id):
        """If the API is available, attach the best Amazon candidate as a *suggested* match."""
        rows = self._listing_rows(product_id)
        if any(r["platform"] == "amazon" for r in rows) or not self.amazon.configured() or not self._reference(product_id):
            return None
        try:
            candidates = self.amazon_candidates(product_id, limit=1)
        except Exception:
            return None
        if not candidates or candidates[0]["match"]["score"] < matching.MEDIUM:
            return None
        best = candidates[0]
        from .platforms import ParsedInput
        with self.db:
            lid = self._insert_listing(product_id, ParsedInput("amazon", best["platform_id"], best["url"]),
                                       "match", "suggested", best["match"])
            self._apply_api_fields(lid, best, now())
        return lid

    def confirm_listing(self, listing_id):
        with self.db:
            self._listing(listing_id)
            self.db.execute("UPDATE listings SET match_state = 'confirmed' WHERE id = ?", (listing_id,))

    def remove_listing(self, listing_id):
        row = self._listing(listing_id)
        if row["role"] == "source":
            raise InputError("This is the product's source listing. Delete the whole product instead.")
        with self.db:
            self.db.execute("DELETE FROM listings WHERE id = ?", (listing_id,))

    def delete_product(self, product_id):
        with self.db:
            self.db.execute("DELETE FROM products WHERE id = ?", (product_id,))

    def manual_verify(self, listing_id, data):
        """Record a price the user checked on the product page themselves."""
        row = self._listing(listing_id)
        available = data.get("available", True)

        def money(key):
            v = data.get(key)
            if v in (None, ""):
                return None
            try:
                v = float(str(v).replace(",", "").replace("₹", "").strip())
            except ValueError:
                raise InputError(f"{key.upper()} must be a number.")
            if v <= 0:
                raise InputError(f"{key.upper()} must be more than zero.")
            return round(v, 2)

        mrp, price = money("mrp"), money("price")
        if available and price is None:
            raise InputError("Enter the current selling price, or mark the product as unavailable.")
        if mrp is not None and price is not None and price > mrp:
            raise InputError("Selling price is higher than MRP. Check both values.")
        if row["source"] == API_SOURCE and row["status"] in ("live", "unavailable") and not data.get("override"):
            raise InputError("This price comes from the Amazon API. Use Refresh instead.")

        ts = now()
        with self.db:
            self.db.execute(
                """UPDATE listings SET title = COALESCE(NULLIF(?, ''), title), brand = COALESCE(NULLIF(?, ''), brand),
                       variant = COALESCE(NULLIF(?, ''), variant), mrp = ?, price = ?, status = ?, source = ?,
                       note = ?, verified_at = ?, last_checked_at = ? WHERE id = ?""",
                ((data.get("title") or "").strip(), (data.get("brand") or "").strip(), (data.get("variant") or "").strip(),
                 mrp, price if available else None, "manual" if available else "unavailable", MANUAL_SOURCE,
                 (data.get("note") or "").strip() or None, ts, ts, listing_id),
            )
            self._record(listing_id)
            self._rescore(row["product_id"])
        if row["role"] == "source":
            self.suggest_amazon_match(row["product_id"])
        return self.get_product(row["product_id"])

    def refresh(self, product_ids=None, force=False):
        """Re-fetch every API-backed listing (batched). Manual listings keep their timestamp."""
        if product_ids is None:
            rows = self.db.execute("SELECT * FROM listings WHERE platform = 'amazon'").fetchall()
        else:
            marks = ",".join("?" * len(product_ids))
            rows = self.db.execute(
                f"SELECT * FROM listings WHERE platform = 'amazon' AND product_id IN ({marks})", product_ids
            ).fetchall()
        with self.db:
            summary = self._fetch_amazon(rows, force=force)
        manual = self.db.execute(
            "SELECT COUNT(*) FROM listings WHERE platform != 'amazon'"
            + ("" if product_ids is None else f" AND product_id IN ({','.join('?' * len(product_ids))})"),
            product_ids or [],
        ).fetchone()[0]
        summary["manual_listings"] = manual
        return summary
