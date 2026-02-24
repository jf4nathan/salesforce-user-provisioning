# Workflow Examples

Concrete examples of common provisioning workflows.

## Example 1: Basic Provisioning with Manager

**Scenario:** Provision a new Sales user with a manager.

**Step 1: Confirm Title**
If the user request doesn't include a title, ask: "What is the job title for this user?"

**Step 2: Verify manager exists**
```bash
python scripts/helpers/check_manager.py --org mavenprod jane.manager@mavenclinic.com
```

**Output:**
```
Found user: Jane Manager
------------------------------------------------------------
Name: Jane Manager
Email: jane.manager@mavenclinic.com
Title: Sales Manager
Profile: Sales
Role: Sales Lead
Department: Sales
```

**Step 3: Create CSV file** (`temp/provision_john_doe.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York
```

**Step 3: Run provisioning**
```bash
./scripts/run_provision.sh --csv temp/provision_john_doe.csv --org mavenprod
```

**Step 5: Verify results**
Check `temp/provisioning_results.json`:
```json
{
  "success": [
    {
      "user": {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@mavenclinic.com",
        "Username": "john.doe@mavenclinic.com",
        "Profile": "Sales",
        "Role": "Sales Rep",
        "ManagerEmail": "jane.manager@mavenclinic.com"
      },
      "userId": "005UG000007VK1dYAG",
      "jira_ticket": "SFDC-946"
    }
  ],
  "failed": []
}
```

**Step 6: Reset password manually in Salesforce UI**

---

## Example 1a: Missing Title (Ask User)

**Scenario:** User requests provisioning but doesn't provide a title.

**User Request:** "Provision a user for John Doe, role Sales Rep, profile Sales, manager Jane Manager."

**Agent Response:** "I need the job title for John Doe to complete the provisioning. What is their job title?"

**After User Provides Title:** Proceed with Example 1 workflow.

**Note:** Title is required even when using MimicUser (unless MimicUser will copy the title). Always ask if not provided.

---

## Example 2: Mimic User Workflow

**Scenario:** Create a new user with the same permissions as an existing user.

**Step 1: Verify mimic user exists**
```bash
python scripts/helpers/check_manager.py --org mavenprod eddie.tang@mavenclinic.com
```

**Step 2: Create CSV file** (`temp/provision_new_user.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,MimicUser
,,new.user@mavenclinic.com,new.user@mavenclinic.com,,,,,eddie.tang@mavenclinic.com
```

**Note:** FirstName, LastName, Title, Profile, and Role are left empty - they will be copied from the mimic user.

**Step 3: Run provisioning**
```bash
./scripts/run_provision.sh --csv temp/provision_new_user.csv --org mavenprod
```

**Result:** New user gets Profile, Role, Title, and all Permission Sets from `eddie.tang@mavenclinic.com`.

---

## Example 3: Manager Lookup with Name Variations

**Scenario:** Manager email format is uncertain (Steph vs Stephanie).

**Step 1: Try email lookup**
```bash
python scripts/helpers/check_manager.py --org mavenprod steph.dagostino@mavenclinic.com
```

**Output:** User not found

**Step 2: Query by name with variations**
```bash
sf data query --query "SELECT Id, FirstName, LastName, Email FROM User WHERE (FirstName LIKE 'Steph%' OR FirstName = 'Stephanie') AND LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod
```

**Output:**
```json
{
  "records": [
    {
      "Id": "0051Q00000XLKaOQAX",
      "FirstName": "Stephanie",
      "LastName": "Dagostino",
      "Email": "stephanie.dagostino@mavenclinic.com"
    }
  ]
}
```

**Step 3: Update CSV with correct email**
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,stephanie.dagostino@mavenclinic.com,Sales,Sales Rep,America/New_York
```

**Step 4: Proceed with provisioning**

---

## Example 4: Client Success Provisioning

**Scenario:** Provision a new Client Success user (triggers Gainsight provisioning).

**Step 1: Confirm Title**
If the user request doesn't include a title, ask: "What is the job title for this user?"

**Step 2: Query similar users**
```bash
python scripts/helpers/query_client_success_users.py --org mavenprod
```

**Output:**
```
Client Success Users Summary:
------------------------------------------------------------
Profile: Client Success, Role: Client Success Rep (41 users)
  - Most common combination
  - Used by: Associates, Analysts, individual contributors

Profile: Client Success, Role: Client Success Lead (10 users)
  - Used by: Directors, Managers, VPs

Profile: Client Success, Role: Operations (7 users)
  - Used by: operations and delivery roles
```

**Step 3: Determine Profile/Role**
Based on title "Client Success Associate", use:
- Profile: `Client Success`
- Role: `Client Success Rep`

**Step 4: Verify manager**
```bash
python scripts/helpers/check_manager.py --org mavenprod manager.email@mavenclinic.com
```

**Step 5: Create CSV file** (`temp/provision_cs_user.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
Jane,Smith,jane.smith@mavenclinic.com,jane.smith@mavenclinic.com,Client Success Associate,manager.email@mavenclinic.com,Client Success,Client Success Rep,America/New_York
```

**Step 6: Run provisioning**
```bash
./scripts/run_provision.sh --csv temp/provision_cs_user.csv --org mavenprod
```

**Result:**
- Salesforce user created
- Gainsight user automatically provisioned (Full license, client resources group)
- Gainsight package license assigned
- Gainsight CS permission set assigned

**Step 7: Verify Gainsight license**
```bash
python scripts/helpers/check_gainsight_license.py --org mavenprod jane.smith@mavenclinic.com
```

**Output:**
```
Found user: Jane Smith (jane.smith@mavenclinic.com)
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

---

## Example 5: VP-Level User Provisioning

**Scenario:** Provision a Vice President in Client Success.

**Step 1: Check VP-level users**
```bash
python scripts/helpers/check_vps.py --org mavenprod
```

**Output:**
```
Found 3 VPs in Client Success:
------------------------------------------------------------
1. Doreen Bortel (doreen.bortel@mavenclinic.com)
   Title: Vice President, Client Success
   Profile: Client Success
   Role: Client Success Lead

2. Solongo Guzman (solongo.guzman@mavenclinic.com)
   Title: Vice President Client Success
   Profile: Client Success
   Role: Client Success Lead
```

**Step 2: Determine Profile/Role**
- Profile: `Client Success`
- Role: `Client Success Lead` (used by VPs)

**Step 3: Create CSV file** (`temp/provision_vp.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
New,VP,new.vp@mavenclinic.com,new.vp@mavenclinic.com,Vice President Client Success,doreen.bortel@mavenclinic.com,Client Success,Client Success Lead,America/New_York
```

**Step 4: Run provisioning**
```bash
./scripts/run_provision.sh --csv temp/provision_vp.csv --org mavenprod
```

---

## Example 6: Sandbox Provisioning

**Scenario:** Provision a user in a sandbox environment.

**Important:** Username automatically gets sandbox suffix, email remains unchanged.

**Step 1: Create CSV file** (`temp/provision_sandbox.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone
Test,User,test.user@mavenclinic.com,test.user@mavenclinic.com,Test Role,,Sales,Sales Rep,America/New_York
```

**Note:** Don't manually add `.qa` suffix to Username - script handles it automatically.

**Step 2: Run provisioning in sandbox**
```bash
./scripts/run_provision.sh --csv temp/provision_sandbox.csv --org qa
```

**Result:**
- Email: `test.user@mavenclinic.com` (unchanged)
- Username: `test.user@mavenclinic.com.qa` (suffix added automatically)

---

## Example 7: Deprovisioning Multiple Users

**Scenario:** Deactivate multiple users from a CSV file.

**Step 1: Create deprovisioning CSV** (`temp/deprovision_list.csv`)
```csv
FirstName,LastName
John,Doe
Jane,Smith
```

**Step 2: Dry run (preview changes)**
```bash
python scripts/core/deprovision_user.py --org mavenprod --csv temp/deprovision_list.csv --dry-run
```

**Step 3: Execute deprovisioning**
```bash
python scripts/core/deprovision_user.py --org mavenprod --csv temp/deprovision_list.csv
```

**Result:**
- Package licenses removed
- Users deactivated in Salesforce
- Users deactivated in Gainsight (if configured)
- Results saved to `temp/deprovisioning_results.json`

---

## Example 8: Reactivating a User

**Scenario:** Reactivate a previously deactivated user.

**Step 1: Reactivate by email**
```bash
python scripts/core/reactivate_user.py --org mavenprod --email user@mavenclinic.com
```

**Or by name:**
```bash
python scripts/core/reactivate_user.py --org mavenprod --first-name "John" --last-name "Doe"
```

**Result:**
- Salesforce user reactivated
- Gainsight license assigned (if not already assigned)
- Gainsight user created/activated (if Client Success profile)

---

## Example 9: Updating User Permissions

**Scenario:** Update an existing user's permissions to match another user.

**Step 1: Dry run (preview changes)**
```bash
python scripts/core/update_user_permissions.py --user-email user@mavenclinic.com --mimic-user-email mimic@mavenclinic.com --org mavenprod --dry-run
```

**Step 2: Execute update**
```bash
python scripts/core/update_user_permissions.py --user-email user@mavenclinic.com --mimic-user-email mimic@mavenclinic.com --org mavenprod
```

**Result:**
- Current user state backed up to `temp/user_backup_*.json`
- Profile and Role updated
- All existing permission sets removed
- New permission sets assigned from mimic user
- Jira ticket created (if configured)

---

## Example 10: Custom Permission Set Threshold

**Scenario:** Use stricter threshold (60% instead of 50%) for permission set assignment.

**Create CSV and run:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod --threshold 0.6
```

**Result:** Only permission sets appearing in 60%+ of similar users are assigned (more selective than default 50%).

---

## Example 11: Updating Existing Jira Ticket

**Scenario:** Add provisioning details to an existing Jira ticket instead of creating a new one.

**Step 1: Create CSV with JiraKey** (`temp/provision_with_jira.csv`)
```csv
FirstName,LastName,Email,Username,Title,ManagerEmail,Profile,Role,TimeZone,JiraKey
John,Doe,john.doe@mavenclinic.com,john.doe@mavenclinic.com,Sales Rep,jane.manager@mavenclinic.com,Sales,Sales Rep,America/New_York,SFDC-1001
```

**Step 2: Run provisioning**
```bash
./scripts/run_provision.sh --csv temp/provision_with_jira.csv --org mavenprod
```

**Result:** Jira ticket SFDC-1001 is updated with a comment containing provisioning details (instead of creating a new ticket).

---

## Example 12: Provisioning Without Jira

**Scenario:** Provision users without creating Jira tickets.

**Simply run without Jira config:**
```bash
python scripts/core/provision_user.py --csv temp/users.csv --org mavenprod
```

**Or ensure `jira_config.json` doesn't exist in repo root** (Jira integration auto-disabled if config not found).

---

## Common Patterns

### Pattern: Query Before Provisioning

Always verify before provisioning:
1. Manager email: `check_manager.py`
2. Mimic user: `check_manager.py`
3. Similar users: `query_client_success_users.py` or `check_vps.py`

### Pattern: Handle Name Variations

When manager email lookup fails:
1. Try `check_manager.py` with expected email
2. Query by name with LIKE patterns: `FirstName LIKE 'Steph%' OR FirstName = 'Stephanie'`
3. Update CSV with correct email
4. Proceed with provisioning

### Pattern: Client Success Workflow

For Client Success users:
1. Query similar users to determine Profile/Role
2. Provision user (Gainsight auto-provisioned)
3. Verify Gainsight license: `check_gainsight_license.py`
4. Reset password manually

### Pattern: Sandbox Provisioning

For sandbox environments:
1. Use production email format in CSV
2. Don't manually add sandbox suffix to Username
3. Script automatically appends suffix (e.g., `.qa`)
4. Email remains unchanged
