import type { ProgramAsset } from '@/types';

// Import source options
export type ImportSource = 'manual' | 'github' | 'upload';

// Wizard steps
export type WizardStep = 'source' | 'input' | 'metadata' | 'review';

// GitHub import data
export interface GitHubImportData {
  url: string;
  branch?: string;
  path?: string;
}

// Upload import data
export interface UploadImportData {
  file: File | null;
  extractedFiles?: ExtractedFile[];
}

export interface ExtractedFile {
  path: string;
  content: string;
  size: number;
}

// Wizard form data (accumulated across steps)
export interface WizardFormData {
  // Step 1 - Source selection
  importSource: ImportSource | null;

  // Step 2 - Source-specific data
  sourceCode: string;
  github: GitHubImportData;
  upload: UploadImportData;

  // Step 3 - Metadata
  name: string;
  description: string;
  entrypoint: string;
  tags: string[];
}

// Validation errors per step
export interface StepErrors {
  source: Record<string, string>;
  input: Record<string, string>;
  metadata: Record<string, string>;
  review: Record<string, string>;
}

// Props for step components
export interface StepComponentProps {
  data: WizardFormData;
  errors: Record<string, string>;
  onChange: <K extends keyof WizardFormData>(field: K, value: WizardFormData[K]) => void;
  onValidate: () => boolean;
}

// Wizard hook return type
export interface UseWizardReturn {
  // Current state
  step: WizardStep;
  stepIndex: number;
  data: WizardFormData;
  errors: StepErrors;
  isSubmitting: boolean;

  // Navigation
  canGoBack: boolean;
  canGoNext: boolean;
  goBack: () => void;
  goNext: () => void;
  goToStep: (step: WizardStep) => void;

  // Data management
  updateField: <K extends keyof WizardFormData>(field: K, value: WizardFormData[K]) => void;
  validateCurrentStep: () => boolean;

  // Actions
  submit: () => Promise<void>;
  reset: () => void;
}

// Wizard props
export interface ProgramCreationWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (program: ProgramAsset) => void;
}
