#!/usr/bin/env python3
"""
Check a user's Profile, Role, and other details by email.

Usage:
    python check_manager.py --org mavenprod user.email@mavenclinic.com
"""

import argparse
from sf_utils import get_sf_connection, print_user_details


def find_user(org_alias: str, email: str):
    """Find user by email and return their details"""
    sf = get_sf_connection(org_alias)
    
    query = f"""
    SELECT Id, FirstName, LastName, Email, Title, Profile.Name, UserRole.Name, Department
    FROM User 
    WHERE Email = '{email}' AND IsActive = true
    LIMIT 1
    """
    
    try:
        result = sf.query(query)
        if result['records']:
            return result['records'][0]
    except Exception as e:
        print(f"Error: {str(e)}")
    
    return None


def main():
    parser = argparse.ArgumentParser(description='Find user by email')
    parser.add_argument('--org', default='mavenprod', help='Salesforce org alias')
    parser.add_argument('email', help='Email address to search for')
    args = parser.parse_args()
    
    user = find_user(args.org, args.email)
    
    if user:
        print(f"Found user: {user.get('FirstName', '')} {user.get('LastName', '')}")
        print("-" * 40)
        print_user_details(user)
    else:
        print(f"User not found: {args.email}")


if __name__ == '__main__':
    main()
