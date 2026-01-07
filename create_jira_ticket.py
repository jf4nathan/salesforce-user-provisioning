#!/usr/bin/env python3
"""
Create a Jira ticket for an existing provisioned user
"""
import json
import sys
import os
import argparse
from provision_user import SalesforceUserProvisioner, JiraClient

def main():
    parser = argparse.ArgumentParser(description='Create Jira ticket for existing user')
    parser.add_argument('--user-id', required=True, help='Salesforce User ID')
    parser.add_argument('--org', required=True, help='Salesforce org alias')
    parser.add_argument('--jira-config', help='Path to JSON file with Jira configuration')
    parser.add_argument('--jira-url', help='Jira instance URL')
    parser.add_argument('--jira-email', help='Jira user email')
    parser.add_argument('--jira-token', help='Jira API token')
    parser.add_argument('--jira-project', help='Jira project key')
    parser.add_argument('--results-file', default='provisioning_results.json', 
                       help='Path to provisioning results JSON file')
    
    args = parser.parse_args()
    
    # Load user data from results file
    if not os.path.exists(args.results_file):
        print(f"ERROR: Results file not found: {args.results_file}")
        sys.exit(1)
    
    with open(args.results_file, 'r') as f:
        results = json.load(f)
    
    # Find user by ID
    user_data = None
    for success in results.get('success', []):
        if success.get('userId') == args.user_id:
            user_data = success['user']
            break
    
    if not user_data:
        print(f"ERROR: User ID {args.user_id} not found in results file")
        sys.exit(1)
    
    # Initialize Jira client
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
        except Exception as e:
            print(f"ERROR: Failed to load Jira config: {e}")
            sys.exit(1)
    elif args.jira_url and args.jira_email and args.jira_token and args.jira_project:
        jira_client = JiraClient(
            jira_url=args.jira_url,
            email=args.jira_email,
            api_token=args.jira_token,
            project_key=args.jira_project,
            issue_type='Task',
            assignee_email=os.getenv('JIRA_ASSIGNEE_EMAIL'),
            board_id=int(os.getenv('JIRA_BOARD_ID')) if os.getenv('JIRA_BOARD_ID') else None
        )
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
        else:
            print("ERROR: Jira configuration required. Use --jira-config, command line args, or environment variables")
            sys.exit(1)
    
    # Initialize provisioner
    try:
        provisioner = SalesforceUserProvisioner(args.org, jira_client)
    except SystemExit:
        sys.exit(1)
    
    # Get user link
    user_link = provisioner.get_user_link(args.user_id)
    
    # Get permission sets (empty for now since none were assigned)
    assigned_group_names = []
    assigned_permission_set_names = []
    
    # Create Jira ticket
    print(f"Creating Jira ticket for {user_data['FirstName']} {user_data['LastName']}...")
    provisioner.create_jira_ticket(
        user_data, 
        args.user_id, 
        user_link,
        assigned_group_names,
        assigned_permission_set_names
    )

if __name__ == '__main__':
    main()

