import apiClient from './client';
import type { ProgramAsset } from '@/types';

// Request/Response types

export interface DependencySpec {
  source: 'pyproject' | 'requirements' | 'manual';
  packages: { name: string; version?: string; extras?: string[] }[];
  pythonVersion?: string;
}

export interface SlotSignature {
  name: string;
  args: { name: string; type: string }[];
  returns?: { type: string };
}

export interface SlotMetadata {
  name: string;
  qualifiedName: string;
  docstring?: string;
  signature: SlotSignature;
  decorators: string[];
  sourceFile: string;
  lineNumber: number;
}

export interface PythonProject {
  path: string;
  entrypoint: string | null;
  confidence: number;
  indicators: string[];
}

export interface AnalysisResult {
  rootFiles: string[];
  pythonProjects: PythonProject[];
  detectedDependencies: DependencySpec | null;
  detectedSlots: SlotMetadata[];
  repoSize: number;
  fileCount: number;
}

export interface AnalyzeRequest {
  repoUrl: string;
  branch?: string;
  accessToken?: string;
}

export interface AnalyzeResponse {
  status: string;
  analysis: AnalysisResult;
  sessionId: string;
  repoUrl: string;
  branch: string;
  commitSha: string;
}

export interface ImportMetadata {
  name: string;
  description?: string;
  tags?: string[];
}

export interface ConfirmRequest {
  sessionId: string;
  selectedPath?: string;
  metadata: ImportMetadata;
  entrypoint?: string;
  dependencies?: DependencySpec;
}

export interface ImportSourceInfo {
  type: string;
  repoUrl: string;
  branch: string;
  commit: string;
  importedAt: string;
}

export interface ConfirmResponse {
  asset: ProgramAsset;
  importSource: ImportSourceInfo;
}

export interface ValidateUrlResponse {
  valid: boolean;
  owner?: string;
  repo?: string;
  branch?: string;
}

export interface CancelResponse {
  cancelled: boolean;
  message: string;
}

export const githubImportApi = {
  /**
   * Analyze a GitHub repository for import
   */
  analyze: async (request: AnalyzeRequest): Promise<AnalyzeResponse> => {
    const response = await apiClient.post<AnalyzeResponse>(
      '/programs/import/github/analyze',
      request
    );
    return response.data;
  },

  /**
   * Confirm and complete the import
   */
  confirm: async (request: ConfirmRequest): Promise<ConfirmResponse> => {
    const response = await apiClient.post<ConfirmResponse>(
      '/programs/import/github/confirm',
      request
    );
    return response.data;
  },

  /**
   * Cancel an import session
   */
  cancel: async (sessionId: string): Promise<CancelResponse> => {
    const response = await apiClient.delete<CancelResponse>(
      `/programs/import/github/session/${sessionId}`
    );
    return response.data;
  },

  /**
   * Validate a GitHub URL without cloning
   */
  validateUrl: async (url: string): Promise<ValidateUrlResponse> => {
    const response = await apiClient.post<ValidateUrlResponse>(
      '/programs/import/github/validate-url',
      { url }
    );
    return response.data;
  },
};
