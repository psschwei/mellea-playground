import type {
  ProgramAsset,
  CreateProgramRequest,
  BuildImageRequest,
  BuildResult,
  UpdateDependenciesRequest,
  UpdateDependenciesResponse,
} from '@/types';
import { delay, generateId, now, programs, currentUserId } from './mock-store';

export const programsApi = {
  create: async (data: CreateProgramRequest): Promise<ProgramAsset> => {
    await delay(150);
    const id = generateId();
    const program: ProgramAsset = {
      id,
      type: 'program',
      name: data.name,
      description: data.description || '',
      tags: data.tags || [],
      version: '1.0.0',
      owner: currentUserId || 'unknown',
      sharing: 'private',
      createdAt: now(),
      updatedAt: now(),
      entrypoint: data.entrypoint,
      sourceCode: data.sourceCode,
      imageBuildStatus: 'pending',
    };
    programs.set(id, program);
    return program;
  },

  get: async (id: string): Promise<ProgramAsset> => {
    await delay();
    const program = programs.get(id);
    if (!program) throw { response: { status: 404, data: { detail: 'Program not found' } } };
    return program;
  },

  list: async (): Promise<ProgramAsset[]> => {
    await delay();
    return Array.from(programs.values());
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    programs.delete(id);
  },

  build: async (id: string, _options?: BuildImageRequest): Promise<BuildResult> => {
    await delay(500);
    const program = programs.get(id);
    if (!program) throw { response: { status: 404, data: { detail: 'Program not found' } } };
    program.imageBuildStatus = 'ready';
    program.imageTag = `mellea/${program.name.toLowerCase().replace(/\s+/g, '-')}:${program.version}`;
    program.updatedAt = now();
    return {
      programId: id,
      success: true,
      imageTag: program.imageTag,
      cacheHit: false,
      totalDurationSeconds: 12.5,
      depsBuildDurationSeconds: 8.3,
      programBuildDurationSeconds: 4.2,
    };
  },

  updateDependencies: async (
    id: string,
    data: UpdateDependenciesRequest
  ): Promise<UpdateDependenciesResponse> => {
    await delay(200);
    const program = programs.get(id);
    if (!program) throw { response: { status: 404, data: { detail: 'Program not found' } } };
    program.dependencies = {
      source: 'manual',
      packages: data.packages,
      pythonVersion: program.dependencies?.pythonVersion || '3.11',
    };
    program.imageBuildStatus = 'pending';
    program.updatedAt = now();
    return {
      programId: id,
      dependencies: program.dependencies,
      buildRequired: true,
    };
  },
};
