## 2. Catalog & Asset Model

The catalog provides a unified registry for all mellea assets with consistent metadata, ID-based linking, and flexible storage.

### 2.1 Asset Types Overview

Three primary asset types, each stored as separate collections:

| Asset Type | Purpose | Storage Key |
|------------|---------|-------------|
| **Programs** | Python projects with entrypoints, configs, and `@generative` slots | `programs.json` |
| **Models** | LLM backend configurations and credentials | `models.json` |
| **Compositions** | Visual workflows linking programs and models (see Section 6.11) | `compositions.json` |

### 2.2 Universal Metadata Fields

All assets share a common metadata schema:

```typescript
interface AssetMetadata {
  // Identity
  id: string                    // UUID, immutable after creation
  name: string                  // Display name (unique per owner)
  description: string           // Free-form description

  // Classification
  tags: string[]                // User-defined tags for filtering
  version: string               // Semantic version (e.g., "1.0.0")

  // Ownership & Access
  owner: string                 // User ID of creator
  sharing: SharingMode          // "private" | "shared" | "public"
  sharedWith?: SharedAccess[]   // Users/groups with access (if sharing="shared")

  // Timestamps
  createdAt: datetime           // ISO 8601 creation time
  updatedAt: datetime           // ISO 8601 last modification time

  // Runtime State
  lastRunStatus?: RunStatus     // "never_run" | "succeeded" | "failed"
  lastRunAt?: datetime          // Timestamp of most recent run
}

interface SharedAccess {
  type: "user" | "group" | "org"
  id: string                    // User/group/org ID
  permission: "view" | "run" | "edit"
}

type SharingMode = "private" | "shared" | "public"
type RunStatus = "never_run" | "succeeded" | "failed"
```

### 2.3 Program Asset Schema

Programs are Python projects with mellea entrypoints and exported `@generative` slots:

```typescript
interface ProgramAsset extends AssetMetadata {
  type: "program"

  // Project Structure
  entrypoint: string            // Path to main script (e.g., "src/main.py")
  projectRoot: string           // Workspace directory path

  // Dependencies
  dependencies: DependencySpec

  // Mellea Integration
  exportedSlots: SlotMetadata[] // Discovered @generative functions
  requirements: string[]        // Declared requirement libraries

  // Resource Profile
  resourceProfile: ResourceProfile

  // Build State
  imageTag?: string             // Container image tag if built
  imageBuildStatus?: "pending" | "building" | "ready" | "failed"
  imageBuildError?: string      // Error message if build failed
}

interface DependencySpec {
  source: "pyproject" | "requirements" | "manual"
  packages: PackageRef[]        // Resolved package list
  pythonVersion?: string        // Required Python version (e.g., ">=3.10")
  lockfileHash?: string         // Hash of lockfile for cache invalidation
}

interface PackageRef {
  name: string
  version?: string              // Version constraint (e.g., ">=1.0.0")
  extras?: string[]             // Optional extras (e.g., ["dev", "test"])
}

interface SlotMetadata {
  name: string                  // Function name
  qualifiedName: string         // Full path (e.g., "mymodule.summarize")
  docstring?: string            // Function docstring
  signature: SlotSignature      // Typed args/returns (see Section 6.2.1)
  decorators: string[]          // Applied decorators (e.g., ["@generative"])
  sourceFile: string            // File containing the slot
  lineNumber: number            // Line number in source file
}

interface ResourceProfile {
  cpuLimit: string              // e.g., "2" (cores) or "500m" (millicores)
  memoryLimit: string           // e.g., "4Gi"
  timeoutSeconds: number        // Max execution time (default: 1800)
  ephemeralStorageLimit?: string // e.g., "10Gi"
}
```

### 2.4 Model Asset Schema

Models represent LLM backend configurations:

```typescript
interface ModelAsset extends AssetMetadata {
  type: "model"

  // Provider Configuration
  provider: ModelProvider       // "openai" | "anthropic" | "ollama" | "custom"
  modelId: string               // Provider-specific model ID (e.g., "gpt-4")

  // Endpoint Configuration
  endpoint?: EndpointConfig     // Custom endpoint (for ollama/custom)

  // Credentials
  credentialsRef?: string       // Reference to Kubernetes secret name

  // Model Parameters
  defaultParams: ModelParams

  // Capabilities & Constraints
  capabilities?: ModelCapabilities

  // Access Control
  accessControl: AccessControl

  // Scope
  scope: ModelScope             // Where this model can be used
}

type ModelProvider = "openai" | "anthropic" | "ollama" | "azure" | "custom"

interface EndpointConfig {
  baseUrl: string               // API base URL
  apiVersion?: string           // API version (e.g., "v1")
  headers?: Record<string, string>  // Additional headers
}

interface ModelParams {
  temperature?: number          // 0.0 - 2.0, default varies by provider
  maxTokens?: number            // Max output tokens
  topP?: number                 // Nucleus sampling threshold
  frequencyPenalty?: number     // -2.0 to 2.0
  presencePenalty?: number      // -2.0 to 2.0
  stopSequences?: string[]      // Stop generation sequences
}

interface ModelCapabilities {
  contextWindow: number         // Max context length in tokens
  supportsStreaming: boolean
  supportsToolCalling: boolean
  supportedModalities: ("text" | "image" | "audio")[]
  languages?: string[]          // Supported languages (ISO 639-1)
}

interface AccessControl {
  endUsers: boolean             // Can end users select this model?
  developers: boolean           // Can developers select this model?
  admins: boolean               // Can admins select this model?
}

type ModelScope = "chat" | "agent" | "composition" | "all"
```

### 2.5 ID-Based Linking

Assets reference each other via IDs rather than embedded objects. This enables:
- Independent versioning of linked assets
- Smaller JSON payloads
- Lazy resolution at runtime
- Easier permission checks on referenced assets

```typescript
// Composition references programs and models by ID
interface CompositionAsset extends AssetMetadata {
  type: "composition"

  // References (resolved at runtime)
  programRefs: string[]         // Program asset IDs used in composition
  modelRefs: string[]           // Model asset IDs used in composition

  // Graph definition (see Section 6.11.1 for full schema)
  graph: CompositionGraph
  spec: CompositionSpec
}

// Example: Resolving references at runtime
async function resolveComposition(composition: CompositionAsset): Promise<ResolvedComposition> {
  const programs = await Promise.all(
    composition.programRefs.map(id => catalogService.getProgram(id))
  )
  const models = await Promise.all(
    composition.modelRefs.map(id => catalogService.getModel(id))
  )

  // Verify user has access to all referenced assets
  for (const program of programs) {
    await authService.checkAccess(currentUser, program, "run")
  }

  return { composition, programs, models }
}
```

### 2.6 Storage Architecture

#### 2.6.1 Dual Storage Model

Assets use a combination of:
1. **Metadata Store**: JSON files (or database) for searchable metadata
2. **File Store**: Filesystem directories for program source code and artifacts

```
storage/
├── metadata/                   # JSON metadata files
│   ├── programs.json           # {"programs": [...]}
│   ├── models.json             # {"models": [...]}
│   ├── compositions.json       # {"compositions": [...]}
│   └── users.json              # {"users": [...]}
│
├── workspaces/                 # Program source trees
│   ├── {program-id}/
│   │   ├── src/
│   │   │   └── main.py
│   │   ├── pyproject.toml
│   │   └── requirements.txt
│   └── {program-id}/
│       └── ...
│
├── artifacts/                  # Run outputs
│   ├── {run-id}/
│   │   ├── stdout.log
│   │   ├── stderr.log
│   │   └── outputs/
│   └── ...
│
└── images/                     # Built container image layers (cache)
    └── ...
```

#### 2.6.2 Metadata JSON Format

Each asset type stored in a separate JSON file with consistent structure:

```json
// programs.json
{
  "programs": [
    {
      "id": "prog-550e8400-e29b-41d4-a716-446655440000",
      "name": "Document Summarizer",
      "description": "Summarizes documents using @generative slots",
      "tags": ["nlp", "summarization"],
      "version": "1.0.0",
      "owner": "user-123",
      "sharing": "shared",
      "sharedWith": [
        {"type": "user", "id": "user-456", "permission": "run"}
      ],
      "createdAt": "2024-01-15T10:30:00Z",
      "updatedAt": "2024-01-20T14:22:00Z",
      "entrypoint": "src/main.py",
      "projectRoot": "workspaces/prog-550e8400-e29b-41d4-a716-446655440000",
      "dependencies": {
        "source": "pyproject",
        "packages": [
          {"name": "mellea", "version": ">=0.5.0"},
          {"name": "pydantic", "version": ">=2.0.0"}
        ],
        "pythonVersion": ">=3.10"
      },
      "exportedSlots": [
        {
          "name": "summarize",
          "qualifiedName": "summarizer.summarize",
          "docstring": "Summarize a document into key points",
          "signature": {
            "name": "summarize",
            "args": [{"name": "document", "type": "str"}],
            "returns": {"type": "str"}
          },
          "decorators": ["@generative"],
          "sourceFile": "src/summarizer.py",
          "lineNumber": 15
        }
      ],
      "resourceProfile": {
        "cpuLimit": "1",
        "memoryLimit": "2Gi",
        "timeoutSeconds": 300
      },
      "lastRunStatus": "succeeded",
      "lastRunAt": "2024-01-20T14:20:00Z",
      "imageTag": "mellea-prog-550e8400:v1.0.0",
      "imageBuildStatus": "ready"
    }
  ]
}
```

#### 2.6.3 Thread-Safe Storage Operations

Storage layer provides atomic read/write with locking:

```python
class CatalogStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self._lock = threading.RLock()

    def read_programs(self) -> List[ProgramAsset]:
        with self._lock:
            data = self._read_json("programs.json")
            return [ProgramAsset(**p) for p in data.get("programs", [])]

    def write_program(self, program: ProgramAsset) -> None:
        with self._lock:
            programs = self.read_programs()
            # Update or append
            idx = next((i for i, p in enumerate(programs) if p.id == program.id), None)
            if idx is not None:
                programs[idx] = program
            else:
                programs.append(program)
            self._write_json("programs.json", {
                "programs": [p.model_dump(by_alias=True) for p in programs]
            })

    def delete_program(self, program_id: str) -> bool:
        with self._lock:
            programs = self.read_programs()
            original_len = len(programs)
            programs = [p for p in programs if p.id != program_id]
            if len(programs) < original_len:
                self._write_json("programs.json", {
                    "programs": [p.model_dump(by_alias=True) for p in programs]
                })
                # Also delete workspace directory
                shutil.rmtree(self.data_dir / "workspaces" / program_id, ignore_errors=True)
                return True
            return False
```

### 2.7 Catalog API Endpoints

RESTful API following `/api/v1/{asset_type}` convention:

#### 2.7.1 Programs API

```
GET    /api/v1/programs                 List all accessible programs
POST   /api/v1/programs                 Create new program
GET    /api/v1/programs/{id}            Get program by ID
PUT    /api/v1/programs/{id}            Update program metadata
DELETE /api/v1/programs/{id}            Delete program
GET    /api/v1/programs/{id}/slots      List exported @generative slots
POST   /api/v1/programs/{id}/build      Trigger container image build
GET    /api/v1/programs/{id}/files      List files in workspace
GET    /api/v1/programs/{id}/files/{path}  Get file content
PUT    /api/v1/programs/{id}/files/{path}  Update file content
```

#### 2.7.2 Models API

```
GET    /api/v1/models                   List all accessible models
POST   /api/v1/models                   Create new model config
GET    /api/v1/models/{id}              Get model by ID
PUT    /api/v1/models/{id}              Update model config
DELETE /api/v1/models/{id}              Delete model
POST   /api/v1/models/{id}/test         Test model connectivity
```

#### 2.7.3 Compositions API

```
GET    /api/v1/compositions             List all accessible compositions
POST   /api/v1/compositions             Create new composition
GET    /api/v1/compositions/{id}        Get composition by ID
PUT    /api/v1/compositions/{id}        Update composition
DELETE /api/v1/compositions/{id}        Delete composition
POST   /api/v1/compositions/{id}/validate  Validate composition graph
GET    /api/v1/compositions/{id}/code   Get generated Python code
```

#### 2.7.4 Unified Search

```
GET    /api/v1/catalog/search?q={query}&type={type}&tags={tags}&owner={owner}

Query Parameters:
- q: Full-text search across name and description
- type: Filter by asset type (program, model, composition)
- tags: Comma-separated tag filter
- owner: Filter by owner ID ("me" for current user)
- sharing: Filter by sharing mode (private, shared, public)
- sort: Sort field (name, createdAt, updatedAt, lastRunAt)
- order: Sort order (asc, desc)
- limit: Max results (default: 50, max: 200)
- offset: Pagination offset

Response:
{
  "results": [...],           // Mixed asset types with "type" field
  "total": 142,               // Total matching results
  "limit": 50,
  "offset": 0
}
```

### 2.8 Navigation & Views

#### 2.8.1 Catalog Views

| View | Filter | Description |
|------|--------|-------------|
| **My Assets** | `owner=me` | Assets created by current user |
| **Shared with Me** | `sharing=shared` + accessible | Assets shared with current user |
| **Public Gallery** | `sharing=public` | Publicly available assets |
| **All Accessible** | (none) | Union of all views |

#### 2.8.2 Asset Detail Page

Each asset type has a detail page showing:

**Common Elements:**
- Header: Name, description, owner avatar, sharing badge
- Metadata panel: Tags, version, timestamps, run status
- Actions: Run, Edit, Clone, Share, Delete

**Program-Specific:**
- File browser with syntax-highlighted preview
- Exported slots list with signatures
- Dependency list with versions
- Build status and image info
- Resource profile editor

**Model-Specific:**
- Provider and model info
- Connection status indicator
- Parameter defaults editor
- Test connection button
- Usage statistics

**Composition-Specific:**
- Visual graph preview (read-only mini canvas)
- Referenced programs/models list
- Input/output schema
- Open in Builder button

