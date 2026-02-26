---
name: deprovision-salesforce-user
description: Guides through Salesforce user deprovisioning workflows including deactivation, package license removal, Gainsight deactivation, and user reactivation. Use when asked to deprovision, deactivate, offboard, or delete a Salesforce user, or when a user's last day is mentioned.
---

# Salesforce User Deprovisioning

## Quick Start

When deprovisioning a Salesforce user, follow this workflow:

1. **Verify user exists**: Search for the user in Salesforce (active users only)
2. **Dry run**: Preview changes before executing
3. **Deprovision**: Run deprovisioning script
4. **Verify**: Check results JSON

## Key Concepts

- Salesforce does **not** support user deletion — deprovisioning means **deactivation**
- Deprovisioning removes package licenses, deactivates the user, and deactivates them in Gainsight
- Profiles, roles, and permission sets are **left unchanged** (preserved for audit/reactivation)
- Always run a **dry run first** for production orgs

## Pre-Deprovisioning Checklist

- [ ] **Confirm target org** — verify you're targeting the correct environment (e.g., `mavenprod`)
- [ ] **Verify user exists and is active** — search by name to confirm the right person
- [ ] **Run dry run first** — preview changes before executing in production
- [ ] **Confirm with user** if the request is ambiguous (e.g., name typo, multiple matches)

### Verify User Exists

Search for the user before running the script:

```bash
sf data query --query "SELECT Id, FirstName, LastName, Email, IsActive, Profile.Name FROM User WHERE FirstName = 'John' AND LastName = 'Doe'" --target-org mavenprod
```

If no results, try broader searches:

```bash
sf data query --query "SELECT Id, FirstName, LastName, Email, IsActive FROM User WHERE LastName LIKE '%Doe%'" --target-org mavenprod
```

## Deprovisioning Workflow

### Step 1: Dry Run

Always dry-run first in production:

```bash
python scripts/core/deprovision_user.py --org mavenprod --names "John Doe" --dry-run
```

Review the output:
- Confirm the correct user was matched
- Note package licenses that will be removed
- Verify Gainsight deactivation status (if applicable)

### Step 2: Execute Deprovisioning

**Single user by name:**
```bash
python scripts/core/deprovision_user.py --org mavenprod --names "John Doe" --skip-confirmation
```

**Multiple users by name:**
```bash
python scripts/core/deprovision_user.py --org mavenprod --names "John Doe, Jane Smith" --skip-confirmation
```

**From CSV file:**
```bash
python scripts/core/deprovision_user.py --org mavenprod --csv temp/deprovisioning_list.csv --skip-confirmation
```

### Step 3: Verify Results

Check `temp/deprovisioning_results.json`:
- `success` — users that were deactivated
- `failed` — users with errors (check error messages)
- `skipped` — users not found or declined

## CSV Format

Either format works:

```csv
Name
John Doe
Jane Smith
```

```csv
FirstName,LastName
John,Doe
Jane,Smith
```

Place CSV files in `temp/` folder (e.g., `temp/deprovisioning_list.csv`).

## What the Script Does

For each user:

1. Searches for **active** users matching the name
2. Prompts for selection if multiple matches (skipped with `--skip-confirmation`)
3. Removes all **package license assignments** (e.g., Gainsight namespace)
4. **Deactivates** the user (`IsActive = false`)
5. **Deactivates in Gainsight** (automatic if `gainsight_config.json` exists and user is active there)
6. Saves results to `temp/deprovisioning_results.json`

**Not changed:** Permission sets, permission set groups, profile, role.

## Script Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--org` | Yes | Salesforce org alias (e.g., `mavenprod`) |
| `--names` | One of | Comma-separated names (e.g., `"John Doe, Jane Smith"`) |
| `--csv` | One of | Path to CSV file with names |
| `--dry-run` | No | Preview changes without executing |
| `--skip-confirmation` | No | Skip per-user confirmation prompts |
| `--output` | No | Output file (default: `temp/deprovisioning_results.json`) |

## User Not Found

If the deprovisioning script reports "No active user found":

1. **Check spelling** — query Salesforce with LIKE patterns for name variations
2. **Check if already inactive** — query without the `IsActive = true` filter:
   ```bash
   sf data query --query "SELECT Id, FirstName, LastName, Email, IsActive FROM User WHERE FirstName = 'John' AND LastName = 'Doe'" --target-org mavenprod
   ```
3. **User may not have a Salesforce account** — not all employees are provisioned; inform the user no action is needed

## Reactivation (Undo)

If a user was deprovisioned by mistake, use the reactivation script:

```bash
python scripts/core/reactivate_user.py --org mavenprod --email user@mavenclinic.com
```

Or by name:
```bash
python scripts/core/reactivate_user.py --org mavenprod --first-name "John" --last-name "Doe"
```

This reactivates the Salesforce user, assigns Gainsight package license, and creates/activates the Gainsight user if applicable.

## Troubleshooting

### Multiple Matches with --skip-confirmation

When `--skip-confirmation` is used and multiple users match a name, the script **skips** that user to avoid ambiguity. Use interactive mode (without `--skip-confirmation`) to select the correct user, or use the dry-run output to identify the exact user first.

### Gainsight Deactivation Failed

- Check if `gainsight_config.json` exists and is valid
- The script continues even if Gainsight deactivation fails — the Salesforce user will still be deactivated
- Manually deactivate in Gainsight UI if needed

### Package License Removal Failed

- Some licenses may be protected or in use by managed packages
- Check the error in `temp/deprovisioning_results.json` for details
- The script continues with remaining steps even if a license removal fails

## Important Notes

- **Always dry-run first** in production — use `--dry-run` flag
- **Salesforce cannot delete users** — deprovisioning means deactivation only
- **All temp files go in `temp/`** — CSVs, results JSON, etc.
- **Gainsight integration is automatic** — no extra flags needed if `gainsight_config.json` exists
- **Results are always saved** — check `temp/deprovisioning_results.json` for full details

## Additional Resources

- For complete script reference, see [../provision-salesforce-user/reference.md](../provision-salesforce-user/reference.md)
- For workflow examples (including deprovisioning), see [../provision-salesforce-user/examples.md](../provision-salesforce-user/examples.md)
