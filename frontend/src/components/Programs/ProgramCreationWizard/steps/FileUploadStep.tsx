import { useState } from 'react';
import {
  VStack,
  Text,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  FormControl,
  FormErrorMessage,
  Spinner,
  Box,
  HStack,
  Icon,
  Badge,
  Divider,
  useColorModeValue,
} from '@chakra-ui/react';
import { FiCheck, FiFile, FiCode, FiPackage } from 'react-icons/fi';
import { FileDropZone } from '../components';
import { archiveUploadApi } from '@/api';
import type { StepComponentProps } from '../types';

const ACCEPTED_TYPES = ['.zip', '.tar.gz', '.tgz', '.tar', '.py'];
const MAX_SIZE_MB = 10;

export function FileUploadStep({ data, errors, onChange }: StepComponentProps) {
  const [isUploading, setIsUploading] = useState(false);

  const cardBg = useColorModeValue('gray.50', 'gray.700');
  const successBg = useColorModeValue('green.50', 'green.900');

  const handleFileSelect = async (file: File | null) => {
    // Clear previous analysis if file removed
    if (!file) {
      onChange('upload', {
        file: null,
        sessionId: undefined,
        analysis: undefined,
        uploadError: undefined,
      });
      return;
    }

    // Validate file size
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      onChange('upload', {
        ...data.upload,
        file,
        uploadError: `File size exceeds ${MAX_SIZE_MB}MB limit`,
      });
      return;
    }

    // Set file and start upload
    onChange('upload', {
      ...data.upload,
      file,
      isUploading: true,
      uploadError: undefined,
      analysis: undefined,
      sessionId: undefined,
    });

    setIsUploading(true);

    try {
      const response = await archiveUploadApi.upload(file);

      onChange('upload', {
        ...data.upload,
        file,
        isUploading: false,
        sessionId: response.sessionId,
        analysis: response.analysis,
        uploadError: undefined,
      });

      // Auto-set entrypoint if detected
      if (response.analysis.detectedEntrypoint && !data.entrypoint) {
        onChange('entrypoint', response.analysis.detectedEntrypoint);
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Upload failed';
      onChange('upload', {
        ...data.upload,
        file,
        isUploading: false,
        uploadError: message,
      });
    } finally {
      setIsUploading(false);
    }
  };

  const analysis = data.upload.analysis;
  const hasAnalysis = !!analysis && !!data.upload.sessionId;

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Upload your program files
      </Text>

      <FormControl isInvalid={!!errors.uploadFile || !!data.upload.uploadError}>
        <FileDropZone
          file={data.upload.file}
          onFileSelect={handleFileSelect}
          acceptedTypes={ACCEPTED_TYPES}
          maxSizeMB={MAX_SIZE_MB}
          isDisabled={isUploading}
        />
        <FormErrorMessage>{errors.uploadFile || data.upload.uploadError}</FormErrorMessage>
      </FormControl>

      {isUploading && (
        <HStack justify="center" spacing={3} py={4}>
          <Spinner size="sm" color="brand.500" />
          <Text>Uploading and analyzing...</Text>
        </HStack>
      )}

      {hasAnalysis && (
        <VStack spacing={4} align="stretch">
          <Alert status="success" variant="subtle" borderRadius="md" bg={successBg}>
            <AlertIcon as={FiCheck} />
            <VStack align="start" spacing={0}>
              <AlertTitle>Upload successful</AlertTitle>
              <AlertDescription fontSize="sm">
                {analysis.fileCount} files ({formatFileSize(analysis.totalSize)}) analyzed
              </AlertDescription>
            </VStack>
          </Alert>

          <Box bg={cardBg} p={4} borderRadius="md">
            <VStack align="stretch" spacing={3}>
              <HStack justify="space-between">
                <HStack spacing={2}>
                  <Icon as={FiFile} />
                  <Text fontWeight="medium">Files</Text>
                </HStack>
                <Badge colorScheme="blue">{analysis.fileCount} files</Badge>
              </HStack>

              {analysis.detectedEntrypoint && (
                <>
                  <Divider />
                  <HStack justify="space-between">
                    <HStack spacing={2}>
                      <Icon as={FiCode} />
                      <Text fontWeight="medium">Detected Entrypoint</Text>
                    </HStack>
                    <Badge colorScheme="green">{analysis.detectedEntrypoint}</Badge>
                  </HStack>
                </>
              )}

              {analysis.detectedDependencies &&
                analysis.detectedDependencies.packages.length > 0 && (
                  <>
                    <Divider />
                    <HStack justify="space-between">
                      <HStack spacing={2}>
                        <Icon as={FiPackage} />
                        <Text fontWeight="medium">Dependencies</Text>
                      </HStack>
                      <Badge colorScheme="purple">
                        {analysis.detectedDependencies.packages.length} packages
                      </Badge>
                    </HStack>
                  </>
                )}

              {analysis.detectedSlots.length > 0 && (
                <>
                  <Divider />
                  <VStack align="stretch" spacing={1}>
                    <Text fontWeight="medium" fontSize="sm">
                      Detected @generative slots:
                    </Text>
                    {analysis.detectedSlots.map((slot) => (
                      <Text key={slot.qualifiedName} fontSize="sm" color="gray.500">
                        {slot.name} ({slot.sourceFile}:{slot.lineNumber})
                      </Text>
                    ))}
                  </VStack>
                </>
              )}
            </VStack>
          </Box>
        </VStack>
      )}

      <Text fontSize="sm" color="gray.500">
        Supported formats: {ACCEPTED_TYPES.join(', ')} (max {MAX_SIZE_MB}MB)
      </Text>
    </VStack>
  );
}
