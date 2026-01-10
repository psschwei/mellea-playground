## 3. Import & Creation Flows

This section describes how users create and import programs, models, and compositions into the catalog.

### 3.1 Overview

| Flow | Use Case | Input | Output |
|------|----------|-------|--------|
| **Manual Form** | Create from scratch or paste code | Files + metadata form | Program asset |
| **GitHub Import** | Import existing project | Repo URL + branch | Program asset |
| **Drag-and-Drop** | Quick upload | Zip/folder | Program asset |
| **Model Config** | Add LLM backend | Provider + credentials | Model asset |
| **Visual Builder** | Create workflow | Canvas design | Composition asset |
| **Clone** | Copy existing asset | Source asset ID | New asset |

### 3.2 Manual Program Creation

#### 3.2.1 Creation Wizard Flow

```
Step 1: Basic Info        Step 2: Files           Step 3: Dependencies      Step 4: Review
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ Name            │      │ Upload files    │      │ Detected deps   │      │ Summary         │
│ Description     │  →   │ Or paste code   │  →   │ Add/remove pkgs │  →   │ Detected slots  │
│ Tags            │      │ Set entrypoint  │      │ Python version  │      │ Confirm & Save  │
└─────────────────┘      └─────────────────┘      └─────────────────┘      └─────────────────┘
```

#### 3.2.2 Step 1: Basic Information

```typescript
// UI Form State
interface ProgramBasicInfoForm {
  name: string              // Required, 3-100 chars
  description: string       // Required, 10-1000 chars
  tags: string[]            // Optional, max 10 tags
  sharing: SharingMode      // Default: "private"
}

// Validation
const basicInfoSchema = {
  name: {
    required: true,
    minLength: 3,
    maxLength: 100,
    pattern: /^[a-zA-Z0-9][a-zA-Z0-9\s\-_]*$/,
    unique: true  // Per owner
  },
  description: {
    required: true,
    minLength: 10,
    maxLength: 1000
  },
  tags: {
    maxItems: 10,
    itemPattern: /^[a-z0-9\-]+$/,
    itemMaxLength: 30
  }
}
```

#### 3.2.3 Step 2: File Upload

```typescript
// File upload options
interface FileUploadState {
  mode: "upload" | "paste" | "template"
  files: UploadedFile[]
  entrypoint: string | null       // Auto-detected or manual
  detectedEntrypoints: string[]   // Candidates found
}

interface UploadedFile {
  path: string                    // Relative path (e.g., "src/main.py")
  content: string | ArrayBuffer   // File content
  size: number
  type: "python" | "config" | "data" | "other"
}

// Template options for quick start
const programTemplates = [
  {
    id: "blank",
    name: "Blank Project",
    files: [
      { path: "main.py", content: "# Your mellea program\n" },
      { path: "requirements.txt", content: "mellea>=0.5.0\n" }
    ]
  },
  {
    id: "generative-slot",
    name: "@generative Slot Example",
    files: [
      { path: "main.py", content: GENERATIVE_TEMPLATE },
      { path: "requirements.txt", content: "mellea>=0.5.0\npydantic>=2.0\n" }
    ]
  },
  {
    id: "ivr-pattern",
    name: "IVR Pattern Example",
    files: [
      { path: "main.py", content: IVR_TEMPLATE },
      { path: "verifier.py", content: VERIFIER_TEMPLATE },
      { path: "requirements.txt", content: "mellea>=0.5.0\n" }
    ]
  }
]
```

#### 3.2.4 Step 3: Dependencies

```typescript
// Dependency configuration
interface DependencyConfigState {
  source: "auto" | "manual"
  detectedFrom: "pyproject" | "requirements" | "imports" | null
  packages: EditablePackage[]
  pythonVersion: string
  conflicts: DependencyConflict[]
}

interface EditablePackage {
  name: string
  version: string           // Version constraint
  detected: boolean         // Auto-detected vs manually added
  required: boolean         // Core dependency vs optional
}

interface DependencyConflict {
  package: string
  issue: string             // e.g., "Version 1.0 conflicts with mellea>=0.5"
  suggestion: string
}
```

#### 3.2.5 Step 4: Review & Create

```typescript
// Final review shows analysis results
interface ProgramReviewState {
  basicInfo: ProgramBasicInfoForm
  files: UploadedFile[]
  entrypoint: string
  dependencies: DependencySpec

  // Analysis results
  detectedSlots: SlotMetadata[]
  validationErrors: ValidationError[]
  validationWarnings: ValidationWarning[]

  // Resource defaults
  resourceProfile: ResourceProfile
}

// Create API
POST /api/v1/programs
Content-Type: multipart/form-data

{
  "metadata": {
    "name": "Document Summarizer",
    "description": "Summarizes documents using @generative slots",
    "tags": ["nlp", "summarization"]
  },
  "entrypoint": "src/main.py",
  "dependencies": {
    "source": "manual",
    "packages": [
      {"name": "mellea", "version": ">=0.5.0"},
      {"name": "pydantic", "version": ">=2.0.0"}
    ],
    "pythonVersion": ">=3.10"
  },
  "resourceProfile": {
    "cpuLimit": "1",
    "memoryLimit": "2Gi",
    "timeoutSeconds": 300
  },
  "files": [/* multipart file uploads */]
}

// Response
{
  "id": "prog-550e8400-e29b-41d4-a716-446655440000",
  "name": "Document Summarizer",
  "status": "created",
  "exportedSlots": [...],
  "imageBuildStatus": "pending",
  "workspaceUrl": "/workspaces/prog-550e8400..."
}
```

### 3.3 GitHub Import

#### 3.3.1 Import Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Enter URL    │     │ Clone &      │     │ Select       │     │ Configure &  │
│ + Branch     │ →   │ Analyze      │ →   │ Subdirectory │ →   │ Import       │
│              │     │              │     │ (if needed)  │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

#### 3.3.2 Step 1: Repository Input

```typescript
// GitHub URL input
interface GitHubImportInput {
  repoUrl: string           // https://github.com/owner/repo or git@github.com:...
  branch: string            // Default: "main" or "master"
  accessToken?: string      // For private repos (stored securely)
}

// URL validation
function parseGitHubUrl(url: string): ParsedRepo | null {
  const patterns = [
    /^https:\/\/github\.com\/([^\/]+)\/([^\/]+?)(\.git)?$/,
    /^git@github\.com:([^\/]+)\/([^\/]+?)(\.git)?$/,
    /^https:\/\/github\.com\/([^\/]+)\/([^\/]+)\/tree\/([^\/]+)(.*)$/
  ]
  // Extract owner, repo, branch, path
}
```

#### 3.3.3 Step 2: Clone & Analyze

```typescript
// Backend analysis endpoint
POST /api/v1/programs/import/github/analyze
{
  "repoUrl": "https://github.com/acme/summarizer",
  "branch": "main",
  "accessToken": "ghp_xxxx"  // Optional, for private repos
}

// Response: Analysis results
{
  "status": "success",
  "analysis": {
    "rootFiles": ["README.md", "pyproject.toml", "src/"],
    "pythonProjects": [
      {
        "path": ".",
        "entrypoint": "src/main.py",
        "confidence": 0.9,
        "indicators": ["pyproject.toml", "src/ directory"]
      },
      {
        "path": "examples/basic",
        "entrypoint": "examples/basic/run.py",
        "confidence": 0.6,
        "indicators": ["run.py file"]
      }
    ],
    "detectedDependencies": {
      "source": "pyproject",
      "packages": [...],
      "pythonVersion": ">=3.10"
    },
    "detectedSlots": [...],
    "repoSize": 1240000,  // bytes
    "fileCount": 45
  },
  "sessionId": "import-session-123"  // For subsequent steps
}
```

#### 3.3.4 Step 3: Select Subdirectory (if multiple projects)

```typescript
// UI presents choice if multiple Python projects detected
interface SubdirectorySelection {
  sessionId: string
  selectedPath: string      // "." or "examples/basic"
  customEntrypoint?: string // Override detected entrypoint
}
```

#### 3.3.5 Step 4: Configure & Import

```typescript
// Confirm import with metadata
POST /api/v1/programs/import/github/confirm
{
  "sessionId": "import-session-123",
  "selectedPath": ".",
  "metadata": {
    "name": "ACME Summarizer",
    "description": "Imported from github.com/acme/summarizer",
    "tags": ["imported", "nlp"]
  },
  "entrypoint": "src/main.py",
  "dependencies": {
    // Can override detected dependencies
  }
}

// Response: Created program
{
  "id": "prog-789",
  "name": "ACME Summarizer",
  "importSource": {
    "type": "github",
    "repoUrl": "https://github.com/acme/summarizer",
    "branch": "main",
    "commit": "abc123def456",
    "importedAt": "2024-01-20T10:00:00Z"
  },
  "exportedSlots": [...],
  "imageBuildStatus": "pending"
}
```

#### 3.3.6 GitHub Import Service

```python
class GitHubImportService:
    async def analyze_repository(
        self,
        repo_url: str,
        branch: str,
        access_token: Optional[str] = None
    ) -> AnalysisResult:
        """Clone repo to temp directory and analyze structure."""

        # Clone to temp directory
        temp_dir = await self._clone_repo(repo_url, branch, access_token)

        try:
            # Find Python projects
            projects = await self._find_python_projects(temp_dir)

            # Analyze each project
            for project in projects:
                project.dependencies = await self._extract_dependencies(
                    temp_dir / project.path
                )
                project.slots = await self._scan_for_slots(
                    temp_dir / project.path
                )

            return AnalysisResult(
                python_projects=projects,
                repo_size=self._get_dir_size(temp_dir),
                file_count=self._count_files(temp_dir)
            )
        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir)

    async def _find_python_projects(self, root: Path) -> List[PythonProject]:
        """Detect Python project roots by looking for indicators."""
        projects = []

        # Check root first
        if self._is_python_project(root):
            projects.append(PythonProject(
                path=".",
                entrypoint=self._detect_entrypoint(root),
                confidence=0.9
            ))

        # Check subdirectories (max depth 2)
        for subdir in root.glob("*/"):
            if self._is_python_project(subdir):
                projects.append(PythonProject(
                    path=subdir.relative_to(root),
                    entrypoint=self._detect_entrypoint(subdir),
                    confidence=0.7
                ))

        return projects

    def _is_python_project(self, path: Path) -> bool:
        """Check if directory looks like a Python project."""
        indicators = [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "main.py",
            "__main__.py"
        ]
        return any((path / ind).exists() for ind in indicators)

    def _detect_entrypoint(self, path: Path) -> Optional[str]:
        """Find likely entrypoint script."""
        candidates = [
            "main.py",
            "app.py",
            "run.py",
            "__main__.py",
            "src/main.py",
            "src/__main__.py"
        ]
        for candidate in candidates:
            if (path / candidate).exists():
                return candidate

        # Fall back to first .py file
        py_files = list(path.glob("*.py"))
        return py_files[0].name if py_files else None
```

### 3.4 Drag-and-Drop Upload

#### 3.4.1 Upload Flow

```typescript
// Drop zone accepts files or folders
interface DropZoneState {
  isDragging: boolean
  uploadProgress: number
  analyzing: boolean
  analysisResult: UploadAnalysisResult | null
}

// Accepted formats
const acceptedFormats = {
  archives: [".zip", ".tar.gz", ".tgz"],
  folders: true,  // Via directory upload
  singleFiles: [".py"]
}
```

#### 3.4.2 Upload Processing

```typescript
// Backend upload endpoint
POST /api/v1/programs/import/upload
Content-Type: multipart/form-data

// File(s) in request body

// Response: Analysis results
{
  "sessionId": "upload-session-456",
  "analysis": {
    "extractedFiles": [
      {"path": "main.py", "size": 1234, "type": "python"},
      {"path": "utils.py", "size": 567, "type": "python"},
      {"path": "requirements.txt", "size": 89, "type": "config"}
    ],
    "detectedEntrypoint": "main.py",
    "entrypointCandidates": ["main.py", "app.py"],
    "detectedDependencies": {...},
    "detectedSlots": [...],
    "validationErrors": [],
    "validationWarnings": [
      {"code": "NO_PYPROJECT", "message": "No pyproject.toml found"}
    ]
  }
}
```

#### 3.4.3 Confirmation Dialog

After upload analysis, show a confirmation dialog:

```typescript
interface UploadConfirmationState {
  sessionId: string

  // Editable fields
  name: string              // Suggested from folder/file name
  description: string       // Empty, user fills in
  entrypoint: string        // Selected from candidates

  // Review sections
  files: FilePreview[]
  dependencies: EditablePackage[]
  detectedSlots: SlotMetadata[]
  warnings: ValidationWarning[]
}
```

### 3.5 Model Configuration

#### 3.5.1 Model Creation Form

```typescript
interface ModelCreationForm {
  // Basic info
  name: string
  description: string
  tags: string[]

  // Provider selection
  provider: ModelProvider
  modelId: string           // e.g., "gpt-4", "claude-3-opus"

  // Endpoint (for ollama/custom)
  endpoint?: {
    baseUrl: string
    apiVersion?: string
  }

  // Credentials
  credentialMode: "existing" | "new" | "none"
  existingCredentialRef?: string
  newCredential?: {
    name: string
    apiKey: string
  }

  // Default parameters
  defaultParams: ModelParams

  // Access control
  accessControl: AccessControl
  scope: ModelScope
}
```

#### 3.5.2 Provider-Specific Configuration

```typescript
// Provider configurations
const providerConfigs: Record<ModelProvider, ProviderConfig> = {
  openai: {
    name: "OpenAI",
    models: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
    requiresApiKey: true,
    defaultEndpoint: "https://api.openai.com/v1",
    parameterDefaults: { temperature: 0.7, maxTokens: 4096 }
  },
  anthropic: {
    name: "Anthropic",
    models: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
    requiresApiKey: true,
    defaultEndpoint: "https://api.anthropic.com",
    parameterDefaults: { temperature: 0.7, maxTokens: 4096 }
  },
  ollama: {
    name: "Ollama (Local)",
    models: [],  // Fetched from endpoint
    requiresApiKey: false,
    defaultEndpoint: "http://localhost:11434",
    parameterDefaults: { temperature: 0.7 }
  },
  azure: {
    name: "Azure OpenAI",
    models: [],  // Deployment-specific
    requiresApiKey: true,
    requiresEndpoint: true,
    parameterDefaults: { temperature: 0.7, maxTokens: 4096 }
  },
  custom: {
    name: "Custom (OpenAI-compatible)",
    models: [],
    requiresApiKey: true,
    requiresEndpoint: true,
    parameterDefaults: {}
  }
}
```

#### 3.5.3 Connection Test

```typescript
// Test model connectivity before saving
POST /api/v1/models/test
{
  "provider": "openai",
  "modelId": "gpt-4",
  "endpoint": {...},
  "apiKey": "sk-..."  // Sent securely, not stored in response
}

// Response
{
  "success": true,
  "latencyMs": 234,
  "modelInfo": {
    "contextWindow": 128000,
    "supportsStreaming": true,
    "supportsToolCalling": true
  }
}

// Or error
{
  "success": false,
  "error": {
    "code": "INVALID_API_KEY",
    "message": "The provided API key is invalid or expired"
  }
}
```

### 3.6 Validation System

#### 3.6.1 Validation Pipeline

```python
class ValidationPipeline:
    """Multi-stage validation for program imports."""

    async def validate(self, workspace_path: Path) -> ValidationResult:
        errors = []
        warnings = []

        # Stage 1: Structure validation
        structure_result = await self._validate_structure(workspace_path)
        errors.extend(structure_result.errors)
        warnings.extend(structure_result.warnings)

        # Stage 2: Dependency validation
        dep_result = await self._validate_dependencies(workspace_path)
        errors.extend(dep_result.errors)
        warnings.extend(dep_result.warnings)

        # Stage 3: Syntax validation
        syntax_result = await self._validate_syntax(workspace_path)
        errors.extend(syntax_result.errors)
        warnings.extend(syntax_result.warnings)

        # Stage 4: Slot detection
        slot_result = await self._detect_slots(workspace_path)
        warnings.extend(slot_result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            detectedSlots=slot_result.slots
        )
```

#### 3.6.2 Structure Validation

```python
async def _validate_structure(self, path: Path) -> StageResult:
    errors = []
    warnings = []

    # Check entrypoint exists
    entrypoint = self._get_entrypoint(path)
    if not (path / entrypoint).exists():
        errors.append(ValidationError(
            code="MISSING_ENTRYPOINT",
            message=f"Entrypoint '{entrypoint}' not found",
            severity="error"
        ))

    # Check for required files
    if not (path / "requirements.txt").exists() and \
       not (path / "pyproject.toml").exists():
        warnings.append(ValidationWarning(
            code="NO_DEPENDENCY_FILE",
            message="No requirements.txt or pyproject.toml found",
            suggestion="Add a dependency file to ensure reproducible builds"
        ))

    # Check file sizes
    total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total_size > 100 * 1024 * 1024:  # 100MB
        errors.append(ValidationError(
            code="SIZE_LIMIT_EXCEEDED",
            message=f"Total size ({total_size // 1024 // 1024}MB) exceeds 100MB limit",
            severity="error"
        ))

    # Check for sensitive files
    sensitive_patterns = [".env", "credentials", "secrets", "*.pem", "*.key"]
    for pattern in sensitive_patterns:
        matches = list(path.glob(f"**/{pattern}"))
        if matches:
            warnings.append(ValidationWarning(
                code="SENSITIVE_FILE_DETECTED",
                message=f"Potentially sensitive file detected: {matches[0]}",
                suggestion="Remove sensitive files before importing"
            ))

    return StageResult(errors=errors, warnings=warnings)
```

#### 3.6.3 Dependency Validation

```python
async def _validate_dependencies(self, path: Path) -> StageResult:
    errors = []
    warnings = []

    deps = await self._extract_dependencies(path)

    # Check mellea is included
    mellea_dep = next((d for d in deps.packages if d.name == "mellea"), None)
    if not mellea_dep:
        warnings.append(ValidationWarning(
            code="MISSING_MELLEA",
            message="mellea package not in dependencies",
            suggestion="Add 'mellea>=0.5.0' to use @generative decorators"
        ))

    # Check for known incompatible packages
    incompatible = ["tensorflow-gpu", "torch-cuda"]  # Example
    for pkg in deps.packages:
        if pkg.name in incompatible:
            errors.append(ValidationError(
                code="GPU_PACKAGE_DETECTED",
                message=f"Package '{pkg.name}' requires GPU (not supported)",
                severity="error"
            ))

    # Check Python version compatibility
    if deps.pythonVersion:
        if not self._version_compatible(deps.pythonVersion, ">=3.9,<3.13"):
            errors.append(ValidationError(
                code="PYTHON_VERSION_INCOMPATIBLE",
                message=f"Python {deps.pythonVersion} not supported (need 3.9-3.12)",
                severity="error"
            ))

    return StageResult(errors=errors, warnings=warnings)
```

#### 3.6.4 Syntax Validation

```python
async def _validate_syntax(self, path: Path) -> StageResult:
    errors = []
    warnings = []

    for py_file in path.rglob("*.py"):
        try:
            with open(py_file) as f:
                source = f.read()
            ast.parse(source)
        except SyntaxError as e:
            errors.append(ValidationError(
                code="SYNTAX_ERROR",
                message=f"Syntax error in {py_file.relative_to(path)}",
                details={
                    "line": e.lineno,
                    "column": e.offset,
                    "text": e.text
                },
                severity="error"
            ))

    return StageResult(errors=errors, warnings=warnings)
```

### 3.7 Slot Detection

#### 3.7.1 AST-Based Detection

```python
class SlotDetector:
    """Detect @generative slots and other mellea decorators."""

    MELLEA_DECORATORS = ["generative", "verifier", "requirement"]

    async def detect_slots(self, workspace_path: Path) -> List[SlotMetadata]:
        slots = []

        for py_file in workspace_path.rglob("*.py"):
            file_slots = await self._analyze_file(py_file, workspace_path)
            slots.extend(file_slots)

        return slots

    async def _analyze_file(
        self,
        file_path: Path,
        workspace_root: Path
    ) -> List[SlotMetadata]:
        slots = []

        with open(file_path) as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []  # Skip files with syntax errors

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = self._get_decorator_names(node)

                if "generative" in decorators:
                    slots.append(SlotMetadata(
                        name=node.name,
                        qualifiedName=self._get_qualified_name(
                            file_path, workspace_root, node.name
                        ),
                        docstring=ast.get_docstring(node),
                        signature=self._extract_signature(node),
                        decorators=[f"@{d}" for d in decorators],
                        sourceFile=str(file_path.relative_to(workspace_root)),
                        lineNumber=node.lineno
                    ))

        return slots

    def _extract_signature(self, func: ast.FunctionDef) -> SlotSignature:
        """Extract typed signature from function definition."""
        args = []

        for arg in func.args.args:
            if arg.arg == "self":
                continue

            arg_type = "Any"
            if arg.annotation:
                arg_type = self._annotation_to_string(arg.annotation)

            args.append({
                "name": arg.arg,
                "type": arg_type,
                "description": None  # Could parse from docstring
            })

        return_type = "Any"
        if func.returns:
            return_type = self._annotation_to_string(func.returns)

        return SlotSignature(
            name=func.name,
            docstring=ast.get_docstring(func),
            args=args,
            returns={"type": return_type}
        )

    def _annotation_to_string(self, annotation: ast.expr) -> str:
        """Convert AST annotation to string representation."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Subscript):
            # Handle List[str], Dict[str, int], etc.
            base = self._annotation_to_string(annotation.value)
            if isinstance(annotation.slice, ast.Tuple):
                args = ", ".join(
                    self._annotation_to_string(a) for a in annotation.slice.elts
                )
            else:
                args = self._annotation_to_string(annotation.slice)
            return f"{base}[{args}]"
        else:
            return ast.unparse(annotation)
```

#### 3.7.2 Slot Detection Example

Given this source file:

```python
# src/summarizer.py
from mellea import generative

@generative
def summarize(document: str, max_length: int = 100) -> str:
    """
    Summarize a document into key points.

    Args:
        document: The text to summarize
        max_length: Maximum summary length in words

    Returns:
        A concise summary of the document
    """
    ...
```

Detected slot metadata:

```json
{
  "name": "summarize",
  "qualifiedName": "src.summarizer.summarize",
  "docstring": "Summarize a document into key points.\n\nArgs:\n    document: The text to summarize\n    max_length: Maximum summary length in words\n\nReturns:\n    A concise summary of the document",
  "signature": {
    "name": "summarize",
    "args": [
      {"name": "document", "type": "str", "description": "The text to summarize"},
      {"name": "max_length", "type": "int", "description": "Maximum summary length in words"}
    ],
    "returns": {"type": "str", "description": "A concise summary of the document"}
  },
  "decorators": ["@generative"],
  "sourceFile": "src/summarizer.py",
  "lineNumber": 4
}
```

### 3.8 Clone & Fork

#### 3.8.1 Clone Flow

```typescript
// Clone creates a copy owned by current user
POST /api/v1/programs/{id}/clone
{
  "name": "My Copy of Document Summarizer",  // Optional, defaults to "{original} (Copy)"
  "description": "...",                       // Optional, copies original
  "tags": ["cloned"]                          // Optional, copies original + adds "cloned"
}

// Response
{
  "id": "prog-new-id",
  "name": "My Copy of Document Summarizer",
  "clonedFrom": {
    "id": "prog-original-id",
    "name": "Document Summarizer",
    "owner": "user-123"
  },
  ...
}
```

#### 3.8.2 What Gets Cloned

| Asset Type | Cloned | Notes |
|------------|--------|-------|
| **Program** | All files, metadata, resource profile | New workspace directory created |
| **Model** | Config, params, access control | Credential refs NOT copied (must add own) |
| **Composition** | Graph, spec, referenced asset IDs | References point to original assets |

### 3.9 Import API Summary

```typescript
// All import-related endpoints

// Manual creation
POST   /api/v1/programs                      Create program with files
POST   /api/v1/models                        Create model config
POST   /api/v1/compositions                  Create composition

// GitHub import
POST   /api/v1/programs/import/github/analyze    Analyze repository
POST   /api/v1/programs/import/github/confirm    Confirm and import

// Upload import
POST   /api/v1/programs/import/upload        Upload and analyze files
POST   /api/v1/programs/import/upload/confirm Confirm upload

// Clone
POST   /api/v1/programs/{id}/clone           Clone program
POST   /api/v1/models/{id}/clone             Clone model
POST   /api/v1/compositions/{id}/clone       Clone composition

// Validation
POST   /api/v1/programs/validate             Validate files without creating
GET    /api/v1/programs/{id}/slots           Re-scan for slots

// Templates
GET    /api/v1/templates/programs            List program templates
GET    /api/v1/templates/compositions        List composition templates
```

