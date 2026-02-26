# Salesforce User Provisioning Rules

## Temporary Files

**All temporary files must be created in the `temp/` folder.**

This includes:
- User provisioning CSV files (e.g., `temp/charita_adla.csv`)
- Provisioning results JSON files (e.g., `temp/provisioning_results.json`)
- User backup JSON files (e.g., `temp/user_backup_*.json`)
- Any other working/scratch files

The `temp/` folder is gitignored and will not be committed to version control.

**Example**:
```bash
# Create CSV in temp folder
# temp/new_user.csv

# Run provisioning with temp file
python scripts/core/provision_user.py --csv temp/new_user.csv --org mavenprod --output temp/results.json
```

## PowerShell Command Syntax

**Issue**: PowerShell does not support `&&` as a command separator like bash does.

**Solution**: 
- Use semicolon (`;`) to chain commands in PowerShell: `cd path; python script.py`
- Or use separate commands: `cd path` then `python script.py`
- For conditional execution, use `; if ($?) { ... }` or separate `if` statements

**Example**:
```powershell
# ❌ Wrong (bash syntax)
cd path && python script.py

# ✅ Correct (PowerShell syntax)
cd path; python script.py
```

**Pipe characters in `python -c`**: Pipe (`|`) inside Python f-strings or print statements gets misinterpreted by PowerShell when passed via `python -c "..."`. For anything non-trivial, write a small `.py` script in `temp/` and run it instead.

## Manager Email Verification

**Issue**: Manager lookup may fail silently if the email format doesn't match exactly. Common scenarios:
- Name variations: `steph.dagostino@mavenclinic.com` vs `stephanie.dagostino@mavenclinic.com`
- Maiden names: Email contains maiden name but display name shows married name
- Different email formats: `firstname.lastname` vs `firstinitial.lastname` vs other patterns

**Best Practice**:
1. **First attempt**: Try to verify manager email using `scripts/helpers/check_manager.py`:
   ```bash
   python scripts/helpers/check_manager.py --org mavenprod manager.email@mavenclinic.com
   ```

2. **If email lookup fails**: Query Salesforce by manager name instead:
   ```bash
   # Query by first and last name (handles name variations)
   sf data query --query "SELECT Id, FirstName, LastName, Email, Title FROM User WHERE (FirstName LIKE 'Steph%' OR FirstName LIKE 'Stephanie%') AND LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod
   
   # Or query by last name only if first name is uncertain
   sf data query --query "SELECT Id, FirstName, LastName, Email, Title FROM User WHERE LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod
   ```

3. **Handle name variations**: When querying, use `LIKE` patterns to handle:
   - Short forms: `Steph` vs `Stephanie`
   - Nicknames: `Bob` vs `Robert`
   - Common variations: `Mike` vs `Michael`, `Bill` vs `William`

4. **Update CSV with correct email**: Once you find the correct email address, update the CSV file before provisioning

5. **If manager still not found**: The user will be created but without a manager assigned. You can manually update the manager in Salesforce after provisioning.

**Example Workflow**:
```bash
# Step 1: Try email lookup
python scripts/helpers/check_manager.py --org mavenprod steph.dagostino@mavenclinic.com

# Step 2: If that fails, query by name (handles Steph/Stephanie variations)
sf data query --query "SELECT Id, FirstName, LastName, Email FROM User WHERE (FirstName LIKE 'Steph%' OR FirstName = 'Stephanie') AND LastName = 'Dagostino' AND IsActive = true" --target-org mavenprod

# Step 3: Use the correct email found in the query results
# Update CSV file with the correct ManagerEmail
# Then proceed with provisioning
```

## Email Format Assumptions

**Issue**: Assuming email formats based on name patterns (e.g., `firstname.lastname@domain.com`) may not always be correct.

**Best Practice**:
- Query Salesforce to find exact email addresses rather than assuming formats
- Use helper scripts like `scripts/helpers/query_client_success_users.py` or `scripts/helpers/check_manager.py` to verify emails
- When creating CSV files, verify all email addresses (user, manager, mimic user) exist in Salesforce first

## User Provisioning Workflow

**Recommended Steps**:
1. **Verify mimic user exists**: Check that the MimicUser email exists and has the desired permissions
   - Use `scripts/helpers/check_manager.py` or query Salesforce if email format is uncertain
2. **Verify manager exists**: 
   - **First**: Try `scripts/helpers/check_manager.py` with the expected email
   - **If email lookup fails**: Query Salesforce by manager name (see Manager Email Verification section)
   - Handle name variations (Steph/Stephanie, maiden names, etc.)
   - Update CSV with the correct manager email once found
3. **Create CSV file**: Use verified email addresses for all fields
4. **Run provisioning script**: Execute `scripts/core/provision_user.py` with appropriate org alias
5. **Verify results**: Check the provisioning results JSON and verify user was created correctly
   - If manager wasn't assigned, manually update in Salesforce UI
6. **Reset password**: Manually reset password in Salesforce UI

## Environment Confirmation and Production Safety

Before any provisioning/deprovisioning action:
- Confirm target org alias and org details before execution
- Require explicit confirmation for production-like orgs unless automation intentionally uses `--skip-confirmation`
- Never deploy or perform irreversible production changes without explicit user instruction
- Prefer dry-run/review steps first when available (`scripts/core/deprovision_user.py --dry-run`)

## Post-Gainsight Provisioning Verification

After creating a Gainsight user (during provisioning or reactivation), **remind the user** to verify:
- **GS Role** is set to **CSM** on the user record
- **Permission Bundle** "Client Resources" is assigned

Use the Gainsight client search to check the created user's attributes, or ask the user to verify in the Gainsight UI.

## Error Handling

**When provisioning fails**:
- Check the `temp/provisioning_results.json` file (or your chosen `--output` path) for detailed error messages
- Verify all email addresses are correct and users exist in Salesforce
- Ensure Profile and Role names match exactly (case-sensitive)
- Check that permission sets can be assigned (some are profile-specific)

## Sandbox Considerations

**Critical**: When provisioning in sandbox environments:
- Usernames **must** have the sandbox name appended (e.g., `user@domain.com.qa`). The script enforces this automatically — never create a sandbox user without the org suffix.
- Do **not** set `Username` in the CSV to the bare email when targeting a sandbox. The script will append the suffix, but if you hardcode a username, it will still be corrected.
- Email addresses remain the same (no suffix).
- MimicUser lookup handles sandbox usernames automatically — provide the production email and the script tries both formats.

## Security and Sensitive Data

- Never commit credential/config files (for example, `jira_config.json`, `gainsight_config.json`, keys, or tokens)
- Keep API tokens and secrets in environment variables or gitignored local config files
- Treat CSV/JSON outputs as sensitive operational data and store them under `temp/`
- Keep rollback data (such as user backup JSON) whenever scripts update user permissions or access

## Code Architecture: Adding New Salesforce Queries

**Pattern**: Use shared utilities from `scripts/core/sf_utils.py` for all Salesforce query scripts.

**Available utilities in `scripts/core/sf_utils.py`**:
- `get_org_info(org_alias)` — Get org info dict from sf CLI
- `get_sf_connection(org_alias)` — Get authenticated Salesforce connection
- `extract_sandbox_name(org_info)` — Extract sandbox name from org info
- `format_user_record(user)` — Format raw User record into clean dict
- `print_user_details(user)` — Print user details in consistent format

**When adding new Salesforce query functionality**:

1. **Import shared utilities** — Don't duplicate `get_org_info()` or connection code:
   ```python
   from scripts.core.sf_utils import get_sf_connection, print_user_details
   
   def my_query(org_alias: str):
       sf = get_sf_connection(org_alias)
       result = sf.query("SELECT ...")
   ```

2. **Create standalone scripts for distinct query types** — Each script should have a single purpose:
   - `scripts/helpers/check_manager.py` — Find user by email
   - `scripts/helpers/check_vps.py` — Find VPs in a profile
   - `scripts/helpers/check_gainsight_license.py` — Check license assignment
   - `scripts/helpers/query_client_success_users.py` — Query users by profile/department

3. **Only modify existing scripts** if extending their specific functionality

4. **Follow the standard script structure**:
   ```python
   #!/usr/bin/env python3
   """Brief description of what this script does."""
   
   import argparse
   import os, sys
   sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
   from scripts.core.sf_utils import get_sf_connection
   
   def main_function(org_alias: str, ...):
       sf = get_sf_connection(org_alias)
       # Query logic here
   
   def main():
       parser = argparse.ArgumentParser(description='...')
       parser.add_argument('--org', default='mavenprod', help='Salesforce org alias')
       # Add other arguments
       args = parser.parse_args()
       
       main_function(args.org, ...)
   
   if __name__ == '__main__':
       main()
   ```

**Benefits of this pattern**:
- Common code is DRY (no duplication)
- Each script stays small and focused
- New queries = new scripts, no modification to existing code
- Easy to understand individual scripts
- No risk of a giant unmaintainable file

**Existing query scripts**:
| Script | Purpose |
|--------|---------|
| `scripts/helpers/check_manager.py` | Find user by email, show profile/role |
| `scripts/helpers/check_vps.py` | Find VPs in Client Success |
| `scripts/helpers/check_gainsight_license.py` | Check Gainsight license for user |
| `scripts/helpers/query_client_success_users.py` | Query all Client Success users |
