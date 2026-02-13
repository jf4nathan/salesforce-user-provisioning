#!/usr/bin/env python3
"""
Salesforce User Deprovisioning Script
Deactivates users and removes package license assignments.

Usage:
    python deprovision_user.py --org mavenprod --names "John Doe, Jane Smith"
    python deprovision_user.py --org mavenprod --csv temp/deprovisioning_list.csv
    python deprovision_user.py --org mavenprod --names "John Doe" --dry-run
    python deprovision_user.py --org mavenprod --csv temp/deprovisioning_list.csv --skip-confirmation

Requirements:
    - Salesforce CLI (sf) installed and authenticated
    - Python 3.7+
    - simple-salesforce library: pip install simple-salesforce
"""

import csv
import json
import argparse
import os
import sys
from datetime import datetime
from simple_salesforce import Salesforce
from typing import List, Dict, Optional, Tuple
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.sf_utils import get_org_info, get_sf_connection, format_user_record, print_user_details
from scripts.integrations.gainsight_client import GainsightClient, create_client_from_config as create_gainsight_client


class SalesforceUserDeprovisioner:
    def __init__(self, org_alias: str, gainsight_client: Optional[GainsightClient] = None):
        """
        Initialize Salesforce connection using sf CLI.

        Args:
            org_alias: Salesforce org alias (e.g., 'mavenprod')
            gainsight_client: Optional Gainsight client for user deactivation
        """
        self.org_alias = org_alias
        self.org_info = get_org_info(org_alias)
        self.sf = Salesforce(
            instance_url=self.org_info["instanceUrl"],
            session_id=self.org_info["accessToken"]
        )
        self.gainsight_client = gainsight_client

    def find_active_users_by_name(self, first_name: str, last_name: str) -> List[Dict]:
        """
        Find active users matching first and last name.

        Args:
            first_name: User's first name
            last_name: User's last name

        Returns:
            List of matching user records
        """
        query = f"""
        SELECT Id, FirstName, LastName, Email, Username, Profile.Name,
               UserRole.Name, Title, Department
        FROM User
        WHERE FirstName = '{first_name}'
        AND LastName = '{last_name}'
        AND IsActive = true
        """
        try:
            result = self.sf.query(query)
            return result['records']
        except Exception as e:
            print(f"  ERROR: Failed to query users: {str(e)}")
            return []

    def get_user_package_licenses(self, user_id: str) -> List[Dict]:
        """
        Get all package license assignments for a user.

        Args:
            user_id: Salesforce User ID

        Returns:
            List of UserPackageLicense records with package details
        """
        query = f"""
        SELECT Id, PackageLicenseId, PackageLicense.NamespacePrefix,
               PackageLicense.Status
        FROM UserPackageLicense
        WHERE UserId = '{user_id}'
        """
        try:
            result = self.sf.query(query)
            return result['records']
        except Exception as e:
            print(f"  WARNING: Could not query package licenses: {str(e)}")
            return []

    def remove_package_license(self, assignment_id: str) -> bool:
        """
        Remove a single package license assignment.

        Args:
            assignment_id: UserPackageLicense record ID

        Returns:
            True if removed successfully, False otherwise
        """
        try:
            self.sf.restful(
                f'sobjects/UserPackageLicense/{assignment_id}',
                method='DELETE'
            )
            return True
        except Exception as e:
            print(f"  WARNING: Failed to remove license {assignment_id}: {str(e)}")
            return False

    def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate a Salesforce user.

        Args:
            user_id: Salesforce User ID

        Returns:
            True if deactivated successfully, False otherwise
        """
        try:
            self.sf.User.update(user_id, {'IsActive': False})
            return True
        except Exception as e:
            print(f"  ERROR: Failed to deactivate user {user_id}: {str(e)}")
            return False

    def deactivate_gainsight_user(self, email: str, dry_run: bool = False) -> Optional[Dict]:
        """
        Deactivate a user in Gainsight if they exist and are active.

        Args:
            email: User's email address
            dry_run: If True, only preview the change

        Returns:
            Dict with Gainsight deactivation details, or None if not applicable
        """
        if not self.gainsight_client:
            return None

        try:
            gs_user = self.gainsight_client.search_user_by_email(email)
            if not gs_user:
                print(f"  Gainsight: User not found, skipping.")
                return None

            gs_user_id = gs_user.get('id', '')
            is_active = gs_user.get('active', False)

            if not is_active:
                print(f"  Gainsight: User already inactive (ID: {gs_user_id}), skipping.")
                return {'gainsightUserId': gs_user_id, 'status': 'already_inactive'}

            if dry_run:
                print(f"  [DRY RUN] Would deactivate Gainsight user (ID: {gs_user_id})")
                return {'gainsightUserId': gs_user_id, 'status': 'dry_run'}

            self.gainsight_client.deactivate_user(gs_user_id)
            print(f"  SUCCESS: Deactivated Gainsight user (ID: {gs_user_id})")
            return {'gainsightUserId': gs_user_id, 'status': 'deactivated'}

        except Exception as e:
            print(f"  WARNING: Failed to deactivate Gainsight user: {str(e)}")
            return {'status': 'error', 'error': str(e)}

    def deprovision_user(self, user_record: Dict, dry_run: bool = False) -> Dict:
        """
        Deprovision a single user: remove package licenses, deactivate in Salesforce,
        and deactivate in Gainsight if applicable.

        Args:
            user_record: Salesforce User record dict
            dry_run: If True, only preview changes without executing

        Returns:
            Result dict with status and details
        """
        user_id = user_record['Id']
        first_name = user_record.get('FirstName', '')
        last_name = user_record.get('LastName', '')
        email = user_record.get('Email', '')
        profile = user_record.get('Profile', {})
        profile_name = profile.get('Name', '') if isinstance(profile, dict) else str(profile)

        result = {
            'userId': user_id,
            'name': f"{first_name} {last_name}",
            'email': email,
            'profile': profile_name,
            'licensesRemoved': [],
            'deactivated': False,
            'gainsight': None,
            'errors': []
        }

        # Step 1: Find and remove package licenses
        licenses = self.get_user_package_licenses(user_id)

        if licenses:
            print(f"  Found {len(licenses)} package license(s):")
            for lic in licenses:
                namespace = lic.get('PackageLicense', {}).get('NamespacePrefix', 'Unknown') if lic.get('PackageLicense') else 'Unknown'
                lic_id = lic['Id']
                print(f"    - {namespace} (ID: {lic_id})")

                if dry_run:
                    print(f"      [DRY RUN] Would remove license: {namespace}")
                    result['licensesRemoved'].append({'id': lic_id, 'namespace': namespace, 'dryRun': True})
                else:
                    if self.remove_package_license(lic_id):
                        print(f"      Removed license: {namespace}")
                        result['licensesRemoved'].append({'id': lic_id, 'namespace': namespace})
                    else:
                        error = f"Failed to remove license: {namespace} ({lic_id})"
                        result['errors'].append(error)
        else:
            print(f"  No package licenses found.")

        # Step 2: Deactivate user in Salesforce
        if dry_run:
            print(f"  [DRY RUN] Would deactivate user: {first_name} {last_name}")
            result['deactivated'] = False
            result['dryRun'] = True
        else:
            if self.deactivate_user(user_id):
                print(f"  SUCCESS: Deactivated user: {first_name} {last_name}")
                result['deactivated'] = True
            else:
                error = f"Failed to deactivate user {user_id}"
                result['errors'].append(error)

        # Step 3: Deactivate user in Gainsight (if configured, exists, and active)
        gs_result = self.deactivate_gainsight_user(email, dry_run=dry_run)
        if gs_result:
            result['gainsight'] = gs_result
            if gs_result.get('status') == 'error':
                result['errors'].append(f"Gainsight: {gs_result.get('error', 'Unknown error')}")

        return result

    def prompt_user_selection(self, matches: List[Dict], name: str) -> Optional[Dict]:
        """
        Prompt user to select from multiple matching records.

        Args:
            matches: List of matching user records
            name: The name that was searched

        Returns:
            Selected user record, or None if skipped
        """
        print(f"\n  Multiple matches found for '{name}':")
        for idx, user in enumerate(matches, 1):
            profile = user.get('Profile', {})
            profile_name = profile.get('Name', '') if isinstance(profile, dict) else ''
            role = user.get('UserRole', {})
            role_name = role.get('Name', '') if isinstance(role, dict) else ''
            print(f"    [{idx}] {user.get('FirstName', '')} {user.get('LastName', '')}")
            print(f"        Email: {user.get('Email', '')}")
            print(f"        Profile: {profile_name}")
            print(f"        Role: {role_name}")
            print(f"        ID: {user['Id']}")

        print(f"    [0] Skip this user")

        while True:
            try:
                choice = input(f"\n  Select user (0-{len(matches)}): ").strip()
                choice_num = int(choice)
                if choice_num == 0:
                    return None
                if 1 <= choice_num <= len(matches):
                    return matches[choice_num - 1]
                print(f"  Invalid choice. Enter 0-{len(matches)}.")
            except (ValueError, EOFError):
                print(f"  Invalid input. Enter a number 0-{len(matches)}.")

    def process_names(self, names: List[Tuple[str, str]], dry_run: bool = False,
                      skip_confirmation: bool = False) -> Dict:
        """
        Process a list of (first_name, last_name) tuples for deprovisioning.

        Args:
            names: List of (first_name, last_name) tuples
            dry_run: If True, only preview changes
            skip_confirmation: If True, skip per-user confirmation prompts

        Returns:
            Results dict with success/failed/skipped lists
        """
        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'timestamp': datetime.now().isoformat(),
            'org': self.org_alias,
            'dryRun': dry_run
        }

        for i, (first_name, last_name) in enumerate(names, 1):
            full_name = f"{first_name} {last_name}"
            print(f"\n{'='*60}")
            print(f"[{i}/{len(names)}] Processing: {full_name}")
            print(f"{'='*60}")

            # Find matching active users
            matches = self.find_active_users_by_name(first_name, last_name)

            if not matches:
                print(f"  No active user found for: {full_name}")
                results['skipped'].append({
                    'name': full_name,
                    'reason': 'No active user found'
                })
                continue

            # Handle single vs multiple matches
            if len(matches) == 1:
                selected_user = matches[0]
                profile = selected_user.get('Profile', {})
                profile_name = profile.get('Name', '') if isinstance(profile, dict) else ''
                print(f"  Found user: {selected_user.get('Email', '')} (Profile: {profile_name})")

                if not skip_confirmation:
                    confirm = input(f"  Proceed with deprovisioning? (y/n): ").strip().lower()
                    if confirm != 'y':
                        print(f"  Skipped: {full_name}")
                        results['skipped'].append({
                            'name': full_name,
                            'reason': 'User declined'
                        })
                        continue
            else:
                if skip_confirmation:
                    # With skip-confirmation and multiple matches, skip to avoid ambiguity
                    print(f"  WARNING: Multiple matches found for '{full_name}', skipping (use interactive mode to select)")
                    results['skipped'].append({
                        'name': full_name,
                        'reason': f'Multiple matches ({len(matches)}) - requires interactive selection'
                    })
                    continue

                selected_user = self.prompt_user_selection(matches, full_name)
                if not selected_user:
                    print(f"  Skipped: {full_name}")
                    results['skipped'].append({
                        'name': full_name,
                        'reason': 'User skipped selection'
                    })
                    continue

            # Deprovision the selected user
            deprovision_result = self.deprovision_user(selected_user, dry_run=dry_run)

            if deprovision_result.get('errors'):
                results['failed'].append(deprovision_result)
            else:
                results['success'].append(deprovision_result)

        return results


def parse_names_from_string(names_str: str) -> List[Tuple[str, str]]:
    """
    Parse comma-separated names into (first_name, last_name) tuples.

    Args:
        names_str: Comma-separated names, e.g. "John Doe, Jane Smith"

    Returns:
        List of (first_name, last_name) tuples
    """
    names = []
    for name in names_str.split(','):
        name = name.strip()
        if not name:
            continue
        parts = name.split(None, 1)  # Split on first whitespace
        if len(parts) == 2:
            names.append((parts[0].strip(), parts[1].strip()))
        elif len(parts) == 1:
            print(f"  WARNING: Could not parse full name from '{name}' (expected 'FirstName LastName'). Skipping.")
        else:
            print(f"  WARNING: Empty name entry, skipping.")
    return names


def parse_names_from_csv(csv_file: str) -> List[Tuple[str, str]]:
    """
    Parse names from a CSV file.

    Supports columns: Name (full name), or FirstName + LastName.

    Args:
        csv_file: Path to CSV file

    Returns:
        List of (first_name, last_name) tuples
    """
    names = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if 'FirstName' in row and 'LastName' in row:
                first = row['FirstName'].strip()
                last = row['LastName'].strip()
                if first and last:
                    names.append((first, last))
            elif 'Name' in row:
                parts = row['Name'].strip().split(None, 1)
                if len(parts) == 2:
                    names.append((parts[0], parts[1]))
                else:
                    print(f"  WARNING: Could not parse name '{row['Name']}'. Skipping.")
    return names


def main():
    parser = argparse.ArgumentParser(
        description='Deprovision Salesforce users: remove package licenses and deactivate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deprovision by names (interactive)
  python deprovision_user.py --org mavenprod --names "John Doe, Jane Smith"

  # Deprovision from CSV file
  python deprovision_user.py --org mavenprod --csv temp/deprovisioning_list.csv

  # Dry run (preview only, no changes)
  python deprovision_user.py --org mavenprod --names "John Doe" --dry-run

  # Skip per-user confirmation
  python deprovision_user.py --org mavenprod --names "John Doe" --skip-confirmation

CSV Format (either format works):
  Name
  John Doe
  Jane Smith

  FirstName,LastName
  John,Doe
  Jane,Smith
        """
    )
    parser.add_argument('--org', required=True, help='Salesforce org alias (e.g., mavenprod)')

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--names', help='Comma-separated list of names (e.g., "John Doe, Jane Smith")')
    input_group.add_argument('--csv', help='Path to CSV file with names')

    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without executing')
    parser.add_argument('--skip-confirmation', action='store_true',
                        help='Skip per-user confirmation prompts')
    parser.add_argument('--output', default='temp/deprovisioning_results.json',
                        help='Output file for results (default: temp/deprovisioning_results.json)')

    args = parser.parse_args()

    # Parse names from input
    if args.names:
        names = parse_names_from_string(args.names)
    else:
        if not os.path.exists(args.csv):
            print(f"ERROR: CSV file not found: {args.csv}")
            sys.exit(1)
        names = parse_names_from_csv(args.csv)

    if not names:
        print("ERROR: No valid names provided.")
        sys.exit(1)

    # Display header
    print("=" * 60)
    print("Salesforce User Deprovisioning")
    print("=" * 60)
    print(f"Target Org: {args.org}")
    print(f"Users to process: {len(names)}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    print("=" * 60)

    # List users to process
    print("\nUsers to deprovision:")
    for first, last in names:
        print(f"  - {first} {last}")

    if not args.skip_confirmation:
        confirm = input(f"\nProceed with deprovisioning {len(names)} user(s)? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)

    # Initialize Gainsight client if configured
    gainsight_client = None
    default_gainsight_config = os.getenv("GAINSIGHT_CONFIG_PATH", "gainsight_config.json")
    if os.path.exists(default_gainsight_config):
        try:
            gainsight_client = create_gainsight_client(default_gainsight_config)
            print("Gainsight integration: ENABLED")
        except Exception as e:
            print(f"WARNING: Failed to load Gainsight config: {e}")
            print("Continuing without Gainsight integration...")
    else:
        print("Gainsight integration: DISABLED (no gainsight_config.json found)")

    print()

    # Initialize deprovisioner
    try:
        deprovisioner = SalesforceUserDeprovisioner(args.org, gainsight_client)
    except SystemExit:
        sys.exit(1)

    # Process users
    results = deprovisioner.process_names(
        names,
        dry_run=args.dry_run,
        skip_confirmation=args.skip_confirmation
    )

    # Summary
    print(f"\n{'='*60}")
    print("Deprovisioning Summary:")
    print(f"  Deactivated: {len(results['success'])}")
    print(f"  Failed: {len(results['failed'])}")
    print(f"  Skipped: {len(results['skipped'])}")
    print(f"{'='*60}")

    if results['success']:
        print("\nDeactivated users:")
        for r in results['success']:
            licenses_count = len(r.get('licensesRemoved', []))
            gs = r.get('gainsight')
            gs_status = f" | Gainsight: {gs['status']}" if gs else ""
            print(f"  - {r['name']} ({r['email']}) | Licenses removed: {licenses_count}{gs_status}")

    if results['failed']:
        print("\nFailed:")
        for r in results['failed']:
            print(f"  - {r['name']} ({r['email']})")
            for err in r.get('errors', []):
                print(f"    Error: {err}")

    if results['skipped']:
        print("\nSkipped:")
        for r in results['skipped']:
            print(f"  - {r['name']}: {r['reason']}")

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Save results
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {args.output}")


if __name__ == '__main__':
    main()
