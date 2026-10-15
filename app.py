"""Price tracker web app: python app.py, then open http://127.0.0.1:5000"""

import os
from datetime import datetime

from flask import Flask, jsonify, request, send_file, send_from_directory
from io import BytesIO

from tracker import amazon, config
from tracker.db import connect
from tracker.export import IST, build_workbook
from tracker.platforms import PLATFORMS, AmbiguousInput, InputError
from tracker.service import NotFound, Tracker

config.load_dotenv()


def create_app(db_path=None, amazon_client=amazon):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    tracker = Tracker(connect(db_path), amazon_client)
    app.config["tracker"] = tracker

    @app.errorhandler(AmbiguousInput)
    def ambiguous(exc):
        return jsonify(error=str(exc), candidates=[{"platform": c, "name": PLATFORMS[c]} for c in exc.candidates]), 409

    @app.errorhandler(InputError)
    def bad_input(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(NotFound)
    def not_found(exc):
        return jsonify(error=str(exc)), 404

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        amazon_on = amazon_client.configured()
        return jsonify(
            sources=[
                {"platform": "amazon", "name": "Amazon India", "mode": "api" if amazon_on else "manual",
                 "detail": "Official Amazon Creators API" if amazon_on
                 else "Creators API credentials not set. Prices can be entered manually."},
                *[{"platform": p, "name": PLATFORMS[p], "mode": "manual",
                   "detail": "No official public product API. Prices are verified manually on the product page."}
                  for p in ("myntra", "nykaa", "tatacliq")],
            ],
            manual_max_age_hours=config.manual_max_age_hours(),
        )

    @app.get("/api/products")
    def products():
        return jsonify(tracker.list_products())

    @app.post("/api/products")
    def add_product():
        body = request.get_json(force=True)
        product, created = tracker.add_product(body.get("input"), body.get("platform") or None)
        return jsonify(product=product, created=created), 201 if created else 200

    @app.delete("/api/products/<int:pid>")
    def delete_product(pid):
        tracker.delete_product(pid)
        return "", 204

    @app.post("/api/products/<int:pid>/listings")
    def add_listing(pid):
        body = request.get_json(force=True)
        return jsonify(tracker.add_listing(pid, body.get("input"), body.get("platform") or None))

    @app.get("/api/products/<int:pid>/amazon-candidates")
    def candidates(pid):
        return jsonify(tracker.amazon_candidates(pid))

    @app.post("/api/products/<int:pid>/refresh")
    def refresh_one(pid):
        summary = tracker.refresh([pid], force=bool(request.args.get("force")))
        return jsonify(summary=summary, product=tracker.get_product(pid))

    @app.post("/api/refresh")
    def refresh_all():
        return jsonify(summary=tracker.refresh(force=bool(request.args.get("force"))))

    @app.post("/api/listings/<int:lid>/manual")
    def manual(lid):
        return jsonify(tracker.manual_verify(lid, request.get_json(force=True)))

    @app.post("/api/listings/<int:lid>/confirm")
    def confirm(lid):
        tracker.confirm_listing(lid)
        return "", 204

    @app.delete("/api/listings/<int:lid>")
    def remove_listing(lid):
        tracker.remove_listing(lid)
        return "", 204

    @app.get("/api/export.xlsx")
    def export():
        data = build_workbook(tracker.list_products(), tracker.history())
        name = f"price-tracker-{datetime.now(IST).strftime('%Y-%m-%d-%H%M')}.xlsx"
        return send_file(BytesIO(data), as_attachment=True, download_name=name,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return app


if __name__ == "__main__":
    create_app().run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
