# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Create Knowledge Assistant from Files in a Volume
# MAGIC
# MAGIC Creates (or reuses) a Databricks Knowledge Assistant backed directly by PDF files
# MAGIC stored in a Unity Catalog Volume (`source_type="files"`).
# MAGIC
# MAGIC This approach skips the AI Functions processing and Vector Search index creation
# MAGIC steps — Databricks handles embedding and retrieval automatically.
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
dbutils.widgets.text("volume_name",  "<volume_name>")
dbutils.widgets.text("topic",        "data_management")
dbutils.widgets.text("config_file",  "./config/ka_data_management.yaml")

CATALOG     = dbutils.widgets.get("catalog")
SCHEMA      = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
TOPIC       = dbutils.widgets.get("topic")
CONFIG_FILE = dbutils.widgets.get("config_file")

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}/{TOPIC}"

import yaml

with open(CONFIG_FILE) as f:
    ka_config = yaml.safe_load(f)

KA_NAME         = ka_config["display_name"]
KA_DESCRIPTION  = ka_config["description"]
KA_INSTRUCTIONS = ka_config["instructions"]

print(f"KA name    : {KA_NAME}")
print(f"Volume path: {VOLUME_PATH}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Create (or reuse) the Knowledge Assistant

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.knowledgeassistants import (
    KnowledgeAssistant,
    KnowledgeSource,
    FilesSpec,
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
# MAGIC ## Step 3 — Attach volume files as knowledge source

# COMMAND ----------

existing_sources = {
    ks.display_name: ks
    for ks in w.knowledge_assistants.list_knowledge_sources(
        parent=f"knowledge-assistants/{ka_id}"
    )
}

SOURCE_DISPLAY_NAME = VOLUME_PATH

if SOURCE_DISPLAY_NAME in existing_sources:
    print(f"Knowledge source already exists — skipping.")
else:
    ks = w.knowledge_assistants.create_knowledge_source(
        parent=f"knowledge-assistants/{ka_id}",
        knowledge_source=KnowledgeSource(
            display_name=SOURCE_DISPLAY_NAME,
            description=KA_DESCRIPTION,
            source_type="files",
            files=FilesSpec(path=VOLUME_PATH),
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
print(f"\nTo use this KA in the app, set ka_data_management_endpoint = '{ka.endpoint_name}' in databricks.yml")

# Pass the actual display name to the create_supervisor task
dbutils.jobs.taskValues.set(key="ka_display_name", value=ka.display_name)
