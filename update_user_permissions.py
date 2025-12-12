#!/usr/bin/env python3
"""
Salesforce User Permissions Update Script
Updates existing user's Profile, Role, and Permission Sets by mimicking another user

Usage:
    python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod
    python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod --dry-run
    python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod --jira-config jira_config.json

Requirements:
    - Salesforce CLI (sf) installed and authenticated
    - Python 3.7+
    - simple-salesforce library: pip install simple-salesforce
    - requests library: pip install requests (for Jira integration)
"""

import json
import argparse
import subprocess
import shutil
import os
import sys
import requests
import base64
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
from simple_salesforce import Salesforce

# Import classes from provision_user.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provision_user import SalesforceUserProvisioner, JiraClient


class UserPermissionsUpdater(SalesforceUserProvisioner):
    """Extends SalesforceUserProvisioner to add user update functionality"""
    
    def find_user_by_email(self, email: str) -> Optional[Dict]:
        """Find user by email address"""
        if not email:
            return None
        
        # Handle sandbox usernames - try both with and without sandbox suffix
        query_email = email
        if self.sandbox_name and not query_email.endswith(f".{self.sandbox_name}"):
            query_email = f"{email}.{self.sandbox_name}"
        
        # Try to find user by email or username
        query = f"""
        SELECT Id, FirstName, LastName, Email, Username, Profile.Name, ProfileId, UserRole.Name, UserRoleId, Title
        FROM User 
        WHERE (Email = '{email}' OR Username = '{query_email}' OR Email = '{query_email}')
        AND IsActive = true 
        LIMIT 1
        """
        
        try:
            result = self.sf.query(query)
            if not result['records']:
                return None
            
            user = result['records'][0]
            return {
                'Id': user['Id'],
                'FirstName': user.get('FirstName', ''),
                'LastName': user.get('LastName', ''),
                'Email': user.get('Email', ''),
                'Username': user.get('Username', ''),
                'Profile': user.get('Profile', {}).get('Name'),
                'ProfileId': user.get('ProfileId'),
                'Role': user.get('UserRole', {}).get('Name'),
                'RoleId': user.get('UserRoleId'),
                'Title': user.get('Title')
            }
        except Exception as e:
            print(f"  ERROR: Could not find user: {str(e)}")
            return None
    
    def get_user_current_permissions(self, user_id: str) -> Dict:
        """Get current Profile, Role, and Permission Sets for a user"""
        # Get user details
        user_query = f"""
        SELECT Id, Profile.Name, ProfileId, UserRole.Name, UserRoleId
        FROM User
        WHERE Id = '{user_id}'
        """
        
        user_result = self.sf.query(user_query)
        if not user_result['records']:
            return {}
        
        user = user_result['records'][0]
        
        # Get permission set assignments
        psa_query = f"""
        SELECT PermissionSetId, PermissionSet.Name, PermissionSet.Label
        FROM PermissionSetAssignment
        WHERE AssigneeId = '{user_id}'
        """
        
        permission_set_ids = []
        permission_set_names = []
        try:
            psa_result = self.sf.query(psa_query)
            for psa in psa_result['records']:
                ps_id = psa['PermissionSetId']
                ps_name = psa.get('PermissionSet', {}).get('Label') or psa.get('PermissionSet', {}).get('Name', 'Unknown')
                permission_set_ids.append(ps_id)
                permission_set_names.append(ps_name)
        except Exception as e:
            print(f"  WARNING: Could not get permission sets: {str(e)}")
        
        # Get permission set group assignments (if supported)
        permission_set_group_ids = []
        permission_set_group_names = []
        try:
            # Note: PermissionSetGroupAssignment may not be available in all orgs
            psg_query = f"""
            SELECT PermissionSetGroupId
            FROM PermissionSetGroupAssignment
            WHERE AssigneeId = '{user_id}'
            """
            psg_result = self.sf.query(psg_query)
            for psg in psg_result['records']:
                psg_id = psg['PermissionSetGroupId']
                permission_set_group_ids.append(psg_id)
        except Exception as e:
            # This is expected if PermissionSetGroupAssignment is not available
            pass
        
        if permission_set_group_ids:
            permission_set_group_names = self.get_permission_set_group_names(permission_set_group_ids)
        
        return {
            'Profile': user.get('Profile', {}).get('Name'),
            'ProfileId': user.get('ProfileId'),
            'Role': user.get('UserRole', {}).get('Name'),
            'RoleId': user.get('UserRoleId'),
            'permission_set_ids': permission_set_ids,
            'permission_set_names': permission_set_names,
            'permission_set_group_ids': permission_set_group_ids,
            'permission_set_group_names': permission_set_group_names
        }
    
    def backup_user_state(self, user_id: str, user_email: str) -> str:
        """Save current user state to JSON file for rollback"""
        permissions = self.get_user_current_permissions(user_id)
        
        backup_data = {
            'user_id': user_id,
            'user_email': user_email,
            'backup_timestamp': datetime.now().isoformat(),
            'profile': permissions.get('Profile'),
            'profile_id': permissions.get('ProfileId'),
            'role': permissions.get('Role'),
            'role_id': permissions.get('RoleId'),
            'permission_set_ids': permissions.get('permission_set_ids', []),
            'permission_set_names': permissions.get('permission_set_names', []),
            'permission_set_group_ids': permissions.get('permission_set_group_ids', []),
            'permission_set_group_names': permissions.get('permission_set_group_names', [])
        }
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"user_backup_{user_id}_{timestamp}.json"
        
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2)
        
        print(f"  Backup saved to: {backup_filename}")
        return backup_filename
    
    def remove_all_permission_sets(self, user_id: str) -> Dict[str, List[str]]:
        """Remove all permission set assignments from user. Returns removed permission set IDs."""
        removed_ps_ids = []
        removed_psg_ids = []
        
        # Get current permission sets
        permissions = self.get_user_current_permissions(user_id)
        
        # Remove individual permission sets
        for ps_id in permissions.get('permission_set_ids', []):
            try:
                # Find the assignment ID
                assignment_query = f"""
                SELECT Id
                FROM PermissionSetAssignment
                WHERE AssigneeId = '{user_id}' AND PermissionSetId = '{ps_id}'
                LIMIT 1
                """
                assignment_result = self.sf.query(assignment_query)
                
                if assignment_result['records']:
                    assignment_id = assignment_result['records'][0]['Id']
                    self.sf.restful(f'sobjects/PermissionSetAssignment/{assignment_id}', method='DELETE')
                    removed_ps_ids.append(ps_id)
                    print(f"  Removed permission set: {ps_id}")
            except Exception as e:
                print(f"  WARNING: Could not remove permission set {ps_id}: {str(e)}")
        
        # Remove permission set groups
        for psg_id in permissions.get('permission_set_group_ids', []):
            try:
                # Find the assignment ID
                assignment_query = f"""
                SELECT Id
                FROM PermissionSetGroupAssignment
                WHERE AssigneeId = '{user_id}' AND PermissionSetGroupId = '{psg_id}'
                LIMIT 1
                """
                assignment_result = self.sf.query(assignment_query)
                
                if assignment_result['records']:
                    assignment_id = assignment_result['records'][0]['Id']
                    self.sf.restful(f'sobjects/PermissionSetGroupAssignment/{assignment_id}', method='DELETE')
                    removed_psg_ids.append(psg_id)
                    print(f"  Removed permission set group: {psg_id}")
            except Exception as e:
                # PermissionSetGroupAssignment may not be available
                print(f"  WARNING: Could not remove permission set group {psg_id}: {str(e)}")
        
        if removed_ps_ids:
            print(f"  SUCCESS: Removed {len(removed_ps_ids)} individual permission sets")
        if removed_psg_ids:
            print(f"  SUCCESS: Removed {len(removed_psg_ids)} permission set groups")
        
        return {
            'permission_set_ids': removed_ps_ids,
            'permission_set_group_ids': removed_psg_ids
        }
    
    def update_user_profile_role(self, user_id: str, profile_id: str, role_id: Optional[str] = None) -> bool:
        """Update user's Profile and Role"""
        try:
            update_data = {
                'ProfileId': profile_id
            }
            
            if role_id:
                update_data['UserRoleId'] = role_id
            else:
                # Set Role to null if not provided
                update_data['UserRoleId'] = None
            
            self.sf.User.update(user_id, update_data)
            print(f"  SUCCESS: Updated Profile and Role")
            return True
        except Exception as e:
            print(f"  ERROR: Failed to update Profile/Role: {str(e)}")
            return False
    
    def get_mimic_user_config(self, mimic_user_email: str) -> Optional[Dict]:
        """Get user details (profile, role, permission sets) to mimic"""
        mimic_user = self.find_user_by_email(mimic_user_email)
        if not mimic_user:
            return None
        
        user_id = mimic_user['Id']
        
        # Get permission sets assigned to this user
        psa_query = f"""
        SELECT PermissionSetId, PermissionSet.Name, PermissionSet.Label
        FROM PermissionSetAssignment
        WHERE AssigneeId = '{user_id}'
        """
        
        permission_set_ids = []
        try:
            psa_result = self.sf.query(psa_query)
            permission_set_ids = [psa['PermissionSetId'] for psa in psa_result['records']]
        except Exception as e:
            print(f"  WARNING: Could not get permission sets: {str(e)}")
        
        # Get permission set groups assigned to this user
        permission_set_group_ids = []
        try:
            psg_query = f"""
            SELECT PermissionSetGroupId
            FROM PermissionSetGroupAssignment
            WHERE AssigneeId = '{user_id}'
            """
            psg_result = self.sf.query(psg_query)
            permission_set_group_ids = [psg['PermissionSetGroupId'] for psg in psg_result['records']]
        except Exception as e:
            # PermissionSetGroupAssignment may not be available
            pass
        
        return {
            'Profile': mimic_user.get('Profile'),
            'ProfileId': mimic_user.get('ProfileId'),
            'Role': mimic_user.get('Role'),
            'RoleId': mimic_user.get('RoleId'),
            'permission_set_ids': permission_set_ids,
            'permission_set_group_ids': permission_set_group_ids,
            'user_id': user_id,
            'name': f"{mimic_user.get('FirstName', '')} {mimic_user.get('LastName', '')}".strip()
        }
    
    def update_user_permissions(self, user_email: str, mimic_user_email: str, dry_run: bool = False) -> Dict:
        """Main method to update user permissions"""
        print(f"\n{'='*60}")
        print(f"Updating User Permissions")
        print(f"{'='*60}")
        print(f"User Email: {user_email}")
        print(f"Mimic User Email: {mimic_user_email}")
        if dry_run:
            print(f"Mode: DRY RUN (no changes will be made)")
        print(f"{'='*60}\n")
        
        # Find users
        print("Finding users...")
        user = self.find_user_by_email(user_email)
        if not user:
            return {
                'success': False,
                'error': f"User not found: {user_email}"
            }
        
        print(f"  Found user: {user['FirstName']} {user['LastName']} ({user['Email']})")
        print(f"  Current Profile: {user.get('Profile', 'N/A')}")
        print(f"  Current Role: {user.get('Role', 'N/A')}")
        
        mimic_config = self.get_mimic_user_config(mimic_user_email)
        if not mimic_config:
            return {
                'success': False,
                'error': f"Mimic user not found: {mimic_user_email}"
            }
        
        print(f"  Found mimic user: {mimic_config['name']}")
        print(f"  Mimic Profile: {mimic_config.get('Profile', 'N/A')}")
        print(f"  Mimic Role: {mimic_config.get('Role', 'N/A')}")
        
        user_id = user['Id']
        
        # Backup current state
        print("\nBacking up current state...")
        backup_filename = self.backup_user_state(user_id, user_email)
        
        if dry_run:
            print("\n" + "="*60)
            print("DRY RUN - No changes will be made")
            print("="*60)
            print(f"Would update Profile: {user.get('Profile')} -> {mimic_config.get('Profile')}")
            print(f"Would update Role: {user.get('Role')} -> {mimic_config.get('Role')}")
            print(f"Would remove {len(self.get_user_current_permissions(user_id).get('permission_set_ids', []))} permission sets")
            print(f"Would assign {len(mimic_config.get('permission_set_ids', []))} permission sets")
            print(f"Would assign {len(mimic_config.get('permission_set_group_ids', []))} permission set groups")
            return {
                'success': True,
                'dry_run': True,
                'backup_file': backup_filename,
                'user': user,
                'mimic_config': mimic_config
            }
        
        # Update Profile and Role
        print("\nUpdating Profile and Role...")
        profile_id = mimic_config.get('ProfileId')
        role_id = mimic_config.get('RoleId')
        
        if not self.update_user_profile_role(user_id, profile_id, role_id):
            return {
                'success': False,
                'error': 'Failed to update Profile/Role',
                'backup_file': backup_filename
            }
        
        # Remove all existing permission sets
        print("\nRemoving existing permission sets...")
        removed = self.remove_all_permission_sets(user_id)
        
        # Assign new permission sets from mimic user
        print("\nAssigning new permission sets...")
        assigned_group_names = []
        if mimic_config.get('permission_set_group_ids'):
            assigned_group_names = self.assign_permission_set_groups(user_id, mimic_config['permission_set_group_ids'])
        
        assigned_permission_set_names = []
        if mimic_config.get('permission_set_ids'):
            assigned_permission_set_names = self.assign_permission_sets(user_id, mimic_config['permission_set_ids'])
        
        print("\n" + "="*60)
        print("Update Summary:")
        print("="*60)
        print(f"  Profile: {user.get('Profile')} -> {mimic_config.get('Profile')}")
        print(f"  Role: {user.get('Role')} -> {mimic_config.get('Role')}")
        print(f"  Removed {len(removed['permission_set_ids'])} permission sets")
        print(f"  Assigned {len(assigned_group_names)} permission set groups")
        print(f"  Assigned {len(assigned_permission_set_names)} individual permission sets")
        print(f"  Backup saved to: {backup_filename}")
        print("="*60)
        
        return {
            'success': True,
            'user_id': user_id,
            'user': user,
            'backup_file': backup_filename,
            'old_profile': user.get('Profile'),
            'new_profile': mimic_config.get('Profile'),
            'old_role': user.get('Role'),
            'new_role': mimic_config.get('Role'),
            'removed_permission_sets': len(removed['permission_set_ids']),
            'assigned_group_names': assigned_group_names,
            'assigned_permission_set_names': assigned_permission_set_names
        }
    
    def create_jira_ticket_for_update(self, user_data: Dict, update_result: Dict, user_link: str):
        """Create a Jira ticket for user permission update"""
        if not self.jira_client:
            return None
        
        user_full_name = f"{user_data['FirstName']} {user_data['LastName']}"
        summary = f"Update Salesforce Permissions for {user_full_name}"
        
        # Build description
        description_content = [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Updated Salesforce user permissions for: "},
                    {"type": "text", "text": user_full_name, "marks": [{"type": "strong"}]}
                ]
            },
            {"type": "paragraph"},
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Changes Made"}]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Profile: {update_result.get('old_profile', 'N/A')} → {update_result.get('new_profile', 'N/A')}"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Role: {update_result.get('old_role', 'N/A')} → {update_result.get('new_role', 'N/A')}"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Removed {update_result.get('removed_permission_sets', 0)} old permission sets"}
                            ]
                        }]
                    }
                ]
            },
            {"type": "paragraph"},
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "New Permission Sets Assigned"}]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Permission Set Group: {group_name}"}
                            ]
                        }]
                    }
                    for group_name in (update_result.get('assigned_group_names') or [])
                ] + [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Permission Set: {ps_name}"}
                            ]
                        }]
                    }
                    for ps_name in (update_result.get('assigned_permission_set_names') or [])
                ]
            },
            {"type": "paragraph"},
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "User Details"}]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"User ID: {update_result.get('user_id', 'N/A')}"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "User Link: "},
                                {
                                    "type": "text",
                                    "text": user_link,
                                    "marks": [{"type": "link", "attrs": {"href": user_link}}]
                                }
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Backup File: {update_result.get('backup_file', 'N/A')}"}
                            ]
                        }]
                    }
                ]
            }
        ]
        
        description = {
            "type": "doc",
            "version": 1,
            "content": description_content
        }
        
        ticket_kwargs = {
            'labels': ['user-permissions-update', 'salesforce']
        }
        
        if self.jira_client.assignee_email:
            ticket_kwargs['assignee'] = self.jira_client.assignee_email
        
        ticket = self.jira_client.create_ticket(
            summary=summary,
            description=description,
            **ticket_kwargs
        )
        
        if ticket:
            print(f"  SUCCESS: Jira ticket created: {ticket['key']}")
            print(f"  Ticket URL: {ticket['url']}")
            return ticket
        else:
            print(f"  WARNING: Jira ticket creation failed")
            return None


def main():
    parser = argparse.ArgumentParser(
        description='Update Salesforce user permissions by mimicking another user',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update user permissions (dry run)
  python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod --dry-run
  
  # Update user permissions
  python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod
  
  # Update with Jira ticket
  python update_user_permissions.py --user-email jessie.rhue@mavenclinic.com --mimic-user-email sd.user@mavenclinic.com --org mavenprod --jira-config jira_config.json
        """
    )
    parser.add_argument('--user-email', required=True, help='Email of user to update')
    parser.add_argument('--mimic-user-email', required=True, help='Email of user to mimic (copy permissions from)')
    parser.add_argument('--org', required=True, help='Salesforce org alias (e.g., mavenprod)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--jira-config', help='Path to JSON file with Jira configuration')
    parser.add_argument('--jira-url', help='Jira instance URL (e.g., https://company.atlassian.net)')
    parser.add_argument('--jira-email', help='Jira user email for API authentication')
    parser.add_argument('--jira-token', help='Jira API token')
    parser.add_argument('--jira-project', help='Jira project key (e.g., PROJ)')
    parser.add_argument('--jira-issue-type', default='Task', help='Jira issue type (default: Task)')
    
    args = parser.parse_args()
    
    # Initialize Jira client if configured
    jira_client = None
    if args.jira_config:
        try:
            with open(args.jira_config, 'r') as f:
                jira_config = json.load(f)
            jira_client = JiraClient(
                jira_url=jira_config['jira_url'],
                email=jira_config['email'],
                api_token=jira_config['api_token'],
                project_key=jira_config['project_key'],
                issue_type=jira_config.get('issue_type', 'Task'),
                assignee_email=jira_config.get('assignee_email'),
                board_id=jira_config.get('board_id')
            )
            print("Jira integration: ENABLED")
        except Exception as e:
            print(f"WARNING: Failed to load Jira config from {args.jira_config}: {e}")
            print("Continuing without Jira integration...")
    elif args.jira_url and args.jira_email and args.jira_token and args.jira_project:
        jira_client = JiraClient(
            jira_url=args.jira_url,
            email=args.jira_email,
            api_token=args.jira_token,
            project_key=args.jira_project,
            issue_type=args.jira_issue_type
        )
        print("Jira integration: ENABLED")
    else:
        print("Jira integration: DISABLED (no configuration provided)")
    
    # Initialize updater
    try:
        updater = UserPermissionsUpdater(args.org, jira_client)
    except SystemExit:
        sys.exit(1)
    
    # Update user permissions
    result = updater.update_user_permissions(args.user_email, args.mimic_user_email, args.dry_run)
    
    if not result.get('success'):
        print(f"\nERROR: {result.get('error', 'Unknown error')}")
        if result.get('backup_file'):
            print(f"Backup saved to: {result['backup_file']}")
        sys.exit(1)
    
    # Create Jira ticket if configured and not dry run
    if jira_client and not args.dry_run and result.get('success'):
        user = result.get('user', {})
        user_id = result.get('user_id')
        if user_id:
            user_link = updater.get_user_link(user_id)
            updater.create_jira_ticket_for_update(user, result, user_link)
    
    print("\nUpdate completed successfully!")


if __name__ == '__main__':
    main()

