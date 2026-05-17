# Airflow image with LedgerFlow pipeline dependencies baked in.
#
# Built by: CI (on merge to main) and aws/ecr_push.sh (manual)
# Pushed to: AWS ECR repository ledgerflow-airflow
# Used by:   ECS Fargate task (Step 8)
#
# Why extend the official image instead of starting from scratch:
#   The official apache/airflow image has Airflow pre-installed with the right
#   Python version, user permissions, and entrypoint scripts. We just add our
#   pipeline dependencies on top.

FROM apache/airflow:2.9.1

USER root

# Install system packages needed by psycopg2 and dbt-postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copy requirements first for better Docker layer caching:
# If only DAG code changes, pip install is skipped (cached layer).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the full repo into the container
COPY --chown=airflow:root . /opt/airflow/repo

# Copy DAG files to Airflow's dag folder
COPY --chown=airflow:root airflow/dags/ /opt/airflow/dags/

# Set the working directory to the repo root
WORKDIR /opt/airflow/repo
