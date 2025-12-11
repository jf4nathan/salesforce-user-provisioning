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
    - requests library: pip install requests (for Jira integration)
"""

import csv
import json
import argparse
import subprocess
import shutil
import os
import sys
import requests
import base64
from collections import Counter
from simple_salesforce import Salesforce
from typing import List, Dict, Set, Optional, Tuple


class JiraClient:
    """Client for creating Jira tickets via REST API"""
    
    def __init__(self, jira_url: str, email: str, api_token: str, project_key: str, issue_type: str = "Task", 
                 assignee_email: Optional[str] = None, board_id: Optional[int] = None):
        """
        Initialize Jira client
        
        Args:
            jira_url: Base URL of Jira instance (e.g., https://yourcompany.atlassian.net)
            email: Jira user email for authentication
            api_token: Jira API token (get from https://id.atlassian.com/manage-profile/security/api-tokens)
            project_key: Jira project key (e.g., "PROJ")
            issue_type: Issue type (default: "Task")
            assignee_email: Email of user to assign tickets to (optional)
            board_id: Jira board ID for getting current sprint (optional)
        """
        self.jira_url = jira_url.rstrip('/')
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.issue_type = issue_type
        self.assignee_email = assignee_email
        self.board_id = board_id
        self.auth_header = self._create_auth_header(email, api_token)
        self._sprint_field_id = None  # Cache sprint custom field ID
    
    def _create_auth_header(self, email: str, api_token: str) -> str:
        """Create Basic Auth header for Jira API"""
        credentials = f"{email}:{api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def _get_assignee_account_id(self, email: str) -> Optional[str]:
        """Get Jira account ID from email address"""
        url = f"{self.jira_url}/rest/api/3/user/search"
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header
        }
        params = {"query": email}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            users = response.json()
            if users and len(users) > 0:
                return users[0].get('accountId')
        except Exception as e:
            print(f"  WARNING: Could not find assignee account ID for {email}: {str(e)}")
        return None
    
    def _find_board_id_for_project(self) -> Optional[int]:
        """Find the board ID for the project automatically"""
        url = f"{self.jira_url}/rest/agile/1.0/board"
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header
        }
        params = {"projectKeyOrId": self.project_key, "type": "scrum"}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            boards = response.json().get('values', [])
            if boards and len(boards) > 0:
                # Return the first board found
                return boards[0].get('id')
        except Exception as e:
            print(f"  WARNING: Could not find board for project: {str(e)}")
        return None
    
    def _get_current_sprint_id(self) -> Optional[int]:
        """Get the current active sprint ID from the board"""
        board_id = self.board_id
        if not board_id:
            # Try to find board automatically
            board_id = self._find_board_id_for_project()
            if not board_id:
                return None
        
        url = f"{self.jira_url}/rest/agile/1.0/board/{board_id}/sprint"
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header
        }
        params = {"state": "active"}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            sprints = response.json().get('values', [])
            if sprints and len(sprints) > 0:
                # Get the first active sprint
                sprint_id = sprints[0].get('id')
                print(f"  Found active sprint: {sprints[0].get('name', 'Unknown')} (ID: {sprint_id})")
                return sprint_id
        except Exception as e:
            print(f"  WARNING: Could not get current sprint: {str(e)}")
        return None
    
    def _get_sprint_custom_field_id(self) -> Optional[str]:
        """Get the sprint custom field ID for the project"""
        if self._sprint_field_id:
            return self._sprint_field_id
        
        url = f"{self.jira_url}/rest/api/3/issue/createmeta"
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header
        }
        params = {
            "projectKeys": self.project_key,
            "issuetypeNames": self.issue_type,
            "expand": "projects.issuetypes.fields"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            metadata = response.json()
            
            # Find sprint field (usually customfield_10020 or similar)
            projects = metadata.get('projects', [])
            if projects:
                fields = projects[0].get('issuetypes', [{}])[0].get('fields', {})
                for field_id, field_data in fields.items():
                    if 'Sprint' in field_data.get('name', '') or field_id.startswith('customfield_10020'):
                        self._sprint_field_id = field_id
                        return field_id
        except Exception as e:
            print(f"  WARNING: Could not get sprint field ID: {str(e)}")
        
        # Fallback to common sprint field ID
        self._sprint_field_id = "customfield_10020"
        return self._sprint_field_id
    
    def create_ticket(self, summary: str, description: str, **kwargs) -> Optional[Dict]:
        """
        Create a Jira ticket
        
        Args:
            summary: Ticket summary/title
            description: Ticket description (supports ADF format dict or plain text)
            **kwargs: Additional fields (e.g., assignee, labels, priority)
        
        Returns:
            Dictionary with ticket info (key, id, url) or None if failed
        """
        url = f"{self.jira_url}/rest/api/3/issue"
        
        # Build issue payload
        # If description is already a dict (ADF format), use it directly
        # Otherwise, wrap plain text in ADF format
        if isinstance(description, dict):
            description_field = description
        else:
            description_field = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }
        
        issue_data = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": description_field,
                "issuetype": {"name": self.issue_type}
            }
        }
        
        # Add optional fields
        if 'assignee' in kwargs:
            # assignee can be accountId (string) or email (will be converted)
            assignee_value = kwargs['assignee']
            if '@' in str(assignee_value):
                # It's an email, get accountId
                account_id = self._get_assignee_account_id(assignee_value)
                if account_id:
                    issue_data["fields"]["assignee"] = {"accountId": account_id}
            else:
                # It's already an accountId
                issue_data["fields"]["assignee"] = {"accountId": assignee_value}
        elif self.assignee_email:
            # Use default assignee from config
            account_id = self._get_assignee_account_id(self.assignee_email)
            if account_id:
                issue_data["fields"]["assignee"] = {"accountId": account_id}
        
        if 'labels' in kwargs:
            issue_data["fields"]["labels"] = kwargs['labels']
        if 'priority' in kwargs:
            issue_data["fields"]["priority"] = {"name": kwargs['priority']}
        if 'components' in kwargs:
            issue_data["fields"]["components"] = [{"name": comp} for comp in kwargs['components']]
        
        # Add sprint if available
        if 'sprint_id' in kwargs:
            sprint_id = kwargs['sprint_id']
        elif self.board_id:
            sprint_id = self._get_current_sprint_id()
        else:
            sprint_id = None
        
        if sprint_id:
            sprint_field_id = self._get_sprint_custom_field_id()
            if sprint_field_id:
                # Sprint field expects just the sprint ID as a number
                issue_data["fields"][sprint_field_id] = sprint_id
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.auth_header
        }
        
        try:
            response = requests.post(url, json=issue_data, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            ticket_key = result.get('key')
            ticket_id = result.get('id')
            ticket_url = f"{self.jira_url}/browse/{ticket_key}"
            
            return {
                'key': ticket_key,
                'id': ticket_id,
                'url': ticket_url
            }
        except requests.exceptions.RequestException as e:
            print(f"  WARNING: Failed to create Jira ticket: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"  Jira API Error: {error_detail}")
                except:
                    print(f"  HTTP Status: {e.response.status_code}")
            return None


class SalesforceUserProvisioner:
    def __init__(self, org_alias: str, jira_client: Optional[JiraClient] = None):
        """
        Initialize Salesforce connection using sf CLI
        
        Args:
            org_alias: Salesforce org alias
            jira_client: Optional Jira client for ticket creation
        """
        self.org_alias = org_alias
        self.org_info = self._get_org_info(org_alias)
        self.sandbox_name = self._extract_sandbox_name()
        self.sf = self._get_sf_connection()
        self.jira_client = jira_client
    
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
            assigned_group_names = []
            if permission_data.get('permission_set_groups'):
                assigned_group_names = self.assign_permission_set_groups(user_id, permission_data['permission_set_groups'])
            
            # Then assign individual permission sets
            assigned_permission_set_names = []
            if permission_data.get('permission_sets'):
                assigned_permission_set_names = self.assign_permission_sets(user_id, permission_data['permission_sets'])
            
            # Create Jira ticket if configured
            if self.jira_client:
                user_link = self.get_user_link(user_id)
                self.create_jira_ticket(user_data, user_id, user_link, assigned_group_names, assigned_permission_set_names)
            
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
    
    def get_permission_set_names(self, permission_set_ids: List[str]) -> List[str]:
        """Get permission set names from IDs"""
        if not permission_set_ids:
            return []
        
        permission_set_ids_str = "', '".join(permission_set_ids)
        query = f"""
        SELECT Id, Name, Label
        FROM PermissionSet
        WHERE Id IN ('{permission_set_ids_str}')
        """
        
        try:
            result = self.sf.query(query)
            # Return Label if available, otherwise Name
            return [ps.get('Label') or ps.get('Name', 'Unknown') for ps in result['records']]
        except Exception as e:
            print(f"  WARNING: Could not get permission set names: {str(e)}")
            return []
    
    def get_permission_set_group_names(self, permission_set_group_ids: List[str]) -> List[str]:
        """Get permission set group names from IDs"""
        if not permission_set_group_ids:
            return []
        
        permission_set_group_ids_str = "', '".join(permission_set_group_ids)
        query = f"""
        SELECT Id, DeveloperName, MasterLabel
        FROM PermissionSetGroup
        WHERE Id IN ('{permission_set_group_ids_str}')
        """
        
        try:
            result = self.sf.query(query)
            # Return MasterLabel if available, otherwise DeveloperName
            return [psg.get('MasterLabel') or psg.get('DeveloperName', 'Unknown') for psg in result['records']]
        except Exception as e:
            print(f"  WARNING: Could not get permission set group names: {str(e)}")
            return []
    
    def assign_permission_sets(self, user_id: str, permission_set_ids: List[str]) -> List[str]:
        """Assign individual permission sets to user. Returns list of successfully assigned permission set names."""
        if not permission_set_ids:
            return []
        
        success_ids = []
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
                success_ids.append(ps_id)
            except Exception as e:
                error_msg = str(e)
                if 'INVALID_CROSS_REFERENCE_KEY' in error_msg and 'profile' in error_msg.lower():
                    # Profile-specific permission set, skip silently
                    pass
                else:
                    print(f"  WARNING: Error assigning permission set {ps_id}: {error_msg}")
        
        if success_ids:
            print(f"  SUCCESS: Assigned {len(success_ids)} individual permission sets")
            # Get names of successfully assigned permission sets
            return self.get_permission_set_names(success_ids)
        return []
    
    def assign_permission_set_groups(self, user_id: str, permission_set_group_ids: List[str]) -> List[str]:
        """Assign permission set groups to user. Returns list of successfully assigned group names."""
        success_ids = []
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
                success_ids.append(psg_id)
                print(f"  SUCCESS: Assigned permission set group: {psg_id}")
            except Exception as e:
                print(f"  WARNING: Error assigning group {psg_id}: {str(e)}")
        
        if success_ids:
            # Get names of successfully assigned groups
            return self.get_permission_set_group_names(success_ids)
        return []
    
    def get_user_link(self, user_id: str) -> str:
        """Generate Salesforce user record link in Setup format"""
        instance_url = self.org_info.get("instanceUrl", "")
        # Extract domain from instance URL (e.g., mavenclinic from https://mavenclinic.my.salesforce.com)
        # Convert to setup URL format: https://mavenclinic.my.salesforce-setup.com/lightning/setup/ManageUsers/page?address=%2F{user_id}%3Fnoredirect%3D1%26isUserEntityOverride%3D1
        if '.my.salesforce.com' in instance_url:
            domain = instance_url.split('//')[1].split('.my.salesforce.com')[0]
            setup_url = f"https://{domain}.my.salesforce-setup.com/lightning/setup/ManageUsers/page?address=%2F{user_id}%3Fnoredirect%3D1%26isUserEntityOverride%3D1"
            return setup_url
        else:
            # Fallback to old format if URL structure is unexpected
            lightning_url = instance_url.replace('.my.salesforce.com', '.lightning.force.com')
            return f"{lightning_url}/lightning/r/User/{user_id}/view"
    
    def create_jira_ticket(self, user_data: Dict, user_id: str, user_link: str, 
                          assigned_group_names: List[str] = None, assigned_permission_set_names: List[str] = None):
        """Create a Jira ticket for new user provisioning"""
        if not self.jira_client:
            return
        
        if assigned_group_names is None:
            assigned_group_names = []
        if assigned_permission_set_names is None:
            assigned_permission_set_names = []
        
        user_full_name = f"{user_data['FirstName']} {user_data['LastName']}"
        summary = f"Salesforce Access for {user_full_name}"
        
        # Build permission sets list items
        permission_set_items = []
        for group_name in assigned_group_names:
            permission_set_items.append({
                "type": "listItem",
                "content": [{
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": f"Permission Set Group: {group_name}"}
                    ]
                }]
            })
        for ps_name in assigned_permission_set_names:
            permission_set_items.append({
                "type": "listItem",
                "content": [{
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": f"Permission Set: {ps_name}"}
                    ]
                }]
            })
        
        # Build description using Atlassian Document Format (ADF) for proper formatting
        description_content = [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Provision Salesforce user for: "},
                    {"type": "text", "text": user_full_name, "marks": [{"type": "strong"}]}
                ]
            },
            {"type": "paragraph"},  # Empty line
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
                                {"type": "text", "text": "Name: "},
                                {"type": "text", "text": f"{user_data['FirstName']} {user_data['LastName']}"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Email: "},
                                {"type": "text", "text": user_data['Email']}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Username: "},
                                {"type": "text", "text": user_data['Username']}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Title: "},
                                {"type": "text", "text": user_data.get('Title', 'N/A')}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Profile: "},
                                {"type": "text", "text": user_data['Profile']}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Role: "},
                                {"type": "text", "text": user_data.get('Role', 'N/A')}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Manager: "},
                                {"type": "text", "text": user_data.get('ManagerEmail', 'N/A')}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Time Zone: "},
                                {"type": "text", "text": user_data.get('TimeZone', 'America/New_York')}
                            ]
                        }]
                    }
                ]
            },
            {"type": "paragraph"},  # Empty line
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Salesforce Details"}]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "User ID: "},
                                {"type": "text", "text": user_id}
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
                    }
                ]
            },
            {"type": "paragraph"},  # Empty line
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Permission Sets Assigned"}]
            },
            {
                "type": "bulletList",
                "content": permission_set_items
            },
            {"type": "paragraph"},  # Empty line
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Next Steps"}]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Password reset required (manual action in Salesforce UI)"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Verify permission sets assigned correctly"}
                            ]
                        }]
                    },
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Confirm user can log in successfully"}
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
        
        # Use assignee from config if available
        ticket_kwargs = {
            'labels': ['user-provisioning', 'salesforce']
        }
        
        # Add assignee if configured
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
        else:
            print(f"  WARNING: Jira ticket creation failed (user still created successfully)")
    
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
    parser.add_argument('--jira-url', help='Jira instance URL (e.g., https://company.atlassian.net)')
    parser.add_argument('--jira-email', help='Jira user email for API authentication')
    parser.add_argument('--jira-token', help='Jira API token')
    parser.add_argument('--jira-project', help='Jira project key (e.g., PROJ)')
    parser.add_argument('--jira-issue-type', default='Task', help='Jira issue type (default: Task)')
    parser.add_argument('--jira-config', help='Path to JSON file with Jira configuration')
    
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
    
    # Initialize Jira client if configured
    jira_client = None
    if args.jira_config:
        # Load Jira config from file
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
            if jira_config.get('assignee_email'):
                print(f"  Assignee: {jira_config['assignee_email']}")
            if jira_config.get('board_id'):
                print(f"  Board ID: {jira_config['board_id']} (for current sprint)")
        except Exception as e:
            print(f"WARNING: Failed to load Jira config from {args.jira_config}: {e}")
            print("Continuing without Jira integration...")
    elif args.jira_url and args.jira_email and args.jira_token and args.jira_project:
        # Use command-line arguments
        jira_client = JiraClient(
            jira_url=args.jira_url,
            email=args.jira_email,
            api_token=args.jira_token,
            project_key=args.jira_project,
            issue_type=args.jira_issue_type,
            assignee_email=os.getenv('JIRA_ASSIGNEE_EMAIL'),
            board_id=int(os.getenv('JIRA_BOARD_ID')) if os.getenv('JIRA_BOARD_ID') else None
        )
        print("Jira integration: ENABLED")
    else:
        # Check environment variables
        jira_url = os.getenv('JIRA_URL')
        jira_email = os.getenv('JIRA_EMAIL')
        jira_token = os.getenv('JIRA_API_TOKEN')
        jira_project = os.getenv('JIRA_PROJECT_KEY')
        
        if jira_url and jira_email and jira_token and jira_project:
            jira_client = JiraClient(
                jira_url=jira_url,
                email=jira_email,
                api_token=jira_token,
                project_key=jira_project,
                issue_type=os.getenv('JIRA_ISSUE_TYPE', 'Task'),
                assignee_email=os.getenv('JIRA_ASSIGNEE_EMAIL'),
                board_id=int(os.getenv('JIRA_BOARD_ID')) if os.getenv('JIRA_BOARD_ID') else None
            )
            print("Jira integration: ENABLED (from environment variables)")
        else:
            print("Jira integration: DISABLED (no configuration provided)")
    
    print()
    
    # Initialize provisioner
    try:
        provisioner = SalesforceUserProvisioner(args.org, jira_client)
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

