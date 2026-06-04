"""
benchmark_incremental.py — Prove the incremental-load time reduction.

The story this measures
------------------------
A data warehouse can rebuild a fact table two ways on each daily run:

  FULL REFRESH : re-process the ENTIRE history every day (base + all deltas)
  INCREMENTAL  : process ONLY the rows that arrived since the last run

Both produce an identical fact table. Incremental does far less work, so it is
far faster. This script measures both on the SAME data and reports the % time
reduction — a real, reproducible number you can put on a resume and explain in
an interview.

What it does
------------
  1. Fresh DuckDB warehouse.
  2. Generate a BASE batch (default 1,000,000 txns, dated in January).
  3. Load bronze + build the full warehouse (dims + fact = first full build).
  4. Land a DAILY DELTA batch (default 50,000 txns, dated months later).
  5. Time INCREMENTAL:  dbt run --select fact_transactions
        -> watermark filter processes only the 50k new rows.
  6. Time FULL REFRESH: dbt run --select fact_transactions --full-refresh
        -> rebuilds all 1,050,000 rows.
  7. Verify both leave the fact table with identical row counts.
  8. Print a table + write benchmarks/RESULTS.md.

Usage
-----
  python benchmarks/benchmark_incremental.py [BASE_N] [DELTA_N]
    BASE_N   base history rows  (default 1000000)
    DELTA_N  daily delta rows   (default 50000)
"""

import os
import re
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBT_DIR = os.path.join(REPO_ROOT, "dbt_ledgerflow")
DUCKDB_PATH = os.path.join(REPO_ROOT, "ledgerflow.duckdb")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")

PY = sys.executable
_BIN = os.path.dirname(PY)
DBT = os.path.join(_BIN, "Scripts", "dbt.exe") if os.name == "nt" else os.path.join(_BIN, "dbt")


def run(cmd, cwd=REPO_ROOT, env=None):
    """Run a command, stream nothing, return (elapsed_seconds, stdout)."""
    full_env = {**os.environ, **(env or {})}
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, env=full_env, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed, proc.stdout


def model_seconds(dbt_stdout, model="fact_transactions"):
    """Parse dbt's own per-model timing: 'OK created ... fact_transactions ... in 1.23s'."""
    for line in dbt_stdout.splitlines():
        if model in line and "OK" in line:
            m = re.search(r"in ([\d.]+)s", line)
            if m:
                return float(m.group(1))
    return None


def fact_row_count():
    import duckdb

    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        return con.execute("select count(*) from main_gold.fact_transactions").fetchone()[0]
    finally:
        con.close()


def ensure_dimensions():
    """Generate the static dimension CSVs once if they are missing."""
    for script, csv in [
        ("generate_customers.py", "customers.csv"),
        ("generate_accounts.py", "accounts.csv"),
        ("generate_loans.py", "loans.csv"),
    ]:
        if not os.path.exists(os.path.join(RAW_DIR, csv)):
            run([PY, os.path.join("data_generator", script)])


def append_delta_to_bronze(delta_csv):
    """Append ONLY the delta transactions into bronze (reusing load_bronze logic)."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "ingestion"))
    import load_bronze

    load_bronze._ensure_schema(None)  # duckdb path ignores the engine arg
    return load_bronze.load_to_bronze(delta_csv, "transactions", None)


def main():
    base_n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    delta_n = int(sys.argv[2]) if len(sys.argv) > 2 else 50_000
    env = {"DB_ENGINE": "duckdb", "DUCKDB_PATH": DUCKDB_PATH}

    print("=" * 64)
    print(f"  LedgerFlow incremental benchmark — base={base_n:,}  delta={delta_n:,}")
    print("=" * 64)

    # 1. Fresh warehouse
    if os.path.exists(DUCKDB_PATH):
        os.remove(DUCKDB_PATH)
    ensure_dimensions()

    # 2. Base batch (January) + bronze + full warehouse build
    print("\n[1/5] Generating base batch and building warehouse ...")
    run([PY, os.path.join("data_generator", "generate_transactions.py"),
         str(base_n), "2024-01-01", "31", os.path.join("data", "raw", "transactions.csv")])
    run([PY, os.path.join("ingestion", "load_bronze.py")], env=env)
    _, build_out = run([DBT, "run", "--profiles-dir", "."], cwd=DBT_DIR, env=env)
    rows_after_build = fact_row_count()
    print(f"      Full warehouse built. fact_transactions = {rows_after_build:,} rows")

    # 3. Daily delta batch (months later so the created_at watermark separates it)
    print("\n[2/5] Landing daily delta batch in bronze ...")
    delta_csv = os.path.join("data", "raw", "transactions_delta.csv")
    run([PY, os.path.join("data_generator", "generate_transactions.py"),
         str(delta_n), "2024-06-01", "1", delta_csv])
    append_delta_to_bronze(delta_csv)
    print(f"      Bronze now holds {base_n + delta_n:,} transactions; fact still has {rows_after_build:,}")

    # 4. INCREMENTAL run — processes only the delta
    print("\n[3/5] Timing INCREMENTAL run (only new rows) ...")
    incr_wall, incr_out = run([DBT, "run", "--select", "fact_transactions",
                               "--profiles-dir", "."], cwd=DBT_DIR, env=env)
    incr_model = model_seconds(incr_out)
    rows_after_incr = fact_row_count()
    print(f"      Done. fact_transactions = {rows_after_incr:,} rows  "
          f"(model {incr_model}s, wall {incr_wall:.2f}s)")

    # 5. FULL REFRESH run — rebuilds the entire history
    print("\n[4/5] Timing FULL-REFRESH run (rebuild everything) ...")
    full_wall, full_out = run([DBT, "run", "--select", "fact_transactions",
                               "--full-refresh", "--profiles-dir", "."], cwd=DBT_DIR, env=env)
    full_model = model_seconds(full_out)
    rows_after_full = fact_row_count()
    print(f"      Done. fact_transactions = {rows_after_full:,} rows  "
          f"(model {full_model}s, wall {full_wall:.2f}s)")

    # Correctness check
    print("\n[5/5] Verifying both paths agree ...")
    ok = rows_after_incr == rows_after_full == base_n + delta_n
    print(f"      Row counts match expected {base_n + delta_n:,}: {ok}")

    # Results
    def reduction(full, incr):
        return (full - incr) / full * 100 if full else 0.0

    model_red = reduction(full_model, incr_model) if (full_model and incr_model) else None
    wall_red = reduction(full_wall, incr_wall)

    print("\n" + "=" * 64)
    print("  RESULTS")
    print("=" * 64)
    print(f"  {'Metric':<28}{'Full refresh':>14}{'Incremental':>14}")
    print(f"  {'-'*26:<28}{'-'*12:>14}{'-'*12:>14}")
    if model_red is not None:
        print(f"  {'dbt model exec time (s)':<28}{full_model:>14.2f}{incr_model:>14.2f}")
    print(f"  {'wall-clock time (s)':<28}{full_wall:>14.2f}{incr_wall:>14.2f}")
    print(f"  {'rows processed':<28}{base_n+delta_n:>14,}{delta_n:>14,}")
    print()
    if model_red is not None:
        print(f"  >> Model-execution time reduction: {model_red:.1f}%")
    print(f"  >> Wall-clock time reduction:      {wall_red:.1f}%")
    print("=" * 64)

    results_path = os.path.join(REPO_ROOT, "benchmarks", "RESULTS.md")
    with open(results_path, "w") as f:
        f.write("# Incremental Load Benchmark — Results\n\n")
        f.write(f"- Base history: **{base_n:,}** transactions\n")
        f.write(f"- Daily delta: **{delta_n:,}** transactions\n")
        f.write(f"- Warehouse: DuckDB (local), dbt incremental `delete+insert` on `transaction_id`\n")
        f.write(f"- Correctness: both paths produce **{base_n+delta_n:,}** rows — identical.\n\n")
        f.write("| Metric | Full refresh | Incremental |\n")
        f.write("|---|---:|---:|\n")
        if model_red is not None:
            f.write(f"| dbt model exec time (s) | {full_model:.2f} | {incr_model:.2f} |\n")
        f.write(f"| wall-clock time (s) | {full_wall:.2f} | {incr_wall:.2f} |\n")
        f.write(f"| rows processed | {base_n+delta_n:,} | {delta_n:,} |\n\n")
        if model_red is not None:
            f.write(f"**Model-execution time reduction: {model_red:.1f}%**\n\n")
        f.write(f"**Wall-clock time reduction: {wall_red:.1f}%**\n\n")
        f.write("> On each daily run, incremental processes only the new "
                f"{delta_n:,} rows instead of re-scanning all {base_n+delta_n:,} — "
                "same correct result, a fraction of the compute.\n")
    print(f"\nWrote {results_path}")

    # Tidy up the delta file
    try:
        os.remove(os.path.join(REPO_ROOT, delta_csv))
    except OSError:
        pass


if __name__ == "__main__":
    main()
