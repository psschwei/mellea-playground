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
  analyze: async (request: AnalyzeRequest): Promise<AnalyzeResponse> => {
    await delay(800);
    const sessionId = generateId();
    return {
      status: 'analyzed',
      analysis: {
        rootFiles: ['main.py', 'setup.py', 'README.md', 'requirements.txt'],
        pythonProjects: [
          {
            path: '.',
            entrypoint: 'main.py',
            confidence: 0.95,
            indicators: ['main.py exists', 'setup.py found', 'requirements.txt found'],
          },
        ],
        detectedDependencies: {
          source: 'requirements',
          packages: [
            { name: 'requests', version: '2.31.0' },
            { name: 'click', version: '8.1.7' },
          ],
          pythonVersion: '3.11',
        },
        detectedSlots: [],
        repoSize: 45000,
        fileCount: 12,
      },
      sessionId,
      repoUrl: request.repoUrl,
      branch: request.branch || 'main',
      commitSha: 'abc123def456789',
    };
  },

  confirm: async (request: ConfirmRequest): Promise<ConfirmResponse> => {
    await delay(400);
    const id = generateId();
    const program: ProgramAsset = {
      id,
      type: 'program',
      name: request.metadata.name,
      description: request.metadata.description || '',
      tags: request.metadata.tags || ['github-import'],
      version: '1.0.0',
      owner: currentUserId || 'unknown',
      sharing: 'private',
      createdAt: now(),
      updatedAt: now(),
      entrypoint: request.entrypoint || 'main.py',
      sourceCode: '# Imported from GitHub\ndef main():\n    print("Hello from GitHub import!")\n\nif __name__ == "__main__":\n    main()\n',
      dependencies: request.dependencies,
      imageBuildStatus: 'pending',
    };
    programs.set(id, program);
    return {
      asset: program,
      importSource: {
        type: 'github',
        repoUrl: 'https://github.com/user/repo',
        branch: 'main',
        commit: 'abc123def456789',
        importedAt: now(),
      },
    };
  },

  cancel: async (_sessionId: string): Promise<CancelResponse> => {
    await delay();
    return { cancelled: true, message: 'Import session cancelled.' };
  },

  validateUrl: async (url: string): Promise<ValidateUrlResponse> => {
    await delay(200);
    const match = url.match(/github\.com\/([^/]+)\/([^/]+)/);
    if (match) {
      return { valid: true, owner: match[1], repo: match[2], branch: 'main' };
    }
    return { valid: false };
  },
};
