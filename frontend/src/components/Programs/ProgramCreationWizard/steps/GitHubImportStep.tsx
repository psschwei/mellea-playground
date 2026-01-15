import {
  VStack,
  FormControl,
  FormLabel,
  FormErrorMessage,
  FormHelperText,
  Input,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Text,
  InputGroup,
  InputLeftElement,
  Icon,
} from '@chakra-ui/react';
import { FiGithub } from 'react-icons/fi';
import type { StepComponentProps, GitHubImportData } from '../types';

export function GitHubImportStep({ data, errors, onChange }: StepComponentProps) {
  const updateGitHub = (field: keyof GitHubImportData, value: string) => {
    onChange('github', { ...data.github, [field]: value });
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Import from GitHub
      </Text>

      <Alert status="info" variant="subtle" borderRadius="md">
        <AlertIcon />
        <VStack align="start" spacing={0}>
          <AlertTitle>Feature in Development</AlertTitle>
          <AlertDescription fontSize="sm">
            GitHub import will be available soon. For now, please copy your code and use the manual
            entry option.
          </AlertDescription>
        </VStack>
      </Alert>

      <FormControl isInvalid={!!errors.githubUrl}>
        <FormLabel>Repository URL</FormLabel>
        <InputGroup>
          <InputLeftElement pointerEvents="none">
            <Icon as={FiGithub} color="gray.400" />
          </InputLeftElement>
          <Input
            placeholder="https://github.com/username/repository"
            value={data.github.url}
            onChange={(e) => updateGitHub('url', e.target.value)}
            isDisabled
          />
        </InputGroup>
        <FormHelperText>Enter the full URL of a public GitHub repository</FormHelperText>
        <FormErrorMessage>{errors.githubUrl}</FormErrorMessage>
      </FormControl>

      <FormControl>
        <FormLabel>Branch (optional)</FormLabel>
        <Input
          placeholder="main"
          value={data.github.branch || ''}
          onChange={(e) => updateGitHub('branch', e.target.value)}
          isDisabled
        />
        <FormHelperText>Leave blank to use the default branch</FormHelperText>
      </FormControl>

      <FormControl>
        <FormLabel>Path (optional)</FormLabel>
        <Input
          placeholder="src/my-app"
          value={data.github.path || ''}
          onChange={(e) => updateGitHub('path', e.target.value)}
          isDisabled
        />
        <FormHelperText>Subdirectory path for monorepos</FormHelperText>
      </FormControl>
    </VStack>
  );
}
