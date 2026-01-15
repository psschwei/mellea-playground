import { HStack, Button } from '@chakra-ui/react';

interface WizardNavigationProps {
  canGoBack: boolean;
  isLastStep: boolean;
  isSubmitting: boolean;
  onBack: () => void;
  onNext: () => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function WizardNavigation({
  canGoBack,
  isLastStep,
  isSubmitting,
  onBack,
  onNext,
  onSubmit,
  onCancel,
}: WizardNavigationProps) {
  return (
    <HStack spacing={3} w="full" justify="space-between">
      <Button variant="ghost" onClick={onCancel}>
        Cancel
      </Button>

      <HStack spacing={3}>
        {canGoBack && (
          <Button variant="outline" onClick={onBack}>
            Back
          </Button>
        )}

        {isLastStep ? (
          <Button
            colorScheme="brand"
            onClick={onSubmit}
            isLoading={isSubmitting}
            loadingText="Creating..."
          >
            Create Program
          </Button>
        ) : (
          <Button colorScheme="brand" onClick={onNext}>
            Next
          </Button>
        )}
      </HStack>
    </HStack>
  );
}
