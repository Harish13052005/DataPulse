"""
Deterministic Synthetic Data Generator for DataPulse Platform.

Generates realistic, seed-controlled e-commerce data for:
- Source 1: Customer profiles (CSV export)
- Source 2: Orders and Line Items (REST API service)

Includes a controlled injection of dirty/malformed records to validate
quarantine, error tracking, and schema/business-rule enforcement.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from app.config.settings import settings

PRODUCT_CATALOG: List[Dict[str, Any]] = [
    {"product_id": "PROD-001", "product_name": "Pro Wireless Headphones", "category": "Electronics", "unit_price": 199.99},
    {"product_id": "PROD-002", "product_name": "Ultra Mechanical Keyboard", "category": "Peripherals", "unit_price": 129.50},
    {"product_id": "PROD-003", "product_name": "4K Ultra-Wide Monitor 34-inch", "category": "Electronics", "unit_price": 549.00},
    {"product_id": "PROD-004", "product_name": "Ergonomic Mesh Desk Chair", "category": "Furniture", "unit_price": 349.99},
    {"product_id": "PROD-005", "product_name": "USB-C Multiport Dock 11-in-1", "category": "Accessories", "unit_price": 79.95},
    {"product_id": "PROD-006", "product_name": "Precision Optical Mouse", "category": "Peripherals", "unit_price": 49.99},
    {"product_id": "PROD-007", "product_name": "Standing Electric Desk 60-inch", "category": "Furniture", "unit_price": 499.00},
    {"product_id": "PROD-008", "product_name": "Active Noise Canceling Earbuds", "category": "Electronics", "unit_price": 149.99},
    {"product_id": "PROD-009", "product_name": "Smart Fitness & Health Tracker", "category": "Fitness", "unit_price": 99.00},
    {"product_id": "PROD-010", "product_name": "Leather Laptop Sleeve 15-inch", "category": "Accessories", "unit_price": 39.99},
    {"product_id": "PROD-011", "product_name": "Aluminum Monitor Arm Dual", "category": "Accessories", "unit_price": 89.90},
    {"product_id": "PROD-012", "product_name": "Studio Condenser USB Mic", "category": "Electronics", "unit_price": 119.00},
    {"product_id": "PROD-013", "product_name": "HD 1080p Streaming Webcam", "category": "Electronics", "unit_price": 69.95},
    {"product_id": "PROD-014", "product_name": "Memory Foam Wrist Rest", "category": "Peripherals", "unit_price": 19.99},
    {"product_id": "PROD-015", "product_name": "Adjustable Footrest Ergonomic", "category": "Furniture", "unit_price": 45.00},
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

CITIES_STATES = [
    ("New York", "NY", "10001"),
    ("San Francisco", "CA", "94102"),
    ("Austin", "TX", "78701"),
    ("Seattle", "WA", "98101"),
    ("Chicago", "IL", "60601"),
    ("Boston", "MA", "02108"),
    ("Denver", "CO", "80202"),
    ("Atlanta", "GA", "30301"),
    ("Miami", "FL", "33101"),
    ("Portland", "OR", "97201")
]

SEGMENTS = ["Standard", "Standard", "Standard", "Premium", "Premium", "VIP"]
PAYMENT_METHODS = ["CREDIT_CARD", "PAYPAL", "APPLE_PAY", "WIRE_TRANSFER"]
STATUSES = ["COMPLETED", "COMPLETED", "COMPLETED", "COMPLETED", "PENDING", "CANCELLED", "REFUNDED"]


def generate_synthetic_customers(
    count: int = 250,
    seed: int = 42,
    dirty_ratio: float = 0.08
) -> List[Dict[str, Any]]:
    """Generate deterministic synthetic customer records with controlled dirty injection."""
    rng = random.Random(seed)
    customers: List[Dict[str, Any]] = []
    base_date = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    for i in range(1, count + 1):
        cust_id = f"CUST-{1000 + i}"
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        city, state, postal = rng.choice(CITIES_STATES)
        days_offset = rng.randint(0, 600)
        reg_date = base_date + timedelta(days=days_offset)
        segment = rng.choice(SEGMENTS)
        is_active = rng.random() > 0.12
        phone = f"+1-{rng.randint(200, 999)}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
        email = f"{first_name.lower()}.{last_name.lower()}{i}@example.com"
        address = f"{rng.randint(100, 9999)} {rng.choice(['Market St', 'Main Ave', 'Broadway', 'Oak Blvd', 'Pine St'])}"

        record: Dict[str, Any] = {
            "customer_id": cust_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "city": city,
            "state": state,
            "postal_code": postal,
            "country": "USA",
            "signup_date": reg_date.strftime("%Y-%m-%d"),
            "customer_segment": segment,
            "is_active": is_active,
        }

        # Deterministic dirty injection based on index and dirty_ratio
        if dirty_ratio > 0 and (i % int(1 / dirty_ratio) == 0):
            dirty_kind = i % 4
            if dirty_kind == 0:
                record["email"] = f"invalid_email_{i}_at_example"
            elif dirty_kind == 1:
                record["first_name"] = ""
            elif dirty_kind == 2:
                record["signup_date"] = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
            elif dirty_kind == 3:
                record["state"] = ""
                record["postal_code"] = "-999"

        customers.append(record)

    return customers


def generate_synthetic_orders(
    count: int = 1000,
    customer_ids: List[str] | None = None,
    seed: int = 42,
    dirty_ratio: float = 0.08
) -> List[Dict[str, Any]]:
    """Generate deterministic synthetic orders with nested line items."""
    rng = random.Random(seed + 100)
    orders: List[Dict[str, Any]] = []

    if not customer_ids:
        customer_ids = [f"CUST-{1000 + i}" for i in range(1, 251)]

    base_date = datetime(2023, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    item_counter = 1

    for i in range(1, count + 1):
        order_id = f"ORD-{5000 + i}"
        customer_id = rng.choice(customer_ids)
        seconds_offset = rng.randint(0, 500 * 86400)
        order_time = base_date + timedelta(seconds=seconds_offset)
        status = rng.choice(STATUSES)
        payment_method = rng.choice(PAYMENT_METHODS)
        shipping_fee = round(rng.choice([0.0, 4.99, 9.99, 14.99]), 2)
        discount_amount = round(rng.choice([0.0, 0.0, 5.0, 10.0, 25.0]), 2)

        num_items = rng.randint(1, 4)
        items: List[Dict[str, Any]] = []
        subtotal = 0.0

        for _ in range(num_items):
            prod = rng.choice(PRODUCT_CATALOG)
            qty = rng.randint(1, 3)
            price = prod["unit_price"]
            line_total = round(qty * price, 2)
            subtotal += line_total

            items.append({
                "item_id": f"ITEM-{item_counter:05d}",
                "product_id": prod["product_id"],
                "product_name": prod["product_name"],
                "category": prod["category"],
                "quantity": qty,
                "unit_price": price,
                "line_total": line_total
            })
            item_counter += 1

        subtotal = round(subtotal, 2)
        tax_amount = round(subtotal * 0.08, 2)
        total_amount = round(max(0.0, subtotal + tax_amount + shipping_fee - discount_amount), 2)

        order_record: Dict[str, Any] = {
            "order_id": order_id,
            "customer_id": customer_id,
            "order_timestamp": order_time.isoformat(),
            "status": status,
            "payment_method": payment_method,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "shipping_fee": shipping_fee,
            "discount_amount": discount_amount,
            "total_amount": total_amount,
            "items": items
        }

        # Deterministic dirty injection
        if dirty_ratio > 0 and (i % int(1 / dirty_ratio) == 0):
            dirty_kind = i % 4
            if dirty_kind == 0:
                order_record["customer_id"] = "CUST-9999"
            elif dirty_kind == 1:
                if order_record["items"]:
                    order_record["items"][0]["quantity"] = -2
                    order_record["items"][0]["line_total"] = -399.98
            elif dirty_kind == 2:
                order_record["total_amount"] = -150.00
            elif dirty_kind == 3:
                order_record["order_timestamp"] = "INVALID_TIMESTAMP_STRING"

        orders.append(order_record)

    return orders


def export_customers_to_csv(filepath: Path | str, customers: List[Dict[str, Any]]) -> Path:
    """Write customer records to CSV file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "customer_id", "first_name", "last_name", "email", "phone",
        "address", "city", "state", "postal_code", "country",
        "signup_date", "customer_segment", "is_active"
    ]

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(customers)

    return path
