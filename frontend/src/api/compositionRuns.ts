import type { RunExecutionStatus } from '@/types';
import {
  delay,
  generateId,
  now,
  compositionRuns,
  compositions,
  currentUserId,
  simulateCompositionRunExecution,
  runLogs,
} from './mock-store';

// =============================================================================
// Types
// =============================================================================

export type NodeExecutionStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped';

export interface NodeExecutionState {
  nodeId: string;
  status: NodeExecutionStatus;
  startedAt: string | null;
  completedAt: string | null;
  output: unknown | null;
  errorMessage: string | null;
  logs: string[];
}

export interface CompositionRun {
  id: string;
  ownerId: string;
  environmentId: string;
  compositionId: string;
  status: RunExecutionStatus;
  jobName: string | null;
  exitCode: number | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  output: string | null;
  executionOrder: string[];
  nodeStates: Record<string, NodeExecutionState>;
  generatedCode: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  currentNodeId: string | null;
  credentialIds: string[];
}

export interface CreateCompositionRunRequest {
  compositionId: string;
  environmentId: string;
  inputs?: Record<string, unknown>;
  credentialIds?: string[];
  validate?: boolean;
}

export interface ProgressResponse {
  total: number;
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
  skipped: number;
  currentNodeId: string | null;
  nodeStates: Record<string, NodeExecutionState>;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  programIds: string[];
  modelIds: string[];
}

export interface GeneratedCodeResponse {
  code: string;
  executionOrder: string[];
  warnings: string[];
}

export interface ResumeRunResponse {
  run: CompositionRun;
  originalRunId: string;
  resumedFromNode: string;
  skippedNodes: string[];
}

// =============================================================================
// API Client
// =============================================================================

export const compositionRunsApi = {
  create: async (data: CreateCompositionRunRequest): Promise<CompositionRun> => {
    await delay(200);
    const comp = compositions.get(data.compositionId);
    const executionOrder = comp?.spec?.nodeExecutionOrder || ['node-1', 'node-2', 'node-3'];
    const id = generateId();

    const nodeStates: Record<string, NodeExecutionState> = {};
    for (const nid of executionOrder) {
      nodeStates[nid] = {
        nodeId: nid,
        status: 'pending',
        startedAt: null,
        completedAt: null,
        output: null,
        errorMessage: null,
        logs: [],
      };
    }

    const run: CompositionRun = {
      id,
      ownerId: currentUserId || 'unknown',
      environmentId: data.environmentId,
      compositionId: data.compositionId,
      status: 'queued',
      jobName: `comp-job-${id.slice(0, 8)}`,
      exitCode: null,
      errorMessage: null,
      createdAt: now(),
      startedAt: null,
      completedAt: null,
      output: null,
      executionOrder,
      nodeStates,
      generatedCode: `# Auto-generated composition runner\nimport asyncio\n\nasync def run_composition():\n${executionOrder.map((n) => `    await execute_node("${n}")`).join('\n')}\n\nasyncio.run(run_composition())\n`,
      inputs: data.inputs || {},
      outputs: {},
      currentNodeId: null,
      credentialIds: data.credentialIds || [],
    };
    compositionRuns.set(id, run);
    simulateCompositionRunExecution(id);
    return run;
  },

  get: async (id: string): Promise<CompositionRun> => {
    await delay();
    const run = compositionRuns.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Composition run not found' } } };
    return run;
  },

  list: async (params?: {
    compositionId?: string;
    status?: RunExecutionStatus;
  }): Promise<CompositionRun[]> => {
    await delay();
    let result = Array.from(compositionRuns.values());
    if (params?.compositionId) result = result.filter((r) => r.compositionId === params.compositionId);
    if (params?.status) result = result.filter((r) => r.status === params.status);
    return result;
  },

  getProgress: async (id: string): Promise<ProgressResponse> => {
    await delay();
    const run = compositionRuns.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Composition run not found' } } };
    const states = Object.values(run.nodeStates);
    return {
      total: states.length,
      pending: states.filter((s) => s.status === 'pending').length,
      running: states.filter((s) => s.status === 'running').length,
      succeeded: states.filter((s) => s.status === 'succeeded').length,
      failed: states.filter((s) => s.status === 'failed').length,
      skipped: states.filter((s) => s.status === 'skipped').length,
      currentNodeId: run.currentNodeId,
      nodeStates: run.nodeStates,
    };
  },

  cancel: async (id: string, _force = false): Promise<CompositionRun> => {
    await delay();
    const run = compositionRuns.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Composition run not found' } } };
    run.status = 'cancelled';
    run.completedAt = now();
    return run;
  },

  sync: async (id: string): Promise<CompositionRun> => {
    await delay();
    const run = compositionRuns.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Composition run not found' } } };
    return run;
  },

  resume: async (
    id: string,
    options?: { fromNodeId?: string }
  ): Promise<ResumeRunResponse> => {
    await delay(200);
    const originalRun = compositionRuns.get(id);
    if (!originalRun) throw { response: { status: 404, data: { detail: 'Composition run not found' } } };

    const resumeFrom = options?.fromNodeId || originalRun.executionOrder[0];
    const resumeIdx = originalRun.executionOrder.indexOf(resumeFrom);
    const skippedNodes = originalRun.executionOrder.slice(0, resumeIdx);

    const newRun = await compositionRunsApi.create({
      compositionId: originalRun.compositionId,
      environmentId: originalRun.environmentId,
      inputs: originalRun.inputs,
      credentialIds: originalRun.credentialIds,
    });

    return {
      run: newRun,
      originalRunId: id,
      resumedFromNode: resumeFrom,
      skippedNodes,
    };
  },

  validate: async (_compositionId: string): Promise<ValidationResult> => {
    await delay(300);
    return {
      valid: true,
      errors: [],
      warnings: [],
      programIds: [],
      modelIds: [],
    };
  },

  generateCode: async (_compositionId: string): Promise<GeneratedCodeResponse> => {
    await delay(400);
    return {
      code: '# Auto-generated composition code\nimport asyncio\n\nasync def run():\n    print("Running composition...")\n    await asyncio.sleep(1)\n    print("Done!")\n\nasyncio.run(run())\n',
      executionOrder: ['node-1', 'node-2'],
      warnings: [],
    };
  },

  getCode: async (id: string): Promise<string> => {
    await delay();
    const run = compositionRuns.get(id);
    return run?.generatedCode || '# No generated code available\n';
  },

  downloadLogs: async (id: string): Promise<void> => {
    await delay();
    const logs = runLogs.get(id) || ['No logs available.'];
    const content = logs.join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `composition-run-${id}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  pollProgress: async (
    id: string,
    onProgress: (progress: ProgressResponse) => void,
    options?: {
      intervalMs?: number;
      timeoutMs?: number;
    }
  ): Promise<CompositionRun> => {
    const { intervalMs = 500, timeoutMs = 300000 } = options || {};
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      const run = await compositionRunsApi.get(id);
      const progress = await compositionRunsApi.getProgress(id);
      onProgress(progress);

      if (['succeeded', 'failed', 'cancelled'].includes(run.status)) {
        return run;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return compositionRunsApi.get(id);
  },
};
