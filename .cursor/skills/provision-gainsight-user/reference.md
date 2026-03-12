# Gainsight Provisioning Reference

## gainsight_client.py CLI Commands

### create
Create/provision a Gainsight user with roles and permission bundles.

```bash
python scripts/integrations/gainsight_client.py create \
  --email user@mavenclinic.com \
  --first-name John --last-name Doe \
  --title "Account Manager" \
  --license-type Full \
  --roles CSM \
  --bundles "Client Resources" \
  --timezone America/New_York
```

### search
Search for a user by email or username.

```bash
python scripts/integrations/gainsight_client.py search --email user@mavenclinic.com
```

### assign-roles
Assign roles to an existing user via SCIM.

```bash
python scripts/integrations/gainsight_client.py assign-roles --email user@mavenclinic.com --roles CSM
```

### assign-bundles
Assign permission bundles via User Management REST API.

```bash
# Append to existing bundles (default)
python scripts/integrations/gainsight_client.py assign-bundles --email user@mavenclinic.com --bundles "Client Resources"

# Overwrite all existing bundles
python scripts/integrations/gainsight_client.py assign-bundles --email user@mavenclinic.com --bundles "Client Resources" --action overwrite
```

### deactivate
Deactivate a Gainsight user.

```bash
python scripts/integrations/gainsight_client.py deactivate --email user@mavenclinic.com
```

## Python API

### GainsightClient Methods

#### User Operations (SCIM)
- `create_user(email, first_name, last_name, ...)` - Create via SCIM
- `search_user_by_email(email)` - Search by email
- `get_user(user_id)` - Get by Gainsight ID
- `update_user(user_id, **kwargs)` - PATCH update (roles, license_type, active, etc.)
- `deactivate_user(user_id)` / `activate_user(user_id)`

#### Permission Bundles (REST API)
- `assign_permission_bundles(email, bundle_names, action="append")` - Assign bundles
- `update_user_via_rest(email, **kwargs)` - General REST API update

#### Convenience
- `provision_user(email, ..., roles=["CSM"], permission_bundles=["Client Resources"])` - Full provisioning

## API Architecture

### SCIM API
- **Base URL**: `{tenant_url}/v1/users/services/scim`
- **Auth**: M2M OAuth Bearer token
- **Token endpoint**: `{tenant_url}/v1/users/m2m/oauth/token`
- **Role assignment**: PATCH with `path: "roles"`, value: `[{"value": "CSM"}]`
- **Groups**: PATCH with `path: "groups"`, value: `[{"value": "<id>", "display": "<name>"}]`

### User Management REST API
- **Base URL**: `{tenant_url}/v1/users/services`
- **Auth**: M2M OAuth Bearer token (same as SCIM)
- **Permission bundles**: PUT with `key=SFDCUserName`, records contain `permissionBundles: ["name"]`
- **Bundle action**: Top-level `permissionBundleAction: "append"` or `"overwrite"` (NOT inside record)

### Key Difference: Roles vs Permission Bundles
- **Roles** (e.g., CSM): Managed via SCIM PATCH on `roles` path
- **Permission Bundles** (e.g., Client Resources): Managed via REST API `permissionBundles` field
- These are separate concepts in Gainsight and use different API endpoints

## gainsight_config.json

```json
{
  "tenant_url": "https://tenant.us2.gainsightcloud.com",
  "client_id": "<M2M OAuth Client ID>",
  "client_secret": "<M2M OAuth Client Secret>",
  "default_license_type": "Full",
  "default_groups": [],
  "default_roles": []
}
```
