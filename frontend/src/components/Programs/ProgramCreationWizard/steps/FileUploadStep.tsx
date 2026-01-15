import {
  VStack,
  Text,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  FormControl,
  FormErrorMessage,
} from '@chakra-ui/react';
import { FileDropZone } from '../components';
import type { StepComponentProps } from '../types';

const ACCEPTED_TYPES = ['.zip', '.tar.gz', '.py'];
const MAX_SIZE_MB = 10;

export function FileUploadStep({ data, errors, onChange }: StepComponentProps) {
  const handleFileSelect = (file: File | null) => {
    onChange('upload', { ...data.upload, file });
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Upload your program files
      </Text>

      <Alert status="info" variant="subtle" borderRadius="md">
        <AlertIcon />
        <VStack align="start" spacing={0}>
          <AlertTitle>Feature in Development</AlertTitle>
          <AlertDescription fontSize="sm">
            File upload will be available soon. For now, please copy your code and use the manual
            entry option.
          </AlertDescription>
        </VStack>
      </Alert>

      <FormControl isInvalid={!!errors.uploadFile}>
        <FileDropZone
          file={data.upload.file}
          onFileSelect={handleFileSelect}
          acceptedTypes={ACCEPTED_TYPES}
          maxSizeMB={MAX_SIZE_MB}
          isDisabled
        />
        <FormErrorMessage>{errors.uploadFile}</FormErrorMessage>
      </FormControl>

      <Text fontSize="sm" color="gray.500">
        Supported formats: .zip, .tar.gz, .py (max {MAX_SIZE_MB}MB)
      </Text>
    </VStack>
  );
}
