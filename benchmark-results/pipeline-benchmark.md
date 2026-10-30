# DataPulse Pipeline Performance Benchmark

- **Run timestamp:** 2026-10-30T16:22:54.465533+00:00
- **Python:** 3.12.10
- **Platform:** Windows-10-10.0.19045-SP0
- **Processor:** Intel64 Family 6 Model 142 Stepping 9, GenuineIntel
- **Database:** SQLite (2.1.6)
- **Repeats per warehouse-load variant:** 1
- **Memory:** peak process working set sampled during benchmark, where supported.

## Results

The requested size is the combined number of customer and order source records. Each order has one line item. Stage timings are measured once on the same deterministic input; each loader variant uses a fresh SQLite database. Total time is the sum of those stages and the measured load time.

| Source records | Variant | Ingestion (s) | Validation (s) | Transformation (s) | Warehouse load (s) | Total (s) | Records/s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1,000 | baseline | 0.0725 | 0.0759 | 0.0425 | 3.0294 | 3.2203 | 310.53 |
| 1,000 | optimized | 0.0725 | 0.0759 | 0.0425 | 1.1888 | 1.3797 | 724.78 |
| 1,000 | speedup (baseline / optimized) | — | — | — | 2.55x | 2.33x | — |
| 10,000 | baseline | 0.4803 | 0.6964 | 0.4137 | 21.2645 | 22.8547 | 437.55 |
| 10,000 | optimized | 0.4803 | 0.6964 | 0.4137 | 4.3643 | 5.9546 | 1679.37 |
| 10,000 | speedup (baseline / optimized) | — | — | — | 4.87x | 3.84x | — |
| 100,000 | baseline | 4.3529 | 6.4621 | 4.2764 | 220.3115 | 235.4028 | 424.80 |
| 100,000 | optimized | 4.3529 | 6.4621 | 4.2764 | 33.6247 | 48.7161 | 2052.71 |
| 100,000 | speedup (baseline / optimized) | — | — | — | 6.55x | 4.83x | — |

## Findings and method

- **Optimization:** batched primary-key lookups and `Session.add_all` replaced a per-row `Session.get` plus `Session.merge` in the warehouse loader. Existing records are still compared and updated in place; unchanged/inserted/updated counters are preserved.
- **Why it helps:** it reduces database round trips from one lookup per record to bounded `IN` queries (up to 500 keys each), and stages new rows together for SQLAlchemy's executemany behavior.
- **Baseline bottleneck:** the slowest measured baseline stage is listed below for the largest input. The comparison isolates warehouse loading; ingestion, validation, and transformation timings are shared for both totals.
- **Ingestion scope:** customer CSV reading is real; order response parsing/enrichment uses deterministic in-process pages and does not measure HTTP transport or a public API.
- **Limits:** totals exclude synthetic data generation, database schema creation, network transport, quarantine export, and audit persistence. The order source is represented by deterministic in-process pages; each order has one line item. A single repeat is sensitive to system noise; use `--repeats 3` or more for a more stable median.
- **Memory limitation:** process peak working-set memory is a high-water mark across both variants and dataset preparation, not per-stage or per-variant allocation. It is `null` on platforms without the sampler.
- **Reproduction:** `python scripts/benchmark_performance.py` (optional: `--sizes 1000 10000 100000 --repeats 1`).

### Bottleneck evidence
- At 100,000 source records, baseline **warehouse loading** was the slowest stage at 220.3115s (93.6% of measured total).

## Dataset reproducibility

- 1,000 source records: `38fdb0fb98171dde910606a6d101a2be31e05f7645751b0091a0058924e4fdb8`
- 10,000 source records: `fcaae7d5f3a37190cdc42bbaa779a74412e9641f65b8657ce02e06b522a5e6b8`
- 100,000 source records: `1f75f0e9e40645d1577ec7fde7f56542c4eb1efd2a814ae14538935fe3ee2860`

Peak sampled process working set: 849.9 MiB.
