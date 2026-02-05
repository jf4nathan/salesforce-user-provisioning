#!/usr/bin/env python3
"""
Shared Salesforce utilities for query scripts.

This module provides common functions used across multiple Salesforce query scripts
to reduce code duplication and ensure consistent connection handling.

Usage:
    from sf_utils import get_sf_connection, get_org_info
    
    sf = get_sf_connection('mavenprod')
    result = sf.query("SELECT Id, Name FROM User LIMIT 10")
"""

import subprocess
import shutil
import os
import sys
import json
from simple_salesforce import Salesforce
from typing import Dict, Optional


def get_org_info(org_alias: str) -> Dict:
    """
    Get org information using sf CLI.
    
    Args:
        org_alias: Salesforce org alias (e.g., 'mavenprod')
    
    Returns:
        Dict with org info including accessToken, instanceUrl, username, etc.
    
    Raises:
        SystemExit: If connection fails
    """
    sf_cmd = shutil.which("sf") or ("sf.cmd" if os.name == 'nt' else "sf")
    
    result = subprocess.run(
        [sf_cmd, "org", "display", "--target-org", org_alias, "--json"],
        capture_output=True,
        text=True,
        shell=False
    )
    
    if result.returncode != 0:
        print(f"ERROR: Could not connect to org '{org_alias}'. Make sure you're authenticated.")
        print(f"Run: sf org login web --alias {org_alias}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    
    output = result.stdout.strip()
    json_start = output.find('{')
    if json_start == -1:
        print(f"ERROR: Could not parse JSON from sf org display output")
        sys.exit(1)
    
    json_output = output[json_start:]
    org_info = json.loads(json_output)
    return org_info["result"]


def get_sf_connection(org_alias: str) -> Salesforce:
    """
    Get authenticated Salesforce connection using sf CLI.
    
    Args:
        org_alias: Salesforce org alias (e.g., 'mavenprod')
    
    Returns:
        Authenticated Salesforce connection object
    
    Raises:
        SystemExit: If connection fails
    """
    org_info = get_org_info(org_alias)
    access_token = org_info["accessToken"]
    instance_url = org_info["instanceUrl"]
    
    return Salesforce(instance_url=instance_url, session_id=access_token)


def extract_sandbox_name(org_info: Dict) -> Optional[str]:
    """
    Extract sandbox name from org info.
    
    Args:
        org_info: Org info dict from get_org_info()
    
    Returns:
        Sandbox name if this is a sandbox org, None otherwise
    """
    instance_url = org_info.get("instanceUrl", "")
    username = org_info.get("username", "")
    
    # Check if it's a sandbox by looking for "sandbox" in instance URL
    if "sandbox" not in instance_url.lower():
        return None
    
    # Extract sandbox name from instance URL: https://mavenclinic--qa.sandbox.my.salesforce.com
    if "--" in instance_url:
        parts = instance_url.split("--")
        if len(parts) > 1:
            sandbox_part = parts[1].split(".")[0]
            return sandbox_part
    
    # Fallback: extract from username if it has format: user@domain.com.sandboxname
    if "." in username and "@" in username:
        domain_part = username.split("@")[1]
        if "." in domain_part:
            parts = domain_part.split(".")
            if len(parts) > 2:
                return parts[-1]
    
    return None


def format_user_record(user: Dict) -> Dict:
    """
    Format a Salesforce User record into a clean dict.
    
    Args:
        user: Raw User record from Salesforce query
    
    Returns:
        Formatted dict with common user fields
    """
    return {
        'Id': user.get('Id', ''),
        'FirstName': user.get('FirstName', ''),
        'LastName': user.get('LastName', ''),
        'Email': user.get('Email', ''),
        'Username': user.get('Username', ''),
        'Title': user.get('Title', ''),
        'Department': user.get('Department', ''),
        'Profile': user.get('Profile', {}).get('Name', '') if user.get('Profile') else '',
        'Role': user.get('UserRole', {}).get('Name', '') if user.get('UserRole') else '',
    }


def print_user_details(user: Dict, indent: str = "") -> None:
    """
    Print user details in a consistent format.
    
    Args:
        user: User dict (either raw Salesforce record or formatted)
        indent: Optional indentation prefix
    """
    # Handle both raw and formatted user dicts
    first_name = user.get('FirstName', '')
    last_name = user.get('LastName', '')
    email = user.get('Email', '')
    title = user.get('Title', '')
    department = user.get('Department', '')
    
    # Handle nested Profile/Role for raw records
    if user.get('Profile') and isinstance(user.get('Profile'), dict):
        profile = user['Profile'].get('Name', '')
    else:
        profile = user.get('Profile', '')
    
    if user.get('UserRole') and isinstance(user.get('UserRole'), dict):
        role = user['UserRole'].get('Name', '')
    else:
        role = user.get('Role', '')
    
    print(f"{indent}Name: {first_name} {last_name}")
    print(f"{indent}Email: {email}")
    if title:
        print(f"{indent}Title: {title}")
    if profile:
        print(f"{indent}Profile: {profile}")
    if role:
        print(f"{indent}Role: {role}")
    if department:
        print(f"{indent}Department: {department}")
