# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Create Knowledge Assistant
# MAGIC
# MAGIC Creates (or reuses) a Databricks Knowledge Assistant backed by the Delta Sync
# MAGIC vector search index produced by `02_create_vector_index`.
# MAGIC
# MAGIC **SDK:** `databricks.sdk.service.knowledgeassistants`

# COMMAND ----------

%pip install -r ./requirements.txt -q
dbutils.library.restartPython()

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
# When running interactively, set the widgets manually or edit the defaults below.
dbutils.widgets.text("catalog",      "<catalog>")
dbutils.widgets.text("schema",       "<schema>")
dbutils.widgets.text("topic",        "<topic>")
dbutils.widgets.text("config_file",  "./config/ka_fuerzas.yaml")
dbutils.widgets.text("retrieve_col", "chunk_text_es")

CATALOG     = dbutils.widgets.get("catalog")
SCHEMA      = dbutils.widgets.get("schema")
TOPIC       = dbutils.widgets.get("topic")
CONFIG_FILE = dbutils.widgets.get("config_file")

import yaml

with open(CONFIG_FILE) as f:
    ka_config = yaml.safe_load(f)

KA_NAME         = ka_config["display_name"]
KA_DESCRIPTION  = ka_config["description"]
KA_INSTRUCTIONS = ka_config["instructions"]
INDEX_NAME  = f"{CATALOG}.{SCHEMA}.documents_{TOPIC}_index"
TEXT_COL    = dbutils.widgets.get("retrieve_col")
DOC_URI_COL = "doc_path"

print(f"Index      : {INDEX_NAME}")
print(f"KA name    : {KA_NAME}")
print(f"Text col   : {TEXT_COL}")
print(f"Doc URI col: {DOC_URI_COL}")
print(f"[v2] retrieve_col widget loaded: {TEXT_COL}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Create (or reuse) the Knowledge Assistant

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.knowledgeassistants import (
    KnowledgeAssistant,
    KnowledgeSource,
    IndexSpec,
)
import time

w = WorkspaceClient()

existing_kas = {ka.display_name: ka for ka in w.knowledge_assistants.list_knowledge_assistants()}

if KA_NAME in existing_kas:
    ka = existing_kas[KA_NAME]
    ka_id = ka.id
    print(f"KA already exists — id: {ka_id}, state: {ka.state}")
else:
    ka = w.knowledge_assistants.create_knowledge_assistant(
        KnowledgeAssistant(
            display_name=KA_NAME,
            description=KA_DESCRIPTION,
            instructions=KA_INSTRUCTIONS,
        )
    )
    ka_id = ka.id
    print(f"KA created — id: {ka_id}, state: {ka.state}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Wait for ACTIVE state

# COMMAND ----------

MAX_WAIT_SECONDS = 300
POLL_INTERVAL    = 10

start = time.time()
while True:
    ka = w.knowledge_assistants.get_knowledge_assistant(name=f"knowledge-assistants/{ka_id}")
    state = ka.state.value if ka.state else "UNKNOWN"
    print(f"  KA state: {state}")
    if state == "ACTIVE":
        print(f"KA is ACTIVE: {ka_id}")
        break
    if state == "FAILED":
        raise RuntimeError(f"KA creation failed: {ka.error_info}")
    elapsed = time.time() - start
    if elapsed > MAX_WAIT_SECONDS:
        print(f"Timed out after {MAX_WAIT_SECONDS}s — check status in the Databricks UI.")
        break
    time.sleep(POLL_INTERVAL)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Attach vector search index as knowledge source

# COMMAND ----------

existing_sources = {
    ks.display_name: ks
    for ks in w.knowledge_assistants.list_knowledge_sources(
        parent=f"knowledge-assistants/{ka_id}"
    )
}

SOURCE_DISPLAY_NAME = INDEX_NAME

if SOURCE_DISPLAY_NAME in existing_sources:
    print(f"Knowledge source already exists — skipping.")
else:
    ks = w.knowledge_assistants.create_knowledge_source(
        parent=f"knowledge-assistants/{ka_id}",
        knowledge_source=KnowledgeSource(
            display_name=SOURCE_DISPLAY_NAME,
            description=KA_DESCRIPTION,
            source_type="index",
            index=IndexSpec(
                index_name=INDEX_NAME,
                text_col=TEXT_COL,
                doc_uri_col=DOC_URI_COL,
            ),
        ),
    )
    print(f"Knowledge source created — id: {ks.id}, state: {ks.state}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Print summary

# COMMAND ----------

ka = w.knowledge_assistants.get_knowledge_assistant(name=f"knowledge-assistants/{ka_id}")
print(f"\nKnowledge Assistant ready.")
print(f"  display_name  : {ka.display_name}")
print(f"  id            : {ka.id}")
print(f"  endpoint_name : {ka.endpoint_name}")
print(f"  state         : {ka.state}")
print(f"\nTo use this KA in the app, set serving_endpoint_name = '{ka.endpoint_name}' in databricks.yml")

# Pass the actual display name to the create_supervisor task so it can look up this KA
# regardless of what name was configured in the YAML.
dbutils.jobs.taskValues.set(key="ka_display_name", value=ka.display_name)
