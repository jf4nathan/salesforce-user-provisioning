# Salesforce User Provisioning Script

Automated user provisioning script for Salesforce that creates users and assigns permission sets based on Profile + Role analysis.

## Features

- ✅ Creates users with all required fields (Profile, Role, Manager, TimeZone, etc.)
- ✅ Automatically analyzes permission sets from similar users (same Profile + Role)
- ✅ Assigns permission sets that appear in >50% of similar users (configurable threshold)
- ✅ Assigns permission set groups first, then individual permission sets
- ✅ Uses Salesforce CLI (sf) for authentication - no credentials needed in code
- ✅ Generates detailed provisioning results

## Prerequisites

1. **Salesforce CLI** installed and authenticated
   - Download: https://developer.salesforce.com/tools/salesforcecli
   - Authenticate: `sf org login web --alias mavenprod`

2. **Python 3.7+** installed

3. **Python dependencies**:
   ```bash
   pip install simple-salesforce
   ```

## Quick Start

1. **Prepare your CSV file** (use `users_template.csv` as a template):
   ```csv
   FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
   John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York
   ```

2. **Run the script**:
   ```bash
   python provision_user.py --csv users.csv --org mavenprod
   ```

3. **Reset passwords manually**:
   - Go to Setup > Users > Users
   - Find the newly created user
   - Click dropdown → Reset Password
   - Check "Generate new password and notify user immediately"

## Usage

### Basic Usage
```bash
python provision_user.py --csv users.csv --org mavenprod
```

### Custom Permission Set Threshold
```bash
# Assign permission sets that appear in 60%+ of similar users
python provision_user.py --csv users.csv --org mavenprod --threshold 0.6
```

### Custom Output File
```bash
python provision_user.py --csv users.csv --org mavenprod --output my_results.json
```

## CSV Format

Required columns:
- `FirstName` - User's first name
- `LastName` - User's last name
- `Email` - User's email address
- `Username` - Salesforce username (usually same as email)
- `Title` - User's job title
- `Profile` - Salesforce profile name (e.g., "Sales", "Marketing", "Client Success")
- `Role` - Salesforce role name (e.g., "Sales Rep", "Marketing Manager")

Optional columns:
- `ManagerEmail` - Manager's email address (for ManagerId lookup)
- `TimeZone` - Time zone (defaults to "America/New_York" if not specified)

## How It Works

1. **Connects to Salesforce** using your authenticated sf CLI session
2. **Analyzes similar users** - Finds all active users with the same Profile + Role combination
3. **Identifies permission sets** - Determines which permission sets/groups are assigned to >50% of similar users
4. **Creates the user** with all required fields
5. **Assigns permission sets** - Assigns permission set groups first, then individual permission sets
6. **Generates results** - Saves detailed results to JSON file

## Output

The script generates a JSON file (`provisioning_results.json` by default) with:
- Successfully created users (with User IDs)
- Failed user creations (with error messages)
- Detailed user information

## Troubleshooting

### "Could not connect to org"
- Make sure you're authenticated: `sf org list`
- Authenticate if needed: `sf org login web --alias mavenprod`

### "Profile not found"
- Verify the Profile name exactly matches Salesforce (case-sensitive)
- Check: `sf data query --query "SELECT Name FROM Profile" --target-org mavenprod`

### "Role not found"
- Verify the Role name exactly matches Salesforce (case-sensitive)
- Check: `sf data query --query "SELECT Name FROM UserRole" --target-org mavenprod`

### Permission sets not assigned
- Some permission sets are profile-specific and cannot be assigned separately
- Check the output JSON file for detailed error messages

## Security Notes

- ✅ Uses Salesforce CLI authentication - no credentials stored in code
- ✅ Requires authenticated Salesforce CLI session
- ⚠️ Password reset must be done manually in Salesforce UI (security best practice)

## Examples

### Provision a single user
```bash
# Create users.csv with one user
python provision_user.py --csv users.csv --org mavenprod
```

### Provision multiple users
```bash
# Create users.csv with multiple users
python provision_user.py --csv users.csv --org mavenprod
```

### Use different org
```bash
# Provision to sandbox
python provision_user.py --csv users.csv --org qa
```

## Support

For issues or questions, contact the Salesforce Admin team.

