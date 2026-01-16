# Secrets Storage Schema Design

This document defines the data model, encryption strategy, and provider-specific credential formats for storing LLM credentials in Mellea.

## Overview

Mellea uses a dual-backend architecture for credential storage:
- **Development**: Encrypted file storage with Fernet symmetric encryption
- **Production**: Kubernetes Secrets with cluster encryption at rest

## Data Model

### Credential Entity

```
Credential
├── id: string (UUID)           # Unique identifier
├── name: string                # Human-readable name
├── description: string         # Optional description
├── type: CredentialType        # Category of credential
├── provider: ModelProvider     # LLM provider (openai, anthropic, etc.)
├── owner_id: string            # Owning user ID (multi-tenant isolation)
├── tags: string[]              # Organization tags
├── created_at: datetime        # Creation timestamp
├── updated_at: datetime        # Last modification
├── last_accessed_at: datetime  # Last usage (audit trail)
├── expires_at: datetime?       # Optional expiration
└── [encrypted] secret_data     # Provider-specific secrets
```

### Credential Types

| Type | Description | Use Case |
|------|-------------|----------|
| `API_KEY` | Simple API key authentication | OpenAI, Anthropic |
| `OAUTH_TOKEN` | OAuth 2.0 access/refresh tokens | Azure AD, future providers |
| `REGISTRY` | Container registry credentials | Image pulling |
| `DATABASE` | Database connection credentials | Future: vector stores |
| `SSH_KEY` | SSH key pairs | Future: git integration |
| `CUSTOM` | Provider-specific formats | Custom endpoints |

### Supported LLM Providers

| Provider | Enum Value | Auth Method |
|----------|------------|-------------|
| OpenAI | `OPENAI` | API Key |
| Anthropic | `ANTHROPIC` | API Key |
| Azure OpenAI | `AZURE` | API Key + Endpoint, or Azure AD |
| Ollama | `OLLAMA` | None (local) or API Key |
| Custom | `CUSTOM` | Varies |

## Provider-Specific Secret Data

The `secret_data` field stores a `dict[str, str]` with provider-specific keys:

### OpenAI

```json
{
  "api_key": "sk-...",
  "organization_id": "org-..."  // optional
}
```

**Required keys**: `api_key`
**Optional keys**: `organization_id`

### Anthropic

```json
{
  "api_key": "sk-ant-..."
}
```

**Required keys**: `api_key`

### Azure OpenAI

```json
{
  "api_key": "...",
  "endpoint": "https://{resource}.openai.azure.com",
  "api_version": "2024-02-01"
}
```

**Required keys**: `api_key`, `endpoint`
**Optional keys**: `api_version`

For Azure AD authentication:
```json
{
  "tenant_id": "...",
  "client_id": "...",
  "client_secret": "...",
  "endpoint": "https://{resource}.openai.azure.com"
}
```

### Ollama (Self-Hosted)

```json
{
  "api_key": "..."  // if authentication enabled
}
```

**Required keys**: None (Ollama typically runs without auth)
**Optional keys**: `api_key`

### Custom Provider

```json
{
  "api_key": "...",
  "custom_header_1": "...",
  "custom_header_2": "..."
}
```

Keys are provider-defined. The `EndpointConfig` on `ModelAsset` specifies how to use them.

## Encryption Strategy

### Development: Encrypted File Backend

```
data/
└── credentials/
    ├── .key                    # Salt file (chmod 0600)
    ├── metadata.json           # Credential metadata (no secrets)
    └── secrets/
        └── {hash}.enc          # Encrypted secret files (chmod 0600)
```

**Encryption details**:
- Algorithm: Fernet (AES-128-CBC with HMAC-SHA256)
- Key derivation: PBKDF2-SHA256, 480,000 iterations
- Salt: 16-byte random, stored in `.key` file
- Master key: Derived from `MELLEA_SECRET_KEY` environment variable

### Production: Kubernetes Secrets Backend

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mellea-cred-{hash}
  namespace: mellea-credentials
  labels:
    app.kubernetes.io/managed-by: mellea-credentials
    mellea.io/credential-id: {uuid}
    mellea.io/credential-type: api_key
  annotations:
    mellea.io/metadata: '{"id":"...","name":"...","type":"..."}'
type: Opaque
data:
  api_key: {base64-encoded}
```

**Security features**:
- Namespace isolation (`mellea-credentials`)
- RBAC-controlled access
- Kubernetes audit logging
- Encryption at rest (cluster-level)
- Automatic backend selection based on environment

## Multi-Tenant Isolation

Credentials are isolated by `owner_id`:

1. **Storage**: All credentials include `owner_id` field
2. **Access control**: API routes enforce `credential.owner_id == current_user.id`
3. **Listing**: Queries filter by `owner_id` parameter
4. **Admin override**: Admin users can access all credentials (for support)

## Usage Flow

### Creating LLM Credentials

```python
# API: POST /api/v1/credentials
{
  "name": "My OpenAI Key",
  "type": "api_key",
  "provider": "openai",
  "secretData": {
    "api_key": "sk-..."
  },
  "expiresAt": "2025-12-31T23:59:59Z"  # optional
}
```

### Referencing from ModelAsset

```python
# API: POST /api/v1/assets/models
{
  "name": "GPT-4 Production",
  "provider": "openai",
  "modelId": "gpt-4",
  "credentialsRef": "{credential-id}"  # References stored credential
}
```

### Runtime Resolution

```python
# Internal: Program execution
credential_service = get_credential_service()
secret_data = credential_service.resolve_credentials_ref(model.credentials_ref)
api_key = secret_data["api_key"]
```

## Security Considerations

1. **Secrets never in responses**: `CredentialResponse` excludes `secret_data`
2. **Audit trail**: `last_accessed_at` updated on every secret retrieval
3. **Expiration support**: `is_expired` property prevents use of stale credentials
4. **File permissions**: Secret files created with `0600` mode
5. **Path traversal prevention**: Credential IDs hashed for filesystem paths
6. **No secrets in logs**: Logger excludes secret values

## Future Considerations

1. **Credential rotation**: Automated key rotation with zero-downtime
2. **External secret managers**: HashiCorp Vault, AWS Secrets Manager integration
3. **Credential sharing**: Team-level credential access
4. **Usage quotas**: Per-credential rate limiting
