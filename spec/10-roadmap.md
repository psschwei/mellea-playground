# 10. Implementation Roadmap

This roadmap references specific components from the detailed specifications in Sections 2-7.

## Phase 0 – Foundations

**Goal**: Establish infrastructure and core abstractions.

### 0.1 Infrastructure Setup
- [ ] Provision Kubernetes cluster with namespace isolation
- [ ] Configure shared NFS storage for assets and artifacts
- [ ] Set up Redis for log streaming and caching
- [ ] Deploy CI/CD pipeline (GitHub Actions or similar)
- [ ] Configure container registry for environment images

### 0.2 Backend Scaffolding
- [ ] Initialize FastAPI project with Pydantic models
- [ ] Implement `JsonStore` class with thread-safe RLock (ref: Section 2.6)
- [ ] Set up directory structure: `data/{assets,users,runs,compositions}/`
- [ ] Configure OpenTelemetry for observability

### 0.3 Authentication Foundation
- [ ] Implement `User` model with roles enum (ref: Section 7.1)
- [ ] Set up dual auth: local JWT + OAuth stub (ref: Section 7.2)
- [ ] Create `get_current_user` dependency for route protection
- [ ] Seed initial admin user

### 0.4 Frontend Scaffolding
- [ ] Initialize React + Chakra UI project
- [ ] Set up React Router with auth-protected routes
- [ ] Create base layout components (sidebar, header)
- [ ] Configure API client with auth token handling

**Exit Criteria**: Can authenticate, store/retrieve JSON documents, deploy to K8s.

---

## Phase 1 – Catalog & Import MVP

**Goal**: Users can create, import, and browse programs and models.

### 1.1 Asset Storage Layer
- [ ] Implement `Asset` base interface with universal metadata (ref: Section 2.2)
- [ ] Implement `Program` asset type with slot signatures (ref: Section 2.3)
- [ ] Implement `Model` asset type with provider configs (ref: Section 2.4)
- [ ] Create `AssetService` with CRUD operations

### 1.2 Catalog API
- [ ] `POST /api/assets` - Create asset with metadata
- [ ] `GET /api/assets` - List with filters (type, owner, tags, visibility)
- [ ] `GET /api/assets/{id}` - Get asset details
- [ ] `PUT /api/assets/{id}` - Update metadata
- [ ] `DELETE /api/assets/{id}` - Soft delete with ownership check

### 1.3 Import Flows
- [ ] Implement `ProgramCreationWizard` component (ref: Section 3.1)
- [ ] Build `GitHubImportService` with repo cloning (ref: Section 3.2)
- [ ] Create drag-and-drop `ArchiveUploader` component (ref: Section 3.3)
- [ ] Implement `ProgramValidator` with AST-based slot detection (ref: Section 3.6)
- [ ] Add `requirements.txt` parser for dependency extraction

### 1.4 Model Configuration
- [ ] Create `ModelConfigForm` for provider selection (ref: Section 3.4)
- [ ] Implement credential reference picker (no plaintext storage)
- [ ] Add model testing endpoint for connectivity validation

### 1.5 Catalog UI
- [ ] Build `CatalogPage` with tabs (My Assets, Shared, Public)
- [ ] Create `AssetCard` component with type icons and status badges
- [ ] Implement `AssetDetailPage` with file browser
- [ ] Add metadata editing panel
- [ ] Create search/filter bar with tag chips

**Exit Criteria**: Can create programs manually, import from GitHub, configure models, browse catalog.

---

## Phase 2 – Environment Provisioning & Execution

**Goal**: Users can run programs in isolated containers with live logs.

### 2.1 Container Build Pipeline
- [ ] Create base images: `mellea-python:3.11`, `mellea-python:3.12` (ref: Section 4.2)
- [ ] Implement `EnvironmentBuilder` with layer caching (ref: Section 4.1)
- [ ] Build dependency installation layer with pip cache
- [ ] Set up container registry push/pull

### 2.2 Environment Lifecycle
- [ ] Implement `EnvironmentService` with state machine (ref: Section 4.4)
- [ ] Create Kubernetes Job/Pod templates with resource limits (ref: Section 4.5)
- [ ] Add idle timeout controller for cost management
- [ ] Implement environment warmup for faster starts

### 2.3 Credential Management
- [ ] Create `CredentialService` for secure storage (ref: Section 4.6)
- [ ] Implement Kubernetes Secret injection at runtime
- [ ] Add credential validation before run start
- [ ] Build credential management UI

### 2.4 Run Service
- [ ] Implement `Run` model with status state machine (ref: Section 5.1, 5.2)
- [ ] Create `RunService` with create/queue/execute flow (ref: Section 5.3)
- [ ] Build `RunExecutor` for Kubernetes job submission
- [ ] Implement run cancellation with graceful shutdown

### 2.5 Log Streaming
- [ ] Implement `LogService` with Redis pub/sub (ref: Section 5.4.2)
- [ ] Create SSE endpoint `/runs/{id}/logs/stream` (ref: Section 5.4.3)
- [ ] Build `LogViewer` React component with auto-scroll (ref: Section 5.4.4)
- [ ] Add log download functionality

### 2.6 Artifacts & Metrics
- [ ] Implement `ArtifactCollector` with quota enforcement (ref: Section 5.5.2)
- [ ] Create `RetentionPolicy` for automatic cleanup (ref: Section 5.5.3)
- [ ] Build `MetricsCollector` for LLM usage tracking (ref: Section 5.7.1)
- [ ] Implement `ModelPricing` for cost estimation

### 2.7 Run Dashboard
- [ ] Create `RunsDashboard` with filters (ref: Section 5.6.1)
- [ ] Build `RunStatusBadge` component (ref: Section 5.6.2)
- [ ] Implement `RunDetailPage` with tabs (ref: Section 5.6.3)
- [ ] Add `RunControls` for cancel/retry (ref: Section 5.9.2)

### 2.8 Container Security
- [ ] Apply network policies for pod isolation (ref: Section 4.7)
- [ ] Configure seccomp profiles
- [ ] Set up egress rules for LLM API access only
- [ ] Implement resource quotas per user

**Exit Criteria**: Can run programs, stream logs live, capture artifacts, view metrics and costs.

---

## Phase 3 – Collaboration & Access Control

**Goal**: Users can share assets and collaborate with role-based permissions.

### 3.1 Permission System
- [ ] Implement `PermissionService` with ACL checks (ref: Section 7.4)
- [ ] Create permission levels: view, edit, execute, admin
- [ ] Add `@require_permission` decorator for routes
- [ ] Build `AccessControlList` model for assets

### 3.2 Sharing Mechanics
- [ ] Implement `SharingService` with user/link sharing (ref: Section 7.5)
- [ ] Create `ShareDialog` component
- [ ] Add share link generation with expiry
- [ ] Build "Shared with me" view

### 3.3 Run Permissions
- [ ] Implement credential delegation for shared runs (ref: Section 7.6)
- [ ] Add run visibility controls (private, shared, public)
- [ ] Create run access audit trail

### 3.4 Audit & Notifications
- [ ] Implement `AuditService` for action logging (ref: Section 7.7)
- [ ] Create `NotificationService` with WebSocket push (ref: Section 7.8)
- [ ] Build notification preferences UI (ref: Section 5.10.2)
- [ ] Add email notifications for long-running jobs

### 3.5 Admin Tools
- [ ] Create admin dashboard for user management (ref: Section 7.9)
- [ ] Implement role assignment UI
- [ ] Add usage quota monitoring
- [ ] Build impersonation feature for support

**Exit Criteria**: Can share assets, control permissions, receive notifications, audit actions.

---

## Phase 4 – Visual Builder MVP

**Goal**: Users can compose workflows visually with drag-and-drop.

### 4.1 Canvas Foundation
- [ ] Set up ReactFlow with custom theme (ref: Section 6.1)
- [ ] Implement canvas state management with `useNodesState`/`useEdgesState`
- [ ] Add zoom, pan, minimap controls
- [ ] Create selection and multi-select handling

### 4.2 Node System
- [ ] Implement `MelleaNodeData` interface (ref: Section 6.2.1)
- [ ] Create `ProgramNode` component with slot handles
- [ ] Create `ModelNode` component with provider badge
- [ ] Create `PrimitiveNode` for loops, conditionals, merge
- [ ] Build `UtilityNode` for input/output/notes

### 4.3 Sidebar & Palette
- [ ] Create `BuilderSidebar` with categorized sections (ref: Section 6.3)
- [ ] Implement drag-from-palette to canvas
- [ ] Add asset search within sidebar
- [ ] Build "Recently Used" section

### 4.4 Connections & Validation
- [ ] Implement edge styling by category (ref: Section 6.4)
- [ ] Create `ConnectionValidator` for type checking (ref: Section 6.5)
- [ ] Add visual feedback for invalid connections
- [ ] Implement auto-layout for messy graphs

### 4.5 Composition Storage
- [ ] Create `Composition` asset type
- [ ] Implement save/load with versioning
- [ ] Add composition metadata (name, description, tags)
- [ ] Build composition list view

### 4.6 Code Generation
- [ ] Implement `CodeGenerator` from graph (ref: Section 6.6)
- [ ] Create code preview panel
- [ ] Add export to standalone Python script

### 4.7 Composition Execution
- [ ] Implement `CompositionExecutor` service (ref: Section 6.9)
- [ ] Add per-node status visualization during run
- [ ] Create execution debugging with node-level logs
- [ ] Implement partial re-run from failed node

**Exit Criteria**: Can build workflows visually, save compositions, execute with per-node status.

---

## Phase 5 – AI Assistant & Automation (Future)

**Goal**: AI-assisted program creation and workflow automation.

### 5.1 Chat Interface
- [ ] Create assistant chat panel
- [ ] Integrate with OpenAI-compatible API
- [ ] Implement context injection (current asset, selection)

### 5.2 Generation Workflows
- [ ] "Create program" from natural language description
- [ ] "Add node" suggestions based on workflow context
- [ ] Code completion within program editor

### 5.3 Approval & Safety
- [ ] Diff preview for AI-generated changes
- [ ] Approval prompts before applying changes
- [ ] Audit trail for AI actions

### 5.4 Automation API
- [ ] REST API for triggering runs externally
- [ ] Webhook notifications for run completion
- [ ] CLI tool for local development integration

**Exit Criteria**: Can use AI to generate programs, automate via API.

---

## Phase 6 – Evaluations & Advanced Features (Future)

**Goal**: Systematic evaluation of programs across models.

### 6.1 Dataset Registry
- [ ] Create `DataCollection` asset type with versioning
- [ ] Build dataset upload and preview UI
- [ ] Implement dataset splitting (train/test/validation)

### 6.2 Experiment Framework
- [ ] Define `Experiment` schema with parameter sweeps
- [ ] Implement experiment runner with parallel runs
- [ ] Create comparison dashboard

### 6.3 Scoring & Metrics
- [ ] Build pluggable scoring adapters
- [ ] Implement human annotation UI
- [ ] Create leaderboard views

### 6.4 Advanced Operations
- [ ] Multi-region deployment support
- [ ] High-availability configuration
- [ ] Advanced quota management

**Exit Criteria**: Can run systematic evaluations, compare results, scale deployment.

---

## Summary Timeline

| Phase | Focus | Key Deliverables |
|-------|-------|------------------|
| 0 | Foundations | Auth, storage, infrastructure |
| 1 | Catalog | Asset CRUD, import flows, UI |
| 2 | Execution | Containers, runs, logs, metrics |
| 3 | Collaboration | Sharing, permissions, audit |
| 4 | Visual Builder | Canvas, nodes, composition execution |
| 5 | AI Assistant | Chat, generation, automation API |
| 6 | Evaluations | Datasets, experiments, scaling |

Each phase builds on the previous. Phases 0-4 constitute the MVP.
