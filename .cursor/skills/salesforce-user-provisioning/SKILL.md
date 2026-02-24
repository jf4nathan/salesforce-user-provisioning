---
name: salesforce-user-provisioning
description: Guides through Salesforce user provisioning workflows including user creation, manager verification, permission set assignment, and Gainsight integration. Use when explicitly asked to provision users, check managers, verify licenses, or manage Salesforce user accounts.
---

# Salesforce User Provisioning

## Quick Start

When provisioning a Salesforce user, follow this workflow:

1. **Pre-provisioning**: Verify manager and determine Profile/Role
2. **Create CSV**: Prepare user data in `temp/` folder
3. **Provision**: Run provisioning script
4. **Verify**: Check results and Gainsight license (if applicable)
5. **Reset password**: Manually in Salesforce UI

## Pre-Provisioning Checklist

Before creating a CSV file, verify:

- [ ] **Title provided**: If user request doesn't include a title, ask the user to provide it before proceeding
- [ ] **Manager email exists**: Use `check_manager.py` to verify manager email
- [ ] **Mimic user exists** (if using MimicUser): Verify mimic user email
- [ ] **Profile and Role determined**: Query similar users or use MimicUser feature
- [ ] **Email formats verified**: Query Salesforce for exact email addresses (don't assume formats)

### Verify Manager Email

```bash
python scripts/helpers/check_manager.py --org mavenprod manager.email@mavenclinic.com
```

**If email lookup fails**, query by name with variations:

```bash
sf data query --query "SELECT Id, FirstName, LastName, Email FROM User WHERE (FirstName LIKE 'Steph%' OR FirstName = 'Stephanie') AND LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod
```

### Determine Profile and Role

**Option 1: Query similar users**
```bash
python scripts/helpers/query_client_success_users.py --org mavenprod
```

**Option 2: Check VP-level users**
```bash
python scripts/helpers/check_vps.py --org mavenprod
```

**Option 3: Use MimicUser** - Copy Profile, Role, Title, and Permission Sets from existing user

## Provisioning Workflow

### Step 1: Create CSV File

Create CSV file in `temp/` folder using `templates/users_template.csv` as reference.

**Important:** If the user request doesn't include a Title, ask the user to provide it before creating the CSV file.

**Required fields:**
- `Email` - User's email address (required)
- `Profile` - Salesforce profile name (required unless MimicUser provided)
- `Role` - Salesforce role name (optional unless MimicUser provided)
- `Title` - Job title (required - ask user if not provided)

**Optional fields:**
- `FirstName`, `LastName` - Auto-parsed from email if not provided
- `Username` - Auto-set to email if not provided
- `ManagerEmail` - Manager's email address
- `TimeZone` - Defaults to `America/New_York` if not specified
- `MimicUser` - Email of existing user to copy from (if provided, Title can be copied from mimic user)
- `JiraKey` - Existing Jira issue key to update (instead of creating new ticket)

**CSV Format:**
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York,
```

**MimicUser Example:**
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
,,new.user@mavenclinic.com,new.user@mavenclinic.com,,,,,eddie.tang@mavenclinic.com
```

### Step 2: Run Provisioning

**Using guardrail wrapper (recommended):**
```bash
./scripts/run_provision.sh --csv temp/users.csv --org mavenprod
```

**Direct Python script:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --output temp/provisioning_results.json
```

**With custom permission set threshold:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --threshold 0.6
```

**Skip confirmation prompt (for automation):**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --skip-confirmation
```

### Step 3: Verify Results

Check the provisioning results JSON file:
- Review `success` array for created users
- Check `failed` array for any errors
- Verify User IDs and Jira ticket URLs
- **Jira tickets**: When `success_status` is set in `jira_config.json` (e.g., `"Shipped"`), tickets are automatically transitioned on success

### Step 4: Verify Gainsight License (Client Success users)

```bash
python scripts/helpers/check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

### Step 5: Reset Password

Manually reset password in Salesforce UI:
- Setup > Users > Users
- Find the newly created user
- Click dropdown → Reset Password
- Check "Generate new password and notify user immediately"

## Helper Scripts

### check_manager.py

Find user by email and display Profile, Role, Title, Department.

```bash
python scripts/helpers/check_manager.py --org mavenprod user.email@mavenclinic.com
```

**Use when:**
- Verifying manager email before provisioning
- Verifying mimic user exists
- Confirming user email formats

### check_gainsight_license.py

Verify Gainsight package license and permission set assignment.

```bash
python scripts/helpers/check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

**Use when:**
- Post-provisioning verification for Client Success users
- Troubleshooting missing Gainsight access
- Checking license availability

### query_client_success_users.py

Query all Client Success users grouped by Profile and Role.

```bash
python scripts/helpers/query_client_success_users.py --org mavenprod
```

**Use when:**
- Determining Profile/Role for new Client Success users
- Finding common configurations
- Analyzing existing user patterns

### check_vps.py

Find Vice Presidents in Client Success profile.

```bash
python scripts/helpers/check_vps.py --org mavenprod
```

**Use when:**
- Finding VP-level managers
- Discovering available Roles for Client Success profile

## Common Workflows

### Standard Provisioning with Manager

1. **Confirm Title**: If not provided in user request, ask user for the job title
2. Verify manager: `check_manager.py`
3. Create CSV with Title, Profile, Role, ManagerEmail
4. Run provisioning: `./scripts/run_provision.sh --csv temp/users.csv --org mavenprod`
5. Verify results JSON
6. Reset password manually

### Mimic User Workflow

1. Verify mimic user: `check_manager.py`
2. Create CSV with MimicUser field (leave Profile/Role empty)
3. Run provisioning (permission sets copied from mimic user)
4. Verify results

### Client Success Provisioning

1. **Confirm Title**: If not provided in user request, ask user for the job title
2. Query similar users: `query_client_success_users.py`
3. Determine Profile/Role from common patterns
4. Create CSV with Title, Profile: "Client Success", Role
5. Run provisioning (Gainsight user auto-provisioned)
6. Verify Gainsight license: `check_gainsight_license.py`
7. Reset password

### Manager Lookup with Name Variations

1. Try email lookup: `check_manager.py`
2. If fails, query by name with LIKE patterns:
   ```bash
   sf data query --query "SELECT Id, FirstName, LastName, Email FROM User WHERE (FirstName LIKE 'Steph%' OR FirstName = 'Stephanie') AND LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod
   ```
3. Update CSV with correct email
4. Proceed with provisioning

## Troubleshooting

### Profile/Role Not Found

- Verify exact names match Salesforce (case-sensitive)
- Query available Profiles: `sf data query --query "SELECT Name FROM Profile" --target-org mavenprod`
- Query available Roles: `sf data query --query "SELECT Name FROM UserRole" --target-org mavenprod`

### Manager Not Assigned

- Verify manager email exists: `check_manager.py`
- Check provisioning results JSON for errors
- Manually update manager in Salesforce UI if needed

### Permission Sets Not Assigned

- Check results JSON for detailed error messages
- Some permission sets are profile-specific and cannot be assigned separately
- Verify permission set names match exactly

### Gainsight License Not Assigned

- Verify Gainsight CS permission set was assigned
- Check license availability: `check_gainsight_license.py`
- Ensure licenses are available (UsedLicenses < AllowedLicenses)

### Sandbox Username Issues

- Usernames automatically get sandbox suffix appended (e.g., `.qa`)
- Don't manually set Username field in CSV for sandboxes
- Email addresses remain unchanged (no suffix)

## Important Notes

- **Jira ticket status** - Add `"success_status": "Shipped"` to `jira_config.json` to auto-transition tickets on successful provisioning
- **Title is required** - If not provided in user request, ask the user to provide it before proceeding
- **All temp files must be in `temp/` folder** (CSV files, results JSON, backups)
- **Never assume email formats** - query Salesforce for exact addresses
- **Verify manager/mimic user emails** before provisioning
- **Check provisioning results JSON** for detailed error messages
- **Sandbox usernames** automatically get org suffix appended
- **Password reset** must be done manually in Salesforce UI

## Additional Resources

- For complete script reference and options, see [reference.md](reference.md)
- For detailed workflow examples, see [examples.md](examples.md)
