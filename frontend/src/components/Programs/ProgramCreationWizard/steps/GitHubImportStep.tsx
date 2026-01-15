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
  Button,
  Box,
  Badge,
  HStack,
  Spinner,
  Select,
} from '@chakra-ui/react';
import { FiGithub, FiCheck } from 'react-icons/fi';
import { useState } from 'react';
import { githubImportApi } from '@/api';
import type { StepComponentProps, GitHubImportData } from '../types';

export function GitHubImportStep({ data, errors, onChange }: StepComponentProps) {
  const [selectedProject, setSelectedProject] = useState<string>('.');

  const updateGitHub = (updates: Partial<GitHubImportData>) => {
    onChange('github', { ...data.github, ...updates });
  };

  const handleAnalyze = async () => {
    if (!data.github.url.trim()) return;

    updateGitHub({ isAnalyzing: true, analysisError: undefined, analysis: undefined });

    try {
      const response = await githubImportApi.analyze({
        repoUrl: data.github.url.trim(),
        branch: data.github.branch || 'main',
      });

      updateGitHub({
        isAnalyzing: false,
        sessionId: response.sessionId,
        analysis: response.analysis,
      });

      // Auto-select the first project and update entrypoint
      if (response.analysis.pythonProjects.length > 0) {
        const firstProject = response.analysis.pythonProjects[0];
        setSelectedProject(firstProject.path);
        if (firstProject.entrypoint) {
          onChange('entrypoint', firstProject.entrypoint);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to analyze repository';
      updateGitHub({ isAnalyzing: false, analysisError: message });
    }
  };

  const handleProjectSelect = (path: string) => {
    setSelectedProject(path);
    const project = data.github.analysis?.pythonProjects.find((p) => p.path === path);
    if (project?.entrypoint) {
      onChange('entrypoint', project.entrypoint);
    }
    // Store selected path for confirm
    updateGitHub({ path });
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Import from GitHub
      </Text>

      <FormControl isInvalid={!!errors.githubUrl}>
        <FormLabel>Repository URL</FormLabel>
        <InputGroup>
          <InputLeftElement pointerEvents="none">
            <Icon as={FiGithub} color="gray.400" />
          </InputLeftElement>
          <Input
            placeholder="https://github.com/username/repository"
            value={data.github.url}
            onChange={(e) => updateGitHub({ url: e.target.value })}
            isDisabled={data.github.isAnalyzing}
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
          onChange={(e) => updateGitHub({ branch: e.target.value })}
          isDisabled={data.github.isAnalyzing}
        />
        <FormHelperText>Leave blank to use the default branch</FormHelperText>
      </FormControl>

      <Button
        colorScheme="blue"
        onClick={handleAnalyze}
        isLoading={data.github.isAnalyzing}
        loadingText="Analyzing repository..."
        isDisabled={!data.github.url.trim()}
        leftIcon={<Icon as={FiGithub} />}
      >
        Analyze Repository
      </Button>

      {/* Analysis Error */}
      {data.github.analysisError && (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          <VStack align="start" spacing={0}>
            <AlertTitle>Analysis Failed</AlertTitle>
            <AlertDescription fontSize="sm">{data.github.analysisError}</AlertDescription>
          </VStack>
        </Alert>
      )}

      {/* Analysis Results */}
      {data.github.analysis && (
        <Box borderWidth={1} borderRadius="md" p={4}>
          <VStack align="stretch" spacing={4}>
            <HStack justify="space-between">
              <HStack>
                <Icon as={FiCheck} color="green.500" />
                <Text fontWeight="medium">Repository Analyzed</Text>
              </HStack>
              <HStack spacing={2}>
                <Badge colorScheme="gray">{data.github.analysis.fileCount} files</Badge>
                <Badge colorScheme="gray">{formatBytes(data.github.analysis.repoSize)}</Badge>
              </HStack>
            </HStack>

            {data.github.analysis.pythonProjects.length === 0 ? (
              <Alert status="warning" borderRadius="md">
                <AlertIcon />
                <AlertDescription>
                  No Python projects detected. The repository may not contain Python code.
                </AlertDescription>
              </Alert>
            ) : (
              <FormControl>
                <FormLabel>Select Python Project</FormLabel>
                <Select
                  value={selectedProject}
                  onChange={(e) => handleProjectSelect(e.target.value)}
                >
                  {data.github.analysis.pythonProjects.map((project) => (
                    <option key={project.path} value={project.path}>
                      {project.path === '.' ? 'Root directory' : project.path}
                      {project.entrypoint && ` (${project.entrypoint})`}
                    </option>
                  ))}
                </Select>
                {data.github.analysis.pythonProjects.find((p) => p.path === selectedProject) && (
                  <FormHelperText>
                    <HStack spacing={2} mt={2} flexWrap="wrap">
                      {data.github.analysis.pythonProjects
                        .find((p) => p.path === selectedProject)
                        ?.indicators.map((indicator, i) => (
                          <Badge key={i} colorScheme="blue" size="sm">
                            {indicator}
                          </Badge>
                        ))}
                    </HStack>
                  </FormHelperText>
                )}
              </FormControl>
            )}
          </VStack>
        </Box>
      )}

      {/* Loading State */}
      {data.github.isAnalyzing && (
        <HStack justify="center" py={4}>
          <Spinner size="sm" />
          <Text color="gray.500">Cloning and analyzing repository...</Text>
        </HStack>
      )}
    </VStack>
  );
}
