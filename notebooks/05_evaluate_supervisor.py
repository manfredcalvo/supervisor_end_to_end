# Databricks notebook source

# COMMAND ----------
# MAGIC %md
# MAGIC # Supervisor Model Evaluation
# MAGIC
# MAGIC Evaluates the Supervisor Agent using `mlflow.genai.evaluate()` with
# MAGIC `RelevanceToQuery` as the quality gate. Results are saved to the
# MAGIC supervisor's MLflow experiment.
# MAGIC
# MAGIC **Depends on:** `04_create_supervisor` (passes `experiment_id` via task values).

# COMMAND ----------

%pip install -r ./requirements.txt -q
dbutils.library.restartPython()

# COMMAND ----------

# Configuration — values injected by the Databricks job via base_parameters.
dbutils.widgets.text("supervisor_display_name", "Supervisor Agent")

SUPERVISOR_NAME = dbutils.widgets.get("supervisor_display_name")

print(f"Supervisor name: {SUPERVISOR_NAME}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Resolve supervisor endpoint and experiment ID

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

supervisors = {s.display_name: s for s in w.supervisor_agents.list_supervisor_agents()}
if SUPERVISOR_NAME not in supervisors:
    raise ValueError(f"Supervisor '{SUPERVISOR_NAME}' not found. Run 04_create_supervisor first.")

supervisor = supervisors[SUPERVISOR_NAME]
ENDPOINT_NAME = supervisor.endpoint_name

# Receive experiment_id from the upstream create_supervisor task via task values.
# debugValue is used when running the notebook interactively.
EXPERIMENT_ID = dbutils.jobs.taskValues.get(
    taskKey="create_supervisor",
    key="experiment_id",
    debugValue=supervisor.experiment_id or "",
)

print(f"Supervisor endpoint  : {ENDPOINT_NAME}")
print(f"MLflow experiment ID : {EXPERIMENT_ID}")

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
# MAGIC ## Step 3 — Define predict function

# COMMAND ----------

predict_fn = mlflow.genai.to_predict_fn(f"endpoints:/{ENDPOINT_NAME}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Define evaluation dataset
# MAGIC
# MAGIC Preguntas en español que cubren ambos tracks: Data Management (Lakeflow, Lakebase, SQL,
# MAGIC Data Sharing) y AI & Analytics (Genie, ML, MLflow, Model Serving, Agent Framework, AI/BI).
# MAGIC Las preguntas están diseñadas para ser respondidas con los documentos ingestados.

# COMMAND ----------

import pandas as pd

eval_data = pd.DataFrame({
    "inputs": [
        # Data Management — Lakebase / OLTP
        {"input": [{"role": "user", "content": "¿Qué es Lakebase y cuáles son sus principales casos de uso como base de datos transaccional en Databricks?"}]},
        {"input": [{"role": "user", "content": "¿Cómo funciona el autoescalado en Lakebase y qué ventajas tiene frente a una instancia provisionada?"}]},
        # Data Management — Lakeflow
        {"input": [{"role": "user", "content": "¿Qué conectores soporta Lakeflow Connect para la ingestión de datos desde fuentes externas?"}]},
        {"input": [{"role": "user", "content": "¿Cuál es la diferencia entre los pipelines declarativos de Lakeflow y los pipelines clásicos de DLT?"}]},
        {"input": [{"role": "user", "content": "¿Cómo se configura y orquesta un job en Lakeflow Jobs para ejecutar tareas en secuencia?"}]},
        # Data Management — SQL / Data Sharing
        {"input": [{"role": "user", "content": "¿Cómo puedo compartir datos con organizaciones externas usando Delta Sharing y Databricks Marketplace?"}]},
        # AI & Analytics — Genie
        {"input": [{"role": "user", "content": "¿Qué es un Genie Space y cómo se configura para permitir consultas en lenguaje natural sobre mis datos?"}]},
        # AI & Analytics — MLflow / Model Serving
        {"input": [{"role": "user", "content": "¿Cómo registro un modelo en MLflow y lo despliego en un endpoint de Model Serving en Databricks?"}]},
        # AI & Analytics — Agent Framework
        {"input": [{"role": "user", "content": "¿Qué herramientas ofrece el Agent Framework de Databricks para construir aplicaciones RAG con Knowledge Assistants?"}]},
        # AI & Analytics — AI/BI
        {"input": [{"role": "user", "content": "¿Cómo puedo crear un dashboard de AI/BI en Databricks y cuáles son sus capacidades de análisis dinámico?"}]},
    ]
})

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 5 — Run evaluation

# COMMAND ----------

from mlflow.genai.scorers import Guidelines, Safety, RelevanceToQuery

SPANISH_GUIDELINES_THRESHOLD = 0.80

with mlflow.start_run(run_name=f"{SUPERVISOR_NAME}_evaluation"):
    results = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=predict_fn,
        scorers=[
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
        ],
    )

results_df = results.tables["eval_results"]
display(results_df)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 6 — Quality gate

# COMMAND ----------

spanish_cols = [
    c for c in results_df.columns
    if "response_en_espanol" in c.lower() and "/value" in c.lower()
]

if spanish_cols:
    pass_rate = (results_df[spanish_cols[0]].astype(str).str.lower() == "yes").mean()
    print(f"Spanish guidelines pass rate: {pass_rate:.1%} (threshold: {SPANISH_GUIDELINES_THRESHOLD:.1%})")
    if pass_rate < SPANISH_GUIDELINES_THRESHOLD:
        raise ValueError(
            f"Quality gate FAILED: Spanish guidelines pass rate {pass_rate:.1%} "
            f"is below the required {SPANISH_GUIDELINES_THRESHOLD:.1%}."
        )
    print("Quality gate PASSED.")
else:
    print("Warning: response_en_espanol column not found in results — skipping quality gate.")
