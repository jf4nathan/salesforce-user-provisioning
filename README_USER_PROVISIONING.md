# Salesforce User Provisioning Script

Automated user provisioning script for Salesforce that creates users and assigns permission sets based on Profile + Role analysis.

## Features

- ✅ Creates users with all required fields (Profile, Role, Manager, TimeZone, etc.)
- ✅ **Mimic User feature** - Copy Profile, Role, Title, and Permission Sets from an existing user
- ✅ Automatically analyzes permission sets from similar users (same Profile + Role)
- ✅ Assigns permission sets that appear in >50% of similar users (configurable threshold)
- ✅ Assigns permission set groups first, then individual permission sets
- ✅ Uses Salesforce CLI (sf) for authentication - no credentials needed in code
- ✅ Generates detailed provisioning results
- ✅ **Environment confirmation prompt** - Shows org details and asks for confirmation before provisioning (prevents accidental production deployments)

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
   **Option 1: Specify Profile and Role manually**
   ```csv
   Email,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
   john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York,
   ```
   
   **Option 2: Mimic an existing user (copies Profile, Role, Title, and Permission Sets)**
   ```csv
   Email,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
   new.user@mavenclinic.com,,,,,eddie.tang@mavenclinic.com
   ```
   
   **Note:** 
   - The script automatically parses the first name and last name from the email address using the `firstname.lastname@domain.com` format
   - The username is automatically set to match the email address
   - **Sandbox environments**: When provisioning in a sandbox, the sandbox name is automatically appended to the username (e.g., `john.doe@mavenclinic.com` becomes `john.doe@mavenclinic.com.qa` in the "qa" sandbox)
   - **MimicUser feature**: Provide an existing user's email to automatically copy their Profile, Role, Title, and all Permission Sets

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

### Skip Confirmation Prompt
```bash
# Skip the org confirmation prompt (useful for automation/CI/CD)
python provision_user.py --csv users.csv --org mavenprod --skip-confirmation
```

## CSV Format

Required columns:
- `Email` - User's email address (must be in `firstname.lastname@domain.com` format)
  - First name and last name are automatically parsed from the email
  - Username is automatically set to match the email address
  - **In sandbox environments**: The sandbox name is automatically appended (e.g., `john.doe@mavenclinic.com` → `john.doe@mavenclinic.com.qa`)

**Either provide Profile/Role OR MimicUser:**
- `Profile` - Salesforce profile name (e.g., "Sales", "Marketing", "Client Success") - *Required if MimicUser not provided*
- `Role` - Salesforce role name (e.g., "Sales Rep", "Marketing Manager") - *Optional if MimicUser not provided*

Optional columns:
- `MimicUser` - Email address of existing user to copy Profile, Role, Title, and Permission Sets from
  - If provided, Profile, Role, and Title will be copied from this user (unless explicitly overridden in CSV)
  - Permission sets will be copied directly from the mimic user (instead of analyzing similar users)
  - Example: `eddie.tang@mavenclinic.com` or `eddie.tang@mavenclinic.com.devjtang1` (for sandbox)
- `Title` - User's job title (optional if MimicUser provided)
- `ManagerEmail` - Manager's email address (for ManagerId lookup)
- `TimeZone` - Time zone (defaults to "America/New_York" if not specified)

## How It Works

1. **Confirms target environment** - Displays org details (alias, username, org ID, instance URL) and asks for confirmation before proceeding
2. **Connects to Salesforce** using your authenticated sf CLI session
3. **Analyzes similar users** - Finds all active users with the same Profile + Role combination
4. **Identifies permission sets** - Determines which permission sets/groups are assigned to >50% of similar users
5. **Creates the user** with all required fields
6. **Assigns permission sets** - Assigns permission set groups first, then individual permission sets
7. **Generates results** - Saves detailed results to JSON file

### Environment Confirmation

Before provisioning users, the script will:
- Display the target org's details (alias, username, org ID, instance URL, org type)
- Show a warning if the org appears to be production
- Ask for explicit confirmation (type "yes" or "y" to proceed)
- Cancel if confirmation is not provided

This helps prevent accidental user provisioning in the wrong environment, especially production. Use `--skip-confirmation` flag to bypass this prompt (useful for automation/CI/CD).

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

