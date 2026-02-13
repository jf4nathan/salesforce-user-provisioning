#!/usr/bin/env python3
"""
Query Client Success users to see their Profiles and Roles.

Usage:
    python query_client_success_users.py --org mavenprod
"""

import argparse
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from scripts.core.sf_utils import get_sf_connection


def query_client_success_users(org_alias: str):
    """Query for Client Success users"""
    sf = get_sf_connection(org_alias)
    
    # Query for users with Client Success in their title, profile, or department
    queries = [
        # Query by Title containing "Client Success"
        """
        SELECT Id, FirstName, LastName, Email, Title, Profile.Name, UserRole.Name, Department
        FROM User 
        WHERE (Title LIKE '%Client Success%' OR Title LIKE '%Client%Success%')
        AND IsActive = true
        ORDER BY Title, LastName
        """,
        # Query by Profile containing "Client Success"
        """
        SELECT Id, FirstName, LastName, Email, Title, Profile.Name, UserRole.Name, Department
        FROM User 
        WHERE Profile.Name LIKE '%Client Success%'
        AND IsActive = true
        ORDER BY Profile.Name, Title, LastName
        """,
        # Query by Department containing "Client Success"
        """
        SELECT Id, FirstName, LastName, Email, Title, Profile.Name, UserRole.Name, Department
        FROM User 
        WHERE Department LIKE '%Client Success%'
        AND IsActive = true
        ORDER BY Department, Title, LastName
        """
    ]
    
    all_users = {}
    
    for i, query in enumerate(queries, 1):
        try:
            result = sf.query(query)
            for user in result['records']:
                user_id = user['Id']
                if user_id not in all_users:
                    all_users[user_id] = {
                        'FirstName': user.get('FirstName', ''),
                        'LastName': user.get('LastName', ''),
                        'Email': user.get('Email', ''),
                        'Title': user.get('Title', ''),
                        'Profile': user.get('Profile', {}).get('Name', '') if user.get('Profile') else '',
                        'Role': user.get('UserRole', {}).get('Name', '') if user.get('UserRole') else '',
                        'Department': user.get('Department', '')
                    }
        except Exception as e:
            print(f"Query {i} failed: {str(e)}")
    
    return list(all_users.values())


def main():
    parser = argparse.ArgumentParser(description='Query Client Success users')
    parser.add_argument('--org', default='mavenprod', help='Salesforce org alias')
    args = parser.parse_args()
    
    print(f"Querying Client Success users from org: {args.org}")
    print("=" * 80)
    
    users = query_client_success_users(args.org)
    
    if not users:
        print("No Client Success users found.")
        return
    
    # Group by Profile and Role
    profile_role_counts = {}
    for user in users:
        profile = user['Profile'] or 'N/A'
        role = user['Role'] or 'N/A'
        key = (profile, role)
        if key not in profile_role_counts:
            profile_role_counts[key] = []
        profile_role_counts[key].append(user)
    
    print(f"\nFound {len(users)} Client Success users\n")
    print("=" * 80)
    print("PROFILE AND ROLE SUMMARY:")
    print("=" * 80)
    
    for (profile, role), user_list in sorted(profile_role_counts.items()):
        print(f"\nProfile: {profile}")
        print(f"Role: {role}")
        print(f"Count: {len(user_list)} users")
        print("\nUsers:")
        for user in sorted(user_list, key=lambda x: (x['Title'] or '', x['LastName'])):
            name = f"{user['FirstName']} {user['LastName']}".strip()
            title = user['Title'] or 'N/A'
            email = user['Email'] or 'N/A'
            print(f"  - {name} ({email}) - {title}")
        print("-" * 80)
    
    # Show most common Profile+Role combination
    if profile_role_counts:
        most_common = max(profile_role_counts.items(), key=lambda x: len(x[1]))
        profile, role = most_common[0]
        print(f"\nMost common combination: Profile='{profile}', Role='{role}' ({len(most_common[1])} users)")


if __name__ == '__main__':
    main()
