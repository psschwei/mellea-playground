## 7. Collaboration & Access Control

The collaboration system provides user authentication, role-based permissions, asset sharing, and audit logging.

### 7.1 User Model

#### 7.1.1 User Schema

```typescript
interface User {
  // Identity
  id: string                    // UUID, immutable
  email: string                 // Primary identifier, unique
  username?: string             // Display username (optional)
  displayName: string           // Full name for UI display

  // Profile
  avatarUrl?: string            // Profile image URL
  department?: string           // Organization department
  jobTitle?: string             // Job title/role description

  // Authentication
  authProvider: AuthProvider    // How user authenticates
  externalId?: string           // ID from external provider (OAuth sub claim)

  // Authorization
  role: UserRole                // System-wide role
  organizationId?: string       // Organization membership (for multi-tenant)

  // State
  status: UserStatus            // "active" | "suspended" | "pending"
  lastLoginAt?: datetime
  createdAt: datetime
  updatedAt: datetime

  // Quotas
  quotas: UserQuotas
}

type AuthProvider = "local" | "google" | "github" | "oidc"
type UserRole = "end_user" | "developer" | "admin"
type UserStatus = "active" | "suspended" | "pending"

interface UserQuotas {
  maxConcurrentRuns: number     // Default: 3
  maxStorageMB: number          // Default: 5000
  maxCpuHoursPerMonth: number   // Default: 100
  maxRunsPerDay: number         // Default: 50
}
```

#### 7.1.2 User Storage

```json
// users.json
{
  "users": [
    {
      "id": "user-550e8400-e29b-41d4-a716-446655440000",
      "email": "alice@example.com",
      "username": "alice",
      "displayName": "Alice Chen",
      "authProvider": "google",
      "externalId": "google-oauth2|123456789",
      "role": "developer",
      "status": "active",
      "lastLoginAt": "2024-01-20T09:15:00Z",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-20T09:15:00Z",
      "quotas": {
        "maxConcurrentRuns": 5,
        "maxStorageMB": 10000,
        "maxCpuHoursPerMonth": 200,
        "maxRunsPerDay": 100
      }
    }
  ]
}
```

### 7.2 Authentication

#### 7.2.1 Dual Authentication Modes

Support both local development auth and production OAuth:

| Mode | Use Case | Configuration |
|------|----------|---------------|
| **Local Auth** | Development, testing | `AUTH_MODE=local` |
| **OAuth/OIDC** | Production | `AUTH_MODE=oidc`, configure provider |

#### 7.2.2 Local Authentication (Development)

Username/password authentication with JWT tokens:

```typescript
// Login request
POST /api/v1/auth/login
{
  "email": "alice@example.com",
  "password": "password123"
}

// Login response
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expiresAt": "2024-01-21T10:30:00Z",
  "user": {
    "id": "user-123",
    "email": "alice@example.com",
    "displayName": "Alice Chen",
    "role": "developer"
  }
}

// Registration
POST /api/v1/auth/register
{
  "email": "bob@example.com",
  "password": "securePassword123",
  "displayName": "Bob Smith"
}
```

Default development users (seeded on first run):
```
admin@mellea.local    / admin123     → admin role
developer@mellea.local / dev123      → developer role
user@mellea.local     / user123      → end_user role
```

#### 7.2.3 OAuth/OIDC Authentication (Production)

Google OAuth flow (primary supported provider):

```typescript
// Initiate OAuth flow
GET /api/v1/auth/oauth/google
→ Redirects to Google consent screen

// OAuth callback
GET /api/v1/auth/oauth/callback?code={code}&state={state}
→ Exchanges code for tokens, creates/updates user, returns JWT

// Configuration (environment variables)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://playground.mellea.ai/api/v1/auth/oauth/callback
```

JWT token structure:
```typescript
interface JWTPayload {
  sub: string           // User ID
  email: string
  name: string
  role: UserRole
  iat: number           // Issued at (Unix timestamp)
  exp: number           // Expiration (Unix timestamp, default: 24 hours)
}
```

#### 7.2.4 Auth Configuration Endpoint

```typescript
// Get auth configuration (public endpoint)
GET /api/v1/auth/config
{
  "mode": "oidc",
  "providers": ["google"],
  "registrationEnabled": true,
  "sessionDurationHours": 24
}
```

### 7.3 Role-Based Access Control

#### 7.3.1 Role Definitions

| Role | Description | Capabilities |
|------|-------------|--------------|
| **end_user** | Basic user | View public assets, run shared assets, manage own assets |
| **developer** | Power user | All end_user + create assets, access builder, view all shared |
| **admin** | Administrator | All developer + manage users, view metrics, modify quotas, system config |

#### 7.3.2 Permission Matrix

| Action | end_user | developer | admin |
|--------|----------|-----------|-------|
| View public assets | ✓ | ✓ | ✓ |
| Run public assets | ✓ | ✓ | ✓ |
| View shared assets | ✓ | ✓ | ✓ |
| Run shared assets | ✓ | ✓ | ✓ |
| Create programs | ✗ | ✓ | ✓ |
| Create models | ✗ | ✓ | ✓ |
| Create compositions | ✗ | ✓ | ✓ |
| Use visual builder | ✗ | ✓ | ✓ |
| Import from GitHub | ✗ | ✓ | ✓ |
| View all users | ✗ | ✗ | ✓ |
| Modify user roles | ✗ | ✗ | ✓ |
| Modify quotas | ✗ | ✗ | ✓ |
| View system metrics | ✗ | ✗ | ✓ |
| Manage system models | ✗ | ✗ | ✓ |

#### 7.3.3 Role Enforcement

```python
from functools import wraps
from fastapi import HTTPException, Depends

def require_role(minimum_role: UserRole):
    """Decorator to enforce minimum role requirement."""
    role_hierarchy = {"end_user": 0, "developer": 1, "admin": 2}

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if role_hierarchy[current_user.role] < role_hierarchy[minimum_role]:
                raise HTTPException(
                    status_code=403,
                    detail=f"This action requires {minimum_role} role or higher"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

# Usage
@router.post("/programs")
@require_role("developer")
async def create_program(request: CreateProgramRequest, current_user: User):
    ...

@router.get("/admin/metrics")
@require_role("admin")
async def get_metrics(current_user: User):
    ...
```

### 7.4 Ownership & Asset Permissions

#### 7.4.1 Ownership Model

Every asset has a single owner (the creator). Ownership grants full control:

```typescript
interface OwnershipRights {
  view: true
  run: true
  edit: true
  delete: true
  share: true
  transfer: true  // Transfer ownership to another user
}
```

#### 7.4.2 Permission Checking

```python
class PermissionService:
    def check_access(
        self,
        user: User,
        asset: AssetMetadata,
        permission: Permission
    ) -> bool:
        """
        Check if user has specified permission on asset.

        Permission hierarchy: view < run < edit
        Higher permissions imply lower ones.
        """
        # Admins have full access
        if user.role == "admin":
            return True

        # Owner has full access
        if asset.owner == user.id:
            return True

        # Check sharing mode
        if asset.sharing == "public":
            return permission in ["view", "run"]

        if asset.sharing == "shared":
            # Check explicit grants
            grant = self._find_grant(asset.sharedWith, user)
            if grant:
                return self._permission_satisfied(grant.permission, permission)

        # Private assets only accessible by owner
        return False

    def check_can_modify(self, user: User, asset: AssetMetadata) -> None:
        """Raise if user cannot modify asset."""
        if asset.owner == "system":
            raise PermissionError("System assets cannot be modified")

        if user.role != "admin" and asset.owner != user.id:
            raise PermissionError("Only the owner can modify this asset")

    def _find_grant(
        self,
        grants: List[SharedAccess],
        user: User
    ) -> Optional[SharedAccess]:
        """Find applicable grant for user."""
        for grant in grants or []:
            if grant.type == "user" and grant.id == user.id:
                return grant
            if grant.type == "org" and grant.id == user.organizationId:
                return grant
            # Group membership would be checked here
        return None

    def _permission_satisfied(
        self,
        granted: Permission,
        required: Permission
    ) -> bool:
        """Check if granted permission satisfies requirement."""
        hierarchy = {"view": 0, "run": 1, "edit": 2}
        return hierarchy[granted] >= hierarchy[required]
```

#### 7.4.3 System Assets

Certain assets are marked as system-owned and cannot be modified:

```typescript
// System assets have owner = "system"
{
  "id": "model-default-gpt4",
  "name": "GPT-4 (System)",
  "owner": "system",           // Special owner ID
  "sharing": "public",         // Available to all users
  ...
}
```

System assets:
- Pre-configured models (GPT-4, Claude, etc.)
- Template compositions from Pattern Library
- Example programs for onboarding

### 7.5 Sharing Mechanics

#### 7.5.1 Sharing Modes

| Mode | Visibility | Who Can Access |
|------|------------|----------------|
| **private** | Owner only | Only the asset owner |
| **shared** | Explicit grants | Owner + users/groups in `sharedWith` |
| **public** | Everyone | All authenticated users (view/run only) |

#### 7.5.2 Sharing API

```typescript
// Share an asset
POST /api/v1/programs/{id}/share
{
  "grants": [
    {"type": "user", "id": "user-456", "permission": "run"},
    {"type": "user", "id": "user-789", "permission": "edit"},
    {"type": "org", "id": "org-acme", "permission": "view"}
  ]
}

// Update sharing mode
PUT /api/v1/programs/{id}/sharing
{
  "sharing": "shared"  // or "private" or "public"
}

// Revoke access
DELETE /api/v1/programs/{id}/share/{grantId}

// List who has access
GET /api/v1/programs/{id}/access
{
  "owner": {"id": "user-123", "displayName": "Alice Chen"},
  "sharing": "shared",
  "grants": [
    {
      "id": "grant-001",
      "type": "user",
      "grantee": {"id": "user-456", "displayName": "Bob Smith"},
      "permission": "run",
      "grantedAt": "2024-01-15T10:00:00Z",
      "grantedBy": "user-123"
    }
  ]
}
```

#### 7.5.3 Sharing UI Components

```typescript
// Share dialog state
interface ShareDialogState {
  asset: AssetMetadata
  currentGrants: SharedAccess[]
  pendingChanges: ShareChange[]
  userSearchResults: User[]
}

// Share dialog actions
type ShareChange =
  | { action: "add", grant: SharedAccess }
  | { action: "update", grantId: string, permission: Permission }
  | { action: "remove", grantId: string }
  | { action: "setMode", mode: SharingMode }
```

#### 7.5.4 Cascading Permissions for Compositions

Compositions reference other assets. Running a composition requires access to all referenced assets:

```python
async def check_composition_access(
    user: User,
    composition: CompositionAsset,
    permission: Permission
) -> None:
    """
    Verify user has required permission on composition
    AND at least 'run' permission on all referenced assets.
    """
    # Check composition itself
    if not permission_service.check_access(user, composition, permission):
        raise PermissionError(f"No {permission} access to composition")

    # Check all referenced programs
    for program_id in composition.programRefs:
        program = await catalog.get_program(program_id)
        if not permission_service.check_access(user, program, "run"):
            raise PermissionError(
                f"No run access to referenced program: {program.name}"
            )

    # Check all referenced models
    for model_id in composition.modelRefs:
        model = await catalog.get_model(model_id)
        if not permission_service.check_access(user, model, "run"):
            raise PermissionError(
                f"No run access to referenced model: {model.name}"
            )
```

### 7.6 Run Permissions & Credential Delegation

#### 7.6.1 Credential Usage

When running assets, credentials (API keys, secrets) come from:

| Scenario | Credential Source |
|----------|-------------------|
| Owner runs own asset | Owner's linked credentials |
| User runs shared asset | Asset owner's credentials (delegated) |
| User runs public asset | Asset owner's credentials (delegated) |
| Composition run | Model's credentialsRef (from model asset) |

#### 7.6.2 Delegation Model

```typescript
interface RunContext {
  initiator: string           // User who started the run
  credentialOwner: string     // User whose credentials are used
  asset: AssetMetadata
  delegated: boolean          // true if using someone else's credentials
}

// Audit log captures delegation
{
  "event": "run.started",
  "runId": "run-123",
  "assetId": "prog-456",
  "initiator": "user-789",      // Who clicked "Run"
  "credentialOwner": "user-123", // Whose API key is used
  "delegated": true
}
```

#### 7.6.3 Quota Enforcement

Runs count against the **initiator's** quotas, not the credential owner's:

```python
async def check_run_quota(user: User) -> None:
    """Check if user can start a new run."""
    # Check concurrent runs
    active_runs = await run_service.count_active_runs(user.id)
    if active_runs >= user.quotas.maxConcurrentRuns:
        raise QuotaExceededError(
            f"Maximum concurrent runs ({user.quotas.maxConcurrentRuns}) exceeded"
        )

    # Check daily runs
    today_runs = await run_service.count_runs_today(user.id)
    if today_runs >= user.quotas.maxRunsPerDay:
        raise QuotaExceededError(
            f"Maximum daily runs ({user.quotas.maxRunsPerDay}) exceeded"
        )

    # Check CPU hours (monthly)
    month_cpu_hours = await run_service.sum_cpu_hours_this_month(user.id)
    if month_cpu_hours >= user.quotas.maxCpuHoursPerMonth:
        raise QuotaExceededError(
            f"Monthly CPU quota ({user.quotas.maxCpuHoursPerMonth}h) exceeded"
        )
```

### 7.7 Audit Logging

#### 7.7.1 Audit Event Schema

```typescript
interface AuditEvent {
  id: string
  timestamp: datetime

  // Actor
  userId: string
  userEmail: string
  userRole: UserRole

  // Action
  action: AuditAction
  resourceType: "program" | "model" | "composition" | "user" | "run"
  resourceId: string
  resourceName?: string

  // Context
  details: Record<string, any>  // Action-specific details
  ipAddress?: string
  userAgent?: string

  // Outcome
  success: boolean
  errorMessage?: string
}

type AuditAction =
  // Asset lifecycle
  | "asset.created"
  | "asset.updated"
  | "asset.deleted"
  | "asset.viewed"
  // Sharing
  | "asset.shared"
  | "asset.unshared"
  | "asset.made_public"
  | "asset.made_private"
  // Execution
  | "run.started"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  // Auth
  | "auth.login"
  | "auth.logout"
  | "auth.login_failed"
  // Admin
  | "user.role_changed"
  | "user.quota_changed"
  | "user.suspended"
```

#### 7.7.2 Audit Storage

```json
// audit_events.json (or database table)
{
  "events": [
    {
      "id": "evt-550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2024-01-20T14:30:00Z",
      "userId": "user-123",
      "userEmail": "alice@example.com",
      "userRole": "developer",
      "action": "asset.shared",
      "resourceType": "program",
      "resourceId": "prog-456",
      "resourceName": "Document Summarizer",
      "details": {
        "grantee": "user-789",
        "granteeEmail": "bob@example.com",
        "permission": "run"
      },
      "success": true
    }
  ]
}
```

#### 7.7.3 Audit API (Admin Only)

```typescript
// Query audit events
GET /api/v1/admin/audit?userId={userId}&action={action}&from={date}&to={date}

Query Parameters:
- userId: Filter by acting user
- resourceId: Filter by resource
- resourceType: Filter by resource type
- action: Filter by action type
- from/to: Date range (ISO 8601)
- limit/offset: Pagination

// Response
{
  "events": [...],
  "total": 1542,
  "limit": 100,
  "offset": 0
}
```

### 7.8 Notifications

#### 7.8.1 Notification Types

| Event | Recipients | Channel |
|-------|------------|---------|
| Asset shared with you | Grantee | In-app, Email (optional) |
| Your shared asset was updated | All grantees | In-app |
| Long-running job completed | Run initiator | In-app, Email |
| Run failed | Run initiator | In-app, Email |
| Quota warning (80% used) | User | In-app, Email |
| Quota exceeded | User | In-app, Email |

#### 7.8.2 Notification Schema

```typescript
interface Notification {
  id: string
  userId: string              // Recipient
  type: NotificationType
  title: string
  message: string
  link?: string               // Deep link to relevant page
  read: boolean
  createdAt: datetime
  expiresAt?: datetime        // Auto-delete after this time
}

type NotificationType =
  | "share_received"
  | "asset_updated"
  | "run_completed"
  | "run_failed"
  | "quota_warning"
  | "quota_exceeded"
  | "system_announcement"
```

#### 7.8.3 Notification Settings

```typescript
interface NotificationPreferences {
  userId: string

  // Per-type settings
  channels: {
    share_received: { inApp: true, email: true }
    asset_updated: { inApp: true, email: false }
    run_completed: { inApp: true, email: true }
    run_failed: { inApp: true, email: true }
    quota_warning: { inApp: true, email: true }
  }

  // Global settings
  emailDigest: "immediate" | "daily" | "weekly" | "never"
  quietHoursStart?: string    // e.g., "22:00"
  quietHoursEnd?: string      // e.g., "08:00"
}
```

### 7.9 Admin Tools

#### 7.9.1 User Management API

```typescript
// List all users (admin only)
GET /api/v1/admin/users?role={role}&status={status}

// Get user details
GET /api/v1/admin/users/{userId}

// Update user role
PUT /api/v1/admin/users/{userId}/role
{ "role": "developer" }

// Update user quotas
PUT /api/v1/admin/users/{userId}/quotas
{
  "maxConcurrentRuns": 10,
  "maxStorageMB": 20000
}

// Suspend user
POST /api/v1/admin/users/{userId}/suspend
{ "reason": "Policy violation" }

// Reactivate user
POST /api/v1/admin/users/{userId}/reactivate
```

#### 7.9.2 System Metrics API

```typescript
// Daily visitor metrics
GET /api/v1/admin/metrics/visitors/daily?from={date}&to={date}
{
  "metrics": [
    {
      "date": "2024-01-20",
      "totalVisitors": 150,
      "uniqueUsers": 45,
      "uniqueSessions": 62,
      "totalRequests": 3420,
      "topEndpoints": {
        "/api/v1/programs": 520,
        "/api/v1/compositions": 380
      }
    }
  ]
}

// Usage summary
GET /api/v1/admin/metrics/usage
{
  "totalUsers": 128,
  "activeUsersLast30Days": 87,
  "totalAssets": {
    "programs": 234,
    "models": 45,
    "compositions": 89
  },
  "totalRuns": {
    "last24Hours": 156,
    "last7Days": 892,
    "last30Days": 3420
  },
  "storageUsedMB": 45230,
  "cpuHoursUsed": {
    "thisMonth": 1240,
    "lastMonth": 980
  }
}

// Quota usage by user
GET /api/v1/admin/metrics/quotas
{
  "users": [
    {
      "userId": "user-123",
      "email": "alice@example.com",
      "storageUsedMB": 4500,
      "storageQuotaMB": 5000,
      "cpuHoursUsed": 85,
      "cpuHoursQuota": 100,
      "runsToday": 23,
      "runsQuota": 50
    }
  ]
}
```

#### 7.9.3 System Configuration

```typescript
// Get system config
GET /api/v1/admin/config
{
  "registrationEnabled": true,
  "defaultUserRole": "end_user",
  "defaultQuotas": {
    "maxConcurrentRuns": 3,
    "maxStorageMB": 5000,
    "maxCpuHoursPerMonth": 100,
    "maxRunsPerDay": 50
  },
  "publicSharingEnabled": true,
  "maxUploadSizeMB": 100
}

// Update system config
PUT /api/v1/admin/config
{
  "registrationEnabled": false,
  "defaultQuotas": {
    "maxConcurrentRuns": 5
  }
}
```

### 7.10 Access-Aware UI Components

#### 7.10.1 Filtered Asset Lists

The catalog only shows assets the current user can access:

```typescript
async function fetchAccessibleAssets(
  user: User,
  filters: AssetFilters
): Promise<AssetMetadata[]> {
  const allAssets = await catalog.search(filters)

  return allAssets.filter(asset =>
    // Owner sees all their assets
    asset.owner === user.id ||
    // Public assets visible to all
    asset.sharing === "public" ||
    // Shared assets if user has grant
    (asset.sharing === "shared" && hasGrant(asset, user)) ||
    // Admins see everything
    user.role === "admin"
  )
}
```

#### 7.10.2 Permission-Based UI State

```typescript
interface AssetUIState {
  canView: boolean
  canRun: boolean
  canEdit: boolean
  canDelete: boolean
  canShare: boolean

  // Derived UI states
  showEditButton: boolean
  showDeleteButton: boolean
  showShareButton: boolean
  showCloneButton: boolean
  runButtonDisabled: boolean
  runButtonTooltip?: string   // e.g., "Quota exceeded"
}

function computeAssetUIState(user: User, asset: AssetMetadata): AssetUIState {
  const isOwner = asset.owner === user.id
  const isAdmin = user.role === "admin"
  const grant = findGrant(asset, user)

  return {
    canView: true,  // If we fetched it, we can view it
    canRun: isOwner || isAdmin || asset.sharing === "public" ||
            (grant && ["run", "edit"].includes(grant.permission)),
    canEdit: isOwner || isAdmin || (grant?.permission === "edit"),
    canDelete: isOwner || isAdmin,
    canShare: isOwner || isAdmin,

    showEditButton: isOwner || isAdmin || grant?.permission === "edit",
    showDeleteButton: isOwner || isAdmin,
    showShareButton: isOwner,
    showCloneButton: user.role !== "end_user",  // Developers+ can clone
    runButtonDisabled: false,  // Updated by quota check
    runButtonTooltip: undefined
  }
}
```

#### 7.10.3 Builder Asset Picker

The visual builder only shows assets the user can use in compositions:

```typescript
// Sidebar shows only accessible programs/models
const availablePrograms = programs.filter(p =>
  permissionService.check_access(currentUser, p, "run")
)

const availableModels = models.filter(m =>
  permissionService.check_access(currentUser, m, "run") &&
  m.accessControl[currentUser.role]  // Role-based model access
)
```

