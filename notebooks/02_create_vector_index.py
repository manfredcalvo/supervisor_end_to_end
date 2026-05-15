# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Create Vector Search Index
# MAGIC
# MAGIC Creates (or re-syncs) a Delta Sync vector search index over the Spanish-normalized
# MAGIC documents table produced by `01_process_documents`.
# MAGIC
# MAGIC **Embedding model:** `databricks-agent-bricks-embedding-v1`

# COMMAND ----------

# Install the Vector Search client library (not bundled in the serverless runtime)
%pip install databricks-vectorsearch -q
dbutils.library.restartPython()

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
# When running interactively, set the widgets manually or edit the defaults below.
dbutils.widgets.text("catalog",                "<catalog>")
dbutils.widgets.text("schema",                 "<schema>")
dbutils.widgets.text("vector_search_endpoint", "<vector_search_endpoint>")
dbutils.widgets.text("topic",                  "<topic>")
dbutils.widgets.text("embedding_col",          "chunk_text_es")

CATALOG         = dbutils.widgets.get("catalog")
SCHEMA          = dbutils.widgets.get("schema")
VS_ENDPOINT     = dbutils.widgets.get("vector_search_endpoint")
TOPIC           = dbutils.widgets.get("topic")
OUTPUT_TABLE    = f"{CATALOG}.{SCHEMA}.documents_{TOPIC}"
INDEX_NAME      = f"{CATALOG}.{SCHEMA}.documents_{TOPIC}_index"
EMBEDDING_MODEL = "databricks-agent-bricks-embedding-v1"
PRIMARY_KEY     = "chunk_id"
EMBEDDING_COL   = dbutils.widgets.get("embedding_col")

print(f"Source table     : {OUTPUT_TABLE}")
print(f"Index name       : {INDEX_NAME}")
print(f"VS endpoint      : {VS_ENDPOINT}")
print(f"Embedding model  : {EMBEDDING_MODEL}")
print(f"Embedding col    : {EMBEDDING_COL}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Ensure the source table has Change Data Feed enabled
# MAGIC
# MAGIC Delta Sync indexes require CDF on the source table.

# COMMAND ----------

spark.sql("""
ALTER TABLE IDENTIFIER(:tbl)
SET TBLPROPERTIES (
    'delta.enableChangeDataFeed'         = 'true',
    'delta.deletedFileRetentionDuration' = 'interval 30 days'
)
""", args={"tbl": OUTPUT_TABLE})

print("CDF and 30-day file retention enabled on source table.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Create the Vector Search endpoint if it does not exist

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

existing_endpoints = {ep["name"] for ep in vsc.list_endpoints().get("endpoints", [])}

if VS_ENDPOINT not in existing_endpoints:
    try:
        print(f"Creating Vector Search endpoint: {VS_ENDPOINT}")
        vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
        print(f"Endpoint created and ready: {VS_ENDPOINT}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"Endpoint already exists (created by a parallel task) — continuing.")
        else:
            raise
else:
    print(f"Endpoint already exists: {VS_ENDPOINT}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Create or re-sync the vector search index

# COMMAND ----------

existing_indexes = {idx["name"] for idx in vsc.list_indexes(VS_ENDPOINT).get("vector_indexes", [])}

if INDEX_NAME not in existing_indexes:
    print(f"Creating new index: {INDEX_NAME}")
    vsc.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=INDEX_NAME,
        source_table_name=OUTPUT_TABLE,
        pipeline_type="TRIGGERED",
        primary_key=PRIMARY_KEY,
        embedding_source_column=EMBEDDING_COL,
        embedding_model_endpoint_name=EMBEDDING_MODEL,
    )
    print("Index created — initial sync will start automatically.")
else:
    print(f"Index already exists — triggering re-sync: {INDEX_NAME}")
    vsc.get_index(VS_ENDPOINT, INDEX_NAME).sync()
    print("Re-sync triggered.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Wait for the index to be ready and print status

# COMMAND ----------

import time

MAX_WAIT_SECONDS = 600
POLL_INTERVAL    = 15

start = time.time()
while True:
    idx = vsc.get_index(VS_ENDPOINT, INDEX_NAME)
    status = idx.describe().get("status", {})
    print(f"  Index status: {status}")
    if status.get("ready"):
        print(f"Index is READY: {INDEX_NAME}")
        break
    elapsed = time.time() - start
    if elapsed > MAX_WAIT_SECONDS:
        print(f"Timed out after {MAX_WAIT_SECONDS}s — check status in the Databricks UI.")
        break
    time.sleep(POLL_INTERVAL)
