#!/usr/bin/env python3
"""
Reactivate a Salesforce user and ensure Gainsight license and user are provisioned.

Usage:
    python reactivate_user.py --org mavenprod --first-name "Gianna" --last-name "Cruz"
    python reactivate_user.py --org mavenprod --email gianna.cruz@mavenclinic.com
"""

import argparse
import json
import os
import sys
from typing import Optional, Dict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.sf_utils import get_org_info, get_sf_connection
from scripts.integrations.gainsight_client import GainsightClient, create_client_from_config as create_gainsight_client
from scripts.core.provision_user import SalesforceUserProvisioner


def find_user_by_name(sf, first_name: str, last_name: str, include_inactive: bool = True) -> Optional[Dict]:
    """Find user by first and last name, optionally including inactive users"""
    is_active_filter = "" if include_inactive else "AND IsActive = true"
    
    query = f"""
    SELECT Id, FirstName, LastName, Email, Username, Profile.Name, IsActive, TimeZoneSidKey
    FROM User
    WHERE FirstName = '{first_name}'
    AND LastName = '{last_name}'
    {is_active_filter}
    LIMIT 10
    """
    
    try:
        result = sf.query(query)
        if result['records']:
            if len(result['records']) == 1:
                return result['records'][0]
            else:
                print(f"Found {len(result['records'])} users matching '{first_name} {last_name}':")
                for i, user in enumerate(result['records'], 1):
                    status = "ACTIVE" if user.get('IsActive') else "INACTIVE"
                    print(f"  {i}. {user.get('Email', 'N/A')} ({status})")
                return result['records'][0]  # Return first match
        return None
    except Exception as e:
        print(f"ERROR: Failed to query users: {str(e)}")
        return None


def find_user_by_email(sf, email: str, include_inactive: bool = True) -> Optional[Dict]:
    """Find user by email, optionally including inactive users"""
    is_active_filter = "" if include_inactive else "AND IsActive = true"
    
    query = f"""
    SELECT Id, FirstName, LastName, Email, Username, Profile.Name, IsActive, TimeZoneSidKey
    FROM User
    WHERE Email = '{email}'
    {is_active_filter}
    LIMIT 1
    """
    
    try:
        result = sf.query(query)
        if result['records']:
            return result['records'][0]
        return None
    except Exception as e:
        print(f"ERROR: Failed to query users: {str(e)}")
        return None


def reactivate_salesforce_user(sf, user_id: str) -> bool:
    """Reactivate a Salesforce user"""
    try:
        sf.User.update(user_id, {'IsActive': True})
        print(f"  SUCCESS: Reactivated Salesforce user")
        return True
    except Exception as e:
        print(f"  ERROR: Failed to reactivate user {user_id}: {str(e)}")
        return False


def ensure_gainsight_license(provisioner: SalesforceUserProvisioner, user_id: str) -> bool:
    """Ensure Gainsight license is assigned to user"""
    return provisioner.assign_gainsight_license(user_id)


def ensure_gainsight_user(gainsight_client: Optional[GainsightClient], user_data: Dict) -> Optional[Dict]:
    """
    Ensure Gainsight user exists and is active.
    Returns Gainsight user dict if successful, None otherwise.
    """
    if not gainsight_client:
        print("  INFO: Gainsight client not configured, skipping Gainsight user provisioning")
        return None
    
    email = user_data.get('Email', '')
    first_name = user_data.get('FirstName', '')
    last_name = user_data.get('LastName', '')
    timezone = user_data.get('TimeZone', 'America/New_York')
    
    print(f"  Checking Gainsight user for: {email}")
    
    try:
        # Check if user exists in Gainsight
        existing_user = gainsight_client.search_user_by_email(email)
        
        if existing_user:
            gs_user_id = existing_user.get('id')
            is_active = existing_user.get('active', False)
            
            # Check current license type
            gs_ext = existing_user.get('urn:ietf:params:scim:schemas:extension:gainsight:2.0:User', {})
            current_license = gs_ext.get('LicenseType', '')
            needs_license_update = current_license != 'Full'
            
            if is_active and not needs_license_update:
                print(f"  INFO: Gainsight user already exists and is active with Full license (ID: {gs_user_id})")
                return existing_user
            else:
                # Update user: reactivate if needed and/or update license type
                updates_needed = []
                if not is_active:
                    updates_needed.append("reactivate")
                if needs_license_update:
                    updates_needed.append("update license to Full")
                
                print(f"  INFO: Gainsight user exists, {' and '.join(updates_needed)}...")
                
                # Update license type to Full
                if needs_license_update:
                    gainsight_client.update_user(gs_user_id, license_type="Full")
                    print(f"  SUCCESS: Updated license type to Full")
                
                # Reactivate if needed
                if not is_active:
                    gainsight_client.activate_user(gs_user_id)
                    print(f"  SUCCESS: Reactivated Gainsight user")
                
                # Fetch updated user
                return gainsight_client.get_user(gs_user_id)
        else:
            # Create new user
            print(f"  INFO: Gainsight user does not exist, creating...")
            result = gainsight_client.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                timezone=timezone,
                license_type="Full",
                groups=[{"display": "client resources"}]
            )
            print(f"  SUCCESS: Created Gainsight user (ID: {result.get('id')})")
            return result
            
    except Exception as e:
        print(f"  WARNING: Failed to provision Gainsight user: {str(e)}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Reactivate a Salesforce user and ensure Gainsight setup')
    parser.add_argument('--org', required=True, help='Salesforce org alias (e.g., mavenprod)')
    parser.add_argument('--first-name', help='User first name')
    parser.add_argument('--last-name', help='User last name')
    parser.add_argument('--email', help='User email address')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    
    args = parser.parse_args()
    
    if not args.email and not (args.first_name and args.last_name):
        print("ERROR: Provide either --email or both --first-name and --last-name")
        sys.exit(1)
    
    # Connect to Salesforce
    print(f"Connecting to org: {args.org}")
    try:
        sf = get_sf_connection(args.org)
        org_info = get_org_info(args.org)
        print(f"Connected to: {org_info.get('username', 'N/A')}")
    except Exception as e:
        print(f"ERROR: Failed to connect to Salesforce: {str(e)}")
        sys.exit(1)
    
    # Find user
    print("\nFinding user...")
    if args.email:
        user = find_user_by_email(sf, args.email, include_inactive=True)
    else:
        user = find_user_by_name(sf, args.first_name, args.last_name, include_inactive=True)
    
    if not user:
        print(f"ERROR: User not found")
        sys.exit(1)
    
    print(f"Found user: {user.get('FirstName', '')} {user.get('LastName', '')} ({user.get('Email', 'N/A')})")
    print(f"  User ID: {user.get('Id')}")
    print(f"  Current Status: {'ACTIVE' if user.get('IsActive') else 'INACTIVE'}")
    print(f"  Profile: {user.get('Profile', {}).get('Name', 'N/A') if user.get('Profile') else 'N/A'}")
    
    user_id = user.get('Id')
    is_active = user.get('IsActive', False)
    
    # Load Gainsight client if config exists
    gainsight_client = None
    default_gainsight_config = os.getenv("GAINSIGHT_CONFIG_PATH", "gainsight_config.json")
    if os.path.exists(default_gainsight_config):
        try:
            gainsight_client = create_gainsight_client(default_gainsight_config)
            print("\nGainsight integration: ENABLED")
        except Exception as e:
            print(f"WARNING: Failed to load Gainsight config: {e}")
            print("Continuing without Gainsight integration...")
    else:
        print("\nGainsight integration: DISABLED (no gainsight_config.json found)")
    
    # Initialize provisioner for license assignment
    provisioner = SalesforceUserProvisioner(args.org, None, gainsight_client)
    
    results = {
        "user_id": user_id,
        "email": user.get('Email'),
        "salesforce_reactivated": False,
        "gainsight_license_assigned": False,
        "gainsight_user_provisioned": False
    }
    
    print("\n" + "="*60)
    print("REACTIVATION SUMMARY")
    print("="*60)
    
    # Step 1: Reactivate Salesforce user if inactive
    if not is_active:
        if args.dry_run:
            print(f"\n[DRY RUN] Would reactivate Salesforce user")
            results["salesforce_reactivated"] = True
        else:
            print(f"\nReactivating Salesforce user...")
            if reactivate_salesforce_user(sf, user_id):
                results["salesforce_reactivated"] = True
            else:
                print("ERROR: Failed to reactivate user. Stopping.")
                sys.exit(1)
    else:
        print(f"\nSalesforce user is already active")
        results["salesforce_reactivated"] = True
    
    # Step 2: Assign Gainsight license
    print(f"\nEnsuring Gainsight license is assigned...")
    if args.dry_run:
        print(f"[DRY RUN] Would check and assign Gainsight license if needed")
        results["gainsight_license_assigned"] = True
    else:
        if ensure_gainsight_license(provisioner, user_id):
            results["gainsight_license_assigned"] = True
        else:
            print("WARNING: Could not assign Gainsight license")
    
    # Step 3: Ensure Gainsight user exists and is active
    if gainsight_client:
        print(f"\nEnsuring Gainsight user exists and is active...")
        if args.dry_run:
            print(f"[DRY RUN] Would check and create/activate Gainsight user if needed")
            results["gainsight_user_provisioned"] = True
        else:
            # Map TimeZoneSidKey to timezone string (common mappings)
            timezone_map = {
                'America/New_York': 'America/New_York',
                'America/Los_Angeles': 'America/Los_Angeles',
                'America/Chicago': 'America/Chicago',
                'America/Denver': 'America/Denver',
            }
            timezone_sid = user.get('TimeZoneSidKey', 'America/New_York')
            timezone = timezone_map.get(timezone_sid, 'America/New_York')
            
            user_data = {
                'Email': user.get('Email'),
                'FirstName': user.get('FirstName', ''),
                'LastName': user.get('LastName', ''),
                'TimeZone': timezone
            }
            gs_user = ensure_gainsight_user(gainsight_client, user_data)
            if gs_user:
                results["gainsight_user_provisioned"] = True
                results["gainsight_user_id"] = gs_user.get('id')
            else:
                print("WARNING: Could not provision Gainsight user")
    
    # Save results
    output_file = "temp/reactivation_results.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Salesforce Reactivated: {'Yes' if results['salesforce_reactivated'] else 'No'}")
    print(f"Gainsight License Assigned: {'Yes' if results['gainsight_license_assigned'] else 'No'}")
    print(f"Gainsight User Provisioned: {'Yes' if results['gainsight_user_provisioned'] else 'No'}")
    print(f"\nResults saved to: {output_file}")


if __name__ == '__main__':
    main()
