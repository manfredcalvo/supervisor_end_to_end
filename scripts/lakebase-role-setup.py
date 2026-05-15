"""
Lakebase Autoscaling - Role Creation & SQL Permissions Grant

Creates a Postgres role for the app's service principal and grants
all necessary permissions for the chatbot database (ai_chatbot + drizzle schemas).

Prerequisites:
  pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0"

Usage:
  python3 scripts/lakebase-role-setup.py \
    --profile <databricks-cli-profile> \
    --project-id <lakebase-project-id> \
    --sp-client-id <service-principal-client-id>

Example:
  python3 scripts/lakebase-role-setup.py \
    --profile e2-demo-field-eng \
    --project-id sura-tendencias-riesgos-dev-manffred-calvosanchez \
    --sp-client-id 840db731-d389-4ed5-840b-e5ba76df59a4

To find these values:
  - profile: your Databricks CLI profile name
  - project-id: from `databricks postgres list-projects --profile <profile>`
  - sp-client-id: from `databricks apps get <app-name> --profile <profile> --output json`
    (look for the `service_principal_client_id` field)
"""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Create Lakebase role and grant SQL permissions for a Databricks App service principal"
    )
    parser.add_argument("--profile", required=True, help="Databricks CLI profile name")
    parser.add_argument("--project-id", required=True, help="Lakebase project ID")
    parser.add_argument("--sp-client-id", required=True, help="App service principal client ID (UUID)")
    args = parser.parse_args()

    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.postgres import (
            Role, RoleRoleSpec, RoleMembershipRole,
            RoleIdentityType, RoleAuthMethod
        )
        import psycopg
    except ImportError:
        print('Missing dependencies. Install with:')
        print('  pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0"')
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)
    branch = f"projects/{args.project_id}/branches/production"
    endpoint_name = f"{branch}/endpoints/primary"
    sp = args.sp_client_id

    # Step 1: Create Postgres role for the service principal
    print("Step 1: Creating Postgres role for service principal...")
    try:
        w.postgres.create_role(
            parent=branch,
            role_id="app-sp",
            role=Role(
                spec=RoleRoleSpec(
                    postgres_role=sp,
                    identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
                    auth_method=RoleAuthMethod.LAKEBASE_OAUTH_V1,
                    membership_roles=[RoleMembershipRole.DATABRICKS_SUPERUSER]
                )
            )
        )
        print("  Role created successfully")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("  Role already exists, skipping")
        else:
            print(f"  Error: {e}")
            sys.exit(1)

    # Step 2: Get endpoint host and connect
    print("\nStep 2: Getting Lakebase endpoint host...")
    endpoint = w.postgres.get_endpoint(name=endpoint_name)
    host = endpoint.status.hosts.host
    print(f"  PGHOST: {host}")

    print("\nStep 3: Connecting to database...")
    cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
    user = w.current_user.me()

    conn = psycopg.connect(
        host=host,
        dbname="databricks_postgres",
        user=user.user_name,
        password=cred.token,
        sslmode="require"
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Step 3: Grant all permissions
    print("\nStep 4: Granting SQL permissions...")
    grants = [
        (f'GRANT CONNECT ON DATABASE databricks_postgres TO "{sp}"', "CONNECT on database"),
        (f'GRANT CREATE ON DATABASE databricks_postgres TO "{sp}"', "CREATE on database"),
        ("CREATE SCHEMA IF NOT EXISTS ai_chatbot", "Create ai_chatbot schema"),
        ("CREATE SCHEMA IF NOT EXISTS drizzle", "Create drizzle schema"),
        (f'GRANT USAGE ON SCHEMA ai_chatbot TO "{sp}"', "USAGE on ai_chatbot"),
        (f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ai_chatbot TO "{sp}"', "ALL PRIVILEGES on ai_chatbot tables"),
        (f'ALTER DEFAULT PRIVILEGES IN SCHEMA ai_chatbot GRANT ALL PRIVILEGES ON TABLES TO "{sp}"', "Default privileges on ai_chatbot"),
        (f'GRANT CREATE ON SCHEMA ai_chatbot TO "{sp}"', "CREATE on ai_chatbot"),
        (f'GRANT ALL PRIVILEGES ON SCHEMA drizzle TO "{sp}"', "ALL PRIVILEGES on drizzle schema"),
        (f'ALTER DEFAULT PRIVILEGES IN SCHEMA drizzle GRANT ALL PRIVILEGES ON TABLES TO "{sp}"', "Default privileges on drizzle"),
    ]

    for sql, desc in grants:
        try:
            cur.execute(sql)
            print(f"  OK: {desc}")
        except Exception as e:
            print(f"  WARN: {desc} -> {e}")

    conn.close()

    print("\n" + "=" * 50)
    print("Done! All permissions granted.")
    print("=" * 50)
    print(f"\nValues for app.yaml:")
    print(f"  PGHOST: {host}")
    print(f"  PGUSER: {sp}")
    print(f"  PGDATABASE: databricks_postgres")
    print(f"  PGPORT: 5432")
    print(f"  PGSSLMODE: require")


if __name__ == "__main__":
    main()
