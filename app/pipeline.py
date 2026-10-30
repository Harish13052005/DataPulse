"""
DataPulse Main Pipeline Orchestrator.

Coordinates the end-to-end ELT lifecycle:
1. Ingestion: Dual-source extraction (CSV + REST API) with SHA-256 audit hashing.
2. Validation: Pydantic schema validation + domain business rules + referential integrity.
3. Quarantine: Non-destructive error logging and quarantine routing.
4. Transformation: Kimball Dimensional modeling (surrogate keys, date dimensions, star schema).
5. Warehouse Loading: ACID transactional upsert and idempotent deduplication.
6. Monitoring: Operational metrics collection, audit persistence, and execution reporting.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config.settings import settings
from app.api.data_generator import PRODUCT_CATALOG
from app.ingestion.api_ingestion import OrdersAPIIngestor
from app.ingestion.csv_ingestion import CustomerCSVIngestor
from app.monitoring.logger import get_logger
from app.monitoring.metrics import PipelineMetricsCollector
from app.transformation.dimensional_transformer import DimensionalTransformer
from app.validation.quarantine import QuarantineManager
from app.validation.rules import BusinessRuleValidator
from app.warehouse.connection import get_db_session
from app.warehouse.loader import WarehouseLoader

logger = get_logger("datapulse.pipeline")


@dataclass
class PipelineExecutionResult:
    run_id: str
    status: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_ingested: int
    total_loaded: int
    total_quarantined: int
    metrics_summary: Dict[str, Any]
    quarantine_summary: Dict[str, Any]


class DataPulsePipeline:
    """Master Pipeline Orchestrator for DataPulse."""

    def __init__(
        self,
        csv_path: Optional[Path | str] = None,
        api_base_url: Optional[str] = None,
        force_mock_api_client: bool = True
    ):
        self.csv_path = csv_path or settings.CUSTOMERS_CSV_PATH
        self.api_base_url = api_base_url or settings.API_BASE_URL
        self.force_mock_api_client = force_mock_api_client

        self.csv_ingestor = CustomerCSVIngestor(self.csv_path)
        self.api_ingestor = OrdersAPIIngestor(
            base_url=self.api_base_url,
            force_mock_client=self.force_mock_api_client
        )
        self.quarantine_manager = QuarantineManager()
        self.transformer = DimensionalTransformer()
        self.loader = WarehouseLoader()

    def run(self) -> PipelineExecutionResult:
        """Execute the complete, idempotent DataPulse ELT pipeline."""
        start_time_perf = time.perf_counter()
        start_time_utc = datetime.now(timezone.utc)
        run_id = f"DP-{start_time_utc.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        logger.info("==================================================")
        logger.info(f"Starting DataPulse Pipeline Run: {run_id}")
        logger.info(f"Environment: {settings.APP_ENV} | Random Seed: {settings.RANDOM_SEED}")
        logger.info("==================================================")

        metrics = PipelineMetricsCollector(run_id)
        self.quarantine_manager.clear()

        # Phase 0: Schema Initialization
        metrics.start_phase("0_init_schema")
        logger.info("Phase 0: Initializing warehouse schema and tables...")
        self.loader.init_schema()
        metrics.stop_phase("0_init_schema")

        # Phase 1: Ingestion
        metrics.start_phase("1_ingestion")
        logger.info("Phase 1: Ingesting data from Source 1 (CSV) and Source 2 (REST API)...")

        raw_customers = self.csv_ingestor.ingest()
        metrics.record_count("customers_ingested", len(raw_customers))
        logger.info(f"Source 1 (CSV): Ingested {len(raw_customers)} raw customer records.")

        raw_orders = self.api_ingestor.ingest(page_size=settings.API_PAGE_SIZE)
        metrics.record_count("orders_ingested", len(raw_orders))
        logger.info(f"Source 2 (API): Ingested {len(raw_orders)} raw order records.")

        total_ingested = len(raw_customers) + len(raw_orders)
        metrics.record_count("total_records_ingested", total_ingested)
        metrics.stop_phase("1_ingestion")

        # Phase 2: Validation & Business Rules
        metrics.start_phase("2_validation")
        logger.info("Phase 2: Validating schemas and applying business rules...")

        valid_customers: List[Dict[str, Any]] = []
        valid_customer_ids: Set[str] = set()

        for raw_c in raw_customers:
            val_result = BusinessRuleValidator.validate_customer(raw_c)
            if val_result.is_valid:
                valid_customers.append(val_result.record_data)
                valid_customer_ids.add(val_result.record_id)
            else:
                self.quarantine_manager.record_quarantine(val_result)

        cust_quarantined = len(raw_customers) - len(valid_customers)
        metrics.record_count("customers_valid", len(valid_customers))
        metrics.record_count("customers_quarantined", cust_quarantined)

        valid_orders: List[Dict[str, Any]] = []
        for raw_o in raw_orders:
            val_result = BusinessRuleValidator.validate_order(
                record=raw_o,
                known_valid_customer_ids=valid_customer_ids
            )
            if val_result.is_valid:
                valid_orders.append(val_result.record_data)
            else:
                self.quarantine_manager.record_quarantine(val_result)

        ord_quarantined = len(raw_orders) - len(valid_orders)
        metrics.record_count("orders_valid", len(valid_orders))
        metrics.record_count("orders_quarantined", ord_quarantined)

        total_quarantined = cust_quarantined + ord_quarantined
        metrics.record_count("total_quarantined", total_quarantined)
        metrics.stop_phase("2_validation")

        # Phase 3: Quarantine Persistence
        metrics.start_phase("3_quarantine_export")
        if total_quarantined > 0:
            quarantine_csv = self.quarantine_manager.persist_to_disk(run_id=run_id)
            logger.warning(
                f"Phase 3: Persisted {total_quarantined} invalid records to quarantine store at {quarantine_csv.name}"
            )
        metrics.stop_phase("3_quarantine_export")

        # Phase 4: Dimensional Transformation
        metrics.start_phase("4_transformation")
        logger.info("Phase 4: Transforming validated records into Kimball Star Schema dimensions & facts...")

        dim_products = self.transformer.transform_products(PRODUCT_CATALOG)
        prod_key_lookup = {p["product_id"]: p["product_key"] for p in dim_products}

        dim_customers = self.transformer.transform_customers(valid_customers)
        cust_key_lookup = {c["customer_id"]: c["customer_key"] for c in dim_customers}

        fact_orders, fact_items, dim_dates = self.transformer.transform_orders_and_items(
            valid_orders=valid_orders,
            customer_key_lookup=cust_key_lookup,
            product_key_lookup=prod_key_lookup
        )

        metrics.record_count("order_items_loaded", len(fact_items))
        metrics.stop_phase("4_transformation")

        # Phase 5: Transactional Idempotent Loading
        metrics.start_phase("5_warehouse_loading")
        logger.info("Phase 5: Loading dimensional star schema into database warehouse...")

        with get_db_session() as session:
            p_ins, p_upd = self.loader.load_products(session, dim_products)
            c_ins, c_upd, c_unch = self.loader.load_customers(session, dim_customers)
            d_ins = self.loader.load_date_dimension(session, dim_dates)
            o_ins, o_upd, o_unch = self.loader.load_orders_and_items(session, fact_orders, fact_items)

            quarantine_list = self.quarantine_manager.get_records()
            q_loaded = self.loader.load_quarantine_records(session, run_id, quarantine_list)

            total_loaded = len(dim_customers) + len(fact_orders)
            metrics.record_count("total_records_loaded", total_loaded)

            end_time_utc = datetime.now(timezone.utc)
            duration_total = round(time.perf_counter() - start_time_perf, 4)
            summary_dict = metrics.get_summary(duration_total)

            self.loader.record_pipeline_run(
                session=session,
                run_id=run_id,
                pipeline_name="datapulse_ecommerce_pipeline",
                start_time=start_time_utc,
                end_time=end_time_utc,
                status="SUCCESS",
                records_ingested=total_ingested,
                valid_records_loaded=total_loaded,
                quarantined_records=total_quarantined,
                details_json=json.dumps(summary_dict)
            )

        metrics.stop_phase("5_warehouse_loading")

        logger.info("==================================================")
        logger.info(f"Pipeline Run {run_id} Completed Successfully!")
        logger.info(f"Duration: {duration_total}s | Ingested: {total_ingested} | Loaded: {total_loaded} | Quarantined: {total_quarantined}")
        logger.info("==================================================")

        return PipelineExecutionResult(
            run_id=run_id,
            status="SUCCESS",
            start_time=start_time_utc,
            end_time=end_time_utc,
            duration_seconds=duration_total,
            total_ingested=total_ingested,
            total_loaded=total_loaded,
            total_quarantined=total_quarantined,
            metrics_summary=summary_dict,
            quarantine_summary=self.quarantine_manager.get_summary()
        )
