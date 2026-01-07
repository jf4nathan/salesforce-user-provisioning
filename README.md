# Salesforce User Provisioning Script

Automated user provisioning script for Salesforce that creates users and assigns permission sets based on Profile + Role analysis. Includes optional Jira ticket creation for tracking user provisioning requests.

## Features

- ✅ Creates users with all required fields (Profile, Role, Manager, TimeZone, etc.)
- ✅ **Mimic User feature** - Copy Profile, Role, Title, and Permission Sets from an existing user
- ✅ Automatically analyzes permission sets from similar users (same Profile + Role)
- ✅ Assigns permission sets that appear in >50% of similar users (configurable threshold)
- ✅ Assigns permission set groups first, then individual permission sets
- ✅ **Jira Integration** - Automatically creates Jira tickets with user details and assigned permission sets
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
   pip install -r requirements.txt
   ```
   
   Or install manually:
   ```bash
   pip install simple-salesforce requests
   ```

## Quick Start

1. **Prepare your CSV file** (use `users_template.csv` as a template):
   **Option 1: Specify Profile and Role manually**
   ```csv
   FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
   John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York,
   ```
   
   **Option 2: Mimic an existing user (copies Profile, Role, Title, and Permission Sets)**
   ```csv
   FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
   ,,new.user@mavenclinic.com,new.user@mavenclinic.com,,,,,eddie.tang@mavenclinic.com
   ```
   
   **Note:** 
   - The script automatically parses the first name and last name from the email address using the `firstname.lastname@domain.com` format if FirstName/LastName are not provided
   - The username is automatically set to match the email address
   - **Sandbox environments**: When provisioning in a sandbox, the sandbox name is automatically appended to the username (e.g., `john.doe@mavenclinic.com` becomes `john.doe@mavenclinic.com.qa` in the "qa" sandbox)
   - **MimicUser feature**: Provide an existing user's email to automatically copy their Profile, Role, Title, and all Permission Sets

2. **Run the script**:
   ```bash
   # Without Jira tickets:
   python provision_user.py --csv users.csv --org mavenprod

   # With Jira tickets (recommended):
   python provision_user.py --csv users.csv --org mavenprod --jira-config jira_config.json
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

### With Jira Integration
```bash
# Using Jira config file
python provision_user.py --csv users.csv --org mavenprod --jira-config jira_config.json

# Or using command line arguments
python provision_user.py --csv users.csv --org mavenprod \
  --jira-url https://company.atlassian.net \
  --jira-email your.email@company.com \
  --jira-token YOUR_API_TOKEN \
  --jira-project PROJECT_KEY
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
- `Email` - User's email address (must be in `firstname.lastname@domain.com` format if FirstName/LastName not provided)
  - First name and last name are automatically parsed from the email if not provided
  - Username is automatically set to match the email address
  - **In sandbox environments**: The sandbox name is automatically appended (e.g., `john.doe@mavenclinic.com` → `john.doe@mavenclinic.com.qa`)

**Either provide Profile/Role OR MimicUser:**
- `Profile` - Salesforce profile name (e.g., "Sales", "Marketing", "Client Success") - *Required if MimicUser not provided*
- `Role` - Salesforce role name (e.g., "Sales Rep", "Marketing Manager") - *Optional if MimicUser not provided*

Optional columns:
- `FirstName` - User's first name (auto-parsed from email if not provided)
- `LastName` - User's last name (auto-parsed from email if not provided)
- `Username` - Salesforce username (auto-set to email if not provided)
- `MimicUser` - Email address of existing user to copy Profile, Role, Title, and Permission Sets from
  - If provided, Profile, Role, and Title will be copied from this user (unless explicitly overridden in CSV)
  - Permission sets will be copied directly from the mimic user (instead of analyzing similar users)
  - Example: `eddie.tang@mavenclinic.com` or `eddie.tang@mavenclinic.com.devjtang1` (for sandbox)
- `Title` - User's job title (optional if MimicUser provided)
- `ManagerEmail` - Manager's email address (for ManagerId lookup)
- `TimeZone` - Time zone (defaults to "America/New_York" if not specified)

## Jira Integration

The script can automatically create Jira tickets for each provisioned user. Tickets include:
- User details (name, email, username, title, profile, role, manager, timezone)
- Salesforce details (User ID and direct link to user record)
- **Permission Sets Assigned** - Lists all permission set groups and individual permission sets by name
- Next steps checklist

### Jira Configuration

**Option 1: JSON Config File (Recommended)**
Create a `jira_config.json` file (start from `jira_config.example.json`):
```json
{
  "jira_url": "https://company.atlassian.net",
  "email": "your.email@company.com",
  "api_token": "YOUR_API_TOKEN",
  "project_key": "PROJECT_KEY",
  "issue_type": "Task",
  "assignee_email": "assignee@company.com",
  "board_id": 123
}
```

**Default behavior (to prevent “Jira integration: DISABLED”)**

- If `jira_config.json` exists in the repo root, the scripts will **auto-load it by default**, so Jira ticket creation is enabled without needing to pass `--jira-config`.
- You can also point to a different file via `JIRA_CONFIG_PATH` (e.g., `JIRA_CONFIG_PATH=/path/to/jira_config.json`).

**Option 2: Environment Variables**
```bash
export JIRA_URL="https://company.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="YOUR_API_TOKEN"
export JIRA_PROJECT_KEY="PROJECT_KEY"
export JIRA_ASSIGNEE_EMAIL="assignee@company.com"  # Optional
export JIRA_BOARD_ID="123"  # Optional, for sprint assignment
```

**Option 3: Command Line Arguments**
See `--jira-url`, `--jira-email`, `--jira-token`, `--jira-project` options

### Getting a Jira API Token
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the token and use it in your configuration

## How It Works

1. **Confirms target environment** - Displays org details (alias, username, org ID, instance URL) and asks for confirmation before proceeding
2. **Connects to Salesforce** using your authenticated sf CLI session
3. **Analyzes similar users** - Finds all active users with the same Profile + Role combination
4. **Identifies permission sets** - Determines which permission sets/groups are assigned to >50% of similar users
5. **Creates the user** with all required fields
6. **Assigns permission sets** - Assigns permission set groups first, then individual permission sets
7. **Creates Jira ticket** (if configured) - Creates a ticket with user details, permission sets, and Salesforce links
8. **Generates results** - Saves detailed results to JSON file

### Environment Confirmation

Before provisioning users, the script will:
- Display the target org's details (alias, username, org ID, instance URL, org type)
- Show a warning if the org appears to be production
- Ask for explicit confirmation (type "yes" or "y" to proceed)
- Cancel if confirmation is not provided

This helps prevent accidental user provisioning in the wrong environment, especially production. Use `--skip-confirmation` flag to bypass this prompt (useful for automation/CI/CD).

## Gainsight CS Permission Set License Requirement

When assigning the Gainsight CS permission set (`GAINSIGHT__Gainsight_CS`) to a user via API, you **must also assign them the Gainsight package license** via API. The Gainsight CS permission set requires the Gainsight managed package license. Without it, users won't have access to Gainsight features even with the permission set assigned.

### API Implementation

When assigning the Gainsight CS permission set, also create a `UserPackageLicense` record:

```python
# After assigning permission set, also assign package license
package_license_id = '050UH00000NFYVZYA5'  # Gainsight package license ID

user_package_license = {
    'PackageLicenseId': package_license_id,
    'UserId': user_id
}

sf.UserPackageLicense.create(user_package_license)
```

### Package License Details

- **Package License ID**: `050UH00000NFYVZYA5` (18-character format)
- **Permission Set Name**: `Gainsight_CS` (API name: `GAINSIGHT__Gainsight_CS`)
- **Permission Set ID**: `0PSUH0000006LTB4A2`

### Example Workflow

1. Create user via User API
2. Assign permission set via `PermissionSetAssignment` API
3. **If permission set is Gainsight CS, also create `UserPackageLicense` record**
4. Assign other permission sets/groups as needed

### Checking License Availability

Before assigning the package license, check license availability via API:

```python
# Query PackageLicense to check available licenses
query = "SELECT Id, UsedLicenses, AllowedLicenses FROM PackageLicense WHERE Id = '050UH00000NFYVZYA5'"
result = sf.query(query)

if result['records']:
    license_info = result['records'][0]
    available = license_info['AllowedLicenses'] - license_info['UsedLicenses']
    print(f"Available Gainsight licenses: {available}")
```

**Note**: Ensure `UsedLicenses < AllowedLicenses` before assigning the license to a user.

## Output

The script generates a JSON file (`provisioning_results.json` by default) with:
- Successfully created users (with User IDs)
- Failed user creations (with error messages)
- Detailed user information
- Jira ticket information (if Jira integration is enabled)

Example output:
```json
{
  "success": [
    {
      "user": {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@mavenclinic.com",
        ...
      },
      "userId": "005UG000007VK1dYAG",
      "jira_ticket": "SFDC-946",
      "jira_ticket_url": "https://company.atlassian.net/browse/SFDC-946",
      "salesforce_user_link": "https://company.my.salesforce-setup.com/..."
    }
  ],
  "failed": []
}
```

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

### Jira ticket creation fails
- Verify your Jira API token is valid and not expired
- Check that the project key exists and you have permission to create issues
- Ensure the assignee email (if provided) exists in Jira
- Check the script output for detailed error messages

## Security Notes

- ✅ Uses Salesforce CLI authentication - no credentials stored in code
- ✅ Requires authenticated Salesforce CLI session
- ✅ Jira API tokens should be stored securely (use environment variables or config files excluded from git)
- ⚠️ Password reset must be done manually in Salesforce UI (security best practice)
- ⚠️ Never commit `jira_config.json` or other files containing API tokens to version control

## Examples

### Provision a single user
```bash
# Create users.csv with one user
python provision_user.py --csv users.csv --org mavenprod --jira-config jira_config.json
```

### Provision multiple users
```bash
# Create users.csv with multiple users
python provision_user.py --csv users.csv --org mavenprod --jira-config jira_config.json
```

### Provision to sandbox
```bash
# Provision to sandbox
python provision_user.py --csv users.csv --org qa --jira-config jira_config.json
```

### Provision without Jira
```bash
# Skip Jira ticket creation
python provision_user.py --csv users.csv --org mavenprod
```

## Support

For issues or questions, contact the Salesforce Admin team.








