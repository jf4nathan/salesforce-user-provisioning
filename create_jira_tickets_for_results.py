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

# Import classes from project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provision_user import SalesforceUserProvisioner  # noqa: E402
from jira_client import load_jira_client_from_args, add_jira_args  # noqa: E402


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

    # Jira options
    add_jira_args(parser)
    parser.add_argument("--jira-assignee-email", help="Assignee email (optional; overrides config/env)")
    parser.add_argument("--jira-board-id", type=int, help="Board ID for sprint assignment (optional)")

    args = parser.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"ERROR: Results JSON not found: {args.results}")

    jira_client = load_jira_client_from_args(args, verbose=False)
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

            # Use the existing ADF builder in provisioner.create_jira_ticket
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
