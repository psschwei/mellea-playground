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

export interface ExtractedFile {
  path: string;
  size: number;
  isPython: boolean;
}

export interface UploadAnalysisResult {
  rootFiles: string[];
  allFiles: ExtractedFile[];
  detectedEntrypoint: string | null;
  detectedDependencies: DependencySpec | null;
  detectedSlots: SlotMetadata[];
  totalSize: number;
  fileCount: number;
}

export interface UploadResponse {
  status: string;
  analysis: UploadAnalysisResult;
  sessionId: string;
  filename: string;
}

export interface ImportMetadata {
  name: string;
  description?: string;
  tags?: string[];
}

export interface ConfirmRequest {
  sessionId: string;
  metadata: ImportMetadata;
  entrypoint?: string;
  dependencies?: DependencySpec;
}

export interface ImportSourceInfo {
  type: string;
  filename: string;
  importedAt: string;
}

export interface ConfirmResponse {
  asset: ProgramAsset;
  importSource: ImportSourceInfo;
}

export interface CancelResponse {
  cancelled: boolean;
  message: string;
}

export const archiveUploadApi = {
  /**
   * Upload and analyze an archive file
   */
  upload: async (file: File): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<UploadResponse>(
      '/programs/import/upload/analyze',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  /**
   * Confirm and complete the import
   */
  confirm: async (request: ConfirmRequest): Promise<ConfirmResponse> => {
    const response = await apiClient.post<ConfirmResponse>(
      '/programs/import/upload/confirm',
      request
    );
    return response.data;
  },

  /**
   * Cancel an upload session
   */
  cancel: async (sessionId: string): Promise<CancelResponse> => {
    const response = await apiClient.delete<CancelResponse>(
      `/programs/import/upload/session/${sessionId}`
    );
    return response.data;
  },
};
