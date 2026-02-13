#!/usr/bin/env python3
"""
Check Gainsight license assignment for a user.

Usage:
    python check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
"""

import argparse
from sf_utils import get_sf_connection


# Gainsight package license ID (18-character format)
GAINSIGHT_PACKAGE_LICENSE_ID = '050UH00000NFYVZYA5'
GAINSIGHT_PS_ID = '0PSUH0000006LTB4A2'


def check_gainsight_license(org_alias: str, user_email: str):
    """Check if user has Gainsight license assigned"""
    sf = get_sf_connection(org_alias)
    
    # Find user
    user_query = f"""
    SELECT Id, FirstName, LastName, Email, Username
    FROM User 
    WHERE Email = '{user_email}' AND IsActive = true
    LIMIT 1
    """
    
    try:
        user_result = sf.query(user_query)
        if not user_result['records']:
            print(f"User not found: {user_email}")
            return
        
        user = user_result['records'][0]
        user_id = user['Id']
        print(f"Found user: {user['FirstName']} {user['LastName']} ({user['Email']})")
        print(f"User ID: {user_id}")
        print("-" * 60)
        
        # Check if Gainsight license is assigned
        license_query = f"""
        SELECT Id, UserId, PackageLicenseId, PackageLicense.NamespacePrefix
        FROM UserPackageLicense 
        WHERE UserId = '{user_id}' 
        AND PackageLicenseId = '{GAINSIGHT_PACKAGE_LICENSE_ID}'
        LIMIT 1
        """
        
        license_result = sf.query(license_query)
        if license_result['records']:
            print("[SUCCESS] Gainsight license IS assigned")
            license_record = license_result['records'][0]
            print(f"  License Assignment ID: {license_record['Id']}")
            if license_record.get('PackageLicense'):
                print(f"  Namespace: {license_record['PackageLicense'].get('NamespacePrefix', 'N/A')}")
        else:
            print("[FAILED] Gainsight license NOT assigned")
        
        # Check license availability
        print("\n" + "-" * 60)
        print("Gainsight License Availability:")
        license_info_query = f"""
        SELECT Id, UsedLicenses, AllowedLicenses, NamespacePrefix
        FROM PackageLicense 
        WHERE Id = '{GAINSIGHT_PACKAGE_LICENSE_ID}'
        LIMIT 1
        """
        
        license_info_result = sf.query(license_info_query)
        if license_info_result['records']:
            license_info = license_info_result['records'][0]
            used = license_info.get('UsedLicenses', 0)
            allowed = license_info.get('AllowedLicenses', 0)
            available = allowed - used
            print(f"  Total Licenses: {allowed}")
            print(f"  Used Licenses: {used}")
            print(f"  Available Licenses: {available}")
            print(f"  Namespace: {license_info.get('NamespacePrefix', 'N/A')}")
        
        # Check if Gainsight CS permission set is assigned
        print("\n" + "-" * 60)
        print("Gainsight CS Permission Set:")
        ps_query = f"""
        SELECT Id, PermissionSetId, PermissionSet.Name, PermissionSet.Label
        FROM PermissionSetAssignment
        WHERE AssigneeId = '{user_id}'
        AND PermissionSetId = '{GAINSIGHT_PS_ID}'
        LIMIT 1
        """
        
        ps_result = sf.query(ps_query)
        if ps_result['records']:
            print("[SUCCESS] Gainsight CS Permission Set IS assigned")
            ps_record = ps_result['records'][0]
            if ps_record.get('PermissionSet'):
                print(f"  Permission Set: {ps_record['PermissionSet'].get('Label', 'N/A')} ({ps_record['PermissionSet'].get('Name', 'N/A')})")
        else:
            print("[FAILED] Gainsight CS Permission Set NOT assigned")
            print("  Note: The Gainsight CS permission set requires the Gainsight package license")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description='Check Gainsight license assignment')
    parser.add_argument('--org', default='mavenprod', help='Salesforce org alias')
    parser.add_argument('email', help='User email address')
    args = parser.parse_args()
    
    check_gainsight_license(args.org, args.email)


if __name__ == '__main__':
    main()
