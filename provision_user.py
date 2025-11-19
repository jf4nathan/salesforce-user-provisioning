#!/usr/bin/env python3
"""
Salesforce User Provisioning Script
Automates user creation with permission set assignment based on Profile + Role analysis

Usage:
    python provision_user.py --csv users.csv --org mavenprod
    python provision_user.py --csv users.csv --org mavenprod --threshold 0.6

Requirements:
    - Salesforce CLI (sf) installed and authenticated
    - Python 3.7+
    - simple-salesforce library: pip install simple-salesforce
"""

import csv
import json
import argparse
import subprocess
import shutil
import os
import sys
from collections import Counter
from simple_salesforce import Salesforce
from typing import List, Dict, Set, Optional, Tuple


class SalesforceUserProvisioner:
    def __init__(self, org_alias: str):
        """Initialize Salesforce connection using sf CLI"""
        self.org_alias = org_alias
        self.org_info = self._get_org_info(org_alias)
        self.sandbox_name = self._extract_sandbox_name()
        self.sf = self._get_sf_connection()
    
    def _get_org_info(self, org_alias: str) -> Dict:
        """Get org information using sf CLI"""
        sf_cmd = shutil.which("sf") or "sf.cmd" if os.name == 'nt' else "sf"
        
        result = subprocess.run(
            [sf_cmd, "org", "display", "--target-org", org_alias, "--json"],
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode != 0:
            print(f"ERROR: Could not connect to org '{org_alias}'. Make sure you're authenticated.")
            print(f"Run: sf org login web --alias {org_alias}")
            print(f"Error: {result.stderr}")
            sys.exit(1)
        
        org_info = json.loads(result.stdout)
        return org_info["result"]
    
    def _extract_sandbox_name(self) -> Optional[str]:
        """Extract sandbox name from instance URL or username"""
        instance_url = self.org_info.get("instanceUrl", "")
        username = self.org_info.get("username", "")
        
        # Check if it's a sandbox by looking for "sandbox" in instance URL
        if "sandbox" not in instance_url.lower():
            return None
        
        # Extract sandbox name from instance URL: https://mavenclinic--qa.sandbox.my.salesforce.com
        # Pattern: --sandboxname.sandbox
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
                if len(parts) > 2:  # More than just domain.com
                    return parts[-1]  # Last part after domain
        
        return None
    
    def _get_sf_connection(self):
        """Get Salesforce connection using stored org info"""
        access_token = self.org_info["accessToken"]
        instance_url = self.org_info["instanceUrl"]
        
        return Salesforce(instance_url=instance_url, session_id=access_token)
    
    def get_profile_id(self, profile_name: str) -> Optional[str]:
        """Get Profile ID by name"""
        result = self.sf.query(
            f"SELECT Id FROM Profile WHERE Name = '{profile_name}' LIMIT 1"
        )
        if result['records']:
            return result['records'][0]['Id']
        return None
    
    def get_role_id(self, role_name: str) -> Optional[str]:
        """Get Role ID by name"""
        result = self.sf.query(
            f"SELECT Id FROM UserRole WHERE Name = '{role_name}' LIMIT 1"
        )
        if result['records']:
            return result['records'][0]['Id']
        return None
    
    def get_manager_id(self, manager_email: str) -> Optional[str]:
        """Get Manager User ID by email"""
        if not manager_email:
            return None
        result = self.sf.query(
            f"SELECT Id FROM User WHERE Email = '{manager_email}' AND IsActive = true LIMIT 1"
        )
        if result['records']:
            return result['records'][0]['Id']
        return None
    
    def get_user_to_mimic(self, mimic_user_email: str) -> Optional[Dict]:
        """Get user details (profile, role, title, permission sets) to mimic"""
        if not mimic_user_email:
            return None
        
        # Handle sandbox usernames - try both with and without sandbox suffix
        query_email = mimic_user_email
        if self.sandbox_name and not query_email.endswith(f".{self.sandbox_name}"):
            query_email = f"{mimic_user_email}.{self.sandbox_name}"
        
        # Try to find user by email or username
        query = f"""
        SELECT Id, FirstName, LastName, Email, Username, Profile.Name, UserRole.Name, Title
        FROM User 
        WHERE (Email = '{mimic_user_email}' OR Username = '{query_email}' OR Email = '{query_email}')
        AND IsActive = true 
        LIMIT 1
        """
        
        result = self.sf.query(query)
        if not result['records']:
            return None
        
        user = result['records'][0]
        user_id = user['Id']
        
        # Get permission sets assigned to this user
        psa_query = f"""
        SELECT PermissionSetId, PermissionSet.Name, PermissionSet.Label
        FROM PermissionSetAssignment
        WHERE AssigneeId = '{user_id}'
        """
        psa_result = self.sf.query(psa_query)
        
        # Get permission set groups assigned to this user
        psg_query = f"""
        SELECT PermissionSetGroupId, PermissionSetGroup.DeveloperName, PermissionSetGroup.MasterLabel
        FROM PermissionSetGroupAssignment
        WHERE AssigneeId = '{user_id}'
        """
        psg_result = self.sf.query(psg_query)
        
        permission_set_ids = [psa['PermissionSetId'] for psa in psa_result['records']]
        permission_set_group_ids = [psg['PermissionSetGroupId'] for psg in psg_result['records']]
        
        return {
            'Profile': user.get('Profile', {}).get('Name'),
            'Role': user.get('UserRole', {}).get('Name'),
            'Title': user.get('Title'),
            'permission_sets': permission_set_ids,
            'permission_set_groups': permission_set_group_ids,
            'user_id': user_id,
            'name': f"{user.get('FirstName', '')} {user.get('LastName', '')}".strip()
        }
    
    def get_permission_set_groups_and_members(self) -> Dict[str, Set[str]]:
        """Get all Permission Set Groups and their member permission sets"""
        group_to_permission_sets: Dict[str, Set[str]] = {}
        
        try:
            psg_query = "SELECT Id, DeveloperName, MasterLabel FROM PermissionSetGroup"
            psg_result = self.sf.query(psg_query)
            
            for group in psg_result['records']:
                group_id = group['Id']
                group_to_permission_sets[group_id] = set()
                
                component_query = f"""
                SELECT PermissionSetId
                FROM PermissionSetGroupComponent
                WHERE PermissionSetGroupId = '{group_id}'
                """
                try:
                    component_result = self.sf.restful(
                        f"tooling/query/?q={component_query.replace(' ', '+')}",
                        method='GET'
                    )
                    if 'records' in component_result:
                        for component in component_result['records']:
                            if 'PermissionSetId' in component:
                                group_to_permission_sets[group_id].add(component['PermissionSetId'])
                except Exception as e:
                    print(f"  WARNING: Could not query group members for {group['DeveloperName']}: {str(e)}")
                    pass
            
        except Exception as e:
            print(f"  WARNING: Error getting permission set groups: {str(e)}")
        
        return group_to_permission_sets
    
    def analyze_permission_sets(self, profile_id: str, role_id: str, threshold: float = 0.5) -> Dict[str, List[str]]:
        """Analyze existing users with same Profile + Role to determine permission sets"""
        query = f"""
        SELECT Id 
        FROM User 
        WHERE ProfileId = '{profile_id}' 
        AND UserRoleId = '{role_id}' 
        AND IsActive = true
        LIMIT 100
        """
        result = self.sf.query(query)
        
        if not result['records']:
            print(f"  WARNING: No existing users found with Profile+Role combo. Skipping permission set analysis.")
            return {'permission_set_groups': [], 'permission_sets': []}
        
        user_ids = [user['Id'] for user in result['records']]
        total_users = len(user_ids)
        user_ids_str = "', '".join(user_ids)
        
        # Get permission set groups and their members
        group_to_permission_sets = self.get_permission_set_groups_and_members()
        
        # Get group metadata
        psg_query = "SELECT Id, DeveloperName, MasterLabel FROM PermissionSetGroup"
        psg_result = self.sf.query(psg_query)
        all_groups = {psg['Id']: psg for psg in psg_result['records']}
        
        # Get permission set assignments
        psa_query = f"""
        SELECT AssigneeId, PermissionSetId, PermissionSet.Name, PermissionSet.Label
        FROM PermissionSetAssignment
        WHERE AssigneeId IN ('{user_ids_str}')
        """
        psa_result = self.sf.query(psa_query)
        
        # Build user -> permission sets mapping
        user_permission_sets: Dict[str, Set[str]] = {}
        for psa in psa_result['records']:
            user_id = psa['AssigneeId']
            ps_id = psa['PermissionSetId']
            if user_id not in user_permission_sets:
                user_permission_sets[user_id] = set()
            user_permission_sets[user_id].add(ps_id)
        
        # Identify which users have which permission set groups
        user_groups: Dict[str, Set[str]] = {}
        group_counts = Counter()
        
        for user_id, ps_set in user_permission_sets.items():
            user_groups[user_id] = set()
            for group_id, group_ps_set in group_to_permission_sets.items():
                if group_ps_set and group_ps_set.issubset(ps_set):
                    user_groups[user_id].add(group_id)
                    group_counts[group_id] += 1
        
        # Determine which groups to assign
        threshold_count = int(total_users * threshold)
        groups_to_assign = [
            group_id for group_id, count in group_counts.items()
            if count >= threshold_count
        ]
        
        # Get permission sets NOT in assigned groups
        ps_in_assigned_groups: Set[str] = set()
        for group_id in groups_to_assign:
            if group_id in group_to_permission_sets:
                ps_in_assigned_groups.update(group_to_permission_sets[group_id])
        
        # Count frequency of individual permission sets
        permission_set_counts = Counter()
        for psa in psa_result['records']:
            ps_id = psa['PermissionSetId']
            if ps_id not in ps_in_assigned_groups:
                permission_set_counts[ps_id] += 1
        
        # Get individual permission sets to assign
        individual_ps_to_assign = [
            ps_id for ps_id, count in permission_set_counts.items()
            if count >= threshold_count
        ]
        
        print(f"  Found {total_users} similar users.")
        print(f"  Found {len(all_groups)} permission set groups")
        print(f"  Assigning {len(groups_to_assign)} permission set groups")
        print(f"  Assigning {len(individual_ps_to_assign)} individual permission sets (not in groups)")
        
        return {
            'permission_set_groups': groups_to_assign,
            'permission_sets': individual_ps_to_assign
        }
    
    def parse_name_from_email(self, email: str) -> Tuple[str, str]:
        """Parse first name and last name from email (firstname.lastname@domain.com format)"""
        if not email or '@' not in email:
            raise ValueError(f"Invalid email format: {email}")
        
        local_part = email.split('@')[0]
        parts = local_part.split('.', 1)
        
        if len(parts) == 2:
            first_name = parts[0].capitalize()
            last_name = parts[1].capitalize()
        else:
            # Fallback: use entire local part as last name if no dot found
            first_name = parts[0].capitalize()
            last_name = parts[0].capitalize()
        
        return first_name, last_name
    
    def generate_alias(self, first_name: str, last_name: str) -> str:
        """Generate user alias (first initial + last name, max 8 chars)"""
        alias = (first_name[0] if first_name else '') + last_name
        return alias[:8]
    
    def create_user(self, user_data: Dict, permission_data: Dict[str, List[str]]) -> Optional[str]:
        """Create user in Salesforce"""
        # Lookup IDs
        profile_id = self.get_profile_id(user_data['Profile'])
        if not profile_id:
            print(f"  ERROR: Profile '{user_data['Profile']}' not found")
            return None
        
        role_id = self.get_role_id(user_data['Role']) if user_data.get('Role') else None
        manager_id = self.get_manager_id(user_data.get('ManagerEmail', ''))
        
        # Determine Marketing User checkbox
        is_marketing_user = user_data['Profile'].lower() == 'marketing'
        
        # Handle TimeZone
        timezone = user_data.get('TimeZone', '').strip() if user_data.get('TimeZone') else ''
        if not timezone:
            timezone = 'America/New_York'
            print(f"  WARNING: TimeZone not specified in CSV, defaulting to: {timezone}")
        else:
            print(f"  TimeZone from CSV: {timezone}")
        
        user_record = {
            'FirstName': user_data['FirstName'],
            'LastName': user_data['LastName'],
            'Email': user_data['Email'],
            'Username': user_data['Username'],
            'Alias': self.generate_alias(user_data['FirstName'], user_data['LastName']),
            'Title': user_data.get('Title', ''),
            'ProfileId': profile_id,
            'UserRoleId': role_id,
            'ManagerId': manager_id,
            'TimeZoneSidKey': timezone,
            'LocaleSidKey': 'en_US',
            'LanguageLocaleKey': 'en_US',
            'EmailEncodingKey': 'UTF-8',
            'UserPermissionsMarketingUser': is_marketing_user,
            'UserPermissionsInteractionUser': True  # Flow User checkbox
        }
        
        try:
            # Create user
            result = self.sf.User.create(user_record)
            user_id = result['id']
            print(f"  SUCCESS: User created: {user_id}")
            
            # Assign permission set groups FIRST
            if permission_data.get('permission_set_groups'):
                self.assign_permission_set_groups(user_id, permission_data['permission_set_groups'])
            
            # Then assign individual permission sets
            if permission_data.get('permission_sets'):
                self.assign_permission_sets(user_id, permission_data['permission_sets'])
            
            # Note: Password reset must be done manually in Salesforce UI
            print(f"  NOTE: Please reset password manually in Setup > Users > Users")
            
            return user_id
            
        except Exception as e:
            print(f"  ERROR: Error creating user: {str(e)}")
            return None
    
    def assign_permission_set_groups(self, user_id: str, permission_set_group_ids: List[str]):
        """Assign permission set groups to user"""
        for psg_id in permission_set_group_ids:
            try:
                assignment = {
                    'AssigneeId': user_id,
                    'PermissionSetGroupId': psg_id
                }
                self.sf.restful(
                    'sobjects/PermissionSetGroupAssignment/',
                    method='POST',
                    json=assignment
                )
                print(f"  SUCCESS: Assigned permission set group: {psg_id}")
            except Exception as e:
                print(f"  WARNING: Error assigning group {psg_id}: {str(e)}")
    
    def assign_permission_sets(self, user_id: str, permission_set_ids: List[str]):
        """Assign individual permission sets to user"""
        if not permission_set_ids:
            return
        
        success_count = 0
        for ps_id in permission_set_ids:
            try:
                assignment = {
                    'AssigneeId': user_id,
                    'PermissionSetId': ps_id
                }
                self.sf.restful(
                    'sobjects/PermissionSetAssignment/',
                    method='POST',
                    json=assignment
                )
                success_count += 1
            except Exception as e:
                error_msg = str(e)
                if 'INVALID_CROSS_REFERENCE_KEY' in error_msg and 'profile' in error_msg.lower():
                    # Profile-specific permission set, skip silently
                    pass
                else:
                    print(f"  WARNING: Error assigning permission set {ps_id}: {error_msg}")
        
        if success_count > 0:
            print(f"  SUCCESS: Assigned {success_count} individual permission sets")
    
    def provision_users_from_csv(self, csv_file: str, permission_set_threshold: float = 0.5):
        """Main method to provision users from CSV file"""
        users = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            users = list(reader)
        
        print(f"Processing {len(users)} users...\n")
        
        results = {
            'success': [],
            'failed': []
        }
        
        for i, user_data in enumerate(users, 1):
            # Validate required fields
            if 'Email' not in user_data or not user_data['Email']:
                results['failed'].append({
                    'user': user_data,
                    'error': 'Email is required'
                })
                continue
            
            email = user_data['Email'].strip()
            
            # Parse name from email and set username
            try:
                first_name, last_name = self.parse_name_from_email(email)
                user_data['FirstName'] = first_name
                user_data['LastName'] = last_name
                
                # Set username: append sandbox name if in sandbox environment
                username = email
                if self.sandbox_name:
                    username = f"{email}.{self.sandbox_name}"
                    print(f"  Sandbox detected: Appending '.{self.sandbox_name}' to username")
                user_data['Username'] = username
            except ValueError as e:
                results['failed'].append({
                    'user': user_data,
                    'error': str(e)
                })
                continue
            
            print(f"\n[{i}/{len(users)}] Creating user: {first_name} {last_name} ({email})")
            
            # Check if MimicUser is provided
            mimic_user_email = user_data.get('MimicUser', '').strip() if user_data.get('MimicUser') else None
            permission_data = {'permission_set_groups': [], 'permission_sets': []}
            
            if mimic_user_email:
                # Get user details to mimic
                print(f"  Mimicking user: {mimic_user_email}")
                mimic_user = self.get_user_to_mimic(mimic_user_email)
                
                if not mimic_user:
                    results['failed'].append({
                        'user': user_data,
                        'error': f"Could not find user to mimic: {mimic_user_email}"
                    })
                    continue
                
                # Copy profile, role, and title from mimic user (unless overridden in CSV)
                if not user_data.get('Profile'):
                    user_data['Profile'] = mimic_user['Profile']
                    print(f"  Using Profile from mimic user: {mimic_user['Profile']}")
                
                if not user_data.get('Role'):
                    user_data['Role'] = mimic_user['Role']
                    if mimic_user['Role']:
                        print(f"  Using Role from mimic user: {mimic_user['Role']}")
                
                if not user_data.get('Title'):
                    user_data['Title'] = mimic_user['Title'] or ''
                    if mimic_user['Title']:
                        print(f"  Using Title from mimic user: {mimic_user['Title']}")
                
                # Use permission sets directly from mimic user
                permission_data = {
                    'permission_set_groups': mimic_user['permission_set_groups'],
                    'permission_sets': mimic_user['permission_sets']
                }
                print(f"  Copying {len(mimic_user['permission_set_groups'])} permission set groups and {len(mimic_user['permission_sets'])} permission sets from {mimic_user['name']}")
            else:
                # Use traditional analysis method - Profile and Role must be provided in CSV
                if not user_data.get('Profile'):
                    results['failed'].append({
                        'user': user_data,
                        'error': 'Profile is required (or provide MimicUser)'
                    })
                    continue
            
            # Verify profile exists before creating user
            profile_id = self.get_profile_id(user_data['Profile'])
            if not profile_id:
                results['failed'].append({
                    'user': user_data,
                    'error': f"Profile '{user_data['Profile']}' not found"
                })
                continue
            
            # If not mimicking, analyze permission sets based on Profile + Role
            if not mimic_user_email:
                role_id = self.get_role_id(user_data['Role']) if user_data.get('Role') else None
                if role_id:
                    permission_data = self.analyze_permission_sets(profile_id, role_id, permission_set_threshold)
            
            # Create user
            user_id = self.create_user(user_data, permission_data)
            
            if user_id:
                results['success'].append({
                    'user': user_data,
                    'userId': user_id
                })
            else:
                results['failed'].append({
                    'user': user_data,
                    'error': 'User creation failed'
                })
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Provisioning Summary:")
        print(f"  Success: {len(results['success'])}")
        print(f"  Failed: {len(results['failed'])}")
        print(f"{'='*60}")
        
        return results


def get_org_info(org_alias: str) -> Optional[Dict]:
    """Get org information without creating a connection"""
    sf_cmd = shutil.which("sf") or "sf.cmd" if os.name == 'nt' else "sf"
    
    result = subprocess.run(
        [sf_cmd, "org", "display", "--target-org", org_alias, "--json"],
        capture_output=True,
        text=True,
        shell=True
    )
    if result.returncode != 0:
        return None
    
    try:
        org_info = json.loads(result.stdout)
        return org_info.get("result", {})
    except:
        return None


def confirm_org(org_alias: str) -> bool:
    """Display org information and ask for confirmation"""
    org_info = get_org_info(org_alias)
    
    if not org_info:
        print(f"ERROR: Could not retrieve information for org '{org_alias}'")
        print(f"Make sure the org alias is correct and you're authenticated.")
        return False
    
    username = org_info.get("username", "Unknown")
    org_id = org_info.get("orgId", "Unknown")
    instance_url = org_info.get("instanceUrl", "Unknown")
    org_type = org_info.get("instanceType", "")
    
    print("\n" + "="*60)
    print("***  CONFIRM TARGET ENVIRONMENT  ***")
    print("="*60)
    print(f"Org Alias:     {org_alias}")
    print(f"Username:      {username}")
    print(f"Org ID:        {org_id}")
    print(f"Instance URL:  {instance_url}")
    if org_type:
        print(f"Org Type:      {org_type}")
    print("="*60)
    print()
    
    # Check if it's production
    is_production = org_type.lower() == "production" or "prod" in org_alias.lower()
    if is_production:
        print("***  WARNING: This appears to be a PRODUCTION environment!  ***")
        print()
    
    response = input("Do you want to proceed with provisioning users in this org? (yes/no): ").strip().lower()
    
    return response in ['yes', 'y']


def main():
    parser = argparse.ArgumentParser(
        description='Provision Salesforce users from CSV file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Provision users in production
  python provision_user.py --csv users.csv --org mavenprod
  
  # Provision with custom threshold (60% instead of 50%)
  python provision_user.py --csv users.csv --org mavenprod --threshold 0.6
  
  # Skip confirmation prompt (useful for automation)
  python provision_user.py --csv users.csv --org mavenprod --skip-confirmation
  
CSV Format:
  Email,Title,ManagerEmail,Profile,Role,TimeZone
  john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York
        """
    )
    parser.add_argument('--csv', required=True, help='Path to CSV file with user data')
    parser.add_argument('--org', required=True, help='Salesforce org alias (e.g., mavenprod)')
    parser.add_argument('--threshold', type=float, default=0.5, 
                       help='Permission set assignment threshold (0.0-1.0, default: 0.5)')
    parser.add_argument('--output', default='provisioning_results.json',
                       help='Output file for results (default: provisioning_results.json)')
    parser.add_argument('--skip-confirmation', action='store_true',
                       help='Skip the org confirmation prompt (useful for automation)')
    
    args = parser.parse_args()
    
    # Validate CSV file exists
    if not os.path.exists(args.csv):
        print(f"ERROR: CSV file not found: {args.csv}")
        sys.exit(1)
    
    print("="*60)
    print("Salesforce User Provisioning")
    print("="*60)
    print(f"CSV File: {args.csv}")
    print(f"Target Org: {args.org}")
    print(f"Permission Set Threshold: {args.threshold * 100}%")
    print("="*60)
    
    # Confirm org unless --skip-confirmation is used
    if not args.skip_confirmation:
        if not confirm_org(args.org):
            print("\nProvisioning cancelled by user.")
            sys.exit(0)
        print()
    
    # Initialize provisioner
    try:
        provisioner = SalesforceUserProvisioner(args.org)
    except SystemExit:
        sys.exit(1)
    
    # Provision users
    results = provisioner.provision_users_from_csv(args.csv, args.threshold)
    
    # Save results
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {args.output}")
    
    # Print summary
    if results['success']:
        print("\nSUCCESS!")
        for success in results['success']:
            print(f"  User ID: {success['userId']}")
            print(f"  Username: {success['user']['Username']}")
            print(f"  Email: {success['user']['Email']}")
            print(f"  Name: {success['user'].get('FirstName', '')} {success['user'].get('LastName', '')}")
    
    if results['failed']:
        print("\nFAILED:")
        for failure in results['failed']:
            email = failure['user'].get('Email', 'Unknown')
            name = f"{failure['user'].get('FirstName', '')} {failure['user'].get('LastName', '')}".strip()
            if not name:
                name = email
            print(f"  User: {name} ({email})")
            print(f"  Error: {failure.get('error', 'Unknown error')}")


if __name__ == '__main__':
    main()

