// User types
export type UserRole = 'end_user' | 'developer' | 'admin';
export type UserStatus = 'active' | 'suspended' | 'pending';

export interface User {
  id: string;
  email: string;
  username?: string;
  displayName: string;
  avatarUrl?: string;
  role: UserRole;
  status: UserStatus;
}

export interface UserQuotas {
  maxConcurrentRuns: number;
  maxStorageMB: number;
  maxCpuHoursPerMonth: number;
  maxRunsPerDay: number;
}

// Auth types
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  displayName: string;
  username?: string;
}

export interface TokenResponse {
  token: string;
  expiresAt: string;
  user: User;
}

export interface AuthConfig {
  mode: string;
  providers: string[];
  registrationEnabled: boolean;
  sessionDurationHours: number;
}

// Asset types
export type SharingMode = 'private' | 'shared' | 'public';
export type RunStatus = 'never_run' | 'succeeded' | 'failed';

export interface AssetMetadata {
  id: string;
  name: string;
  description: string;
  tags: string[];
  version: string;
  owner: string;
  sharing: SharingMode;
  createdAt: string;
  updatedAt: string;
  lastRunStatus?: RunStatus;
  lastRunAt?: string;
}

// Program types
export type ImageBuildStatus = 'pending' | 'building' | 'ready' | 'failed';

export interface ResourceProfile {
  cpuLimit: string;
  memoryLimit: string;
  timeoutSeconds: number;
}

export interface ProgramDependencies {
  source: 'pyproject' | 'requirements' | 'manual';
  packages: { name: string; version?: string }[];
  pythonVersion?: string;
}

export interface ProgramAsset extends AssetMetadata {
  type: 'program';
  entrypoint: string;
  sourceCode?: string;
  dependencies?: ProgramDependencies;
  resourceProfile?: ResourceProfile;
  imageTag?: string;
  imageBuildStatus?: ImageBuildStatus;
  imageBuildError?: string;
}

// Run types
export type RunExecutionStatus =
  | 'queued'
  | 'starting'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface RunMetrics {
  queueDurationMs?: number;
  startupDurationMs?: number;
  executionDurationMs?: number;
  totalDurationMs?: number;
}

export interface Run {
  id: string;
  programId: string;
  environmentId?: string;
  status: RunExecutionStatus;
  jobName?: string;
  exitCode?: number;
  errorMessage?: string;
  output?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  metrics?: RunMetrics;
}

// Create request types
export interface CreateProgramRequest {
  type: 'program';
  name: string;
  description?: string;
  entrypoint: string;
  sourceCode: string;
  tags?: string[];
}

export interface CreateRunRequest {
  programId: string;
}

export interface BuildImageRequest {
  forceRebuild?: boolean;
  push?: boolean;
}

export interface BuildResult {
  programId: string;
  success: boolean;
  imageTag?: string;
  cacheHit: boolean;
  errorMessage?: string;
  totalDurationSeconds: number;
  depsBuildDurationSeconds?: number;
  programBuildDurationSeconds?: number;
}

// Credential types
export type CredentialType =
  | 'api_key'
  | 'registry'
  | 'database'
  | 'oauth_token'
  | 'ssh_key'
  | 'custom';

export type ModelProvider =
  | 'openai'
  | 'anthropic'
  | 'ollama'
  | 'azure'
  | 'custom';

export interface Credential {
  id: string;
  name: string;
  description: string;
  type: CredentialType;
  provider?: ModelProvider | string;
  ownerId?: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  lastAccessedAt?: string;
  expiresAt?: string;
  isExpired: boolean;
}

export interface CreateCredentialRequest {
  name: string;
  description?: string;
  type: CredentialType;
  provider?: ModelProvider | string;
  secretData: Record<string, string>;
  tags?: string[];
  expiresAt?: string;
}

export interface UpdateCredentialRequest {
  name?: string;
  description?: string;
  secretData?: Record<string, string>;
  tags?: string[];
  expiresAt?: string;
}

// Log streaming types
export interface LogEntry {
  runId: string;
  content: string;
  timestamp: string | null;
  isComplete: boolean;
}

export interface LogStreamCompleteEvent {
  status: string;
}

// Model asset types
export type ModelScope = 'chat' | 'agent' | 'composition' | 'all';

export interface EndpointConfig {
  baseUrl: string;
  apiVersion?: string;
  headers?: Record<string, string>;
}

export interface ModelParams {
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  frequencyPenalty?: number;
  presencePenalty?: number;
  stopSequences?: string[];
}

export interface ModelCapabilities {
  contextWindow: number;
  supportsStreaming?: boolean;
  supportsToolCalling?: boolean;
  supportedModalities?: string[];
  languages?: string[];
}

export interface AccessControl {
  endUsers?: boolean;
  developers?: boolean;
  admins?: boolean;
}

export interface ModelAsset extends AssetMetadata {
  type: 'model';
  provider: ModelProvider;
  modelId: string;
  endpoint?: EndpointConfig;
  credentialsRef?: string;
  defaultParams?: ModelParams;
  capabilities?: ModelCapabilities;
  accessControl?: AccessControl;
  scope?: ModelScope;
}

export interface CreateModelRequest {
  type: 'model';
  name: string;
  description?: string;
  provider: ModelProvider;
  modelId: string;
  endpoint?: EndpointConfig;
  credentialsRef?: string;
  defaultParams?: ModelParams;
  capabilities?: ModelCapabilities;
  accessControl?: AccessControl;
  scope?: ModelScope;
  tags?: string[];
}

export interface TestModelRequest {
  prompt?: string;
}

export interface TestModelResponse {
  success: boolean;
  response?: string;
  error?: string;
  latencyMs?: number;
}

// Composition asset types (spec 6.11.1)

/** Viewport state for composition canvas */
export interface CompositionViewport {
  x: number;
  y: number;
  zoom: number;
}

/** Input parameter definition for composition */
export interface CompositionInput {
  name: string;
  type: string;
  required: boolean;
  defaultValue?: unknown;
  description?: string;
}

/** Output definition for composition */
export interface CompositionOutput {
  name: string;
  type: string;
  description?: string;
}

/** Serialized node for composition storage */
export interface CompositionNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    category: 'program' | 'model' | 'primitive' | 'utility';
    icon?: string;
    parameters?: Record<string, unknown>;
    [key: string]: unknown;
  };
}

/** Edge definition for composition graph */
export interface CompositionEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  animated?: boolean;
  style?: { stroke?: string };
  label?: string;
  dataType?: string;
}

/** Graph structure for composition */
export interface CompositionGraph {
  nodes: CompositionNode[];
  edges: CompositionEdge[];
  viewport: CompositionViewport;
}

/** Executable specification for headless runs */
export interface CompositionSpec {
  inputs: CompositionInput[];
  outputs: CompositionOutput[];
  nodeExecutionOrder: string[];
  generatedCode?: string;
}

/** Full composition asset with graph and spec */
export interface CompositionAsset extends AssetMetadata {
  type: 'composition';

  /** Visual graph definition */
  graph: CompositionGraph;

  /** Executable specification for headless runs */
  spec: CompositionSpec;

  /** IDs of referenced program assets */
  programRefs: string[];

  /** IDs of referenced model assets */
  modelRefs: string[];
}

// Union type for all asset types
export type Asset = ProgramAsset | ModelAsset | CompositionAsset;

// Asset type literal
export type AssetType = 'program' | 'model' | 'composition';

// API response types
export interface ApiError {
  detail: string;
}
