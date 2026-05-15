<a href="https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app">
  <h1 align="center">Databricks Supervisor Agent — End-to-End Demo</h1>
</a>

<p align="center">
    A complete reference implementation that showcases how to build a production-grade, multi-agent AI system on the Databricks platform — from document ingestion to a deployed chat application.
</p>

<p align="center">
  <a href="#what-this-demo-showcases"><strong>What's Inside</strong></a> ·
  <a href="#architecture-overview"><strong>Architecture</strong></a> ·
  <a href="#databricks-products-used"><strong>Products Used</strong></a> ·
  <a href="#deployment"><strong>Deployment</strong></a> ·
  <a href="#knowledge-base-pipeline"><strong>Pipeline</strong></a>
</p>
<br/>

## What This Demo Showcases

This repository demonstrates a full end-to-end supervisor agent architecture on Databricks, suitable for use as a customer demo or internal reference. It covers the entire lifecycle:

| Layer | What it demonstrates |
|---|---|
| **Document Ingestion** | Parsing PDFs from Unity Catalog Volumes with `ai_parse_document` and `ai_prep_search` |
| **Incremental Processing** | Auto Loader (`cloudFiles`) streams new PDFs incrementally with checkpoint-based resumability |
| **Delta Lake** | Processed documents stored in Delta tables with Change Data Feed enabled — source for Vector Search Delta Sync indexes |
| **Language Detection & Translation** | Using `ai_classify` and `ai_translate` AI Functions to detect and normalize document language |
| **Vector Search** | Creating Delta Sync indexes backed by `databricks-agent-bricks-embedding-v1` embeddings |
| **Knowledge Assistants** | Topic-specific KAs grounded in Vector Search indexes or UC Volume files |
| **Supervisor Agent** | Multi-Agent Supervisor (MAS) that routes questions to the right KA |
| **MLflow Evaluation** | `mlflow.genai.evaluate()` quality gate after every pipeline run |
| **MLflow Tracing** | Serving endpoint returns a `traceId` per response; the app stores it and links user feedback to the trace |
| **MLflow Monitoring** | Production scorers (Safety, Relevance, custom scorers) at 100% sample rate |
| **Lakebase Memory** | Persistent chat history stored in Databricks Lakebase (Postgres) |
| **User Feedback** | Thumbs up/down stored as MLflow assessments on the associated trace |
| **Databricks Apps** | Deployed React + Express chat UI served as a Databricks App |
| **Asset Bundles** | Full IaC via Databricks Asset Bundles (DAB) — one command to deploy everything |

---

## Architecture Overview

This demo has **two parallel tracks** that feed into a single Supervisor Agent:

```
┌─────────────────────────────────────────────────────────────────┐
│  Track 1: Data Management                                       │
│  UC Volume (PDFs) ──► 03_create_ka_from_files.py               │
│                       └── KA: Data Management                  │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
┌─────────────────────────────────────────┼───────────────────────┐
│  Track 2: AI & Analytics                │                       │
│  UC Volume (PDFs)                       │                       │
│      │                                  │                       │
│      ▼                                  │                       │
│  01_process_documents.py                │                       │
│  ├── ai_parse_document                  │                       │
│  ├── ai_prep_search                     │                       │
│  ├── ai_classify                        │                       │
│  └── ai_translate                       │                       │
│      │                                  │                       │
│      ▼                                  │                       │
│  02_create_vector_index.py              │                       │
│  └── Vector Search index               │                       │
│      │                                  │                       │
│      ▼                                  │                       │
│  03_create_knowledge_assistant.py       │                       │
│  └── KA: AI & Analytics ───────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
              04_create_supervisor.py
              └── Multi-Agent Supervisor (MAS)
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
  05_evaluate_supervisor.py   06_monitor_supervisor.py
  └── mlflow.genai.evaluate   └── Production scorers
                          │
                          ▼
              Databricks Serving Endpoint
                          │
                          ▼
              Databricks App (React + Express)
              ├── Lakebase (Postgres) — chat memory
              ├── MLflow assessments — user feedback
              └── Real-time MAS streaming UI
```

The **Data Management track** creates a KA directly from PDF files in a Unity Catalog Volume — no AI Functions processing or Vector Search index required.

The **AI & Analytics track** runs a full pipeline: AI Functions processing → Vector Search index → Knowledge Assistant.

---

## Databricks Products Used

- **[Agent Bricks / Multi-Agent Supervisor (MAS)](https://docs.databricks.com/aws/en/generative-ai/agent-bricks/multi-agent-supervisor)** — routes user questions across topic-specific Knowledge Assistants
- **[Knowledge Assistants (KA)](https://docs.databricks.com/aws/en/generative-ai/agent-bricks/knowledge-assistant)** — retrieval-augmented agents grounded in Vector Search or UC Volume files
- **[Databricks Vector Search](https://docs.databricks.com/aws/en/generative-ai/vector-search)** — Delta Sync indexes with `databricks-agent-bricks-embedding-v1` embeddings
- **[Lakebase](https://docs.databricks.com/aws/en/database-objects/lakebase)** — Postgres-compatible autoscaling database for persistent chat history
- **[MLflow Evaluation](https://docs.databricks.com/aws/en/mlflow/genai-evaluation)** — `mlflow.genai.evaluate()` quality gate after each pipeline run
- **[MLflow Production Monitoring](https://docs.databricks.com/aws/en/mlflow/monitor-diagnose-apps)** — Safety, RelevanceToQuery, and custom scorers at 100% sample rate
- **[Auto Loader](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader)** — incremental PDF ingestion from Unity Catalog Volumes using `cloudFiles` structured streaming with checkpoint-based resumability
- **[Delta Lake](https://docs.databricks.com/aws/en/delta)** — processed documents stored in Delta tables with Change Data Feed enabled, used as the source for Vector Search Delta Sync indexes
- **[AI Functions](https://docs.databricks.com/aws/en/large-language-models/ai-functions)** — `ai_parse_document`, `ai_prep_search`, `ai_classify`, `ai_translate`
- **[MLflow Tracing](https://docs.databricks.com/aws/en/mlflow/mlflow-tracing)** — serving endpoint returns a `traceId` per response; the app captures it and attaches user feedback as MLflow assessments
- **[Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps)** — React + Express chat UI deployed as a managed application
- **[Unity Catalog](https://docs.databricks.com/aws/en/data-governance/unity-catalog)** — catalog/schema/volume governance for all data assets
- **[Databricks Asset Bundles (DAB)](https://docs.databricks.com/aws/en/dev-tools/bundles)** — Infrastructure-as-code for every resource in this demo

---

## Deployment

All resources — the Lakebase database, the Databricks App, and the pipeline job — are managed by a single `databricks.yml`. Follow these steps in order.

### Prerequisites

1. **Databricks workspace** with access to Agent Bricks, Vector Search, and Lakebase.
2. **Databricks CLI** (v0.240+):
   ```bash
   brew install databricks
   # or upgrade
   brew upgrade databricks && databricks -v
   ```
3. **Authenticate**:
   ```bash
   databricks auth login
   # or with a named profile
   databricks auth login --profile <your-profile>
   ```
4. **Node.js 20** (for local development only):
   ```bash
   nvm install 20 && nvm use 20
   npm install
   ```

---

### Step 1 — Configure `databricks.yml`

Open `databricks.yml` and set the variables for your workspace. The variables you must review are:

| Variable | Description | Example |
|---|---|---|
| `catalog` | Unity Catalog catalog | `my_catalog` |
| `schema` | Unity Catalog schema | `my_schema` |
| `data_management_volume_name` | Volume with Data Management PDFs | `docs` |
| `ai_analytics_volume` | Volume with AI & Analytics PDFs | `docs` |
| `vector_search_endpoint` | Vector Search endpoint name | `my_vs_endpoint` |
| `serving_endpoint_name` | Supervisor MAS serving endpoint _(set after Step 3)_ | `mas-xxxxxxxx-endpoint` |
| `ka_data_management_endpoint` | Data Management KA endpoint _(set after Step 3)_ | `ka-xxxxxxxx-endpoint` |
| `ka_ai_analytics_endpoint` | AI & Analytics KA endpoint _(set after Step 3)_ | `ka-xxxxxxxx-endpoint` |
| `supervisor_display_name` | Display name for the Supervisor Agent | `Supervisor Agent` |
| `mlflow_experiment_id` | MLflow experiment ID _(set after Step 3)_ | `596640452270627` |

Leave `lakebase_database_id` at its default (`placeholder`) for now — it will be updated in Step 5.

Also review the KA and Supervisor YAML configs under `notebooks/config/`:

```
notebooks/config/
├── ka_data_management.yaml   # Data Management KA — display_name, description, instructions
├── ka_ai_analytics.yaml      # AI & Analytics KA
└── supervisor.yaml           # Supervisor Agent
```

---

### Step 2 — First bundle deploy (creates Lakebase project)

The first deploy provisions the Lakebase autoscaling project. The app binding will fail with a placeholder DB ID — that is expected and fixed in Step 5.

```bash
databricks bundle deploy
# or with a named profile
databricks bundle deploy --profile <your-profile>
```

---

### Step 3 — Run the pipeline job

The pipeline job ingests PDFs, builds Vector Search indexes, creates Knowledge Assistants, assembles the Supervisor Agent, runs evaluation, and sets up monitoring.

```bash
databricks bundle run create_supervisor_agent
```

The job runs the two tracks in parallel and then creates the Supervisor. Total runtime is typically 30–60 minutes depending on document volume.

#### Retrieve endpoint names and experiment ID

Once the job completes, run the helper script to discover and optionally write all values back to `databricks.yml`:

```bash
# Print discovered values (dry run)
python3 scripts/get_endpoints.py --profile <your-profile>

# Print and automatically update databricks.yml
python3 scripts/get_endpoints.py --profile <your-profile> --update
```

The script resolves:
- **`serving_endpoint_name`** — the Supervisor MAS serving endpoint
- **`ka_data_management_endpoint`** — the Data Management KA serving endpoint
- **`ka_ai_analytics_endpoint`** — the AI & Analytics KA serving endpoint
- **`mlflow_experiment_id`** — the MLflow experiment ID linked to the Supervisor Agent

If you prefer to set the values manually, the script prints a summary table you can copy from. Example output:

```
============================================================
Values to set in databricks.yml:
============================================================
  serving_endpoint_name      : mas-xxxxxxxx-endpoint
  ka_data_management_endpoint: ka-xxxxxxxx-endpoint
  ka_ai_analytics_endpoint   : ka-xxxxxxxx-endpoint
  mlflow_experiment_id       : 596640452270627
============================================================
```

---

### Step 4 — Get the Lakebase database ID

After the first deploy (Step 2), the Lakebase project was created with an auto-generated database ID. Retrieve it:

```bash
# Replace <suffix> with your resource_name_suffix (e.g. dev-firstname-lastname)
databricks postgres list-databases \
  "projects/supervisor-end-to-end-<suffix>/branches/production" \
  --output json | python3 -c "import sys,json; db=json.load(sys.stdin)[0]; print(db['name'].split('/')[-1])"
```

The returned value looks like `databricks-postgres` or `db-xxxx-xxxxxxxxxxxx`. Update `databricks.yml`:

```yaml
variables:
  lakebase_database_id:
    default: "databricks-postgres"   # ← replace with value from command above
```

---

### Step 5 — Final bundle deploy

Redeploy to wire up the app with the real Lakebase database ID, endpoint names, and MLflow experiment:

```bash
databricks bundle deploy
```

---

### Step 6 — Start the app

```bash
databricks bundle run databricks_chatbot
```

The app will build, run database migrations, and start. Access it at the URL printed in the output.

---

### Deployment Targets

```bash
# Default: dev
databricks bundle deploy

# Staging
databricks bundle deploy -t staging

# Production
databricks bundle deploy -t prod
```

---

## Knowledge Base Pipeline

### Pipeline Overview

```
ka_data_management  ─────────────────────────────────────────────────────────────┐
                                                                                  │
process_ai_analytics → index_ai_analytics → ka_ai_analytics ─────────────────────┤
                                                                                  ▼
                                                               create_supervisor
                                                                       │
                                                                       ▼
                                                            evaluate_supervisor
                                                                       │
                                                                       ▼
                                                             monitor_supervisor
```

The two tracks run in parallel; the Supervisor is created once both KAs are ready.

| Stage | Notebook | Description |
|---|---|---|
| **Data Management KA** | `notebooks/03_create_ka_from_files.py` | Creates a KA directly from PDFs in a Unity Catalog Volume. No processing or Vector Search required. |
| **Process** | `notebooks/01_process_documents.py` | Auto Loader reads new PDFs from `<volume>/<topic>/`, parses with `ai_parse_document`, chunks with `ai_prep_search`, detects language with `ai_classify`, translates non-English chunks with `ai_translate`. Incremental via checkpoint. |
| **Index** | `notebooks/02_create_vector_index.py` | Creates a Vector Search endpoint and a Delta Sync index using `databricks-agent-bricks-embedding-v1` embeddings. Race-condition safe — runs in parallel across topics. |
| **AI & Analytics KA** | `notebooks/03_create_knowledge_assistant.py` | Creates a KA backed by the Vector Search index. Display name, description, and instructions loaded from YAML config. |
| **Supervisor** | `notebooks/04_create_supervisor.py` | Creates a Multi-Agent Supervisor that routes questions to the topic KAs. Config and KA display names loaded from YAML. |
| **Evaluate** | `notebooks/05_evaluate_supervisor.py` | Runs `mlflow.genai.evaluate()` with Spanish question set. Acts as a quality gate (≥80% Spanish compliance) before monitoring is activated. |
| **Monitor** | `notebooks/06_monitor_supervisor.py` | Registers production monitoring scorers (Safety, RelevanceToQuery, custom scorers) at 100% sample rate. Idempotent — safe to re-run. |

### Volume Structure

PDFs must be placed in topic subfolders within the configured volumes:

```
<catalog>/<schema>/<data_management_volume_name>/
└── data_management/    ← Data Management PDFs

<catalog>/<schema>/<ai_analytics_volume>/
└── ai_analytics/       ← AI & Analytics PDFs
```

---

## Chat App Features

### Multi-Agent Supervisor (MAS) UI

When the serving endpoint is a Multi-Agent Supervisor, the chat UI automatically activates:

- **Real-time sub-agent panels** — collapsible panels show each KA's response as it streams, labeled "Consulting \<agent name\>…" during processing.
- **Sources section** — after the supervisor's final response, all cited source documents are listed with citation counts.
- **Clean sub-agent text** — footnote markers, internal Databricks URLs, and `localhost` citation links are automatically stripped before display.

### Persistent Chat History (Lakebase)

Conversations are stored in Databricks Lakebase (Postgres autoscaling) and visible in the sidebar across sessions. The database schema (`ai_chatbot`) is created automatically when the app starts via `npm run db:migrate`.

### User Feedback (MLflow Assessments)

Thumbs up/down feedback on assistant responses is stored as [MLflow assessments](https://docs.databricks.com/aws/en/generative-ai/agent-evaluation/assessments) on the underlying traces, making it easy to review in the MLflow Experiment Tracking UI.

---

## Local Development

```bash
npm install
cp .env.example .env
# Edit .env: set DATABRICKS_CONFIG_PROFILE and DATABRICKS_SERVING_ENDPOINT

npm run dev        # starts frontend (port 3000) and backend (port 3001)
npm run dev:server # backend only
npm run dev:client # frontend only
```

### Required `.env` Variables

```bash
DATABRICKS_CONFIG_PROFILE=your-profile-name
DATABRICKS_SERVING_ENDPOINT=your-supervisor-endpoint

# Optional: Lakebase connection for persistent chat history
PGHOST=your-lakebase-host
PGDATABASE=databricks_postgres
PGPORT=5432
```

---

## Testing

```bash
npm test                              # all Playwright tests
npx playwright test --ui              # interactive UI mode
npx playwright test --headed --project=e2e  # browser visible
```

---

## Troubleshooting

### "Invalid access token" during `databricks bundle deploy`

Re-authenticate:
```bash
databricks auth login
```

### "reference does not exist" errors

Your Databricks CLI may be out of date:
```bash
brew upgrade databricks && databricks -v
```

### "Resource not found" errors during deploy

Resources may have been manually deleted or created outside the bundle. Reconcile with:
```bash
databricks bundle summary
databricks bundle unbind <resource-name>   # if manually deleted
databricks bundle bind <resource-name>     # if manually created
```

### App fails to start with database errors

Ensure `lakebase_database_id` in `databricks.yml` is set to the real value (not `placeholder`). See Step 4 above.

---

## Using Claude Code with This Project

### Overview

This project includes a `CLAUDE.md` file that gives Claude Code complete context about the architecture, deployment steps, and key file paths — so you can use Claude for development and deployment without having to explain the project from scratch each session.

### Connecting Claude Code to Databricks

Rather than purchasing an Anthropic subscription, you can route Claude Code API calls through your Databricks workspace AI Gateway. Claude Code bills against your Databricks workspace spend — no separate Anthropic account or license is needed.

#### Project-Level Settings (Option A)

Copy the template and fill in your values:

```bash
cp .claude/settings_template.json .claude/settings.json
# Edit .claude/settings.json with your workspace URL and PAT
```

The file sets the following environment variables for Claude Code:

| Variable | Description |
|---|---|
| `ANTHROPIC_BASE_URL` | Your workspace AI Gateway route |
| `ANTHROPIC_MODEL` | Primary Claude model (e.g. `databricks-claude-opus-4-6`) |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Opus model override |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Sonnet model override |
| `CLAUDE_CODE_SUBAGENT_MODEL` | Model used for background sub-agent tasks |
| `ANTHROPIC_AUTH_TOKEN` | Your Databricks PAT |

**Important:** `.claude/settings.json` is in `.gitignore` — never commit it since it contains your PAT.

#### Global Settings (Option B)

Configure the file below to apply the same settings across all projects on your machine.

**Windows** — `%USERPROFILE%\.claude\settings.json` (e.g. `C:\Users\<your-username>\.claude\settings.json`):

```powershell
# Create the directory if it doesn't exist
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude"

# Open in Notepad (or replace notepad with code, vim, etc.)
notepad "$env:USERPROFILE\.claude\settings.json"
```

**Mac/Linux** — `~/.claude/settings.json`:

```bash
mkdir -p ~/.claude
# Open in your preferred editor
nano ~/.claude/settings.json
```

Paste the same JSON from `.claude/settings_template.json` (with your real values) into the file.

**Note:** No `.gitignore` entry is needed — the file lives outside any repository.

**Precedence:** Project-level settings override global settings.

### Capabilities

Once configured, Claude automatically reads `CLAUDE.md` and understands:

- The full deployment sequence and Databricks CLI profiles
- All bundle resource names, UC paths, and `databricks.yml` variables
- Key code paths, database conventions, and migration workflow

You can ask Claude to deploy the app, run the pipeline job, update endpoint variables, or make code changes — all with full project context.
