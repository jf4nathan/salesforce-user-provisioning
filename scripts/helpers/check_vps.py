#!/usr/bin/env python3
"""
Check Vice Presidents in Client Success profile.

Usage:
    python check_vps.py --org mavenprod
"""

import argparse
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.sf_utils import get_sf_connection, print_user_details


def find_vps(org_alias: str):
    """Find VPs in Client Success"""
    sf = get_sf_connection(org_alias)
    
    query = """
    SELECT Id, FirstName, LastName, Email, Title, Profile.Name, UserRole.Name, Department
    FROM User 
    WHERE (Title LIKE '%Vice President%' OR Title LIKE '%VP%')
    AND Profile.Name LIKE '%Client Success%'
    AND IsActive = true
    ORDER BY Title, LastName
    """
    
    try:
        result = sf.query(query)
        return result['records']
    except Exception as e:
        print(f"Error: {str(e)}")
        return []


def get_client_success_roles(org_alias: str):
    """Get all roles used by Client Success profile users"""
    sf = get_sf_connection(org_alias)
    
    query = """
    SELECT UserRole.Name, COUNT(Id) UserCount
    FROM User 
    WHERE Profile.Name = 'Client Success'
    AND IsActive = true
    AND UserRoleId != null
    GROUP BY UserRole.Name
    ORDER BY COUNT(Id) DESC
    """
    
    try:
        result = sf.query(query)
        return result['records']
    except Exception as e:
        print(f"Error querying roles: {str(e)}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Find VPs in Client Success')
    parser.add_argument('--org', default='mavenprod', help='Salesforce org alias')
    args = parser.parse_args()
    
    vps = find_vps(args.org)
    
    if vps:
        print(f"Found {len(vps)} Vice President(s) in Client Success:\n")
        for user in vps:
            print_user_details(user)
            print("-" * 60)
    else:
        print("No Vice Presidents found in Client Success profile")
        print("\nChecking all available Roles for Client Success profile...")
        
        roles = get_client_success_roles(args.org)
        if roles:
            print("\nAvailable Roles for Client Success profile:")
            for record in roles:
                role = record.get('UserRole', {}).get('Name', '') if record.get('UserRole') else ''
                count = record.get('expr0', 0)
                print(f"  - {role} ({count} users)")


if __name__ == '__main__':
    main()
