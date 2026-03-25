import type { Run, CreateRunRequest, RunExecutionStatus, SharingMode, Permission } from '@/types';
import { delay, generateId, now, runs, currentUserId, simulateRunExecution } from './mock-store';

interface BulkDeleteResponse {
  results: Record<string, boolean | string>;
  deletedCount: number;
  failedCount: number;
}

interface ListRunsParams {
  programId?: string;
  status?: RunExecutionStatus;
  visibility?: SharingMode;
  includeShared?: boolean;
}

interface SharedUserResponse {
  userId: string;
  permission: Permission;
}

export const runsApi = {
  create: async (data: CreateRunRequest): Promise<Run> => {
    await delay(150);
    const id = generateId();
    const run: Run = {
      id,
      ownerId: currentUserId || 'unknown',
      programId: data.programId,
      status: 'queued',
      visibility: 'private',
      createdAt: now(),
    };
    runs.set(id, run);
    simulateRunExecution(id);
    return run;
  },

  get: async (id: string): Promise<Run> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    return run;
  },

  list: async (params?: ListRunsParams): Promise<Run[]> => {
    await delay();
    let result = Array.from(runs.values());
    if (params?.programId) result = result.filter((r) => r.programId === params.programId);
    if (params?.status) result = result.filter((r) => r.status === params.status);
    if (params?.visibility) result = result.filter((r) => r.visibility === params.visibility);
    return result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  },

  listByProgram: async (programId: string): Promise<Run[]> => {
    return runsApi.list({ programId });
  },

  cancel: async (id: string): Promise<Run> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    run.status = 'cancelled';
    run.completedAt = now();
    return run;
  },

  pollStatus: async (
    id: string,
    currentStatus: string,
    timeoutMs: number = 30000
  ): Promise<Run> => {
    const startTime = Date.now();
    const pollInterval = 500;

    while (Date.now() - startTime < timeoutMs) {
      const run = await runsApi.get(id);
      if (run.status !== currentStatus) return run;
      await new Promise((resolve) => setTimeout(resolve, pollInterval));
    }
    return runsApi.get(id);
  },

  downloadLogs: async (id: string): Promise<void> => {
    await delay();
    const run = runs.get(id);
    const content = run?.output || `Logs for run ${id}\nNo output captured.`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `run-${id}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    runs.delete(id);
  },

  bulkDelete: async (runIds: string[]): Promise<BulkDeleteResponse> => {
    await delay();
    const results: Record<string, boolean | string> = {};
    let deletedCount = 0;
    let failedCount = 0;
    for (const rid of runIds) {
      const run = runs.get(rid);
      if (run && ['succeeded', 'failed', 'cancelled'].includes(run.status)) {
        runs.delete(rid);
        results[rid] = true;
        deletedCount++;
      } else {
        results[rid] = run ? 'Run is not in a terminal state' : 'Not found';
        failedCount++;
      }
    }
    return { results, deletedCount, failedCount };
  },

  updateVisibility: async (id: string, visibility: SharingMode): Promise<Run> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    run.visibility = visibility;
    return run;
  },

  shareWithUser: async (
    id: string,
    userId: string,
    permission: Permission = 'view'
  ): Promise<Run> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    if (!run.sharedWith) run.sharedWith = [];
    run.sharedWith.push({ type: 'user', id: userId, permission });
    return run;
  },

  revokeAccess: async (id: string, userId: string): Promise<Run> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    run.sharedWith = (run.sharedWith || []).filter((s) => s.id !== userId);
    return run;
  },

  getSharedUsers: async (id: string): Promise<SharedUserResponse[]> => {
    await delay();
    const run = runs.get(id);
    if (!run) throw { response: { status: 404, data: { detail: 'Run not found' } } };
    return (run.sharedWith || []).map((s) => ({ userId: s.id, permission: s.permission }));
  },
};
