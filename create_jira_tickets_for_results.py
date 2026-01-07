#!/usr/bin/env python3
"""
Retroactively create Jira tickets for users already created in Salesforce.

Reads a provisioning results JSON (from provision_user.py) and creates one Jira
ticket per user using jira_config.json (or --jira-config / env vars).

Usage:
  python create_jira_tickets_for_results.py --org mavenprod --results provisioning_results_20260107.json
  python create_jira_tickets_for_results.py --org mavenprod --results provisioning_results_20260107.json --jira-config jira_config.json
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

# Import classes from provision_user.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provision_user import SalesforceUserProvisioner, JiraClient  # noqa: E402


def _load_jira_client(args: argparse.Namespace) -> Optional[JiraClient]:
    # Convenience: if a local jira_config.json exists and no Jira options were provided,
    # auto-load it so Jira ticket creation is enabled by default.
    if not args.jira_config:
        default_jira_config = os.getenv("JIRA_CONFIG_PATH", "jira_config.json")
        if os.path.exists(default_jira_config):
            args.jira_config = default_jira_config

    if args.jira_config:
        with open(args.jira_config, "r", encoding="utf-8") as f:
            jira_config = json.load(f)
        return JiraClient(
            jira_url=jira_config["jira_url"],
            email=jira_config["email"],
            api_token=jira_config["api_token"],
            project_key=jira_config["project_key"],
            issue_type=jira_config.get("issue_type", "Task"),
            assignee_email=jira_config.get("assignee_email"),
            board_id=jira_config.get("board_id"),
        )

    # Command-line args
    if args.jira_url and args.jira_email and args.jira_token and args.jira_project:
        return JiraClient(
            jira_url=args.jira_url,
            email=args.jira_email,
            api_token=args.jira_token,
            project_key=args.jira_project,
            issue_type=args.jira_issue_type,
            assignee_email=args.jira_assignee_email,
            board_id=args.jira_board_id,
        )

    # Env vars
    jira_url = os.getenv("JIRA_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")
    jira_project = os.getenv("JIRA_PROJECT_KEY")
    if jira_url and jira_email and jira_token and jira_project:
        return JiraClient(
            jira_url=jira_url,
            email=jira_email,
            api_token=jira_token,
            project_key=jira_project,
            issue_type=os.getenv("JIRA_ISSUE_TYPE", "Task"),
            assignee_email=os.getenv("JIRA_ASSIGNEE_EMAIL"),
            board_id=int(os.getenv("JIRA_BOARD_ID")) if os.getenv("JIRA_BOARD_ID") else None,
        )

    return None


def _get_assigned_permission_set_names(provisioner: SalesforceUserProvisioner, user_id: str) -> List[str]:
    psa_query = f"""
    SELECT PermissionSet.Name, PermissionSet.Label
    FROM PermissionSetAssignment
    WHERE AssigneeId = '{user_id}'
    """
    result = provisioner.sf.query(psa_query)
    names: List[str] = []
    for rec in result.get("records", []):
        ps = rec.get("PermissionSet") or {}
        names.append(ps.get("Label") or ps.get("Name") or "Unknown")
    # Stable-ish ordering (nice for Jira description)
    return sorted(set(names), key=str.lower)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Jira tickets for users in a provisioning results JSON")
    parser.add_argument("--org", required=True, help="Salesforce org alias (e.g., mavenprod)")
    parser.add_argument("--results", required=True, help="Provisioning results JSON file (e.g., provisioning_results_20260107.json)")

    # Jira options (mirrors provision_user.py)
    parser.add_argument("--jira-url", help="Jira instance URL (e.g., https://company.atlassian.net)")
    parser.add_argument("--jira-email", help="Jira user email for API authentication")
    parser.add_argument("--jira-token", help="Jira API token")
    parser.add_argument("--jira-project", help="Jira project key (e.g., PROJ)")
    parser.add_argument("--jira-issue-type", default="Task", help="Jira issue type (default: Task)")
    parser.add_argument("--jira-config", help="Path to JSON file with Jira configuration")
    parser.add_argument("--jira-assignee-email", help="Assignee email (optional; overrides config/env)")
    parser.add_argument("--jira-board-id", type=int, help="Board ID for sprint assignment (optional)")

    args = parser.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"ERROR: Results JSON not found: {args.results}")

    jira_client = _load_jira_client(args)
    if not jira_client:
        raise SystemExit(
            "ERROR: Jira is not configured. Provide --jira-config jira_config.json or set JIRA_* env vars."
        )

    provisioner = SalesforceUserProvisioner(args.org, jira_client)

    with open(args.results, "r", encoding="utf-8") as f:
        results: Dict = json.load(f)

    successes = results.get("success", [])
    if not successes:
        print("No successful users found in results JSON. Nothing to do.")
        return

    created = []
    failed = []

    print(f"Creating Jira tickets for {len(successes)} users...\n")
    for entry in successes:
        user_data = entry.get("user") or {}
        user_id = entry.get("userId")
        if not user_id:
            failed.append({"user": user_data, "error": "Missing userId in results JSON entry"})
            continue

        try:
            user_link = provisioner.get_user_link(user_id)
            assigned_permission_set_names = _get_assigned_permission_set_names(provisioner, user_id)

            # This org doesn't support PermissionSetGroupAssignment via API in our earlier run,
            # so group names are usually empty. Still pass through for completeness.
            assigned_group_names: List[str] = []

            # Create ticket
            ticket = provisioner.jira_client.create_ticket  # type: ignore[union-attr]
            # Prefer the existing ADF builder in provisioner.create_jira_ticket
            provisioner.create_jira_ticket(
                user_data=user_data,
                user_id=user_id,
                user_link=user_link,
                assigned_group_names=assigned_group_names,
                assigned_permission_set_names=assigned_permission_set_names,
            )

            # create_jira_ticket prints success/warn; also return minimal info for summary
            created.append({"user": user_data, "userId": user_id})
        except Exception as e:
            failed.append({"user": user_data, "userId": user_id, "error": str(e)})

    print("\n" + "=" * 60)
    print("Jira Ticket Creation Summary")
    print("=" * 60)
    print(f"  Created: {len(created)}")
    print(f"  Failed:  {len(failed)}")
    if failed:
        print("\nFAILED:")
        for f in failed:
            u = f.get("user") or {}
            name = f"{u.get('FirstName', '')} {u.get('LastName', '')}".strip()
            print(f"  - {name or u.get('Email', 'Unknown')}: {f.get('error')}")


if __name__ == "__main__":
    main()

