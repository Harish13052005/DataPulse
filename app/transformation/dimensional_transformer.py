"""
Dimensional Modeling & Data Transformation for DataPulse.

Transforms validated customer, order, and product records into a Kimball-style
Star Schema:
- DimCustomer
- DimProduct
- DimDate
- FactOrders
- FactOrderItems
"""

from __future__ import annotations

import calendar
import hashlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple

from app.transformation.cleaner import DataCleaner


class DimensionalTransformer:
    """Transforms validated staging data into Dimensional Star Schema entities."""

    @staticmethod
    def generate_surrogate_key(*keys: Any) -> int:
        """Generate deterministic 32-bit integer surrogate key from natural key inputs."""
        raw = ":".join(str(k) for k in keys)
        h = hashlib.sha256(raw.encode("utf-8")).digest()
        val = int.from_bytes(h[:4], byteorder="big", signed=False)
        return val % 2147483647

    @staticmethod
    def build_date_dimension_record(dt: datetime | date) -> Dict[str, Any]:
        """Generate a complete date dimension row for a given date."""
        d = dt.date() if isinstance(dt, datetime) else dt
        date_key = int(d.strftime("%Y%m%d"))
        day_of_week = d.isoweekday()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]

        quarter = (d.month - 1) // 3 + 1
        is_weekend = day_of_week in (6, 7)

        _, last_day = calendar.monthrange(d.year, d.month)
        is_month_end = (d.day == last_day)

        return {
            "date_key": date_key,
            "full_date": d,
            "day_of_month": d.day,
            "day_of_week": day_of_week,
            "day_name": day_names[day_of_week - 1],
            "month_num": d.month,
            "month_name": month_names[d.month - 1],
            "quarter": quarter,
            "year": d.year,
            "is_weekend": is_weekend,
            "is_month_end": is_month_end
        }

    @classmethod
    def transform_customers(cls, valid_customer_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform validated customer dictionaries into DimCustomer rows."""
        now_utc = datetime.now(timezone.utc)
        dim_customers: List[Dict[str, Any]] = []

        for rec in valid_customer_records:
            cid = rec["customer_id"]
            cust_key = cls.generate_surrogate_key("CUST", cid)
            first_name = DataCleaner.clean_name(rec.get("first_name"))
            last_name = DataCleaner.clean_name(rec.get("last_name"))
            email = DataCleaner.clean_email(rec.get("email"))
            state = DataCleaner.clean_state(rec.get("state"))
            city = DataCleaner.clean_name(rec.get("city"))

            raw_signup = rec.get("signup_date")
            if isinstance(raw_signup, str):
                signup_dt = datetime.strptime(raw_signup[:10], "%Y-%m-%d").date()
            elif isinstance(raw_signup, (datetime, date)):
                signup_dt = raw_signup.date() if isinstance(raw_signup, datetime) else raw_signup
            else:
                signup_dt = date(2023, 1, 1)

            dim_customers.append({
                "customer_key": cust_key,
                "customer_id": cid,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}",
                "email": email,
                "phone": rec.get("phone", ""),
                "address": rec.get("address", ""),
                "city": city,
                "state": state,
                "postal_code": str(rec.get("postal_code", "")),
                "country": rec.get("country", "USA"),
                "signup_date": signup_dt,
                "signup_year": signup_dt.year,
                "signup_month": signup_dt.month,
                "customer_segment": rec.get("customer_segment", "Standard"),
                "is_active": bool(rec.get("is_active", True)),
                "ingested_at": rec.get("_ingested_at", now_utc.isoformat()),
                "record_hash": rec.get("_record_hash", ""),
                "updated_at": now_utc
            })

        return dim_customers

    @classmethod
    def transform_products(cls, product_catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform raw product catalog items into DimProduct rows."""
        now_utc = datetime.now(timezone.utc)
        dim_products: List[Dict[str, Any]] = []

        for p in product_catalog:
            pid = p["product_id"]
            prod_key = cls.generate_surrogate_key("PROD", pid)
            price = float(p["unit_price"])

            if price < 50.0:
                tier = "Budget"
            elif price < 150.0:
                tier = "Standard"
            elif price < 400.0:
                tier = "Premium"
            else:
                tier = "Luxury"

            dim_products.append({
                "product_key": prod_key,
                "product_id": pid,
                "product_name": p["product_name"],
                "category": p["category"],
                "unit_price": price,
                "price_tier": tier,
                "updated_at": now_utc
            })

        return dim_products

    @classmethod
    def transform_orders_and_items(
        cls,
        valid_orders: List[Dict[str, Any]],
        customer_key_lookup: Dict[str, int],
        product_key_lookup: Dict[str, int]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Transform validated orders into FactOrders, FactOrderItems, and associated DimDate rows.
        Returns: (fact_orders, fact_order_items, date_dimension_records)
        """
        now_utc = datetime.now(timezone.utc)
        fact_orders: List[Dict[str, Any]] = []
        fact_order_items: List[Dict[str, Any]] = []
        date_records_dict: Dict[int, Dict[str, Any]] = {}

        for order in valid_orders:
            order_id = order["order_id"]
            cust_id = order["customer_id"]
            order_key = cls.generate_surrogate_key("ORD", order_id)

            cust_key = customer_key_lookup.get(cust_id)
            if not cust_key:
                cust_key = cls.generate_surrogate_key("CUST", cust_id)

            order_dt = DataCleaner.normalize_timestamp(order["order_timestamp"])
            date_row = cls.build_date_dimension_record(order_dt)
            date_key = date_row["date_key"]
            date_records_dict[date_key] = date_row

            items = order.get("items", [])
            item_count = len(items)
            total_quantity = sum(int(it.get("quantity", 0)) for it in items)

            subtotal = float(order.get("subtotal", 0.0))
            tax_amount = float(order.get("tax_amount", 0.0))
            shipping_fee = float(order.get("shipping_fee", 0.0))
            discount_amount = float(order.get("discount_amount", 0.0))
            total_amount = float(order.get("total_amount", 0.0))
            net_amount = round(subtotal - discount_amount, 2)

            fact_orders.append({
                "order_key": order_key,
                "order_id": order_id,
                "customer_key": cust_key,
                "customer_id": cust_id,
                "order_date_key": date_key,
                "order_timestamp": order_dt,
                "status": order["status"].upper(),
                "payment_method": order["payment_method"],
                "item_count": item_count,
                "total_quantity": total_quantity,
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "shipping_fee": shipping_fee,
                "discount_amount": discount_amount,
                "total_amount": total_amount,
                "net_amount": net_amount,
                "ingested_at": order.get("_ingested_at", now_utc.isoformat()),
                "record_hash": order.get("_record_hash", "")
            })

            for it in items:
                item_id = it.get("item_id", f"{order_id}-ITEM")
                pid = it["product_id"]
                prod_key = product_key_lookup.get(pid)
                if not prod_key:
                    prod_key = cls.generate_surrogate_key("PROD", pid)

                item_key = cls.generate_surrogate_key("ITEM", order_id, item_id)
                qty = int(it.get("quantity", 1))
                unit_price = float(it.get("unit_price", 0.0))
                line_total = float(it.get("line_total", qty * unit_price))

                discount_alloc = 0.0
                if subtotal > 0 and discount_amount > 0:
                    discount_alloc = round((line_total / subtotal) * discount_amount, 2)

                fact_order_items.append({
                    "order_item_key": item_key,
                    "order_key": order_key,
                    "order_id": order_id,
                    "product_key": prod_key,
                    "product_id": pid,
                    "customer_key": cust_key,
                    "order_date_key": date_key,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "discount_allocated": discount_alloc
                })

        return fact_orders, fact_order_items, list(date_records_dict.values())
