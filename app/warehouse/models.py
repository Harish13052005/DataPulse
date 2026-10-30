"""
SQLAlchemy ORM Dimensional Models for DataPulse Warehouse.

Implements Kimball Dimensional Star Schema:
- dim_customers
- dim_products
- dim_date
- fact_orders
- fact_order_items

And operational audit models:
- pipeline_runs
- quarantine_records
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.warehouse.connection import Base


class DimCustomer(Base):
    """Customer Dimension Table."""
    __tablename__ = "dim_customers"

    customer_key = Column(Integer, primary_key=True, autoincrement=False)
    customer_id = Column(String(64), nullable=False, unique=True, index=True)
    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=False)
    email = Column(String(256), nullable=False, index=True)
    phone = Column(String(64), nullable=True)
    address = Column(String(256), nullable=True)
    city = Column(String(128), nullable=False)
    state = Column(String(32), nullable=False, index=True)
    postal_code = Column(String(32), nullable=False)
    country = Column(String(64), nullable=False, default="USA")
    signup_date = Column(Date, nullable=False)
    signup_year = Column(Integer, nullable=False, index=True)
    signup_month = Column(Integer, nullable=False)
    customer_segment = Column(String(64), nullable=False, default="Standard")
    is_active = Column(Boolean, nullable=False, default=True)
    ingested_at = Column(String(64), nullable=False)
    record_hash = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    orders = relationship("FactOrder", back_populates="customer")

    __table_args__ = (
        Index("idx_dim_cust_seg_state", "customer_segment", "state"),
    )


class DimProduct(Base):
    """Product Dimension Table."""
    __tablename__ = "dim_products"

    product_key = Column(Integer, primary_key=True, autoincrement=False)
    product_id = Column(String(64), nullable=False, unique=True, index=True)
    product_name = Column(String(256), nullable=False)
    category = Column(String(128), nullable=False, index=True)
    unit_price = Column(Float, nullable=False)
    price_tier = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    order_items = relationship("FactOrderItem", back_populates="product")


class DimDate(Base):
    """Calendar Date Dimension Table."""
    __tablename__ = "dim_date"

    date_key = Column(Integer, primary_key=True, autoincrement=False)
    full_date = Column(Date, nullable=False, unique=True, index=True)
    day_of_month = Column(Integer, nullable=False)
    day_of_week = Column(Integer, nullable=False)
    day_name = Column(String(32), nullable=False)
    month_num = Column(Integer, nullable=False, index=True)
    month_name = Column(String(32), nullable=False)
    quarter = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    is_weekend = Column(Boolean, nullable=False)
    is_month_end = Column(Boolean, nullable=False)

    orders = relationship("FactOrder", back_populates="date_dim")


class FactOrder(Base):
    """Orders Fact Table."""
    __tablename__ = "fact_orders"

    order_key = Column(Integer, primary_key=True, autoincrement=False)
    order_id = Column(String(64), nullable=False, unique=True, index=True)
    customer_key = Column(Integer, ForeignKey("dim_customers.customer_key"), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False)
    order_date_key = Column(Integer, ForeignKey("dim_date.date_key"), nullable=False, index=True)
    order_timestamp = Column(DateTime, nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    payment_method = Column(String(64), nullable=False)
    item_count = Column(Integer, nullable=False)
    total_quantity = Column(Integer, nullable=False)
    subtotal = Column(Float, nullable=False)
    tax_amount = Column(Float, nullable=False)
    shipping_fee = Column(Float, nullable=False)
    discount_amount = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    net_amount = Column(Float, nullable=False)
    ingested_at = Column(String(64), nullable=False)
    record_hash = Column(String(64), nullable=False)

    customer = relationship("DimCustomer", back_populates="orders")
    date_dim = relationship("DimDate", back_populates="orders")
    items = relationship("FactOrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_fact_orders_status_date", "status", "order_date_key"),
    )


class FactOrderItem(Base):
    """Order Line Items Fact Table."""
    __tablename__ = "fact_order_items"

    order_item_key = Column(Integer, primary_key=True, autoincrement=False)
    order_key = Column(Integer, ForeignKey("fact_orders.order_key"), nullable=False, index=True)
    order_id = Column(String(64), nullable=False, index=True)
    product_key = Column(Integer, ForeignKey("dim_products.product_key"), nullable=False, index=True)
    product_id = Column(String(64), nullable=False)
    customer_key = Column(Integer, ForeignKey("dim_customers.customer_key"), nullable=False)
    order_date_key = Column(Integer, ForeignKey("dim_date.date_key"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    discount_allocated = Column(Float, nullable=False, default=0.0)

    order = relationship("FactOrder", back_populates="items")
    product = relationship("DimProduct", back_populates="order_items")


class PipelineRun(Base):
    """Operational Audit: Execution Runs Tracking."""
    __tablename__ = "pipeline_runs"

    run_id = Column(String(64), primary_key=True)
    pipeline_name = Column(String(128), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(32), nullable=False)
    records_ingested = Column(Integer, nullable=False, default=0)
    valid_records_loaded = Column(Integer, nullable=False, default=0)
    quarantined_records = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=True)


class QuarantineRecord(Base):
    """Operational Audit: Quarantine Table for Invalid Records."""
    __tablename__ = "quarantine_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=True, index=True)
    record_id = Column(String(64), nullable=False, index=True)
    source_system = Column(String(64), nullable=False)
    error_type = Column(String(64), nullable=False)
    rule_code = Column(String(64), nullable=False, index=True)
    field_name = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=False)
    raw_payload = Column(Text, nullable=False)
    quarantined_at = Column(DateTime, nullable=False, default=datetime.utcnow)
