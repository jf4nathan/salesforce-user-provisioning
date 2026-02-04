#!/usr/bin/env python3
"""
Gainsight SCIM API Client for User Provisioning and Permission Management

Usage:
    # Create a user
    python gainsight_client.py create --email john.doe@company.com --first-name John --last-name Doe
    
    # Search for a user
    python gainsight_client.py search --email john.doe@company.com
    
    # List all groups
    python gainsight_client.py list-groups
    
    # Add user to group
    python gainsight_client.py add-to-group --user-id <user_id> --group-id <group_id>

Requirements:
    - requests library: pip install requests
    - gainsight_config.json with access key
"""

import json
import os
import sys
import argparse
import base64
import time
import requests
from typing import Dict, List, Optional, Any


class GainsightClient:
    """Client for Gainsight SCIM API - User Provisioning and Permission Management"""
    
    def __init__(self, tenant_url: str, client_id: str, client_secret: str,
                 default_license_type: str = "Full",
                 default_groups: List[str] = None,
                 default_roles: List[str] = None):
        """
        Initialize Gainsight SCIM client with M2M OAuth authentication
        
        Args:
            tenant_url: Gainsight tenant URL (e.g., https://mavenclinic.us2.gainsightcloud.com)
            client_id: M2M OAuth Client ID
            client_secret: M2M OAuth Client Secret
            default_license_type: Default license type (Full, Viewer_Analytics, Viewer, Internal_Collaborator)
            default_groups: Default group IDs to assign to new users
            default_roles: Default roles to assign to new users
        """
        self.tenant_url = tenant_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.default_license_type = default_license_type
        self.default_groups = default_groups or []
        self.default_roles = default_roles or []
        self.base_url = f"{self.tenant_url}/v1/users/services/scim"
        
        # Token caching
        self._access_token = None
        self._token_expires_at = 0
    
    def _get_basic_auth_header(self) -> str:
        """Create Basic auth header for token requests"""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def _get_access_token(self) -> str:
        """Get M2M OAuth access token, refreshing if expired"""
        # Return cached token if still valid (with 60s buffer)
        if self._access_token and time.time() < (self._token_expires_at - 60):
            return self._access_token
        
        # Request new token
        url = f"{self.tenant_url}/v1/users/m2m/oauth/token"
        headers = {
            "Authorization": self._get_basic_auth_header(),
            "Content-Type": "application/json"
        }
        
        print("  Authenticating with Gainsight...")
        response = requests.post(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            error_detail = response.text[:500] if response.text else "Unknown error"
            raise Exception(f"Failed to get access token (HTTP {response.status_code}): {error_detail}")
        
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 86400)
        print("  Authentication successful")
        
        return self._access_token
    
    def _get_headers(self, content_type: str = "application/scim+json") -> Dict[str, str]:
        """Get headers for SCIM API requests"""
        return {
            "Content-Type": content_type,
            "Accept": "application/scim+json",
            "Authorization": f"Bearer {self._get_access_token()}"
        }
    
    def _handle_response(self, response: requests.Response, operation: str) -> Dict:
        """Handle API response and errors"""
        if response.status_code in [200, 201]:
            return response.json()
        elif response.status_code == 204:
            return {"success": True, "message": f"{operation} completed successfully"}
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = error_data.get('detail', str(error_data))
            except:
                error_detail = response.text[:500] if response.text else "Unknown error"
            
            raise Exception(f"{operation} failed (HTTP {response.status_code}): {error_detail}")
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, email: str, first_name: str, last_name: str,
                    username: str = None, title: str = None, timezone: str = "America/New_York",
                    license_type: str = None, is_super_admin: bool = False,
                    groups: List[Dict] = None, roles: List[str] = None,
                    manager_id: str = None) -> Dict:
        """
        Create a new user in Gainsight
        
        Args:
            email: User's email address
            first_name: User's first name
            last_name: User's last name
            username: Username (defaults to email)
            title: Job title
            timezone: Timezone (default: America/New_York)
            license_type: License type (Full, Viewer_Analytics, Viewer, Internal_Collaborator)
            is_super_admin: Whether user is a super admin
            groups: List of groups to assign (each dict has 'value' and/or 'display')
            roles: List of role names to assign
            manager_id: Gainsight user ID of the manager
        
        Returns:
            Dict with created user details including Gainsight user ID
        """
        url = f"{self.base_url}/Users"
        
        # Build user payload
        user_data = {
            "schemas": [
                "urn:ietf:params:scim:schemas:core:2.0:User",
                "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
                "urn:ietf:params:scim:schemas:extension:gainsight:2.0:User"
            ],
            "userName": username or email,
            "name": {
                "givenName": first_name,
                "familyName": last_name
            },
            "displayName": f"{first_name} {last_name}",
            "emails": [
                {
                    "primary": True,
                    "value": email
                }
            ],
            "active": True,
            "timezone": timezone
        }
        
        # Add optional fields
        if title:
            user_data["title"] = title
        
        # Add groups
        if groups:
            user_data["groups"] = groups
        elif self.default_groups:
            user_data["groups"] = [{"value": g} for g in self.default_groups]
        
        # Add manager if provided
        if manager_id:
            user_data["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"] = {
                "manager": {
                    "value": manager_id
                }
            }
        
        # Add Gainsight-specific fields
        gainsight_ext = {
            "IsSuperAdmin": is_super_admin,
            "LicenseType": license_type or self.default_license_type
        }
        
        if roles:
            gainsight_ext["custom_roles"] = roles
        elif self.default_roles:
            gainsight_ext["custom_roles"] = self.default_roles
        
        user_data["urn:ietf:params:scim:schemas:extension:gainsight:2.0:User"] = gainsight_ext
        
        print(f"  Creating Gainsight user: {email}...")
        response = requests.post(url, json=user_data, headers=self._get_headers(), timeout=30)
        result = self._handle_response(response, "Create user")
        
        print(f"  SUCCESS: Gainsight user created with ID: {result.get('id')}")
        return result
    
    def get_user(self, user_id: str) -> Dict:
        """Get user by Gainsight user ID"""
        url = f"{self.base_url}/Users/{user_id}"
        response = requests.get(url, headers=self._get_headers(), timeout=30)
        return self._handle_response(response, "Get user")
    
    def search_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Search for a user by email address
        
        Returns:
            User dict if found, None otherwise
        """
        # Gainsight uses userName as email typically, try both approaches
        # First try by userName (more reliable)
        result = self.search_user_by_username(email.lower())
        if result:
            return result
        
        # Fallback to email filter
        url = f"{self.base_url}/Users"
        params = {
            "filter": f'emails.value eq "{email}"',
            "count": 1
        }
        
        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        result = self._handle_response(response, "Search user")
        
        resources = result.get("Resources", [])
        if resources:
            return resources[0]
        return None
    
    def search_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Search for a user by username
        
        Returns:
            User dict if found, None otherwise
        """
        url = f"{self.base_url}/Users"
        params = {
            "filter": f'userName eq "{username}"',
            "count": 1
        }
        
        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        result = self._handle_response(response, "Search user")
        
        resources = result.get("Resources", [])
        if resources:
            return resources[0]
        return None
    
    def update_user(self, user_id: str, **kwargs) -> Dict:
        """
        Update user attributes using PATCH
        
        Supported kwargs:
            - first_name, last_name, display_name
            - email, username, title
            - timezone, locale
            - active (bool)
            - groups (list of dicts with 'value' and/or 'display')
            - roles (list of role names)
            - license_type
            - is_super_admin (bool)
            - manager_id
        """
        url = f"{self.base_url}/Users/{user_id}"
        
        operations = []
        
        # Map kwargs to SCIM operations
        simple_mappings = {
            'username': 'userName',
            'display_name': 'displayName',
            'title': 'title',
            'timezone': 'timezone',
            'locale': 'locale',
            'active': 'active'
        }
        
        for key, scim_path in simple_mappings.items():
            if key in kwargs and kwargs[key] is not None:
                operations.append({
                    "op": "replace",
                    "path": scim_path,
                    "value": kwargs[key]
                })
        
        # Handle name separately
        if 'first_name' in kwargs:
            operations.append({
                "op": "replace",
                "path": "name.givenName",
                "value": kwargs['first_name']
            })
        
        if 'last_name' in kwargs:
            operations.append({
                "op": "replace",
                "path": "name.familyName",
                "value": kwargs['last_name']
            })
        
        # Handle email
        if 'email' in kwargs:
            operations.append({
                "op": "replace",
                "path": "emails",
                "value": [{"value": kwargs['email'], "primary": True}]
            })
        
        # Handle groups
        if 'groups' in kwargs:
            operations.append({
                "op": "replace",
                "path": "groups",
                "value": kwargs['groups']
            })
        
        # Handle manager
        if 'manager_id' in kwargs:
            operations.append({
                "op": "replace",
                "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager",
                "value": {"value": kwargs['manager_id']}
            })
        
        # Handle Gainsight-specific fields
        gainsight_updates = {}
        if 'is_super_admin' in kwargs:
            gainsight_updates['IsSuperAdmin'] = kwargs['is_super_admin']
        if 'license_type' in kwargs:
            gainsight_updates['LicenseType'] = kwargs['license_type']
        if 'roles' in kwargs:
            gainsight_updates['custom_roles'] = kwargs['roles']
        
        if gainsight_updates:
            operations.append({
                "op": "replace",
                "path": "urn:ietf:params:scim:schemas:extension:gainsight:2.0:User",
                "value": gainsight_updates
            })
        
        if not operations:
            return {"message": "No updates provided"}
        
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": operations
        }
        
        response = requests.patch(url, json=payload, headers=self._get_headers(), timeout=30)
        return self._handle_response(response, "Update user")
    
    def deactivate_user(self, user_id: str) -> Dict:
        """Deactivate a user"""
        return self.update_user(user_id, active=False)
    
    def activate_user(self, user_id: str) -> Dict:
        """Activate a user"""
        return self.update_user(user_id, active=True)
    
    # ==================== GROUP OPERATIONS ====================
    
    def list_groups(self, count: int = 100) -> List[Dict]:
        """
        List all groups in Gainsight
        
        Returns:
            List of group dicts with id, displayName, etc.
        """
        url = f"{self.base_url}/Groups"
        params = {
            "count": count,
            "excludedAttributes": "members"  # Don't fetch all members for performance
        }
        
        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        result = self._handle_response(response, "List groups")
        return result.get("Resources", [])
    
    def get_group(self, group_id: str) -> Dict:
        """Get group details including members"""
        url = f"{self.base_url}/Groups/{group_id}"
        response = requests.get(url, headers=self._get_headers(), timeout=30)
        return self._handle_response(response, "Get group")
    
    def search_group_by_name(self, display_name: str) -> Optional[Dict]:
        """Search for a group by display name"""
        url = f"{self.base_url}/Groups"
        params = {
            "filter": f'displayName eq "{display_name}"',
            "count": 1,
            "excludedAttributes": "members"
        }
        
        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        result = self._handle_response(response, "Search group")
        
        resources = result.get("Resources", [])
        if resources:
            return resources[0]
        return None
    
    def add_user_to_group(self, group_id: str, user_id: str) -> Dict:
        """Add a user to a group"""
        url = f"{self.base_url}/Groups/{group_id}"
        
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "add",
                    "path": "members",
                    "value": [{"value": user_id}]
                }
            ]
        }
        
        response = requests.patch(url, json=payload, headers=self._get_headers(), timeout=30)
        return self._handle_response(response, "Add user to group")
    
    def remove_user_from_group(self, group_id: str, user_id: str) -> Dict:
        """Remove a user from a group"""
        url = f"{self.base_url}/Groups/{group_id}"
        
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "remove",
                    "path": "members",
                    "value": [{"value": user_id}]
                }
            ]
        }
        
        response = requests.patch(url, json=payload, headers=self._get_headers(), timeout=30)
        return self._handle_response(response, "Remove user from group")
    
    # ==================== CONVENIENCE METHODS ====================
    
    def provision_user(self, email: str, first_name: str = None, last_name: str = None,
                       title: str = None, timezone: str = "America/New_York",
                       license_type: str = None, group_names: List[str] = None,
                       roles: List[str] = None, mimic_user_email: str = None) -> Dict:
        """
        Provision a user with optional mimic functionality
        
        Args:
            email: User's email
            first_name: First name (parsed from email if not provided)
            last_name: Last name (parsed from email if not provided)
            title: Job title
            timezone: Timezone
            license_type: License type
            group_names: List of group names to assign
            roles: List of roles to assign
            mimic_user_email: Email of existing user to copy settings from
        
        Returns:
            Dict with created/found user details
        """
        # Parse name from email if not provided
        if not first_name or not last_name:
            local_part = email.split('@')[0]
            parts = local_part.split('.', 1)
            first_name = first_name or parts[0].capitalize()
            last_name = last_name or (parts[1].capitalize() if len(parts) > 1 else parts[0].capitalize())
        
        # Check if user already exists
        existing_user = self.search_user_by_email(email)
        if existing_user:
            print(f"  User already exists in Gainsight: {email} (ID: {existing_user.get('id')})")
            return existing_user
        
        # Get settings from mimic user if provided
        groups = None
        if mimic_user_email:
            mimic_user = self.search_user_by_email(mimic_user_email)
            if mimic_user:
                print(f"  Mimicking user: {mimic_user.get('displayName', mimic_user_email)}")
                groups = mimic_user.get('groups', [])
                if not roles:
                    roles = [r.get('value') for r in mimic_user.get('roles', [])]
                if not license_type:
                    gs_ext = mimic_user.get('urn:ietf:params:scim:schemas:extension:gainsight:2.0:User', {})
                    license_type = gs_ext.get('LicenseType')
            else:
                print(f"  WARNING: Mimic user not found: {mimic_user_email}")
        
        # Resolve group names to IDs if provided
        if group_names and not groups:
            groups = []
            for name in group_names:
                group = self.search_group_by_name(name)
                if group:
                    groups.append({"value": group['id'], "display": name})
                else:
                    print(f"  WARNING: Group not found: {name}")
        
        # Create the user
        return self.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            title=title,
            timezone=timezone,
            license_type=license_type,
            groups=groups,
            roles=roles
        )


def load_config(config_path: str = None) -> Dict:
    """Load Gainsight configuration from file"""
    if not config_path:
        config_path = os.getenv("GAINSIGHT_CONFIG_PATH", "gainsight_config.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Gainsight config not found: {config_path}\n"
            f"Create gainsight_config.json from gainsight_config.example.json"
        )
    
    with open(config_path, 'r') as f:
        return json.load(f)


def create_client_from_config(config_path: str = None) -> GainsightClient:
    """Create GainsightClient from config file"""
    config = load_config(config_path)
    return GainsightClient(
        tenant_url=config['tenant_url'],
        client_id=config['client_id'],
        client_secret=config['client_secret'],
        default_license_type=config.get('default_license_type', 'Full'),
        default_groups=config.get('default_groups', []),
        default_roles=config.get('default_roles', [])
    )


def main():
    parser = argparse.ArgumentParser(
        description='Gainsight SCIM API Client for User Provisioning',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create user command
    create_parser = subparsers.add_parser('create', help='Create a new user')
    create_parser.add_argument('--email', required=True, help='User email')
    create_parser.add_argument('--first-name', help='First name')
    create_parser.add_argument('--last-name', help='Last name')
    create_parser.add_argument('--title', help='Job title')
    create_parser.add_argument('--timezone', default='America/New_York', help='Timezone')
    create_parser.add_argument('--license-type', choices=['Full', 'Viewer_Analytics', 'Viewer', 'Internal_Collaborator'],
                               help='License type')
    create_parser.add_argument('--groups', nargs='+', help='Group names to assign')
    create_parser.add_argument('--roles', nargs='+', help='Roles to assign')
    create_parser.add_argument('--mimic', help='Email of user to mimic settings from')
    
    # Search user command
    search_parser = subparsers.add_parser('search', help='Search for a user')
    search_parser.add_argument('--email', help='Search by email')
    search_parser.add_argument('--username', help='Search by username')
    
    # Get user command
    get_parser = subparsers.add_parser('get', help='Get user by ID')
    get_parser.add_argument('--user-id', required=True, help='Gainsight user ID')
    
    # List groups command
    list_groups_parser = subparsers.add_parser('list-groups', help='List all groups')
    list_groups_parser.add_argument('--count', type=int, default=100, help='Max groups to return')
    
    # Get group command
    get_group_parser = subparsers.add_parser('get-group', help='Get group details')
    get_group_parser.add_argument('--group-id', help='Group ID')
    get_group_parser.add_argument('--name', help='Group name')
    
    # Add to group command
    add_group_parser = subparsers.add_parser('add-to-group', help='Add user to group')
    add_group_parser.add_argument('--user-id', required=True, help='User ID')
    add_group_parser.add_argument('--group-id', help='Group ID')
    add_group_parser.add_argument('--group-name', help='Group name (alternative to group-id)')
    
    # Remove from group command
    remove_group_parser = subparsers.add_parser('remove-from-group', help='Remove user from group')
    remove_group_parser.add_argument('--user-id', required=True, help='User ID')
    remove_group_parser.add_argument('--group-id', help='Group ID')
    remove_group_parser.add_argument('--group-name', help='Group name (alternative to group-id)')
    
    # Deactivate user command
    deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate a user')
    deactivate_parser.add_argument('--user-id', help='User ID')
    deactivate_parser.add_argument('--email', help='User email (alternative to user-id)')
    
    # Config path
    parser.add_argument('--config', help='Path to gainsight_config.json')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        client = create_client_from_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    try:
        if args.command == 'create':
            result = client.provision_user(
                email=args.email,
                first_name=args.first_name,
                last_name=args.last_name,
                title=args.title,
                timezone=args.timezone,
                license_type=args.license_type,
                group_names=args.groups,
                roles=args.roles,
                mimic_user_email=args.mimic
            )
            print(json.dumps(result, indent=2))
        
        elif args.command == 'search':
            if args.email:
                result = client.search_user_by_email(args.email)
            elif args.username:
                result = client.search_user_by_username(args.username)
            else:
                print("ERROR: Provide --email or --username")
                sys.exit(1)
            
            if result:
                print(json.dumps(result, indent=2))
            else:
                print("User not found")
        
        elif args.command == 'get':
            result = client.get_user(args.user_id)
            print(json.dumps(result, indent=2))
        
        elif args.command == 'list-groups':
            groups = client.list_groups(args.count)
            print(f"Found {len(groups)} groups:\n")
            for group in groups:
                print(f"  ID: {group.get('id')}")
                print(f"  Name: {group.get('displayName')}")
                print()
        
        elif args.command == 'get-group':
            if args.group_id:
                result = client.get_group(args.group_id)
            elif args.name:
                result = client.search_group_by_name(args.name)
                if result:
                    result = client.get_group(result['id'])
            else:
                print("ERROR: Provide --group-id or --name")
                sys.exit(1)
            
            if result:
                print(json.dumps(result, indent=2))
            else:
                print("Group not found")
        
        elif args.command == 'add-to-group':
            group_id = args.group_id
            if not group_id and args.group_name:
                group = client.search_group_by_name(args.group_name)
                if group:
                    group_id = group['id']
                else:
                    print(f"ERROR: Group not found: {args.group_name}")
                    sys.exit(1)
            
            if not group_id:
                print("ERROR: Provide --group-id or --group-name")
                sys.exit(1)
            
            result = client.add_user_to_group(group_id, args.user_id)
            print(f"SUCCESS: User added to group")
        
        elif args.command == 'remove-from-group':
            group_id = args.group_id
            if not group_id and args.group_name:
                group = client.search_group_by_name(args.group_name)
                if group:
                    group_id = group['id']
                else:
                    print(f"ERROR: Group not found: {args.group_name}")
                    sys.exit(1)
            
            if not group_id:
                print("ERROR: Provide --group-id or --group-name")
                sys.exit(1)
            
            result = client.remove_user_from_group(group_id, args.user_id)
            print(f"SUCCESS: User removed from group")
        
        elif args.command == 'deactivate':
            user_id = args.user_id
            if not user_id and args.email:
                user = client.search_user_by_email(args.email)
                if user:
                    user_id = user['id']
                else:
                    print(f"ERROR: User not found: {args.email}")
                    sys.exit(1)
            
            if not user_id:
                print("ERROR: Provide --user-id or --email")
                sys.exit(1)
            
            result = client.deactivate_user(user_id)
            print(f"SUCCESS: User deactivated")
    
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
