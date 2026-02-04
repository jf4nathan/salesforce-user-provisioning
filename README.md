# Salesforce User Provisioning Script

User provisioning script for Salesforce that creates users and assigns permission sets based on Profile + Role analysis. Includes optional Jira ticket creation for tracking user provisioning requests.

## Features

- ✅ Creates users with all required fields (Profile, Role, Manager, TimeZone, etc.)
- ✅ **Mimic User feature** - Copy Profile, Role, Title, and Permission Sets from an existing user
- ✅ Automatically analyzes permission sets from similar users (same Profile + Role)
- ✅ Assigns permission sets that appear in >50% of similar users (configurable threshold)
- ✅ Assigns permission set groups first, then individual permission sets
- ✅ **Automatic Gainsight License Assignment** - Automatically assigns Gainsight package license when Gainsight CS permission set is detected
- ✅ **Gainsight User Provisioning** - Automatically creates Gainsight users for Client Success profile (with Full license and client resources group)
- ✅ **Jira Integration** - Automatically creates Jira tickets with user details and assigned permission sets
- ✅ Uses Salesforce CLI (sf) for authentication - no credentials needed in code
- ✅ Generates detailed provisioning results
- ✅ **Environment confirmation prompt** - Shows org details and asks for confirmation before provisioning (prevents accidental production deployments)
- ✅ **Helper Scripts** - Query existing users, check managers, verify licenses before/after provisioning

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

### Step 1: Determine Profile and Role (Best Practice)

Before provisioning, it's recommended to check existing users with similar titles/departments to determine the correct Profile and Role. Use the helper scripts provided:

```bash
# Query users in a specific department/profile
python query_client_success_users.py --org mavenprod

# Check a manager's Profile and Role
python check_manager.py --org mavenprod manager.email@mavenclinic.com

# Check for VP-level users
python check_vps.py --org mavenprod
```

**Best Practice Workflow:**
1. Query existing users in the same department/title to see what Profile and Role they use
2. Check the manager's Profile and Role (may differ from the user's department)
3. Use the most common Profile+Role combination for similar positions
4. If unsure, use the **MimicUser** feature to copy from a similar user

**Example:** For a "Vice President, Client Success":
- Query Client Success users to see available Roles
- Most common: `Profile: Client Success, Role: Client Success Lead` (used by Directors/Managers)
- Alternative: Use MimicUser to copy from another VP or Director

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
- `JiraKey` - If provided, the script will **update this existing Jira issue** by adding a comment with the provisioning details (instead of creating a new Jira ticket)

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

## Gainsight Integration

The script automatically provisions users in Gainsight when the Salesforce profile is **Client Success**. This creates a corresponding Gainsight user with:
- **License Type**: Full
- **Permission Bundle**: client resources

### Gainsight Configuration

Create a `gainsight_config.json` file (start from `gainsight_config.example.json`):

```json
{
  "tenant_url": "https://yourcompany.us2.gainsightcloud.com",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "default_license_type": "Full",
  "default_groups": [],
  "default_roles": []
}
```

**Authentication**: Uses M2M OAuth (Machine-to-Machine). Generate credentials in Gainsight:
1. Go to Administration > Connectors 2.0
2. Create Connection > Gainsight API
3. Select **OAuth** as Authentication Type
4. Click "Generate OAuth Credentials"
5. Copy the Client ID and Client Secret

**Default behavior**:
- If `gainsight_config.json` exists in the repo root, Gainsight integration is **auto-enabled**
- You can also point to a different file via `GAINSIGHT_CONFIG_PATH` environment variable

### Gainsight Client (Standalone)

The `gainsight_client.py` script can also be used independently for Gainsight user management:

```bash
# Search for a user
python gainsight_client.py search --email user@company.com

# Create a user
python gainsight_client.py create --email new.user@company.com --title "CSM"

# Create user mimicking another user's settings
python gainsight_client.py create --email new.user@company.com --mimic existing.user@company.com

# List all groups
python gainsight_client.py list-groups

# Add user to a group
python gainsight_client.py add-to-group --user-id <ID> --group-name "Support"

# Deactivate a user
python gainsight_client.py deactivate --email user@company.com
```

## How It Works

1. **Confirms target environment** - Displays org details (alias, username, org ID, instance URL) and asks for confirmation before proceeding
2. **Connects to Salesforce** using your authenticated sf CLI session
3. **Analyzes similar users** - Finds all active users with the same Profile + Role combination
4. **Identifies permission sets** - Determines which permission sets/groups are assigned to >50% of similar users
5. **Creates the user** with all required fields
6. **Assigns permission sets** - Assigns permission set groups first, then individual permission sets
7. **Creates Jira ticket** (if configured) - Creates a ticket with user details, permission sets, and Salesforce links
8. **Provisions Gainsight user** (if Profile is Client Success) - Creates user in Gainsight with Full license and client resources group
9. **Generates results** - Saves detailed results to JSON file

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

### Automatic License Assignment

The provisioning script **automatically assigns the Gainsight package license** when it detects that the Gainsight CS permission set has been assigned. This happens during the permission set assignment process - no manual intervention required.

### Verifying Gainsight License Assignment

After provisioning, verify the Gainsight license was assigned correctly:

```bash
python check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

This script will show:
- Whether the Gainsight package license is assigned
- License assignment ID
- Gainsight CS permission set assignment status
- Current license availability (total, used, available)

**Example Output:**
```
Found user: Solongo Guzman (solongo.guzman@mavenclinic.com)
User ID: 005UG000008E4ojYAC
------------------------------------------------------------
[SUCCESS] Gainsight license IS assigned
  License Assignment ID: 051UG00000ehdn6YAA
  Namespace: GAINSIGHT

------------------------------------------------------------
Gainsight License Availability:
  Total Licenses: 135
  Used Licenses: 134
  Available Licenses: 1
  Namespace: GAINSIGHT

------------------------------------------------------------
Gainsight CS Permission Set:
[SUCCESS] Gainsight CS Permission Set IS assigned
  Permission Set: Gainsight CS (Gainsight_CS)
```

## Helper Scripts

The repository includes several helper scripts to assist with user provisioning:

### `query_client_success_users.py`

Queries all users in Client Success (by Profile, Title, or Department) and groups them by Profile and Role to help determine the correct configuration.

**Usage:**
```bash
python query_client_success_users.py --org mavenprod
```

**Output:** Shows all Client Success users grouped by Profile+Role combination, making it easy to see what roles are used for different positions.

### `check_manager.py`

Finds a user by email and displays their Profile, Role, Title, and Department. Useful for verifying manager information before provisioning.

**Usage:**
```bash
python check_manager.py --org mavenprod manager.email@mavenclinic.com
```

### `check_vps.py`

Searches for Vice Presidents in a specific profile to see what roles they use. Helps determine appropriate roles for VP-level positions.

**Usage:**
```bash
python check_vps.py --org mavenprod
```

### `check_gainsight_license.py`

Verifies that a user has the Gainsight package license and Gainsight CS permission set assigned correctly. Also shows license availability.

**Usage:**
```bash
python check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

### `gainsight_client.py`

Standalone Gainsight SCIM API client for user provisioning and permission management. Can create users, search users, manage group memberships, and deactivate users.

**Usage:**
```bash
# Search for a user
python gainsight_client.py search --email user@company.com

# Create a user with specific settings
python gainsight_client.py create --email new.user@company.com --license-type Full --groups "client resources"

# List all groups
python gainsight_client.py list-groups

# Deactivate a user
python gainsight_client.py deactivate --email user@company.com
```

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
- Some permission sets may require specific licenses (e.g., CampaignInfluence2 requires Marketing User license)

### Gainsight license not assigned
- Verify the Gainsight CS permission set was assigned successfully
- Check license availability: `python check_gainsight_license.py --org mavenprod user.email@mavenclinic.com`
- The script automatically assigns the license when Gainsight CS permission set is detected, but you can verify manually
- If license assignment failed, check if licenses are available (UsedLicenses < AllowedLicenses)

### Jira ticket creation fails
- Verify your Jira API token is valid and not expired
- Check that the project key exists and you have permission to create issues
- Ensure the assignee email (if provided) exists in Jira
- Check the script output for detailed error messages

### Gainsight user provisioning fails
- Verify your Gainsight M2M OAuth credentials are valid (Client ID and Client Secret)
- Check that the "client resources" group exists in Gainsight
- Ensure the tenant URL is correct (e.g., `https://yourcompany.us2.gainsightcloud.com`)
- Gainsight provisioning only triggers for **Client Success** profile users
- Check the script output for detailed error messages

## Security Notes

- ✅ Uses Salesforce CLI authentication - no credentials stored in code
- ✅ Requires authenticated Salesforce CLI session
- ✅ Jira and Gainsight API tokens should be stored securely (use environment variables or config files excluded from git)
- ⚠️ Password reset must be done manually in Salesforce UI (security best practice)
- ⚠️ Never commit `jira_config.json` or `gainsight_config.json` or other files containing API tokens to version control

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

### Complete Workflow Example

Here's a complete example workflow for provisioning a new user:

**Step 1: Research existing users**
```bash
# Query users in the same department
python query_client_success_users.py --org mavenprod

# Check manager's configuration
python check_manager.py --org mavenprod doreen.bortel@mavenclinic.com
```

**Step 2: Create CSV file**
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
Solongo,Guzman,solongo.guzman@mavenclinic.com,solongo.guzman@mavenclinic.com,Vice President Client Success,doreen.bortel@mavenclinic.com,Client Success,Client Success Lead,America/New_York
```

**Step 3: Provision user**
```bash
python provision_user.py --csv solongo_guzman.csv --org mavenprod
```

**Step 4: Verify Gainsight license (if applicable)**
```bash
python check_gainsight_license.py --org mavenprod solongo.guzman@mavenclinic.com
```

**Step 5: Reset password manually in Salesforce UI**

## Common Profile and Role Combinations

Based on analysis of existing users, here are common Profile and Role combinations:

### Client Success
- **Profile**: `Client Success`
- **Roles**:
  - `Client Success Lead` - Used by Directors, Managers, VPs (10 users)
  - `Client Success Rep` - Used by individual contributors, Associates, Analysts (41 users)
  - `Operations` - Used by operations and delivery roles (7 users)

### Sales
- **Profile**: `Sales`
- **Roles**: `Sales Lead`, `Sales Rep`, etc.

### Marketing
- **Profile**: `Marketing`
- **Roles**: `Marketing Manager`, etc.

**Note**: Always verify Profile and Role names match exactly (case-sensitive) before provisioning. Use the helper scripts to query existing users for reference.

## Support

For issues or questions, contact the Salesforce Admin team.








