# DataPulse Performance Benchmark Report

## Summary

This report records an A/B benchmark of the former per-row ORM loader and the
batched primary-key-prefetch loader. It measured customer CSV ingestion,
in-process paginated order response parsing, record validation, dimensional
transformation, and warehouse loading on the same deterministic input.

The largest tested data set contained **100,000 source records**: 50,000
customers and 50,000 orders, with one line per order. In that run, loading
changed from **220.3115 seconds** to **33.6247 seconds**; measured total stage
time changed from **235.4028 seconds** to **48.7161 seconds**. These measurements
are specific to the environment below and are not a production throughput
guarantee.

## Benchmark environment

| Property | Recorded value |
|---|---|
| Date/time | 2026-10-30 16:22:54 UTC |
| Python | 3.12.10 |
| Platform | Windows 10, build 19045 |
| Processor string | Intel64 Family 6 Model 142 Stepping 9 |
| SQLAlchemy | 2.1.6 |
| Database | SQLite |
| Repeats | 1 per loader and size |
| Peak sampled process working set | 849.9 MiB |

Machine load and runtime variance can affect timings. Repeat runs should be
performed before using these figures for capacity or release decisions.

## Results

| Source records | Loader | Ingestion (s) | Validation (s) | Transformation (s) | Warehouse load (s) | Measured total (s) | Records/s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1,000 | Baseline | 0.0725 | 0.0759 | 0.0425 | 3.0294 | 3.2203 | 310.53 |
| 1,000 | Batched | 0.0725 | 0.0759 | 0.0425 | 1.1888 | 1.3797 | 724.78 |
| 1,000 | Baseline / batched speedup | — | — | — | 2.55x | 2.33x | — |
| 10,000 | Baseline | 0.4803 | 0.6964 | 0.4137 | 21.2645 | 22.8547 | 437.55 |
| 10,000 | Batched | 0.4803 | 0.6964 | 0.4137 | 4.3643 | 5.9546 | 1,679.37 |
| 10,000 | Baseline / batched speedup | — | — | — | 4.87x | 3.84x | — |
| 100,000 | Baseline | 4.3529 | 6.4621 | 4.2764 | 220.3115 | 235.4028 | 424.80 |
| 100,000 | Batched | 4.3529 | 6.4621 | 4.2764 | 33.6247 | 48.7161 | 2,052.71 |
| 100,000 | Baseline / batched speedup | — | — | — | 6.55x | 4.83x | — |

The recorded JSON, including exact floating-point timings and source-data hashes,
is [`../benchmark-results/pipeline-benchmark.json`](../benchmark-results/pipeline-benchmark.json).

## What was measured

- **Ingestion:** actual CSV read and deterministic order response parsing and
  metadata enrichment. The order pages are synthesized in process and exercise
  the ingestor's pagination/record parser without an HTTP server or public
  network.
- **Validation:** per-record Pydantic and `BusinessRuleValidator` validation for
  generated customer and order payloads.
- **Transformation:** customer/product/order/line/date mapping through
  `DimensionalTransformer`.
- **Warehouse load:** product, customer, date, and order/order-line fact loading
  and commit in a fresh SQLite database for each loader run.
- **Measured total:** sum of the above stage measurements; database schema
  creation is excluded.
- **Throughput:** combined source-record count divided by measured total seconds.
- **Memory:** peak process working set sampled on Windows. The 849.9 MiB value
  is a high-water mark spanning dataset preparation and both loader variants,
  not incremental or per-stage memory.

Input data are deterministic for each size. SHA-256 hashes are included in the
JSON artifact for verification.

## Bottleneck and optimization

At 100,000 records, baseline warehouse loading was the slowest stage and
accounted for **93.6%** of measured baseline total time. The previous loader
issued a `Session.get` per row, then used `Session.merge` for new or changed
rows.

The optimized `_merge_rows` now:

1. Collects unique primary keys for a model.
2. Fetches existing rows using `IN` queries in batches of at most 500 keys.
3. Compares incoming values with existing values in memory.
4. Updates changed ORM objects in place and adds new objects with `Session.add_all`.
5. Keeps the existing inserted/updated/unchanged count contract.

The optimization reduced individual lookup round trips and enabled SQLAlchemy to
group insert work. In this recorded run, the measured warehouse load was 6.55x
faster at 100k and the measured stage total was 4.83x faster. Single-repeat
measurements should be treated as evidence from this run, not a statistically
stable expected speedup.

## Surrogate-key issue found at scale

The initial 32-bit hash-derived customer key space produced a duplicate primary
key for the 50,000-customer benchmark dataset, so the first 100k attempt could
not load. The dimensional transformer and ORM/schema now use positive 63-bit
hashed keys for customer, product, order, and order-line keys; date keys remain
`YYYYMMDD`. A PostgreSQL migration is provided at
[`../sql/migrations/02_expand_surrogate_keys_to_bigint.sql`](../sql/migrations/02_expand_surrogate_keys_to_bigint.sql).
The expanded key range makes hash collisions much less likely but does not make
them mathematically impossible.

## Reproduce

From the repository root:

```powershell
python scripts/benchmark_performance.py
```

This runs all requested sizes and writes:

- `benchmark-results/pipeline-benchmark.json`
- `benchmark-results/pipeline-benchmark.md`

Run fewer sizes or use repeated load timings (median is reported):

```powershell
python scripts/benchmark_performance.py --sizes 1000 10000 --repeats 3
```

`--output <path>` changes the JSON destination; the Markdown report uses the
same path with an `.md` suffix.

## Limitations

- SQLite is not PostgreSQL; query planning, concurrency, storage, and bulk-load
  behavior differ.
- Synthetic data has one line item per order in this benchmark; real-world
  nesting and distributions can change memory and transformation cost.
- Ingestion excludes network latency, serialization over HTTP, and source
  service initialization.
- Totals exclude data generation, schema creation, quarantine export, and
  pipeline audit persistence.
- Baseline/optimized comparison uses one repeat in the committed report. For
  stable conclusions, rerun with multiple repeats on an otherwise idle machine.
- Memory is only a single process working-set high-water mark; memory per stage
  and per loader is not isolated.
- The baseline exists in the benchmark script for comparison; it is not the
  active application loader.
