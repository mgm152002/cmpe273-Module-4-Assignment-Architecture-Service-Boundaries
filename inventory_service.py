"""Inventory Service — tracks item availability.

Owns: the inventory catalog (item -> quantity on hand).
Exposes:
  GET  /health
  GET  /inventory/<item_id>              -> Query: is this item available?
  POST /inventory/<item_id>/reserve      -> Command: decrement stock for an order
Runs on port 5001 as an independent process.
"""
import os
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory sample catalog. This service is the sole owner of this data.
INVENTORY = {
    "widget": 10,
    "gadget": 5,
    "thingamajig": 0,  # out of stock on purpose, for demoing the 409 path
}


@app.get("/health")
def health():
    return jsonify({"service": "inventory", "status": "ok"})


@app.get("/inventory/<item_id>")
def check_availability(item_id):
    """Query — read-only check, changes nothing."""
    quantity = INVENTORY.get(item_id)
    if quantity is None:
        return jsonify({"error": f"unknown item '{item_id}'"}), 404
    return jsonify({
        "item_id": item_id,
        "available": quantity > 0,
        "quantity": quantity,
    })


@app.post("/inventory/<item_id>/reserve")
def reserve(item_id):
    """Command — mutates stock owned by this service."""
    body = request.get_json(silent=True) or {}
    qty = body.get("quantity", 1)
    if not isinstance(qty, int) or qty <= 0:
        return jsonify({"error": "quantity must be a positive integer"}), 400
    stock = INVENTORY.get(item_id)
    if stock is None:
        return jsonify({"error": f"unknown item '{item_id}'"}), 404
    if stock < qty:
        return jsonify({"error": "insufficient stock", "available": stock}), 409
    INVENTORY[item_id] = stock - qty
    return jsonify({"item_id": item_id, "reserved": qty,
                    "remaining": INVENTORY[item_id]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
