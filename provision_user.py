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
from typing import List, Dict, Set, Optional


class SalesforceUserProvisioner:
    def __init__(self, org_alias: str):
        """Initialize Salesforce connection using sf CLI"""
        self.org_alias = org_alias
        self.sf = self._get_sf_connection(org_alias)
    
    def _get_sf_connection(self, org_alias: str):
        """Get Salesforce connection using sf CLI"""
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
        access_token = org_info["result"]["accessToken"]
        instance_url = org_info["result"]["instanceUrl"]
        
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
            print(f"\n[{i}/{len(users)}] Creating user: {user_data['FirstName']} {user_data['LastName']}")
            
            # Analyze permission sets
            profile_id = self.get_profile_id(user_data['Profile'])
            role_id = self.get_role_id(user_data['Role']) if user_data.get('Role') else None
            
            if not profile_id:
                results['failed'].append({
                    'user': user_data,
                    'error': f"Profile '{user_data['Profile']}' not found"
                })
                continue
            
            permission_data = {'permission_set_groups': [], 'permission_sets': []}
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
  
CSV Format:
  FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
  John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York
        """
    )
    parser.add_argument('--csv', required=True, help='Path to CSV file with user data')
    parser.add_argument('--org', required=True, help='Salesforce org alias (e.g., mavenprod)')
    parser.add_argument('--threshold', type=float, default=0.5, 
                       help='Permission set assignment threshold (0.0-1.0, default: 0.5)')
    parser.add_argument('--output', default='provisioning_results.json',
                       help='Output file for results (default: provisioning_results.json)')
    
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
    
    if results['failed']:
        print("\nFAILED:")
        for failure in results['failed']:
            print(f"  User: {failure['user'].get('FirstName', '')} {failure['user'].get('LastName', '')}")
            print(f"  Error: {failure.get('error', 'Unknown error')}")


if __name__ == '__main__':
    main()

