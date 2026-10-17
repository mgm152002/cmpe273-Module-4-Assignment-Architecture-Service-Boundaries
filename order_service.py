"""Order Service — creates and tracks orders.

Owns: the order records (order id -> item, quantity, status).
Flow for POST /orders:
  1. Query  Inventory Service: is the item available?   (GET /inventory/<id>)
  2. Command Inventory Service: reserve the stock        (POST /inventory/<id>/reserve)
  3. Create the order record (owned here)
  4. Event   Notify Notification Service, fire-and-forget (POST /notify)
If the Inventory Service is down, return 503 and keep running.
Runs on port 5000 as an independent process.
"""
import itertools
import os
import threading
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://127.0.0.1:5001")
NOTIFY_URL = os.environ.get("NOTIFY_URL", "http://127.0.0.1:5002")
TIMEOUT = 3  # seconds — fail fast instead of hanging on a dead dependency

# In-memory order store. This service is the sole owner of this data.
ORDERS = {}
order_ids = itertools.count(1)


def _fire_notification(order):
    """Best-effort notify on a background thread — never blocks the response."""
    try:
        requests.post(f"{NOTIFY_URL}/notify", json=order, timeout=TIMEOUT)
    except requests.RequestException:
        pass  # notification failure must never fail the order


@app.get("/health")
def health():
    return jsonify({"service": "order", "status": "ok",
                    "orders": len(ORDERS)})


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    quantity = body.get("quantity", 1)
    if not item_id or not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "body must be "
                                 '{"item_id": str, "quantity": positive int}'}), 400

    # 1. Query inventory for availability.
    try:
        r = requests.get(f"{INVENTORY_URL}/inventory/{item_id}",
                         timeout=TIMEOUT)
    except requests.RequestException:
        # Dependency failure: degrade gracefully, do NOT crash.
        return jsonify({"error": "inventory service unavailable, "
                                 "order could not be placed"}), 503
    if r.status_code == 404:
        return jsonify({"error": f"unknown item '{item_id}'"}), 404
    if r.status_code != 200:
        return jsonify({"error": "inventory service error"}), 502
    if not r.json().get("available"):
        return jsonify({"error": f"item '{item_id}' is out of stock"}), 409

    # 2. Command inventory to reserve the stock.
    try:
        r = requests.post(f"{INVENTORY_URL}/inventory/{item_id}/reserve",
                          json={"quantity": quantity}, timeout=TIMEOUT)
    except requests.RequestException:
        return jsonify({"error": "inventory service unavailable, "
                                 "order could not be placed"}), 503
    if r.status_code != 200:
        return jsonify({"error": "could not reserve stock",
                        "detail": r.json()}), 409

    # 3. Create the order (owned by this service).
    order_id = next(order_ids)
    order = {"order_id": order_id, "item_id": item_id,
             "quantity": quantity, "status": "created"}
    ORDERS[order_id] = order

    # 4. Event: "order was created" -> notification service, truly
    # fire-and-forget: dispatched on a daemon thread so the 201 response
    # never waits for the notification round-trip.
    threading.Thread(target=_fire_notification, args=(order,),
                     daemon=True).start()

    return jsonify(order), 201


@app.get("/orders")
def list_orders():
    return jsonify(list(ORDERS.values()))


@app.get("/orders/<int:order_id>")
def get_order(order_id):
    order = ORDERS.get(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    return jsonify(order)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
