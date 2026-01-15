import { useState, useCallback } from 'react';
import { useToast } from '@chakra-ui/react';
import { programsApi } from '@/api';
import type { ProgramAsset, CreateProgramRequest } from '@/types';
import type { WizardStep, WizardFormData, StepErrors, UseWizardReturn } from './types';

const STEPS: WizardStep[] = ['source', 'input', 'metadata', 'review'];

const DEFAULT_CODE = `# Your Python program
print("Hello, Mellea!")
`;

const INITIAL_DATA: WizardFormData = {
  importSource: null,
  sourceCode: DEFAULT_CODE,
  github: { url: '', branch: 'main', path: '' },
  upload: { file: null, extractedFiles: [] },
  name: '',
  description: '',
  entrypoint: 'main.py',
  tags: [],
};

const INITIAL_ERRORS: StepErrors = {
  source: {},
  input: {},
  metadata: {},
  review: {},
};

interface UseProgramWizardOptions {
  onSuccess?: (program: ProgramAsset) => void;
  onClose?: () => void;
}

export function useProgramWizard(options: UseProgramWizardOptions = {}): UseWizardReturn {
  const { onSuccess, onClose } = options;
  const toast = useToast();

  const [stepIndex, setStepIndex] = useState(0);
  const [data, setData] = useState<WizardFormData>(INITIAL_DATA);
  const [errors, setErrors] = useState<StepErrors>(INITIAL_ERRORS);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const step = STEPS[stepIndex];

  // Update a single field
  const updateField = useCallback(
    <K extends keyof WizardFormData>(field: K, value: WizardFormData[K]) => {
      setData((prev) => ({ ...prev, [field]: value }));
      // Clear errors for the current step when field changes
      setErrors((prev) => ({
        ...prev,
        [step]: {},
      }));
    },
    [step]
  );

  // Validation functions per step
  const validateSource = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};
    if (!data.importSource) {
      newErrors.importSource = 'Please select an import source';
    }
    setErrors((prev) => ({ ...prev, source: newErrors }));
    return Object.keys(newErrors).length === 0;
  }, [data.importSource]);

  const validateInput = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};

    switch (data.importSource) {
      case 'manual':
        if (!data.sourceCode.trim()) {
          newErrors.sourceCode = 'Code is required';
        }
        break;
      case 'github':
        if (!data.github.url.trim()) {
          newErrors.githubUrl = 'GitHub URL is required';
        } else if (!isValidGitHubUrl(data.github.url)) {
          newErrors.githubUrl = 'Please enter a valid GitHub repository URL';
        }
        break;
      case 'upload':
        if (!data.upload.file) {
          newErrors.uploadFile = 'Please select a file to upload';
        }
        break;
    }

    setErrors((prev) => ({ ...prev, input: newErrors }));
    return Object.keys(newErrors).length === 0;
  }, [data]);

  const validateMetadata = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};

    if (!data.name.trim()) {
      newErrors.name = 'Name is required';
    } else if (!/^[a-z0-9-]+$/.test(data.name)) {
      newErrors.name = 'Name must be lowercase letters, numbers, and hyphens only';
    }

    if (!data.entrypoint.trim()) {
      newErrors.entrypoint = 'Entrypoint is required';
    }

    setErrors((prev) => ({ ...prev, metadata: newErrors }));
    return Object.keys(newErrors).length === 0;
  }, [data.name, data.entrypoint]);

  const validateCurrentStep = useCallback((): boolean => {
    switch (step) {
      case 'source':
        return validateSource();
      case 'input':
        return validateInput();
      case 'metadata':
        return validateMetadata();
      case 'review':
        return true;
      default:
        return false;
    }
  }, [step, validateSource, validateInput, validateMetadata]);

  // Navigation
  const canGoBack = stepIndex > 0;
  const canGoNext = stepIndex < STEPS.length - 1;

  const goBack = useCallback(() => {
    if (canGoBack) {
      setStepIndex((prev) => prev - 1);
    }
  }, [canGoBack]);

  const goNext = useCallback(() => {
    if (canGoNext && validateCurrentStep()) {
      setStepIndex((prev) => prev + 1);
    }
  }, [canGoNext, validateCurrentStep]);

  const goToStep = useCallback(
    (targetStep: WizardStep) => {
      const targetIndex = STEPS.indexOf(targetStep);
      if (targetIndex >= 0 && targetIndex <= stepIndex) {
        setStepIndex(targetIndex);
      }
    },
    [stepIndex]
  );

  // Get final source code based on import method
  const getFinalSourceCode = useCallback(async (): Promise<string> => {
    switch (data.importSource) {
      case 'manual':
        return data.sourceCode;
      case 'github':
        throw new Error('GitHub import is not yet implemented');
      case 'upload':
        if (data.upload.extractedFiles && data.upload.extractedFiles.length > 0) {
          const mainFile = data.upload.extractedFiles.find(
            (f) => f.path === data.entrypoint || f.path.endsWith(data.entrypoint)
          );
          if (mainFile) return mainFile.content;
        }
        throw new Error('File upload processing is not yet implemented');
      default:
        throw new Error('Invalid import source');
    }
  }, [data]);

  // Submit
  const submit = useCallback(async () => {
    if (!validateMetadata()) return;

    setIsSubmitting(true);
    try {
      const sourceCode = await getFinalSourceCode();

      const request: CreateProgramRequest = {
        type: 'program',
        name: data.name.trim(),
        description: data.description.trim() || undefined,
        entrypoint: data.entrypoint,
        sourceCode,
        tags: data.tags.length > 0 ? data.tags : undefined,
      };

      const program = await programsApi.create(request);

      toast({
        title: 'Program created',
        description: `${program.name} has been created successfully.`,
        status: 'success',
        duration: 3000,
      });

      onSuccess?.(program);
      onClose?.();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to create program';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [data, validateMetadata, getFinalSourceCode, toast, onSuccess, onClose]);

  // Reset
  const reset = useCallback(() => {
    setStepIndex(0);
    setData(INITIAL_DATA);
    setErrors(INITIAL_ERRORS);
    setIsSubmitting(false);
  }, []);

  return {
    step,
    stepIndex,
    data,
    errors,
    isSubmitting,
    canGoBack,
    canGoNext,
    goBack,
    goNext,
    goToStep,
    updateField,
    validateCurrentStep,
    submit,
    reset,
  };
}

function isValidGitHubUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.hostname === 'github.com' || parsed.hostname === 'www.github.com';
  } catch {
    return false;
  }
}
