# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Create Supervisor Agent
# MAGIC
# MAGIC Creates (or reuses) a Databricks Supervisor Agent that routes user questions to
# MAGIC the appropriate Knowledge Assistant (Data Management or AI & Analytics).
# MAGIC
# MAGIC **Depends on:** `03_create_knowledge_assistant` having run for both topics.
# MAGIC **SDK:** `databricks.sdk.service.supervisoragents`

# COMMAND ----------

%pip install -r ./requirements.txt -q
dbutils.library.restartPython()

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
# When running interactively, set the widgets manually or edit the defaults below.
dbutils.widgets.text("catalog",                 "<catalog>")
dbutils.widgets.text("schema",                  "<schema>")
dbutils.widgets.text("supervisor_display_name", "Supervisor Agent")
dbutils.widgets.text("config_file",             "./config/supervisor.yaml")
dbutils.widgets.text("ka_topics",               "data_management,ai_analytics")

CATALOG         = dbutils.widgets.get("catalog")
SCHEMA          = dbutils.widgets.get("schema")
SUPERVISOR_NAME = dbutils.widgets.get("supervisor_display_name")
CONFIG_FILE     = dbutils.widgets.get("config_file")
KA_TOPICS       = [t.strip() for t in dbutils.widgets.get("ka_topics").split(",")]

import yaml

with open(CONFIG_FILE) as f:
    sup_config = yaml.safe_load(f)

print(f"Supervisor name : {SUPERVISOR_NAME}")
print(f"KA topics       : {KA_TOPICS}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Look up the KA IDs by display name

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import supervisoragents as sa
import time

w = WorkspaceClient()

all_kas = {ka.display_name: ka for ka in w.knowledge_assistants.list_knowledge_assistants()}

# Resolve KA display names from config files — avoids fragile taskValues dependency.
ka_config_paths = {
    "data_management": "./config/ka_data_management.yaml",
    "ai_analytics":    "./config/ka_ai_analytics.yaml",
}

ka_ids   = {}
ka_names = {}
for topic in KA_TOPICS:
    config_path = ka_config_paths.get(topic, f"./config/ka_{topic}.yaml")
    with open(config_path) as _f:
        name = yaml.safe_load(_f)["display_name"]
    if name not in all_kas:
        raise ValueError(f"KA '{name}' not found. Run the KA creation notebook for topic '{topic}' first.")
    ka_ids[topic]   = all_kas[name].id
    ka_names[topic] = name
    print(f"  {name}: {ka_ids[topic]}")


# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Create Supervisor Agent (idempotent)

# COMMAND ----------

existing = {s.display_name: s for s in w.supervisor_agents.list_supervisor_agents()}

if SUPERVISOR_NAME in existing:
    supervisor = existing[SUPERVISOR_NAME]
    supervisor_id = supervisor.supervisor_agent_id
    print(f"Supervisor already exists — id: {supervisor_id}")
else:
    supervisor = w.supervisor_agents.create_supervisor_agent(
        supervisor_agent=sa.SupervisorAgent(
            display_name=SUPERVISOR_NAME,
            description=sup_config["description"],
            instructions=sup_config["instructions"],
        )
    )
    supervisor_id = supervisor.supervisor_agent_id
    print(f"Supervisor created — id: {supervisor_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Attach each KA as a tool (idempotent)

# COMMAND ----------

parent = f"supervisor-agents/{supervisor_id}"

try:
    existing_tools = {t.tool_id: t for t in w.supervisor_agents.list_tools(parent=parent)}
except Exception as e:
    print(f"Warning: could not list existing tools ({e}) — will attempt to recreate all tools.")
    existing_tools = {}

for topic in KA_TOPICS:
    tool_id = topic
    if tool_id in existing_tools:
        existing_ka_id = existing_tools[tool_id].knowledge_assistant.knowledge_assistant_id if existing_tools[tool_id].knowledge_assistant else None
        if existing_ka_id == ka_ids[topic]:
            print(f"Tool '{tool_id}' already attached with correct KA — skipping.")
            continue
        print(f"Tool '{tool_id}' points to a different KA — deleting and recreating.")
        w.supervisor_agents.delete_tool(name=f"{parent}/tools/{tool_id}")
    topic_descriptions = {
        "data_management": (
            "Knowledge Assistant for Databricks Data Management: Lakeflow (pipelines & ETL), "
            "Lakebase (managed PostgreSQL), Databricks SQL (warehousing & BI), "
            "Delta Sharing, Marketplace, and Clean Rooms."
        ),
        "ai_analytics": (
            "Knowledge Assistant for Databricks AI & Analytics: Genie (natural-language analytics), "
            "Machine Learning & MLflow, Generative AI & Agent Framework, Model Serving, "
            "AI/BI Dashboards, and Business Semantics (Metric Views)."
        ),
    }
    description = topic_descriptions.get(
        topic,
        f"Knowledge Assistant for the '{topic}' Databricks documentation track.",
    )
    try:
        w.supervisor_agents.create_tool(
            parent=parent,
            tool_id=tool_id,
            tool=sa.Tool(
                tool_type="knowledge_assistant",
                description=description,
                knowledge_assistant=sa.KnowledgeAssistant(
                    knowledge_assistant_id=ka_ids[topic],
                ),
            ),
        )
        print(f"Tool '{tool_id}' attached — KA id: {ka_ids[topic]}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"Tool '{tool_id}' already exists — skipping.")
        else:
            raise

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Print summary

# COMMAND ----------

supervisor = w.supervisor_agents.get_supervisor_agent(name=f"supervisor-agents/{supervisor_id}")
print(f"\nSupervisor Agent ready.")
print(f"  display_name  : {supervisor.display_name}")
print(f"  id            : {supervisor_id}")
print(f"  endpoint_name : {supervisor.endpoint_name}")
print(f"  experiment_id : {supervisor.experiment_id}")

# Pass experiment_id to the next task (05_evaluate_supervisor)
dbutils.jobs.taskValues.set(key="experiment_id", value=supervisor.experiment_id or "")

print(f"\nTo wire this supervisor to the app, set in databricks.yml:")
print(f"  serving_endpoint_name: '{supervisor.endpoint_name}'")
