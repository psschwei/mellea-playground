/**
 * In-memory mock store for all application state.
 * Replaces the backend API — all data lives here during a browser session.
 */

import type {
  User,
  UserRole,
  UserStatus,
  UserQuotas,
  ProgramAsset,
  ModelAsset,
  CompositionAsset,
  Run,
  RunExecutionStatus,
  Credential,
  ShareLink,
  SharingMode,
} from '@/types';
import type { NotificationPreferences } from './notifications';
import type { CompositionRun, NodeExecutionState } from './compositionRuns';

// =============================================================================
// Helpers
// =============================================================================

export function generateId(): string {
  return crypto.randomUUID();
}

export function now(): string {
  return new Date().toISOString();
}

export function delay(ms: number = 80): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Password store (email -> password)
// =============================================================================

export const passwords = new Map<string, string>();

// =============================================================================
// Users
// =============================================================================

interface StoredUser extends User {
  createdAt: string;
  lastLoginAt?: string;
  quotas?: UserQuotas;
}

export const users = new Map<string, StoredUser>();

const demoUser: StoredUser = {
  id: 'user-demo-001',
  email: 'demo@mellea.dev',
  username: 'demo',
  displayName: 'Demo Developer',
  role: 'developer' as UserRole,
  status: 'active' as UserStatus,
  createdAt: '2025-11-15T10:00:00.000Z',
  lastLoginAt: '2026-03-24T14:30:00.000Z',
  quotas: {
    maxConcurrentRuns: 5,
    maxStorageMB: 1024,
    maxCpuHoursPerMonth: 100,
    maxRunsPerDay: 50,
  },
};

const adminUser: StoredUser = {
  id: 'user-admin-001',
  email: 'admin@mellea.dev',
  username: 'admin',
  displayName: 'Platform Admin',
  role: 'admin' as UserRole,
  status: 'active' as UserStatus,
  createdAt: '2025-10-01T08:00:00.000Z',
  lastLoginAt: '2026-03-25T09:00:00.000Z',
  quotas: {
    maxConcurrentRuns: 20,
    maxStorageMB: 10240,
    maxCpuHoursPerMonth: 1000,
    maxRunsPerDay: 200,
  },
};

users.set(demoUser.id, demoUser);
users.set(adminUser.id, adminUser);
passwords.set('demo@mellea.dev', 'demo123');
passwords.set('admin@mellea.dev', 'admin123');

// Current session state
export let currentUserId: string | null = null;
export let impersonatingFromId: string | null = null;

export function setCurrentUserId(id: string | null) {
  currentUserId = id;
}

export function setImpersonatingFromId(id: string | null) {
  impersonatingFromId = id;
}

export function getCurrentUser(): StoredUser | null {
  if (!currentUserId) return null;
  return users.get(currentUserId) ?? null;
}

export function getUserByEmail(email: string): StoredUser | undefined {
  for (const u of users.values()) {
    if (u.email === email) return u;
  }
  return undefined;
}

// =============================================================================
// Programs
// =============================================================================

export const programs = new Map<string, ProgramAsset>();

const prog1: ProgramAsset = {
  id: 'prog-001',
  type: 'program',
  name: 'Hello World',
  description: 'A simple Python program that prints a greeting message.',
  tags: ['starter', 'python'],
  version: '1.0.0',
  owner: 'user-demo-001',
  sharing: 'private',
  createdAt: '2026-01-10T12:00:00.000Z',
  updatedAt: '2026-01-10T12:00:00.000Z',
  lastRunStatus: 'succeeded',
  lastRunAt: '2026-03-20T15:30:00.000Z',
  entrypoint: 'main.py',
  sourceCode: `def main():\n    print("Hello from Mellea!")\n    print("This is a simple demo program.")\n\nif __name__ == "__main__":\n    main()\n`,
  imageBuildStatus: 'ready',
  imageTag: 'mellea/hello-world:1.0.0',
};

const prog2: ProgramAsset = {
  id: 'prog-002',
  type: 'program',
  name: 'Data Analyzer',
  description: 'Analyzes CSV data using pandas and generates summary statistics.',
  tags: ['data-science', 'pandas', 'analysis'],
  version: '2.1.0',
  owner: 'user-demo-001',
  sharing: 'private',
  createdAt: '2026-02-05T09:00:00.000Z',
  updatedAt: '2026-03-15T11:00:00.000Z',
  lastRunStatus: 'succeeded',
  lastRunAt: '2026-03-22T10:15:00.000Z',
  entrypoint: 'analyzer.py',
  sourceCode: `import pandas as pd\nimport numpy as np\n\ndef analyze(data_path: str) -> dict:\n    df = pd.read_csv(data_path)\n    return {\n        "shape": df.shape,\n        "columns": list(df.columns),\n        "summary": df.describe().to_dict(),\n    }\n\nif __name__ == "__main__":\n    result = analyze("data.csv")\n    print(result)\n`,
  dependencies: {
    source: 'manual',
    packages: [
      { name: 'pandas', version: '2.2.0' },
      { name: 'numpy', version: '1.26.0' },
    ],
    pythonVersion: '3.11',
  },
  imageBuildStatus: 'ready',
  imageTag: 'mellea/data-analyzer:2.1.0',
};

const prog3: ProgramAsset = {
  id: 'prog-003',
  type: 'program',
  name: 'LLM Chat Bot',
  description: 'A generative AI chatbot that uses LLM slots for conversational responses.',
  tags: ['ai', 'llm', 'chatbot', 'generative'],
  version: '0.3.0',
  owner: 'user-demo-001',
  sharing: 'shared',
  createdAt: '2026-03-01T14:00:00.000Z',
  updatedAt: '2026-03-20T16:00:00.000Z',
  lastRunStatus: 'failed',
  lastRunAt: '2026-03-20T16:10:00.000Z',
  entrypoint: 'chatbot.py',
  sourceCode: `from mellea import generative\n\n@generative\ndef respond(user_message: str) -> str:\n    """Generate a response to the user's message."""\n    pass\n\ndef main():\n    print("Chat Bot started!")\n    response = respond("Hello, how are you?")\n    print(f"Bot: {response}")\n\nif __name__ == "__main__":\n    main()\n`,
  dependencies: {
    source: 'manual',
    packages: [{ name: 'openai', version: '1.12.0' }],
    pythonVersion: '3.11',
  },
  imageBuildStatus: 'pending',
};

programs.set(prog1.id, prog1);
programs.set(prog2.id, prog2);
programs.set(prog3.id, prog3);

// =============================================================================
// Models
// =============================================================================

export const models = new Map<string, ModelAsset>();

const model1: ModelAsset = {
  id: 'model-001',
  type: 'model',
  name: 'GPT-4o',
  description: 'OpenAI GPT-4o — fast, multimodal model for general-purpose tasks.',
  tags: ['openai', 'multimodal', 'production'],
  version: '1.0.0',
  owner: 'user-demo-001',
  sharing: 'shared',
  createdAt: '2026-01-20T10:00:00.000Z',
  updatedAt: '2026-02-10T12:00:00.000Z',
  provider: 'openai',
  modelId: 'gpt-4o',
  credentialsRef: 'cred-001',
  defaultParams: { temperature: 0.7, maxTokens: 4096 },
  capabilities: {
    contextWindow: 128000,
    supportsStreaming: true,
    supportsToolCalling: true,
    supportedModalities: ['text', 'image'],
  },
  scope: 'all',
};

const model2: ModelAsset = {
  id: 'model-002',
  type: 'model',
  name: 'Claude Sonnet',
  description: 'Anthropic Claude Sonnet 4 — strong reasoning and coding capabilities.',
  tags: ['anthropic', 'coding', 'production'],
  version: '1.0.0',
  owner: 'user-demo-001',
  sharing: 'private',
  createdAt: '2026-02-01T08:00:00.000Z',
  updatedAt: '2026-03-10T14:00:00.000Z',
  provider: 'anthropic',
  modelId: 'claude-sonnet-4-20250514',
  credentialsRef: 'cred-002',
  defaultParams: { temperature: 0.5, maxTokens: 8192 },
  capabilities: {
    contextWindow: 200000,
    supportsStreaming: true,
    supportsToolCalling: true,
    supportedModalities: ['text', 'image'],
  },
  scope: 'all',
};

const model3: ModelAsset = {
  id: 'model-003',
  type: 'model',
  name: 'Local Llama',
  description: 'Locally-hosted Llama 3.1 8B via Ollama for development and testing.',
  tags: ['ollama', 'local', 'development'],
  version: '1.0.0',
  owner: 'user-demo-001',
  sharing: 'private',
  createdAt: '2026-03-05T16:00:00.000Z',
  updatedAt: '2026-03-05T16:00:00.000Z',
  provider: 'ollama',
  modelId: 'llama3.1:8b',
  endpoint: { baseUrl: 'http://localhost:11434' },
  defaultParams: { temperature: 0.8, maxTokens: 2048 },
  capabilities: {
    contextWindow: 32768,
    supportsStreaming: true,
    supportsToolCalling: false,
    supportedModalities: ['text'],
  },
  scope: 'chat',
};

models.set(model1.id, model1);
models.set(model2.id, model2);
models.set(model3.id, model3);

// =============================================================================
// Compositions
// =============================================================================

export const compositions = new Map<string, CompositionAsset>();

// =============================================================================
// Runs
// =============================================================================

export const runs = new Map<string, Run>();

const run1: Run = {
  id: 'run-001',
  ownerId: 'user-demo-001',
  programId: 'prog-001',
  status: 'succeeded' as RunExecutionStatus,
  visibility: 'private' as SharingMode,
  createdAt: '2026-03-20T15:28:00.000Z',
  startedAt: '2026-03-20T15:28:05.000Z',
  completedAt: '2026-03-20T15:30:00.000Z',
  exitCode: 0,
  output: 'Hello from Mellea!\nThis is a simple demo program.\n',
  metrics: {
    queueDurationMs: 1200,
    startupDurationMs: 3800,
    executionDurationMs: 115000,
    totalDurationMs: 120000,
  },
};

const run2: Run = {
  id: 'run-002',
  ownerId: 'user-demo-001',
  programId: 'prog-002',
  status: 'succeeded' as RunExecutionStatus,
  visibility: 'private' as SharingMode,
  createdAt: '2026-03-22T10:10:00.000Z',
  startedAt: '2026-03-22T10:10:08.000Z',
  completedAt: '2026-03-22T10:15:00.000Z',
  exitCode: 0,
  output: "{'shape': (1000, 5), 'columns': ['id', 'name', 'value', 'category', 'timestamp']}\n",
  metrics: {
    queueDurationMs: 800,
    startupDurationMs: 7200,
    executionDurationMs: 292000,
    totalDurationMs: 300000,
  },
};

const run3: Run = {
  id: 'run-003',
  ownerId: 'user-demo-001',
  programId: 'prog-003',
  status: 'failed' as RunExecutionStatus,
  visibility: 'private' as SharingMode,
  createdAt: '2026-03-20T16:05:00.000Z',
  startedAt: '2026-03-20T16:05:10.000Z',
  completedAt: '2026-03-20T16:10:00.000Z',
  exitCode: 1,
  errorMessage: 'openai.AuthenticationError: API key not configured. Set OPENAI_API_KEY credential.',
  output: 'Chat Bot started!\nTraceback (most recent call last):\n  File "chatbot.py", line 12, in <module>\n    main()\n  ...\nopenai.AuthenticationError: API key not configured.\n',
  metrics: {
    queueDurationMs: 500,
    startupDurationMs: 9500,
    executionDurationMs: 290000,
    totalDurationMs: 300000,
  },
};

runs.set(run1.id, run1);
runs.set(run2.id, run2);
runs.set(run3.id, run3);

// =============================================================================
// Credentials
// =============================================================================

export const credentials = new Map<string, Credential>();

const cred1: Credential = {
  id: 'cred-001',
  name: 'OpenAI API Key',
  description: 'Production OpenAI API key for GPT models.',
  type: 'api_key',
  provider: 'openai',
  ownerId: 'user-demo-001',
  tags: ['openai', 'production'],
  createdAt: '2026-01-15T10:00:00.000Z',
  updatedAt: '2026-03-01T08:00:00.000Z',
  lastAccessedAt: '2026-03-22T10:10:00.000Z',
  isExpired: false,
};

const cred2: Credential = {
  id: 'cred-002',
  name: 'Anthropic API Key',
  description: 'Anthropic API key for Claude models.',
  type: 'api_key',
  provider: 'anthropic',
  ownerId: 'user-demo-001',
  tags: ['anthropic', 'production'],
  createdAt: '2026-02-01T08:00:00.000Z',
  updatedAt: '2026-03-10T14:00:00.000Z',
  isExpired: false,
};

credentials.set(cred1.id, cred1);
credentials.set(cred2.id, cred2);

// =============================================================================
// Share Links
// =============================================================================

export const shareLinks = new Map<string, ShareLink>();

// =============================================================================
// Composition Runs
// =============================================================================

export const compositionRuns = new Map<string, CompositionRun>();

// =============================================================================
// Notification Preferences
// =============================================================================

export const notificationPrefs = new Map<string, NotificationPreferences>();

// =============================================================================
// Run Logs (mock log content per run)
// =============================================================================

export const runLogs = new Map<string, string[]>();

runLogs.set('run-001', [
  '[2026-03-20 15:28:05] Starting program: Hello World',
  '[2026-03-20 15:28:06] Loading runtime environment...',
  '[2026-03-20 15:28:07] Dependencies satisfied.',
  '[2026-03-20 15:28:08] Executing main.py...',
  '[2026-03-20 15:29:50] Hello from Mellea!',
  '[2026-03-20 15:29:50] This is a simple demo program.',
  '[2026-03-20 15:30:00] Program completed with exit code 0.',
]);

runLogs.set('run-002', [
  '[2026-03-22 10:10:08] Starting program: Data Analyzer',
  '[2026-03-22 10:10:10] Installing dependencies: pandas==2.2.0, numpy==1.26.0',
  '[2026-03-22 10:10:30] Dependencies installed successfully.',
  '[2026-03-22 10:10:31] Executing analyzer.py...',
  '[2026-03-22 10:14:50] Analysis complete. Processed 1000 rows.',
  '[2026-03-22 10:15:00] Program completed with exit code 0.',
]);

runLogs.set('run-003', [
  '[2026-03-20 16:05:10] Starting program: LLM Chat Bot',
  '[2026-03-20 16:05:12] Installing dependencies: openai==1.12.0',
  '[2026-03-20 16:05:25] Dependencies installed successfully.',
  '[2026-03-20 16:05:26] Executing chatbot.py...',
  '[2026-03-20 16:05:27] Chat Bot started!',
  '[2026-03-20 16:09:50] ERROR: openai.AuthenticationError: API key not configured.',
  '[2026-03-20 16:10:00] Program failed with exit code 1.',
]);

// =============================================================================
// Run simulation
// =============================================================================

const MOCK_LOG_LINES = [
  'Pulling container image...',
  'Image pulled successfully.',
  'Mounting workspace volume...',
  'Installing dependencies...',
  'Dependencies installed.',
  'Executing program entrypoint...',
  'Processing...',
  'Step 1/3 complete.',
  'Step 2/3 complete.',
  'Step 3/3 complete.',
  'Output generated successfully.',
  'Cleaning up resources...',
  'Program completed with exit code 0.',
];

export function simulateRunExecution(runId: string): void {
  const run = runs.get(runId);
  if (!run) return;

  const logs: string[] = [];
  runLogs.set(runId, logs);

  // queued -> starting after 1s
  setTimeout(() => {
    const r = runs.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'starting';
    r.startedAt = now();
    logs.push(`[${new Date().toISOString()}] Starting program...`);
  }, 1000);

  // starting -> running after 2s
  setTimeout(() => {
    const r = runs.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'running';
    logs.push(`[${new Date().toISOString()}] Runtime environment ready.`);
  }, 2000);

  // Emit log lines every 400ms from 2.5s to ~7.5s
  MOCK_LOG_LINES.forEach((line, i) => {
    setTimeout(() => {
      const r = runs.get(runId);
      if (!r || r.status === 'cancelled') return;
      logs.push(`[${new Date().toISOString()}] ${line}`);
    }, 2500 + i * 400);
  });

  // running -> succeeded after 8s
  setTimeout(() => {
    const r = runs.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'succeeded';
    r.completedAt = now();
    r.exitCode = 0;
    r.output = 'Program output:\nHello from Mellea!\nExecution complete.\n';
    r.metrics = {
      queueDurationMs: 1000,
      startupDurationMs: 1000,
      executionDurationMs: 6000,
      totalDurationMs: 8000,
    };
    logs.push(`[${new Date().toISOString()}] Run completed successfully.`);
  }, 8000);
}

export function simulateCompositionRunExecution(runId: string): void {
  const run = compositionRuns.get(runId);
  if (!run) return;

  const nodeIds = run.executionOrder;
  const logs: string[] = [];
  runLogs.set(runId, logs);

  // queued -> starting
  setTimeout(() => {
    const r = compositionRuns.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'starting';
    r.startedAt = now();
    logs.push(`[${new Date().toISOString()}] Starting composition...`);
  }, 500);

  // starting -> running
  setTimeout(() => {
    const r = compositionRuns.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'running';
  }, 1000);

  // Execute each node sequentially, ~1.5s per node
  nodeIds.forEach((nodeId, i) => {
    const startMs = 1500 + i * 1500;

    setTimeout(() => {
      const r = compositionRuns.get(runId);
      if (!r || r.status === 'cancelled') return;
      r.currentNodeId = nodeId;
      const ns: NodeExecutionState = {
        nodeId,
        status: 'running',
        startedAt: now(),
        completedAt: null,
        output: null,
        errorMessage: null,
        logs: [`Executing node ${nodeId}...`],
      };
      r.nodeStates[nodeId] = ns;
      logs.push(`[${new Date().toISOString()}] Node ${nodeId}: running`);
    }, startMs);

    setTimeout(() => {
      const r = compositionRuns.get(runId);
      if (!r || r.status === 'cancelled') return;
      const ns = r.nodeStates[nodeId];
      if (ns) {
        ns.status = 'succeeded';
        ns.completedAt = now();
        ns.output = `Result from node ${nodeId}`;
        ns.logs.push('Done.');
      }
      logs.push(`[${new Date().toISOString()}] Node ${nodeId}: succeeded`);
    }, startMs + 1200);
  });

  // Final completion
  const totalMs = 1500 + nodeIds.length * 1500 + 500;
  setTimeout(() => {
    const r = compositionRuns.get(runId);
    if (!r || r.status === 'cancelled') return;
    r.status = 'succeeded';
    r.completedAt = now();
    r.currentNodeId = null;
    logs.push(`[${new Date().toISOString()}] Composition completed successfully.`);
  }, totalMs);
}
