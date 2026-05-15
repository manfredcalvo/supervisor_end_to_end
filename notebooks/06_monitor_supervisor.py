# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Supervisor Model Monitoring
# MAGIC
# MAGIC Registers production monitoring scorers on the supervisor's MLflow experiment.
# MAGIC Each scorer is evaluated on 100% of production traces.
# MAGIC
# MAGIC **Scorers:** `response_en_espanol` (Guidelines), `Safety`, `RelevanceToQuery`
# MAGIC **Depends on:** `05_evaluate_supervisor` (experiment must exist before registering monitors).

# COMMAND ----------

%pip install -r ./requirements.txt -q
dbutils.library.restartPython()

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
dbutils.widgets.text("supervisor_display_name", "Sura Supervisor")

SUPERVISOR_NAME = dbutils.widgets.get("supervisor_display_name")

print(f"Supervisor name: {SUPERVISOR_NAME}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Resolve experiment ID

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

supervisors = {s.display_name: s for s in w.supervisor_agents.list_supervisor_agents()}
if SUPERVISOR_NAME not in supervisors:
    raise ValueError(f"Supervisor '{SUPERVISOR_NAME}' not found.")

supervisor = supervisors[SUPERVISOR_NAME]

EXPERIMENT_ID = dbutils.jobs.taskValues.get(
    taskKey="create_supervisor",
    key="experiment_id",
    debugValue=supervisor.experiment_id or "",
)

print(f"MLflow experiment ID: {EXPERIMENT_ID}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Set MLflow experiment

# COMMAND ----------

import mlflow

if EXPERIMENT_ID:
    mlflow.set_experiment(experiment_id=EXPERIMENT_ID)
else:
    mlflow.set_experiment(f"/Shared/{SUPERVISOR_NAME}-evaluation")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Register monitoring scorers

# COMMAND ----------

from mlflow.genai.scorers import (
    Guidelines,
    Safety,
    RelevanceToQuery,
    ScorerSamplingConfig,
)

scorers = [
    Guidelines(
        name="response_en_espanol",
        guidelines=(
            "La respuesta debe estar escrita principalmente en español. "
            "Se permiten términos técnicos en inglés cuando no existe una traducción estándar al español, "
            "como nombres de productos (Databricks, Lakebase, Lakeflow, Genie, MLflow, Delta Sharing), "
            "tecnologías (Postgres, JDBC, Python, SQL, REST, API, YAML, JSON), "
            "y comandos o nombres de código (psycopg2, pip, dbutils, etc.). "
            "Fuera de estos términos técnicos, el texto debe estar en español."
        ),
    ),
    Safety(),
    RelevanceToQuery(),
]

sampling_cfg = ScorerSamplingConfig(sample_rate=1.0)

for scorer in scorers:
    try:
        scorer.register(name=scorer.name, experiment_id=EXPERIMENT_ID) \
              .start(sampling_config=sampling_cfg)
        print(f"Monitoring scorer registered and started: {scorer.name}")
    except ValueError as e:
        if "already been registered" in str(e):
            scorer.update(
                name=scorer.name,
                experiment_id=EXPERIMENT_ID,
                sampling_config=sampling_cfg,
            )
            print(f"Monitoring scorer updated: {scorer.name}")
        else:
            raise

print("\nAll monitoring scorers active — 100% of production traces will be evaluated.")
