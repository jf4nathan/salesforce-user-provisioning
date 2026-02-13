#!/usr/bin/env python3
"""
Salesforce User Provisioning Script
Creates users with permission set assignment based on Profile + Role analysis

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
import os
import sys
from collections import Counter
from simple_salesforce import Salesforce
from typing import List, Dict, Set, Optional, Tuple
from gainsight_client import GainsightClient, create_client_from_config as create_gainsight_client
from jira_client import JiraClient, load_jira_client_from_args, add_jira_args
from sf_utils import get_org_info, extract_sandbox_name



class SalesforceUserProvisioner:
    def __init__(self, org_alias: str, jira_client: Optional[JiraClient] = None, 
                 gainsight_client: Optional[GainsightClient] = None):
        """
        Initialize Salesforce connection using sf CLI
        
        Args:
            org_alias: Salesforce org alias
            jira_client: Optional Jira client for ticket creation
            gainsight_client: Optional Gainsight client for user provisioning
        """
        self.org_alias = org_alias
        self.org_info = get_org_info(org_alias)
        self.sandbox_name = extract_sandbox_name(self.org_info)
        self.sf = Salesforce(
            instance_url=self.org_info["instanceUrl"],
            session_id=self.org_info["accessToken"]
        )
        self.jira_client = jira_client
        self.gainsight_client = gainsight_client
    
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
            if result['records']:
                user = result['records'][0]
                return {
                    'Id': user['Id'],
                    'FirstName': user.get('FirstName', ''),
                    'LastName': user.get('LastName', ''),
                    'Email': user.get('Email', ''),
                    'Username': user.get('Username', ''),
                    'Profile': user.get('Profile', {}).get('Name', '') if user.get('Profile') else '',
                    'ProfileId': user.get('ProfileId', ''),
                    'Role': user.get('UserRole', {}).get('Name', '') if user.get('UserRole') else '',
                    'RoleId': user.get('UserRoleId', ''),
                    'Title': user.get('Title', '')
                }
        except Exception as e:
            print(f"  WARNING: Error finding user by email {email}: {str(e)}")
        
        return None
    
    def get_mimic_user_config(self, mimic_user_email: str) -> Optional[Dict]:
        """Get user details (profile, role, permission sets) to mimic"""
        mimic_user = self.find_user_by_email(mimic_user_email)
        if not mimic_user:
            print(f"  ERROR: Mimic user not found: {mimic_user_email}")
            return None
        
        user_id = mimic_user['Id']
        print(f"  Found mimic user: {mimic_user.get('FirstName', '')} {mimic_user.get('LastName', '')} ({mimic_user_email})")
        
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
            print(f"  Found {len(permission_set_ids)} permission sets")
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
            print(f"  Found {len(permission_set_group_ids)} permission set groups")
        except Exception as e:
            # PermissionSetGroupAssignment may not be available
            pass
        
        return {
            'Profile': mimic_user.get('Profile', ''),
            'ProfileId': mimic_user.get('ProfileId', ''),
            'Role': mimic_user.get('Role', ''),
            'RoleId': mimic_user.get('RoleId', ''),
            'Title': mimic_user.get('Title', ''),
            'permission_set_ids': permission_set_ids,
            'permission_set_group_ids': permission_set_group_ids,
            'user_id': user_id,
            'name': f"{mimic_user.get('FirstName', '')} {mimic_user.get('LastName', '')}".strip()
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
        profile_name = user_data.get('Profile', '').strip()
        if not profile_name:
            print(f"  ERROR: Profile is required")
            return None
        
        profile_id = self.get_profile_id(profile_name)
        if not profile_id:
            print(f"  ERROR: Profile '{profile_name}' not found")
            return None
        
        role_name = user_data.get('Role', '').strip()
        role_id = self.get_role_id(role_name) if role_name else None
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
            
            # Create or update Jira ticket if configured
            if self.jira_client:
                user_link = self.get_user_link(user_id)
                jira_key = (user_data.get('JiraKey') or '').strip()
                if jira_key:
                    self.update_existing_jira_ticket(
                        issue_key=jira_key,
                        user_data=user_data,
                        user_id=user_id,
                        user_link=user_link,
                        assigned_group_names=assigned_group_names,
                        assigned_permission_set_names=assigned_permission_set_names,
                    )
                else:
                    self.create_jira_ticket(
                        user_data,
                        user_id,
                        user_link,
                        assigned_group_names,
                        assigned_permission_set_names,
                    )
            
            # Provision Gainsight user if profile is Client Success
            if self.gainsight_client and user_data.get('Profile', '').lower() == 'client success':
                self._provision_gainsight_user(user_data)
            
            # Note: Password reset must be done manually in Salesforce UI
            print(f"  NOTE: Please reset password manually in Setup > Users > Users")
            
            return user_id
            
        except Exception as e:
            print(f"  ERROR: Error creating user: {str(e)}")
            return None
    
    def _provision_gainsight_user(self, user_data: Dict) -> Optional[Dict]:
        """
        Provision user in Gainsight for Client Success profile users
        
        Args:
            user_data: User data dict with Email, FirstName, LastName, TimeZone
        
        Returns:
            Gainsight user dict if successful, None otherwise
        """
        if not self.gainsight_client:
            return None
        
        email = user_data.get('Email', '')
        first_name = user_data.get('FirstName', '')
        last_name = user_data.get('LastName', '')
        timezone = user_data.get('TimeZone', 'America/New_York')
        
        print(f"  Provisioning Gainsight user for: {email}")
        
        try:
            # Check if user already exists in Gainsight
            existing_user = self.gainsight_client.search_user_by_email(email)
            if existing_user:
                print(f"  INFO: User already exists in Gainsight (ID: {existing_user.get('id')})")
                return existing_user
            
            # Create user with Full license and client resources group
            result = self.gainsight_client.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                timezone=timezone,
                license_type="Full",
                groups=[{"display": "client resources"}]
            )
            
            print(f"  SUCCESS: Gainsight user created (ID: {result.get('id')})")
            return result
            
        except Exception as e:
            print(f"  WARNING: Failed to provision Gainsight user: {str(e)}")
            return None
    
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
    
    def assign_gainsight_license(self, user_id: str) -> bool:
        """Assign Gainsight package license to user if not already assigned"""
        # Gainsight package license ID (18-character format)
        gainsight_package_license_id = '050UH00000NFYVZYA5'
        
        try:
            # Check if license is already assigned
            query = f"""
            SELECT Id FROM UserPackageLicense 
            WHERE UserId = '{user_id}' 
            AND PackageLicenseId = '{gainsight_package_license_id}'
            LIMIT 1
            """
            result = self.sf.query(query)
            if result['records']:
                print(f"  INFO: Gainsight license already assigned")
                return True
            
            # Check license availability
            license_query = f"SELECT Id, UsedLicenses, AllowedLicenses FROM PackageLicense WHERE Id = '{gainsight_package_license_id}'"
            license_result = self.sf.query(license_query)
            
            if license_result['records']:
                license_info = license_result['records'][0]
                available = license_info['AllowedLicenses'] - license_info['UsedLicenses']
                if available <= 0:
                    print(f"  WARNING: No Gainsight licenses available ({license_info['UsedLicenses']}/{license_info['AllowedLicenses']} used)")
                    return False
            
            # Assign the license
            user_package_license = {
                'PackageLicenseId': gainsight_package_license_id,
                'UserId': user_id
            }
            self.sf.UserPackageLicense.create(user_package_license)
            print(f"  SUCCESS: Assigned Gainsight package license")
            return True
        except Exception as e:
            print(f"  WARNING: Could not assign Gainsight license: {str(e)}")
            return False
    
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
            assigned_names = self.get_permission_set_names(success_ids)
            
            # Check if Gainsight CS permission set was assigned
            gainsight_ps_id = '0PSUH0000006LTB4A2'
            gainsight_ps_names = ['Gainsight_CS', 'GAINSIGHT__Gainsight_CS', 'Gainsight CS']
            
            # Check by permission set ID or name
            if gainsight_ps_id in success_ids or any(name in assigned_names for name in gainsight_ps_names) or any('gainsight' in name.lower() for name in assigned_names):
                self.assign_gainsight_license(user_id)
            
            return assigned_names
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
            assigned_group_names = self.get_permission_set_group_names(success_ids)
            
            # Check if any permission set group contains Gainsight CS permission set
            # Query permission sets in these groups to check for Gainsight
            try:
                group_to_permission_sets = self.get_permission_set_groups_and_members()
                gainsight_ps_id = '0PSUH0000006LTB4A2'
                for psg_id in success_ids:
                    if psg_id in group_to_permission_sets:
                        if gainsight_ps_id in group_to_permission_sets[psg_id]:
                            # Gainsight CS is in this group, assign license
                            self.assign_gainsight_license(user_id)
                            break
            except Exception as e:
                # If we can't check, that's okay - we'll rely on individual permission set check
                pass
            
            return assigned_group_names
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
        
        # Build description using Atlassian Document Format (ADF) for proper formatting
        description_content = [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Provision Salesforce user for: "},
                    {"type": "text", "text": user_full_name, "marks": [{"type": "strong"}]}
                ]
            }
        ] + self._build_jira_description_content(
            user_data, user_id, user_link, assigned_group_names, assigned_permission_set_names
        )
        
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

    def update_existing_jira_ticket(self, issue_key: str, user_data: Dict, user_id: str, user_link: str,
                                    assigned_group_names: List[str] = None, assigned_permission_set_names: List[str] = None) -> bool:
        """Update an existing Jira issue by adding a comment with the same details we normally include in a ticket."""
        if not self.jira_client:
            return False

        if assigned_group_names is None:
            assigned_group_names = []
        if assigned_permission_set_names is None:
            assigned_permission_set_names = []

        user_full_name = f"{user_data['FirstName']} {user_data['LastName']}"

        # Reuse the same ADF structure we use for ticket description, but as a comment body.
        # We'll prepend a short header so it's clear this is an automated update.
        description_adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Provisioning update for: "},
                        {"type": "text", "text": user_full_name, "marks": [{"type": "strong"}]}
                    ]
                },
                {"type": "paragraph"},
            ] + (self._build_jira_description_content(user_data, user_id, user_link, assigned_group_names, assigned_permission_set_names))
        }

        ok = self.jira_client.add_comment(issue_key, description_adf)
        if ok:
            print(f"  SUCCESS: Updated Jira ticket (comment added): {issue_key}")
            print(f"  Ticket URL: {self.jira_client.jira_url}/browse/{issue_key}")
        else:
            print(f"  WARNING: Failed to update Jira ticket: {issue_key}")
        return ok

    def _build_jira_description_content(self, user_data: Dict, user_id: str, user_link: str,
                                        assigned_group_names: List[str], assigned_permission_set_names: List[str]) -> List[Dict]:
        """Build the ADF content array used in Jira descriptions/comments (excluding doc wrapper)."""
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
                "content": permission_set_items if permission_set_items else [
                    {
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "None assigned"}
                            ]
                        }]
                    }
                ]
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

        return description_content
    
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
            # Parse name from email if not provided
            if not user_data.get('FirstName') or not user_data.get('LastName'):
                try:
                    first_name, last_name = self.parse_name_from_email(user_data['Email'])
                    user_data['FirstName'] = user_data.get('FirstName', first_name)
                    user_data['LastName'] = user_data.get('LastName', last_name)
                except Exception as e:
                    print(f"  ERROR: Could not parse name from email: {str(e)}")
                    results['failed'].append({
                        'user': user_data,
                        'error': f"Could not parse name from email: {str(e)}"
                    })
                    continue
            
            # Set username to email if not provided
            if not user_data.get('Username'):
                user_data['Username'] = user_data['Email']
            
            # Always append sandbox suffix to username in sandbox environments
            if self.sandbox_name and not user_data['Username'].endswith(f".{self.sandbox_name}"):
                user_data['Username'] = f"{user_data['Username']}.{self.sandbox_name}"
                print(f"  INFO: Appended sandbox suffix to username: {user_data['Username']}")
            
            print(f"\n[{i}/{len(users)}] Creating user: {user_data['FirstName']} {user_data['LastName']}")
            
            # Check for MimicUser
            mimic_user_email = user_data.get('MimicUser', '').strip()
            if mimic_user_email:
                print(f"  Using MimicUser: {mimic_user_email}")
                mimic_config = self.get_mimic_user_config(mimic_user_email)
                if not mimic_config:
                    results['failed'].append({
                        'user': user_data,
                        'error': f"Mimic user '{mimic_user_email}' not found"
                    })
                    continue
                
                # Copy Profile, Role, and Title from mimic user
                user_data['Profile'] = mimic_config['Profile']
                user_data['Role'] = mimic_config.get('Role', '')
                if not user_data.get('Title'):
                    user_data['Title'] = mimic_config.get('Title', '')
                
                # Get permission sets from mimic user
                permission_data = {
                    'permission_set_groups': mimic_config.get('permission_set_group_ids', []),
                    'permission_sets': mimic_config.get('permission_set_ids', [])
                }
            else:
                # Use Profile/Role from CSV
                profile_name = user_data.get('Profile', '').strip()
                role_name = user_data.get('Role', '').strip()
                
                if not profile_name:
                    results['failed'].append({
                        'user': user_data,
                        'error': "Profile is required (or provide MimicUser)"
                    })
                    continue
                
                profile_id = self.get_profile_id(profile_name)
                role_id = self.get_role_id(role_name) if role_name else None
                
                if not profile_id:
                    results['failed'].append({
                        'user': user_data,
                        'error': f"Profile '{profile_name}' not found"
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
    parser.add_argument('--output', default='temp/provisioning_results.json',
                       help='Output file for results (default: temp/provisioning_results.json)')
    add_jira_args(parser)
    
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
    
    # Initialize Jira client (auto-detects config from file, CLI args, or env vars)
    jira_client = load_jira_client_from_args(args)
    
    # Initialize Gainsight client if configured
    # Auto-load gainsight_config.json if it exists
    gainsight_client = None
    default_gainsight_config = os.getenv("GAINSIGHT_CONFIG_PATH", "gainsight_config.json")
    if os.path.exists(default_gainsight_config):
        try:
            gainsight_client = create_gainsight_client(default_gainsight_config)
            print("Gainsight integration: ENABLED (for Client Success users)")
        except Exception as e:
            print(f"WARNING: Failed to load Gainsight config from {default_gainsight_config}: {e}")
            print("Continuing without Gainsight integration...")
    else:
        print("Gainsight integration: DISABLED (no gainsight_config.json found)")
    
    print()
    
    # Initialize provisioner
    try:
        provisioner = SalesforceUserProvisioner(args.org, jira_client, gainsight_client)
    except SystemExit:
        sys.exit(1)
    
    # Provision users
    results = provisioner.provision_users_from_csv(args.csv, args.threshold)
    
    # Save results (ensure output directory exists)
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
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

