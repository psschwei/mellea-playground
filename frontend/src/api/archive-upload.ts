import type { ProgramAsset } from '@/types';
import { delay, generateId, now, programs, currentUserId } from './mock-store';

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
  upload: async (file: File): Promise<UploadResponse> => {
    await delay(500);
    const sessionId = generateId();
    return {
      status: 'analyzed',
      analysis: {
        rootFiles: ['main.py', 'requirements.txt', 'README.md'],
        allFiles: [
          { path: 'main.py', size: 1024, isPython: true },
          { path: 'utils.py', size: 512, isPython: true },
          { path: 'requirements.txt', size: 64, isPython: false },
          { path: 'README.md', size: 256, isPython: false },
        ],
        detectedEntrypoint: 'main.py',
        detectedDependencies: {
          source: 'requirements',
          packages: [{ name: 'requests', version: '2.31.0' }],
          pythonVersion: '3.11',
        },
        detectedSlots: [],
        totalSize: 1856,
        fileCount: 4,
      },
      sessionId,
      filename: file.name,
    };
  },

  confirm: async (request: ConfirmRequest): Promise<ConfirmResponse> => {
    await delay(300);
    const id = generateId();
    const program: ProgramAsset = {
      id,
      type: 'program',
      name: request.metadata.name,
      description: request.metadata.description || '',
      tags: request.metadata.tags || ['imported'],
      version: '1.0.0',
      owner: currentUserId || 'unknown',
      sharing: 'private',
      createdAt: now(),
      updatedAt: now(),
      entrypoint: request.entrypoint || 'main.py',
      sourceCode: '# Imported from archive\ndef main():\n    print("Hello from imported program!")\n\nif __name__ == "__main__":\n    main()\n',
      dependencies: request.dependencies,
      imageBuildStatus: 'pending',
    };
    programs.set(id, program);
    return {
      asset: program,
      importSource: {
        type: 'archive',
        filename: 'uploaded-archive.zip',
        importedAt: now(),
      },
    };
  },

  cancel: async (_sessionId: string): Promise<CancelResponse> => {
    await delay();
    return { cancelled: true, message: 'Upload session cancelled.' };
  },
};
