export { default as apiClient } from './client';
export { setToken, getToken, clearToken, isAuthenticated } from './client';
export { adminApi } from './admin';
export { archiveUploadApi } from './archive-upload';
export { assetsApi } from './assets';
export { authApi } from './auth';
export { compositionRunsApi } from './compositionRuns';
export { credentialsApi } from './credentials';
export { githubImportApi } from './github-import';
export { modelsApi } from './models';
export { notificationsApi } from './notifications';
export { programsApi } from './programs';
export { runsApi } from './runs';

// Re-export types from compositionRuns
export type {
  CompositionRun,
  CreateCompositionRunRequest,
  ProgressResponse,
  NodeExecutionState,
  NodeExecutionStatus,
  ValidationResult,
  GeneratedCodeResponse,
} from './compositionRuns';
