#!/usr/bin/env python3
"""
Update an existing Jira issue by adding a comment with Salesforce provisioning details.

Typical use-case: a Jira ticket already exists (e.g., SFDC-1001) and we want to
attach the provisioning results (UserId + link + permission sets) without creating
an additional ticket.

Usage:
  python update_jira_issue_with_provisioning.py --org mavenprod --issue-key SFDC-1001 --results provisioning_results_brian_cota.json --user-id 005XXXXXXXXXXXX
"""

import argparse
import json
import os
import sys
from typing import Dict, Optional

# Import classes from project modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.provision_user import SalesforceUserProvisioner  # noqa: E402
from scripts.integrations.jira_client import load_jira_client_from_config  # noqa: E402


def _find_user_entry(results: Dict, user_id: str) -> Optional[Dict]:
    for entry in results.get("success", []):
        if entry.get("userId") == user_id:
            return entry
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Add provisioning details as a comment to an existing Jira issue")
    parser.add_argument("--org", required=True, help="Salesforce org alias (e.g., mavenprod)")
    parser.add_argument("--issue-key", required=True, help="Jira issue key (e.g., SFDC-1001)")
    parser.add_argument("--results", required=True, help="Provisioning results JSON file")
    parser.add_argument("--user-id", required=True, help="Salesforce User ID to pull from the results JSON")
    parser.add_argument("--jira-config", default="jira_config.json", help="Path to jira_config.json (default: jira_config.json)")
    args = parser.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"ERROR: Results JSON not found: {args.results}")
    if not os.path.exists(args.jira_config):
        raise SystemExit(f"ERROR: Jira config not found: {args.jira_config}")

    with open(args.results, "r", encoding="utf-8") as f:
        results = json.load(f)

    entry = _find_user_entry(results, args.user_id)
    if not entry:
        raise SystemExit(f"ERROR: user-id {args.user_id} not found in results JSON: {args.results}")

    user_data = entry.get("user") or {}
    jira_client = load_jira_client_from_config(args.jira_config)
    provisioner = SalesforceUserProvisioner(args.org, jira_client)

    user_link = provisioner.get_user_link(args.user_id)

    # Query assigned permission sets (nice for the comment)
    psa_query = f"""
    SELECT PermissionSet.Name, PermissionSet.Label
    FROM PermissionSetAssignment
    WHERE AssigneeId = '{args.user_id}'
    """
    psa_result = provisioner.sf.query(psa_query)
    assigned_permission_set_names = sorted(
        {
            (rec.get("PermissionSet") or {}).get("Label")
            or (rec.get("PermissionSet") or {}).get("Name")
            or "Unknown"
            for rec in psa_result.get("records", [])
        },
        key=str.lower,
    )

    ok = provisioner.update_existing_jira_ticket(
        issue_key=args.issue_key,
        user_data=user_data,
        user_id=args.user_id,
        user_link=user_link,
        assigned_group_names=[],
        assigned_permission_set_names=assigned_permission_set_names,
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
