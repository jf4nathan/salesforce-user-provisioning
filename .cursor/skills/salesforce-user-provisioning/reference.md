# Script Reference

Complete documentation for all provisioning scripts, command-line arguments, and options.

## Core Scripts

### provision_user.py

Main user provisioning script. Creates Salesforce users with automatic permission set assignment.

**Location:** `scripts/core/provision_user.py`

**Required Arguments:**
- `--csv` - Path to CSV file with user data
- `--org` - Salesforce org alias (e.g., `mavenprod`)

**Optional Arguments:**
- `--threshold` - Permission set assignment threshold (0.0-1.0, default: 0.5)
- `--output` - Output file for results (default: `temp/provisioning_results.json`)
- `--skip-confirmation` - Skip org confirmation prompt
- `--jira-config` - Path to Jira config JSON (auto-detected if `jira_config.json` exists)
- `--jira-url`, `--jira-email`, `--jira-token`, `--jira-project` - Jira CLI args

**Features:**
- Analyzes similar users (same Profile + Role) to determine permission sets
- Assigns permission sets appearing in >threshold% of similar users
- MimicUser feature: Copy Profile, Role, Title, and Permission Sets from existing user
- Automatic Gainsight license assignment when Gainsight CS permission set detected
- Automatic Gainsight user provisioning for Client Success profile users
- Jira ticket creation with user details and permission sets
- Sandbox username handling (auto-appends sandbox suffix)

**Example:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --threshold 0.6
```

### deprovision_user.py

Deactivates Salesforce users and removes package license assignments.

**Location:** `scripts/core/deprovision_user.py`

**Required Arguments:**
- `--org` - Salesforce org alias
- `--names` OR `--csv` (mutually exclusive) - User names or CSV file

**Optional Arguments:**
- `--dry-run` - Preview changes without executing
- `--skip-confirmation` - Skip per-user confirmation prompts
- `--output` - Output file (default: `temp/deprovisioning_results.json`)

**What it does:**
- Removes all package license assignments (e.g., Gainsight)
- Deactivates user in Salesforce (`IsActive = false`)
- Deactivates user in Gainsight (if configured)
- Leaves permissions, profile, and role unchanged

**CSV Format:**
```csv
Name
John Doe
Jane Smith
```
OR
```csv
FirstName,LastName
John,Doe
Jane,Smith
```

**Example:**
```bash
python scripts/core/deprovision_user.py --org mavenprod --names "John Doe, Jane Smith" --dry-run
```

### reactivate_user.py

Reactivates a Salesforce user and ensures Gainsight license and user are provisioned.

**Location:** `scripts/core/reactivate_user.py`

**Required Arguments:**
- `--org` - Salesforce org alias
- `--email` OR `--first-name` + `--last-name` - User identifier

**Optional Arguments:**
- `--dry-run` - Preview changes without making them

**What it does:**
- Reactivates Salesforce user if inactive
- Assigns Gainsight package license if not already assigned
- Ensures Gainsight user exists and is active (creates if needed)
- Updates Gainsight license type to Full if needed

**Example:**
```bash
python scripts/core/reactivate_user.py --org mavenprod --email user@mavenclinic.com
```

### update_user_permissions.py

Updates existing user's Profile, Role, and Permission Sets by mimicking another user.

**Location:** `scripts/core/update_user_permissions.py`

**Required Arguments:**
- `--user-email` - Email of user to update
- `--mimic-user-email` - Email of user to mimic (copy permissions from)
- `--org` - Salesforce org alias

**Optional Arguments:**
- `--dry-run` - Preview changes without making them
- Jira args (optional) - For creating Jira tickets

**What it does:**
- Backs up current user state to JSON file
- Updates Profile and Role
- Removes all existing permission sets
- Assigns new permission sets from mimic user
- Creates Jira ticket documenting changes (if configured)

**Example:**
```bash
python scripts/core/update_user_permissions.py --user-email user@mavenclinic.com --mimic-user-email mimic@mavenclinic.com --org mavenprod --dry-run
```

## Helper Scripts

### check_manager.py

Find user by email and display Profile, Role, Title, Department.

**Location:** `scripts/helpers/check_manager.py`

**Arguments:**
- `--org` (optional, default: `mavenprod`) - Salesforce org alias
- `email` (positional, required) - Email address to search for

**Example:**
```bash
python scripts/helpers/check_manager.py --org mavenprod manager.email@mavenclinic.com
```

### check_gainsight_license.py

Check Gainsight license and permission set assignment for a user.

**Location:** `scripts/helpers/check_gainsight_license.py`

**Arguments:**
- `--org` (optional, default: `mavenprod`) - Salesforce org alias
- `email` (positional, required) - User email address

**Output:**
- User details (ID, name, email, username)
- License assignment status (assigned/not assigned)
- License availability stats
- Permission set assignment status

**Example:**
```bash
python scripts/helpers/check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

### query_client_success_users.py

Query all Client Success users grouped by Profile and Role.

**Location:** `scripts/helpers/query_client_success_users.py`

**Arguments:**
- `--org` (optional, default: `mavenprod`) - Salesforce org alias

**Output:**
- Summary of Client Success users
- Grouped by Profile and Role with counts
- User list with name, email, and title
- Most common Profile+Role combination

**Example:**
```bash
python scripts/helpers/query_client_success_users.py --org mavenprod
```

### check_vps.py

Find Vice Presidents in Client Success profile and list available Roles.

**Location:** `scripts/helpers/check_vps.py`

**Arguments:**
- `--org` (optional, default: `mavenprod`) - Salesforce org alias

**Output:**
- List of VPs with details (name, email, title, profile, role, department)
- If no VPs: list of available Roles for Client Success profile with user counts

**Example:**
```bash
python scripts/helpers/check_vps.py --org mavenprod
```

## Wrapper Scripts

### run_provision.sh

Guardrail wrapper that enforces temp/ folder usage for CSV input and JSON output.

**Location:** `scripts/run_provision.sh`

**Features:**
- Validates CSV path is under `temp/`
- Validates output path is under `temp/`
- Defaults output to `temp/provisioning_results.json`
- Passes all arguments to `provision_user.py`

**Usage:**
```bash
./scripts/run_provision.sh --csv temp/users.csv --org mavenprod
```

## CSV Format Reference

### Provisioning CSV Fields

**Required:**
- `Email` - User's email address (must be in `firstname.lastname@domain.com` format if FirstName/LastName not provided)
- `Title` - User's job title (required - ask user if not provided in request)

**Either provide Profile/Role OR MimicUser:**
- `Profile` - Salesforce profile name (required if MimicUser not provided)
- `Role` - Salesforce role name (optional if MimicUser not provided)

**Optional:**
- `FirstName` - User's first name (auto-parsed from email if not provided)
- `LastName` - User's last name (auto-parsed from email if not provided)
- `Username` - Salesforce username (auto-set to email if not provided)
- `ManagerEmail` - Manager's email address (for ManagerId lookup)
- `TimeZone` - Time zone (defaults to `America/New_York` if not specified)
- `MimicUser` - Email address of existing user to copy Profile, Role, Title, and Permission Sets from (if provided, Title can be copied from mimic user)
- `JiraKey` - If provided, updates existing Jira issue instead of creating new ticket

**CSV Template:**
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York,
```

### Deprovisioning CSV Fields

Either format is accepted:

**Format 1:**
```csv
Name
John Doe
Jane Smith
```

**Format 2:**
```csv
FirstName,LastName
John,Doe
Jane,Smith
```

## Integration Details

### Jira Integration

**Auto-detection:**
- If `jira_config.json` exists in repo root, auto-loaded
- Can also use `--jira-config` to specify path
- Falls back to CLI args or environment variables

**Configuration file** (`jira_config.json`):
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

**Environment variables:**
- `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`
- `JIRA_ASSIGNEE_EMAIL`, `JIRA_BOARD_ID` (optional)

**Ticket content:**
- User details (name, email, username, title, profile, role, manager, timezone)
- Salesforce details (User ID, direct link to user record)
- Permission Sets (all assigned Permission Set Groups and individual Permission Sets)
- Gainsight Provisioning status (if applicable)
- Next steps checklist

### Gainsight Integration

**Auto-detection:**
- If `gainsight_config.json` exists in repo root, auto-enabled
- Can also use `GAINSIGHT_CONFIG_PATH` environment variable

**Configuration file** (`gainsight_config.json`):
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

**Automatic provisioning:**
- Triggers when Salesforce profile is "Client Success"
- Creates Gainsight user with Full license type
- Assigns "client resources" group by default
- Also used during user reactivation

**Package License:**
- Package License ID: `050UH00000NFYVZYA5`
- Permission Set Name: `Gainsight_CS` (API name: `GAINSIGHT__Gainsight_CS`)
- Permission Set ID: `0PSUH0000006LTB4A2`
- Automatically assigned when Gainsight CS permission set is detected

## Advanced Options

### Permission Set Threshold

Controls which permission sets are assigned based on similar user analysis.

- Default: `0.5` (50%)
- Range: `0.0` to `1.0`
- Meaning: Assign permission sets that appear in >threshold% of similar users

**Example:**
```bash
# Assign permission sets appearing in 60%+ of similar users
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --threshold 0.6
```

### Dry Run Mode

Preview changes without making them (available for deprovisioning, reactivation, permission updates).

**Example:**
```bash
python scripts/core/deprovision_user.py --org mavenprod --names "John Doe" --dry-run
```

### Skip Confirmation

Skip interactive confirmation prompts (useful for automation/CI/CD).

**Example:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --skip-confirmation
```

## Sandbox Considerations

**Username handling:**
- Usernames automatically get sandbox suffix appended (e.g., `user@domain.com.qa`)
- Don't manually set Username field in CSV for sandboxes
- Email addresses remain unchanged (no suffix)

**MimicUser lookup:**
- Handles sandbox usernames automatically
- Provide production email, script tries both formats

**Example:**
- Production: `user@mavenclinic.com`
- Sandbox (qa): `user@mavenclinic.com.qa`
- Email remains: `user@mavenclinic.com`

## Output Files

### Provisioning Results

**Default location:** `temp/provisioning_results.json`

**Structure:**
```json
{
  "success": [
    {
      "user": {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@mavenclinic.com",
        "Username": "john.doe@mavenclinic.com",
        "Title": "Sales Rep",
        "ManagerEmail": "jane.manager@mavenclinic.com",
        "Profile": "Sales",
        "Role": "Sales Rep",
        "TimeZone": "America/New_York"
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

### Deprovisioning Results

**Default location:** `temp/deprovisioning_results.json`

**Structure:**
```json
{
  "success": [
    {
      "user": {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@mavenclinic.com"
      },
      "userId": "005UG000007VK1dYAG",
      "actions": ["removed_package_licenses", "deactivated_user"]
    }
  ],
  "failed": []
}
```

### User Backup Files

Created by `update_user_permissions.py` before making changes.

**Location:** `temp/user_backup_*.json`

**Contains:** Complete user state (Profile, Role, Permission Sets) before update.
