import {
  Stepper,
  Step,
  StepIndicator,
  StepStatus,
  StepIcon,
  StepNumber,
  StepTitle,
  StepSeparator,
  Box,
} from '@chakra-ui/react';

interface WizardStepperProps {
  steps: string[];
  currentStepIndex: number;
  onStepClick?: (index: number) => void;
}

export function WizardStepper({ steps, currentStepIndex, onStepClick }: WizardStepperProps) {
  return (
    <Stepper index={currentStepIndex} colorScheme="brand" mb={8} size="sm">
      {steps.map((stepTitle, index) => (
        <Step
          key={index}
          onClick={() => index <= currentStepIndex && onStepClick?.(index)}
          style={{ cursor: index <= currentStepIndex ? 'pointer' : 'default' }}
        >
          <StepIndicator>
            <StepStatus
              complete={<StepIcon />}
              incomplete={<StepNumber />}
              active={<StepNumber />}
            />
          </StepIndicator>

          <Box flexShrink="0">
            <StepTitle>{stepTitle}</StepTitle>
          </Box>

          <StepSeparator />
        </Step>
      ))}
    </Stepper>
  );
}
