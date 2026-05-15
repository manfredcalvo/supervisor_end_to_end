# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Document Processing Pipeline
# MAGIC
# MAGIC Uses **Auto Loader** to incrementally process PDF files from a Unity Catalog Volume.
# MAGIC Only files added since the last run are processed; existing chunks are preserved.
# MAGIC Each file is parsed with `ai_parse_document`, chunked with `ai_prep_search`, language-
# MAGIC classified with `ai_classify`, and translated to Spanish with `ai_translate` if needed.
# MAGIC
# MAGIC **Output:** `<catalog>.<schema>.documents_<topic>` — all chunks normalized to Spanish.
# MAGIC **Checkpoint:** stored in `<volume>/_checkpoint/documents_<topic>` (auto-excluded from PDF scan).

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
# When running interactively, set the widgets manually or edit the defaults below.
dbutils.widgets.text("catalog", "<catalog>")
dbutils.widgets.text("schema",  "<schema>")
dbutils.widgets.text("volume",  "<volume>")
dbutils.widgets.text("topic",   "<topic>")

CATALOG         = dbutils.widgets.get("catalog")
SCHEMA          = dbutils.widgets.get("schema")
VOLUME          = dbutils.widgets.get("volume")
TOPIC           = dbutils.widgets.get("topic")
VOLUME_PATH     = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{TOPIC}/"
OUTPUT_TABLE    = f"{CATALOG}.{SCHEMA}.documents_{TOPIC}"
CHECKPOINT_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/_checkpoint/documents_{TOPIC}"

print(f"Source volume   : {VOLUME_PATH}")
print(f"Output table    : {OUTPUT_TABLE}")
print(f"Checkpoint path : {CHECKPOINT_PATH}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Create output table (if it doesn't exist)
# MAGIC
# MAGIC Explicit schema + CDF enabled up front so notebook 02 can create the vector search
# MAGIC index against this table immediately after the first run.

# COMMAND ----------

spark.sql("""
CREATE TABLE IF NOT EXISTS IDENTIFIER(:tbl) (
    doc_path          STRING,
    chunk_id          STRING,
    chunk_text_es     STRING,
    chunk_to_retrieve STRING,
    original_language STRING
) USING DELTA
TBLPROPERTIES (
    'delta.enableChangeDataFeed'          = 'true',
    'delta.deletedFileRetentionDuration'  = 'interval 30 days'
)
""", args={"tbl": OUTPUT_TABLE})

print(f"Table ready: {OUTPUT_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Define per-batch processing function
# MAGIC
# MAGIC Auto Loader calls this function for each micro-batch of new files.
# MAGIC The SQL CTE chain is identical to the original batch pipeline.

# COMMAND ----------

def process_batch(batch_df, batch_id):
    if batch_df.isEmpty():
        print(f"Batch {batch_id}: no new files — skipping.")
        return

    file_count = batch_df.count()
    print(f"Batch {batch_id}: processing {file_count} new file(s)...")

    batch_df.select("path", "content").createOrReplaceTempView("raw_files")

    spark.sql("""
    INSERT INTO IDENTIFIER(:tbl)

    WITH

    parsed AS (
      SELECT
        path                       AS doc_path,
        ai_parse_document(content) AS parsed_content
      FROM raw_files
    ),

    chunked AS (
      SELECT
        doc_path,
        chunk.chunk_id          AS chunk_id,
        chunk.chunk_to_embed    AS chunk_to_embed,
        chunk.chunk_to_retrieve AS chunk_to_retrieve
      FROM parsed
      LATERAL VIEW EXPLODE(
        ai_prep_search(parsed_content):document:contents
        ::ARRAY<STRUCT<chunk_id:STRING, chunk_to_embed:STRING, chunk_to_retrieve:STRING>>
      ) AS chunk
    ),

    classified AS (
      SELECT
        doc_path,
        chunk_id,
        chunk_to_embed,
        chunk_to_retrieve,
        ai_classify(chunk_to_embed, ARRAY('English', 'Spanish')) AS original_language
      FROM chunked
    )

    SELECT
      doc_path,
      chunk_id,
      CASE
        WHEN original_language = 'English' THEN ai_translate(chunk_to_embed, 'es')
        ELSE chunk_to_embed
      END AS chunk_text_es,
      chunk_to_retrieve,
      original_language
    FROM classified
    """, args={"tbl": OUTPUT_TABLE})

    print(f"Batch {batch_id}: done — {file_count} file(s) appended to {OUTPUT_TABLE}.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Run Auto Loader
# MAGIC
# MAGIC `trigger(availableNow=True)` processes all files discovered since the last checkpoint
# MAGIC in one shot, then the stream stops — equivalent to a batch job.

# COMMAND ----------

query = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "binaryFile")
    .option("cloudFiles.schemaLocation", CHECKPOINT_PATH + "/schema")
    .option("pathGlobFilter", "*.pdf")
    .option("recursiveFileLookup", "true")
    .load(VOLUME_PATH)
    .writeStream
    .trigger(availableNow=True)
    .option("checkpointLocation", CHECKPOINT_PATH)
    .foreachBatch(process_batch)
    .start()
)

query.awaitTermination()
print(f"\nDone — all new PDF files processed and appended to {OUTPUT_TABLE}.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Quick sanity check

# COMMAND ----------

summary = spark.sql("""
SELECT
  original_language,
  COUNT(*) AS chunk_count
FROM IDENTIFIER(:tbl)
GROUP BY original_language
ORDER BY chunk_count DESC
""", args={"tbl": OUTPUT_TABLE})

summary.show()
