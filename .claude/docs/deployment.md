# Deployment Architecture

## Databricks Asset Bundle Resources (`databricks.yml`)

| Resource | Type | Description |
|---|---|---|
| `chatbot_lakebase` | `postgres_projects` | Lakebase autoscaling DB (PG 17) |
| `create_supervisor_agent` | `jobs` | Full pipeline job (ingest → KAs → Supervisor → eval → monitor) |
| `databricks_chatbot` | `apps` | Databricks App (React + Express) |

**App resource bindings:**

- `serving-endpoint` — Supervisor MAS endpoint (CAN_QUERY) → `DATABRICKS_SERVING_ENDPOINT`
- `ka-data-management-endpoint` — Data Management KA endpoint (CAN_QUERY)
- `ka-ai-analytics-endpoint` — AI & Analytics KA endpoint (CAN_QUERY)
- `mlflow-experiment` — MLflow experiment (CAN_MANAGE) → `MLFLOW_EXPERIMENT_ID`
- `database` — Lakebase postgres branch (CAN_CONNECT_AND_CREATE) → `LAKEBASE_ENDPOINT`

## Deployment Targets

- **dev** (default): user-scoped suffix (`dev-{username}`)
- **staging**: shared staging environment
- **prod**: production environment

## Key `databricks.yml` Variables

| Variable | Description |
|---|---|
| `serving_endpoint_name` | Supervisor MAS serving endpoint |
| `ka_data_management_endpoint` | Data Management KA endpoint |
| `ka_ai_analytics_endpoint` | AI & Analytics KA endpoint |
| `mlflow_experiment_id` | MLflow experiment ID |
| `catalog` / `schema` | Unity Catalog location |
| `data_management_volume_name` | Volume with Data Management PDFs |
| `ai_analytics_volume` | Volume with AI & Analytics PDFs |
| `vector_search_endpoint` | Vector Search endpoint name |

Use `scripts/get_endpoints.py --profile <profile> --update` to auto-populate endpoint variables after running the pipeline job.
