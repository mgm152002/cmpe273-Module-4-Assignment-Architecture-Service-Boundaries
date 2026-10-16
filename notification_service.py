"""Notification Service — notifies users when an order is created.

Owns: the notification log (which order notifications were sent).
It is purely event-driven: it does nothing until the Order Service
tells it "order was created" via POST /notify.
Runs on port 5002 as an independent process.
"""
import os
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory notification log. This service is the sole owner of this data.
NOTIFICATIONS = []


@app.get("/health")
def health():
    return jsonify({"service": "notification", "status": "ok",
                    "sent": len(NOTIFICATIONS)})


@app.post("/notify")
def notify():
    """Event handler — 'order was created'."""
    body = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if order_id is None:
        return jsonify({"error": "order_id required"}), 400
    message = (f"Order #{order_id}: {body.get('quantity', 1)} x "
               f"{body.get('item_id')} confirmed. Thanks for shopping!")
    NOTIFICATIONS.append({"order_id": order_id, "message": message})
    # In a real system this would send email/SMS/push; here we log it.
    print(f"[notification] {message}", flush=True)
    return jsonify({"notified": order_id}), 202


@app.get("/notifications")
def list_notifications():
    return jsonify(NOTIFICATIONS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
