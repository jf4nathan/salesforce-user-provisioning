#!/usr/bin/env python3
"""
Create a Jira ticket for an existing provisioned user
"""
import json
import sys
import os
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.provision_user import SalesforceUserProvisioner
from scripts.integrations.jira_client import load_jira_client_from_args, add_jira_args

def main():
    parser = argparse.ArgumentParser(description='Create Jira ticket for existing user')
    parser.add_argument('--user-id', required=True, help='Salesforce User ID')
    parser.add_argument('--org', required=True, help='Salesforce org alias')
    add_jira_args(parser)
    parser.add_argument('--results-file', default='temp/provisioning_results.json', 
                       help='Path to provisioning results JSON file (default: temp/provisioning_results.json)')
    
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
    jira_client = load_jira_client_from_args(args, verbose=False)
    if not jira_client:
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
