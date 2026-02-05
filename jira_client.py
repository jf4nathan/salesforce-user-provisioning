#!/usr/bin/env python3
"""
Jira client for creating and updating tickets via REST API.

Provides:
    - JiraClient class for Jira REST API operations
    - Helper functions for loading Jira configuration from various sources
    - add_jira_args() to add standard Jira CLI arguments to argparse
"""

import json
import os
import argparse
import base64
import time
import requests
from typing import Dict, Optional


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
    
    def create_ticket(self, summary: str, description: str, max_retries: int = 3, **kwargs) -> Optional[Dict]:
        """
        Create a Jira ticket with retry logic and detailed error logging
        
        Args:
            summary: Ticket summary/title
            description: Ticket description (supports ADF format dict or plain text)
            max_retries: Maximum number of retry attempts (default: 3)
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
                    print(f"  WARNING: Could not find assignee account ID for {assignee_value}, skipping assignee")
            else:
                # It's already an accountId
                issue_data["fields"]["assignee"] = {"accountId": assignee_value}
        elif self.assignee_email:
            # Use default assignee from config
            account_id = self._get_assignee_account_id(self.assignee_email)
            if account_id:
                issue_data["fields"]["assignee"] = {"accountId": account_id}
            else:
                print(f"  WARNING: Could not find assignee account ID for {self.assignee_email}, skipping assignee")
        
        if 'labels' in kwargs:
            issue_data["fields"]["labels"] = kwargs['labels']
        if 'priority' in kwargs:
            issue_data["fields"]["priority"] = {"name": kwargs['priority']}
        if 'components' in kwargs:
            issue_data["fields"]["components"] = [{"name": comp} for comp in kwargs['components']]
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.auth_header
        }
        
        # Create sanitized copy of issue_data for logging (remove sensitive data)
        log_data = json.loads(json.dumps(issue_data))
        if 'assignee' in log_data.get('fields', {}):
            log_data['fields']['assignee'] = {'accountId': '[REDACTED]'}
        
        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** (attempt - 1)
                    print(f"  Retrying Jira ticket creation (attempt {attempt + 1}/{max_retries}) after {wait_time}s...")
                    time.sleep(wait_time)
                
                response = requests.post(url, json=issue_data, headers=headers, timeout=10)
                response.raise_for_status()
                
                result = response.json()
                ticket_key = result.get('key')
                ticket_id = result.get('id')
                ticket_url = f"{self.jira_url}/browse/{ticket_key}"
                
                if attempt > 0:
                    print(f"  SUCCESS: Jira ticket created on retry attempt {attempt + 1}")
                
                # Assign sprint after ticket creation (if available)
                sprint_id = None
                if 'sprint_id' in kwargs:
                    sprint_id = kwargs['sprint_id']
                elif self.board_id:
                    sprint_id = self._get_current_sprint_id()
                
                if sprint_id:
                    sprint_field_id = self._get_sprint_custom_field_id()
                    if sprint_field_id:
                        try:
                            # Update ticket to add sprint
                            update_url = f"{self.jira_url}/rest/api/3/issue/{ticket_id}"
                            update_data = {
                                "fields": {
                                    sprint_field_id: int(sprint_id)
                                }
                            }
                            update_response = requests.put(update_url, json=update_data, headers=headers, timeout=10)
                            update_response.raise_for_status()
                            print(f"  SUCCESS: Assigned sprint to ticket")
                        except Exception as e:
                            print(f"  WARNING: Could not assign sprint to ticket: {str(e)}")
                
                return {
                    'key': ticket_key,
                    'id': ticket_id,
                    'url': ticket_url
                }
            except requests.exceptions.RequestException as e:
                last_exception = e
                is_last_attempt = (attempt == max_retries - 1)
                
                # Detailed error logging
                print(f"  ERROR: Jira ticket creation failed (attempt {attempt + 1}/{max_retries})")
                print(f"    URL: {url}")
                print(f"    Project Key: {self.project_key}")
                print(f"    Issue Type: {self.issue_type}")
                print(f"    Summary: {summary}")
                
                if hasattr(e, 'response') and e.response is not None:
                    print(f"    HTTP Status: {e.response.status_code}")
                    print(f"    Response Headers: {dict(e.response.headers)}")
                    
                    try:
                        error_detail = e.response.json()
                        print(f"    Error Response: {json.dumps(error_detail, indent=6)}")
                        
                        # Log specific field errors if available
                        if 'errors' in error_detail and error_detail['errors']:
                            print(f"    Field Errors:")
                            for field, error_msg in error_detail['errors'].items():
                                print(f"      - {field}: {error_msg}")
                    except:
                        try:
                            error_text = e.response.text
                            print(f"    Response Body: {error_text[:500]}")  # First 500 chars
                        except:
                            print(f"    Could not parse error response")
                else:
                    print(f"    Exception Type: {type(e).__name__}")
                    print(f"    Exception Message: {str(e)}")
                
                # Log request payload (sanitized) for debugging
                if is_last_attempt:
                    print(f"    Request Payload (sanitized):")
                    print(f"    {json.dumps(log_data, indent=6)}")
                
                # Don't retry on 4xx errors (client errors) except 429 (rate limit)
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    if 400 <= status_code < 500 and status_code != 429:
                        print(f"    Skipping retry - client error (4xx) that won't be fixed by retrying")
                        break
        
        # All retries exhausted
        print(f"  WARNING: Failed to create Jira ticket after {max_retries} attempts")
        return None

    def add_comment(self, issue_key: str, comment: str, max_retries: int = 3) -> bool:
        """
        Add a comment to an existing Jira issue with retry logic and detailed error logging.

        Args:
            issue_key: Jira issue key (e.g., "SFDC-1001")
            comment: Comment body (either ADF dict or plain text)
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            True if successful, False otherwise.
        """
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/comment"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.auth_header
        }

        # If comment is already a dict (ADF format), use it directly
        # Otherwise, wrap plain text in ADF format
        if isinstance(comment, dict):
            body_field = comment
        else:
            body_field = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": str(comment)
                            }
                        ]
                    }
                ]
            }

        payload = {"body": body_field}

        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** (attempt - 1)
                    print(f"  Retrying Jira comment addition (attempt {attempt + 1}/{max_retries}) after {wait_time}s...")
                    time.sleep(wait_time)
                
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                response.raise_for_status()
                
                if attempt > 0:
                    print(f"  SUCCESS: Jira comment added on retry attempt {attempt + 1}")
                return True
            except requests.exceptions.RequestException as e:
                last_exception = e
                is_last_attempt = (attempt == max_retries - 1)
                
                # Detailed error logging
                print(f"  ERROR: Failed to add Jira comment to {issue_key} (attempt {attempt + 1}/{max_retries})")
                print(f"    URL: {url}")
                
                if hasattr(e, 'response') and e.response is not None:
                    print(f"    HTTP Status: {e.response.status_code}")
                    
                    try:
                        error_detail = e.response.json()
                        print(f"    Error Response: {json.dumps(error_detail, indent=6)}")
                        
                        # Log specific field errors if available
                        if 'errors' in error_detail and error_detail['errors']:
                            print(f"    Field Errors:")
                            for field, error_msg in error_detail['errors'].items():
                                print(f"      - {field}: {error_msg}")
                    except:
                        try:
                            error_text = e.response.text
                            print(f"    Response Body: {error_text[:500]}")  # First 500 chars
                        except:
                            print(f"    Could not parse error response")
                else:
                    print(f"    Exception Type: {type(e).__name__}")
                    print(f"    Exception Message: {str(e)}")
                
                # Don't retry on 4xx errors (client errors) except 429 (rate limit)
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    if 400 <= status_code < 500 and status_code != 429:
                        print(f"    Skipping retry - client error (4xx) that won't be fixed by retrying")
                        break
        
        # All retries exhausted
        print(f"  WARNING: Failed to add Jira comment after {max_retries} attempts")
        return False


def add_jira_args(parser: argparse.ArgumentParser) -> None:
    """Add standard Jira CLI arguments to an argument parser."""
    parser.add_argument('--jira-config', help='Path to JSON file with Jira configuration')
    parser.add_argument('--jira-url', help='Jira instance URL (e.g., https://company.atlassian.net)')
    parser.add_argument('--jira-email', help='Jira user email for API authentication')
    parser.add_argument('--jira-token', help='Jira API token')
    parser.add_argument('--jira-project', help='Jira project key (e.g., PROJ)')
    parser.add_argument('--jira-issue-type', default='Task', help='Jira issue type (default: Task)')


def load_jira_client_from_config(config_path: str) -> JiraClient:
    """
    Create JiraClient from a JSON config file.
    
    Args:
        config_path: Path to Jira config JSON file
    
    Returns:
        Configured JiraClient instance
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        KeyError: If required config fields are missing
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return JiraClient(
        jira_url=config['jira_url'],
        email=config['email'],
        api_token=config['api_token'],
        project_key=config['project_key'],
        issue_type=config.get('issue_type', 'Task'),
        assignee_email=config.get('assignee_email'),
        board_id=config.get('board_id'),
    )


def load_jira_client_from_args(args: argparse.Namespace, verbose: bool = True) -> Optional[JiraClient]:
    """
    Create JiraClient from argparse namespace, env vars, or auto-detected config.
    
    Priority:
        1. Config file (--jira-config or auto-detected jira_config.json / JIRA_CONFIG_PATH)
        2. CLI arguments (--jira-url, --jira-email, --jira-token, --jira-project)
        3. Environment variables (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY)
    
    Args:
        args: Parsed argparse namespace with Jira-related attributes
        verbose: If True, print status messages about Jira configuration
    
    Returns:
        Configured JiraClient or None if no valid configuration found
    """
    # Auto-detect config path
    config_path = getattr(args, 'jira_config', None)
    if not config_path:
        default = os.getenv("JIRA_CONFIG_PATH", "jira_config.json")
        if os.path.exists(default):
            config_path = default

    # Try config file
    if config_path:
        try:
            client = load_jira_client_from_config(config_path)
            if verbose:
                print("Jira integration: ENABLED")
                with open(config_path, 'r') as f:
                    cfg = json.load(f)
                if cfg.get('assignee_email'):
                    print(f"  Assignee: {cfg['assignee_email']}")
                if cfg.get('board_id'):
                    print(f"  Board ID: {cfg['board_id']} (for current sprint)")
            return client
        except Exception as e:
            if verbose:
                print(f"WARNING: Failed to load Jira config from {config_path}: {e}")
                print("Continuing without Jira integration...")
            return None

    # Try CLI args
    jira_url = getattr(args, 'jira_url', None)
    jira_email = getattr(args, 'jira_email', None)
    jira_token = getattr(args, 'jira_token', None)
    jira_project = getattr(args, 'jira_project', None)

    if jira_url and jira_email and jira_token and jira_project:
        assignee = getattr(args, 'jira_assignee_email', None) or os.getenv('JIRA_ASSIGNEE_EMAIL')
        board = getattr(args, 'jira_board_id', None)
        if board is None and os.getenv('JIRA_BOARD_ID'):
            board = int(os.getenv('JIRA_BOARD_ID'))

        client = JiraClient(
            jira_url=jira_url,
            email=jira_email,
            api_token=jira_token,
            project_key=jira_project,
            issue_type=getattr(args, 'jira_issue_type', 'Task'),
            assignee_email=assignee,
            board_id=board,
        )
        if verbose:
            print("Jira integration: ENABLED")
        return client

    # Try environment variables
    env_url = os.getenv('JIRA_URL')
    env_email = os.getenv('JIRA_EMAIL')
    env_token = os.getenv('JIRA_API_TOKEN')
    env_project = os.getenv('JIRA_PROJECT_KEY')

    if env_url and env_email and env_token and env_project:
        client = JiraClient(
            jira_url=env_url,
            email=env_email,
            api_token=env_token,
            project_key=env_project,
            issue_type=os.getenv('JIRA_ISSUE_TYPE', 'Task'),
            assignee_email=os.getenv('JIRA_ASSIGNEE_EMAIL'),
            board_id=int(os.getenv('JIRA_BOARD_ID')) if os.getenv('JIRA_BOARD_ID') else None,
        )
        if verbose:
            print("Jira integration: ENABLED (from environment variables)")
        return client

    if verbose:
        print("Jira integration: DISABLED (no configuration provided)")
    return None
