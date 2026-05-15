"""
Retrieve Supervisor Agent and Knowledge Assistant endpoint names and the
MLflow experiment ID after running the pipeline job, then optionally update
databricks.yml with the discovered values.

Prerequisites:
  pip install "databricks-sdk>=0.105.0" pyyaml

Usage:
  python3 scripts/get_endpoints.py --profile <databricks-cli-profile>

  # Auto-update databricks.yml
  python3 scripts/get_endpoints.py --profile <databricks-cli-profile> --update

Example:
  python3 scripts/get_endpoints.py --profile andreas_workspace --update
"""

import argparse
import re
import sys
from pathlib import Path


def load_display_name(config_path: Path) -> str:
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f).get("display_name", "")
    except Exception as e:
        print(f"WARNING: Could not read {config_path}: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve supervisor/KA endpoints and MLflow experiment ID"
    )
    parser.add_argument("--profile", default=None, help="Databricks CLI profile name")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Write discovered values back to databricks.yml",
    )
    parser.add_argument(
        "--supervisor-name",
        default=None,
        help="Display name of the Supervisor Agent (default: first one found)",
    )
    args = parser.parse_args()

    try:
        import yaml
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.supervisoragents import SupervisorAgentsAPI
        from databricks.sdk.service.knowledgeassistants import KnowledgeAssistantsAPI
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with:  pip install 'databricks-sdk>=0.105.0' pyyaml")
        sys.exit(1)

    kwargs = {"profile": args.profile} if args.profile else {}
    w = WorkspaceClient(**kwargs)

    config_dir = Path(__file__).parent.parent / "notebooks" / "config"

    # ── 1. Supervisor Agent ───────────────────────────────────────────────────
    print("Fetching Supervisor Agents...")
    supervisors = list(w.supervisor_agents.list_supervisor_agents())
    if not supervisors:
        print("ERROR: No Supervisor Agents found. Run the pipeline job first.")
        sys.exit(1)

    if args.supervisor_name:
        matches = [s for s in supervisors if s.display_name == args.supervisor_name]
        if not matches:
            available = [s.display_name for s in supervisors]
            print(f"ERROR: '{args.supervisor_name}' not found. Available: {available}")
            sys.exit(1)
        supervisor = matches[0]
    else:
        if len(supervisors) > 1:
            available = [s.display_name for s in supervisors]
            print(f"Multiple supervisors found: {available}")
            print(f"Using '{supervisors[0].display_name}'. Pass --supervisor-name to pick another.")
        supervisor = supervisors[0]

    print(f"\nSupervisor Agent     : {supervisor.display_name}")
    print(f"  endpoint_name      : {supervisor.endpoint_name}")
    print(f"  experiment_id      : {supervisor.experiment_id or '(none)'}")

    # ── 2. Knowledge Assistants ───────────────────────────────────────────────
    print("\nFetching Knowledge Assistants...")
    all_kas = {ka.display_name: ka for ka in w.knowledge_assistants.list_knowledge_assistants()}

    ka_config_map = {
        "data_management": config_dir / "ka_data_management.yaml",
        "ai_analytics":    config_dir / "ka_ai_analytics.yaml",
    }

    resolved: dict[str, str] = {}
    for topic, config_path in ka_config_map.items():
        display_name = load_display_name(config_path)
        if not display_name:
            print(f"  WARNING: No display_name in {config_path.name}, skipping")
            continue
        ka = all_kas.get(display_name)
        if not ka:
            print(f"  WARNING: KA '{display_name}' not found. Pipeline may still be running.")
            continue
        resolved[topic] = ka.endpoint_name or ""
        print(f"  {topic}: {display_name} → {ka.endpoint_name}")

    # ── 3. Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Values to set in databricks.yml:")
    print("=" * 60)
    print(f"  serving_endpoint_name      : {supervisor.endpoint_name}")
    print(f"  ka_data_management_endpoint: {resolved.get('data_management', 'UNKNOWN')}")
    print(f"  ka_ai_analytics_endpoint   : {resolved.get('ai_analytics', 'UNKNOWN')}")
    print(f"  mlflow_experiment_id       : {supervisor.experiment_id or 'UNKNOWN'}")
    print("=" * 60)

    # ── 4. Optionally update databricks.yml ──────────────────────────────────
    if not args.update:
        print("\nRun with --update to write these values to databricks.yml automatically.")
        return

    updates = {
        "serving_endpoint_name":       supervisor.endpoint_name or "",
        "ka_data_management_endpoint": resolved.get("data_management", ""),
        "ka_ai_analytics_endpoint":    resolved.get("ai_analytics", ""),
        "mlflow_experiment_id":        supervisor.experiment_id or "",
    }

    yml_path = Path(__file__).parent.parent / "databricks.yml"
    content = yml_path.read_text()

    for var, value in updates.items():
        if not value:
            print(f"  Skipping {var} (no value resolved)")
            continue
        pattern = rf'({re.escape(var)}:(?:[^\n]*\n)+?\s*default: ")[^"]*(")'
        new_content, count = re.subn(pattern, rf'\g<1>{value}\g<2>', content, flags=re.DOTALL)
        if count:
            content = new_content
            print(f"  Updated {var} → {value}")
        else:
            print(f"  WARNING: Could not find default for '{var}' in databricks.yml")

    yml_path.write_text(content)
    print(f"\ndatabricks.yml updated. Run 'databricks bundle deploy' to apply.")


if __name__ == "__main__":
    main()
