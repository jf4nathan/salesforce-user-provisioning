---
name: provision-gainsight-user
description: Provisions Gainsight user accounts for existing Salesforce users, including license assignment, permission set assignment, SCIM user creation/upgrade, role assignment, and permission bundle assignment. Use when asked to set up Gainsight access, create a Gainsight account, enable Gainsight for a user, assign Gainsight roles, or assign permission bundles.
---

# Gainsight User Provisioning

## Quick Start

When provisioning a Gainsight user for an existing Salesforce user:

1. **Verify Salesforce user** exists and get their details
2. **Check Gainsight license** and permission set status in Salesforce
3. **Assign license/PS** in Salesforce if missing
4. **Provision Gainsight user** (create or upgrade) with role + permission bundle
5. **Verify** final state

## Prerequisites

- Salesforce user must already exist
- `gainsight_config.json` must be configured in the repo root
- Gainsight licenses must be available (check with `check_gainsight_license.py`)

## Two APIs

Gainsight has two separate APIs used during provisioning:

| API | Auth | Used For |
|-----|------|----------|
| **SCIM API** (`/v1/users/services/scim`) | M2M OAuth (Bearer token) | User CRUD, roles, groups, license type |
| **User Management REST API** (`/v1/users/services`) | M2M OAuth (Bearer token) | Permission bundles |

**Roles** are set via SCIM PATCH on the `roles` path (not `custom_roles` in extension).
**Permission bundles** are set via the User Management REST API with `permissionBundles` field.

## Workflow

### Step 1: Verify Salesforce User

```bash
python scripts/helpers/check_manager.py --org mavenprod user.email@mavenclinic.com
```

### Step 2: Check Gainsight License and Permission Set

```bash
python scripts/helpers/check_gainsight_license.py --org mavenprod user.email@mavenclinic.com
```

### Step 3: Assign License and Permission Set (if missing)

If the Gainsight CS permission set is not assigned:

```bash
sf data create record --sobject PermissionSetAssignment --values "AssigneeId=<USER_ID> PermissionSetId=0PSUH0000006LTB4A2" --target-org mavenprod
```

If the package license is not assigned:

```bash
sf data create record --sobject UserPackageLicense --values "UserId=<USER_ID> PackageLicenseId=050UH00000NFYVZYA5" --target-org mavenprod
```

### Step 4: Provision Gainsight User

**Full provisioning (new user or existing):**

```bash
python scripts/integrations/gainsight_client.py create \
  --email user.email@mavenclinic.com \
  --first-name First --last-name Last \
  --title "Job Title" --license-type Full \
  --roles CSM --bundles "Client Resources"
```

This handles:
- Creating the user via SCIM (or detecting existing)
- Setting role via SCIM PATCH `roles` path
- Assigning permission bundle via User Management REST API

**Assign roles to existing user:**

```bash
python scripts/integrations/gainsight_client.py assign-roles \
  --email user.email@mavenclinic.com --roles CSM
```

**Assign permission bundles to existing user:**

```bash
python scripts/integrations/gainsight_client.py assign-bundles \
  --email user.email@mavenclinic.com --bundles "Client Resources"
```

**Upgrade existing user license + add role (Python):**

```python
from scripts.integrations.gainsight_client import create_client_from_config
client = create_client_from_config()
user_id = '<GAINSIGHT_USER_ID>'
client.update_user(user_id, license_type='Full', roles=['CSM'])
client.assign_permission_bundles('user@mavenclinic.com', ['Client Resources'])
```

### Step 5: Verify

```bash
python scripts/integrations/gainsight_client.py search --email user.email@mavenclinic.com
```

Confirm:
- `active: true`
- `LicenseType: Full`
- `roles: [{"value": "CSM"}]`

## Default Provisioning Settings

When provisioning via `provision_user.py`, Gainsight users are auto-created for **Client Success** profile users with:
- License type: `Full`
- Role: `CSM` (via SCIM)
- Permission bundle: `Client Resources` (via REST API)

For non-Client Success users (like Sales), Gainsight provisioning must be done manually using this workflow.

## Gainsight License Types

| Type | Description |
|------|-------------|
| `Full` | Full access (default for provisioned users) |
| `Viewer_Analytics` | Read-only with analytics |
| `Viewer` | Read-only access |
| `Internal_Collaborator` | Limited internal access |

## Key Salesforce IDs

| Resource | ID |
|----------|-----|
| Gainsight Package License | `050UH00000NFYVZYA5` |
| Gainsight CS Permission Set | `0PSUH0000006LTB4A2` |
| Gainsight CS Permission Set API Name | `GAINSIGHT__Gainsight_CS` |

## Troubleshooting

### Roles Not Showing After Update
Roles must be set via the top-level SCIM `roles` path, not `custom_roles` in the Gainsight extension schema. The `update_user()` method handles this correctly.

### Permission Bundle Not Assigned
Permission bundles use the User Management REST API (`/v1/users/services`), not SCIM. Use `assign_permission_bundles()` or the `assign-bundles` CLI command. The `permissionBundleAction` field must be at the top level of the payload, not inside the record.

### No Gainsight Licenses Available
Check license counts: `python scripts/helpers/check_gainsight_license.py --org mavenprod <email>`

### Permission Set Assignment Fails
The package license may need to be assigned first. Assign the package license, then retry.

## Additional Resources

- For complete API details, see [reference.md](reference.md)
