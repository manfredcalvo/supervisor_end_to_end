# Last Changes — Since app.yaml Update

## `databricks.yml`
- Added variables: `catalog`, `schema`, `volume`, `vector_search_endpoint`, `ka_display_name`, `supervisor_display_name`
- Added job `create_supervisor_agent` with a full 11-task DAG
- Removed old single-topic `create_vector_index` job

## `notebooks/` (all new)

| Notebook | Description |
|---|---|
| `01_process_documents.py` | Auto Loader pipeline: reads PDFs from `<volume>/<topic>/`, parses, chunks, classifies, translates to Spanish, appends to `documents_<topic>` Delta table incrementally |
| `02_create_vector_index.py` | Creates VS endpoint (race-condition safe) + Delta Sync index `documents_<topic>_index` using `databricks-bge-large-en` |
| `03_create_knowledge_assistant.py` | Creates a Knowledge Assistant backed by the VS index (idempotent) |
| `04_create_supervisor.py` | Creates a Supervisor Agent wiring all 3 KAs (Fuerzas, Tendencias, Riesgos) as tools; passes `experiment_id` to next task via task values |
| `05_evaluate_supervisor.py` | Runs `mlflow.genai.evaluate()` against the supervisor endpoint; quality gate: Spanish guidelines pass rate ≥ 80% |
| `06_monitor_supervisor.py` | Registers production monitors (`response_en_espanol`, `Safety`, `RelevanceToQuery`) at 100% sample rate |

## Job DAG (`create_supervisor_agent`)

```
process_fuerzas    → index_fuerzas    → ka_fuerzas    ─┐
process_tendencias → index_tendencias → ka_tendencias  ─┼─→ create_supervisor → evaluate_supervisor → monitor_supervisor
process_riesgos    → index_riesgos    → ka_riesgos    ─┘
```

## `notebooks/config/` (all new)

| File | Description |
|---|---|
| `ka_fuerzas.yaml` | display_name, description, instructions for the Fuerzas KA |
| `ka_tendencias.yaml` | display_name, description, instructions for the Tendencias KA |
| `ka_riesgos.yaml` | display_name, description, instructions for the Riesgos KA |
| `supervisor.yaml` | description and instructions for the Supervisor Agent |

Notebooks 03 and 04 now accept a `config_file` widget (path to the YAML) instead of individual `ka_display_name`/`ka_description` parameters. The YAML is loaded at runtime with `yaml.safe_load`. To change a KA's instructions, edit its YAML and redeploy — no notebook changes needed.

## Key Design Decisions

- **Auto Loader** (`trigger(availableNow=True)`) for incremental PDF processing — only new files are processed on each run; checkpoint stored at `<volume>/_checkpoint/documents_<topic>`
- **Single shared volume** (`tendencias_riesgos`) with one subfolder per topic (`fuerzas/`, `tendencias/`, `riesgos/`)
- **VS endpoint race condition** handled with try/except on `create_endpoint` — safe for parallel execution
- **`delta.deletedFileRetentionDuration = interval 30 days`** set on all source tables to prevent VS sync failures
- **`experiment_id`** extracted from the `SupervisorAgent` object and passed between tasks via `dbutils.jobs.taskValues`
