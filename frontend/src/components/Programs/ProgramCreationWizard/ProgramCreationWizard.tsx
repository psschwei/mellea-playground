import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
} from '@chakra-ui/react';
import { useProgramWizard } from './useProgramWizard';
import { WizardStepper, WizardNavigation } from './components';
import {
  ImportSourceStep,
  ManualCodeStep,
  GitHubImportStep,
  FileUploadStep,
  MetadataStep,
  ReviewStep,
} from './steps';
import type { ProgramCreationWizardProps, WizardStep } from './types';

const STEP_TITLES: Record<WizardStep, string> = {
  source: 'Choose Source',
  input: 'Enter Code',
  metadata: 'Program Details',
  review: 'Review & Create',
};

export function ProgramCreationWizard({ isOpen, onClose, onCreated }: ProgramCreationWizardProps) {
  const wizard = useProgramWizard({
    onSuccess: onCreated,
    onClose: handleClose,
  });

  function handleClose() {
    wizard.reset();
    onClose();
  }

  // Get dynamic title for step 2 based on import source
  const getInputStepTitle = () => {
    switch (wizard.data.importSource) {
      case 'manual':
        return 'Write Code';
      case 'github':
        return 'GitHub Repository';
      case 'upload':
        return 'Upload Files';
      default:
        return 'Enter Code';
    }
  };

  const stepTitles = {
    ...STEP_TITLES,
    input: getInputStepTitle(),
  };

  // Render current step content
  const renderStepContent = () => {
    const stepProps = {
      data: wizard.data,
      errors: wizard.errors[wizard.step],
      onChange: wizard.updateField,
      onValidate: wizard.validateCurrentStep,
    };

    switch (wizard.step) {
      case 'source':
        return <ImportSourceStep {...stepProps} />;
      case 'input':
        switch (wizard.data.importSource) {
          case 'manual':
            return <ManualCodeStep {...stepProps} />;
          case 'github':
            return <GitHubImportStep {...stepProps} />;
          case 'upload':
            return <FileUploadStep {...stepProps} />;
          default:
            return null;
        }
      case 'metadata':
        return <MetadataStep {...stepProps} />;
      case 'review':
        return <ReviewStep {...stepProps} />;
      default:
        return null;
    }
  };

  const handleStepClick = (index: number) => {
    const stepKeys: WizardStep[] = ['source', 'input', 'metadata', 'review'];
    if (index <= wizard.stepIndex) {
      wizard.goToStep(stepKeys[index]);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="2xl" scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent maxH="85vh">
        <ModalHeader>Create Program</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <WizardStepper
            steps={Object.values(stepTitles)}
            currentStepIndex={wizard.stepIndex}
            onStepClick={handleStepClick}
          />

          {renderStepContent()}
        </ModalBody>

        <ModalFooter>
          <WizardNavigation
            canGoBack={wizard.canGoBack}
            isLastStep={wizard.step === 'review'}
            isSubmitting={wizard.isSubmitting}
            onBack={wizard.goBack}
            onNext={wizard.goNext}
            onSubmit={wizard.submit}
            onCancel={handleClose}
          />
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
