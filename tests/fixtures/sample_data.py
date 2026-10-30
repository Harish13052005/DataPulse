"""
Test Sample Payloads and Data Fixtures for DataPulse.
"""

from typing import Any, Dict

SAMPLE_VALID_CUSTOMER: Dict[str, Any] = {
    "customer_id": "CUST-9001",
    "first_name": "Alice",
    "last_name": "Walker",
    "email": "alice.walker@example.com",
    "phone": "+1-555-019-2834",
    "address": "123 Innovation Way",
    "city": "Austin",
    "state": "TX",
    "postal_code": "78701",
    "country": "USA",
    "signup_date": "2023-04-15",
    "customer_segment": "Premium",
    "is_active": True,
    "_source_system": "CSV_CUSTOMERS",
    "_record_hash": "dummyhash9001",
    "_raw_payload": '{"customer_id": "CUST-9001"}'
}

SAMPLE_INVALID_CUSTOMER: Dict[str, Any] = {
    "customer_id": "CUST-9002",
    "first_name": "",
    "last_name": "Broken",
    "email": "not-an-email",
    "phone": "+1-555-000-0000",
    "address": "404 Error Rd",
    "city": "Nowhere",
    "state": "INVALID",
    "postal_code": "00000",
    "country": "USA",
    "signup_date": "2099-01-01",
    "customer_segment": "Standard",
    "is_active": True,
    "_source_system": "CSV_CUSTOMERS",
    "_record_hash": "dummyhash9002",
    "_raw_payload": '{"customer_id": "CUST-9002"}'
}

SAMPLE_VALID_ORDER: Dict[str, Any] = {
    "order_id": "ORD-9001",
    "customer_id": "CUST-9001",
    "order_timestamp": "2023-11-20T14:30:00Z",
    "status": "COMPLETED",
    "payment_method": "CREDIT_CARD",
    "subtotal": 249.98,
    "tax_amount": 20.00,
    "shipping_fee": 9.99,
    "discount_amount": 10.00,
    "total_amount": 269.97,
    "items": [
        {
            "item_id": "ITEM-90001",
            "product_id": "PROD-001",
            "product_name": "Pro Wireless Headphones",
            "category": "Electronics",
            "quantity": 1,
            "unit_price": 199.99,
            "line_total": 199.99
        },
        {
            "item_id": "ITEM-90002",
            "product_id": "PROD-006",
            "product_name": "Precision Optical Mouse",
            "category": "Peripherals",
            "quantity": 1,
            "unit_price": 49.99,
            "line_total": 49.99
        }
    ],
    "_source_system": "REST_API_ORDERS",
    "_record_hash": "dummyorderhash9001",
    "_raw_payload": '{"order_id": "ORD-9001"}'
}
