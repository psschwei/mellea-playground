import { useState, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Text,
  Input,
  Button,
  IconButton,
  Badge,
  FormControl,
  FormLabel,
  FormHelperText,
  useToast,
  Spinner,
  Alert,
  AlertIcon,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Tooltip,
} from '@chakra-ui/react';
import { FiPlus, FiTrash2, FiPackage, FiSave } from 'react-icons/fi';
import type { PackageRef, ProgramDependencies } from '@/types';
import { programsApi } from '@/api';

interface DependenciesEditorProps {
  programId: string;
  dependencies?: ProgramDependencies;
  onUpdate?: (dependencies: ProgramDependencies, buildRequired: boolean) => void;
  readOnly?: boolean;
}

const PACKAGE_NAME_REGEX = /^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$/;

export function DependenciesEditor({
  programId,
  dependencies,
  onUpdate,
  readOnly = false,
}: DependenciesEditorProps) {
  const toast = useToast();
  const [packages, setPackages] = useState<PackageRef[]>(
    dependencies?.packages || []
  );
  const [newPackageName, setNewPackageName] = useState('');
  const [newPackageVersion, setNewPackageVersion] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const validatePackageName = (name: string): boolean => {
    if (!name) return false;
    return PACKAGE_NAME_REGEX.test(name);
  };

  const handleAddPackage = useCallback(() => {
    const trimmedName = newPackageName.trim();
    const trimmedVersion = newPackageVersion.trim();

    if (!trimmedName) {
      setValidationError('Package name is required');
      return;
    }

    if (!validatePackageName(trimmedName)) {
      setValidationError('Invalid package name format');
      return;
    }

    // Check for duplicates
    if (packages.some((p) => p.name.toLowerCase() === trimmedName.toLowerCase())) {
      setValidationError('Package already exists');
      return;
    }

    const newPackage: PackageRef = {
      name: trimmedName,
      version: trimmedVersion || undefined,
    };

    setPackages([...packages, newPackage]);
    setNewPackageName('');
    setNewPackageVersion('');
    setValidationError(null);
    setHasChanges(true);
  }, [newPackageName, newPackageVersion, packages]);

  const handleRemovePackage = useCallback((index: number) => {
    setPackages((prev) => prev.filter((_, i) => i !== index));
    setHasChanges(true);
  }, []);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      const response = await programsApi.updateDependencies(programId, {
        packages,
      });

      toast({
        title: 'Dependencies updated',
        description: response.buildRequired
          ? 'A rebuild is required for changes to take effect'
          : 'Dependencies saved successfully',
        status: response.buildRequired ? 'warning' : 'success',
        duration: 5000,
      });

      setHasChanges(false);
      onUpdate?.(response.dependencies, response.buildRequired);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to update dependencies';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsSaving(false);
    }
  }, [programId, packages, toast, onUpdate]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddPackage();
    }
  };

  const sourceLabel = {
    pyproject: 'pyproject.toml',
    requirements: 'requirements.txt',
    manual: 'Manually specified',
  };

  return (
    <VStack align="stretch" spacing={4}>
      {/* Header */}
      <HStack justify="space-between">
        <HStack spacing={2}>
          <FiPackage />
          <Text fontWeight="bold">Dependencies</Text>
          <Badge colorScheme="gray" variant="outline">
            {packages.length} package{packages.length !== 1 ? 's' : ''}
          </Badge>
        </HStack>
        {dependencies?.source && (
          <Badge variant="subtle" colorScheme="blue">
            Source: {sourceLabel[dependencies.source]}
          </Badge>
        )}
      </HStack>

      {/* Python version if set */}
      {dependencies?.pythonVersion && (
        <Text fontSize="sm" color="gray.500">
          Python version: {dependencies.pythonVersion}
        </Text>
      )}

      {/* Add package form */}
      {!readOnly && (
        <Box p={4} bg="gray.50" borderRadius="md">
          <VStack align="stretch" spacing={3}>
            <HStack spacing={3}>
              <FormControl flex={2}>
                <FormLabel fontSize="sm">Package Name</FormLabel>
                <Input
                  placeholder="e.g., requests"
                  value={newPackageName}
                  onChange={(e) => {
                    setNewPackageName(e.target.value);
                    setValidationError(null);
                  }}
                  onKeyPress={handleKeyPress}
                  size="sm"
                  isInvalid={!!validationError}
                />
              </FormControl>
              <FormControl flex={1}>
                <FormLabel fontSize="sm">Version (optional)</FormLabel>
                <Input
                  placeholder="e.g., >=2.0.0"
                  value={newPackageVersion}
                  onChange={(e) => setNewPackageVersion(e.target.value)}
                  onKeyPress={handleKeyPress}
                  size="sm"
                />
              </FormControl>
              <Box pt={6}>
                <Button
                  leftIcon={<FiPlus />}
                  size="sm"
                  colorScheme="brand"
                  onClick={handleAddPackage}
                >
                  Add
                </Button>
              </Box>
            </HStack>
            {validationError && (
              <Text color="red.500" fontSize="sm">
                {validationError}
              </Text>
            )}
            <FormHelperText>
              Specify packages your program needs. Version constraints follow pip format (e.g.,
              &gt;=1.0, ==2.3.4, ~=1.4.2).
            </FormHelperText>
          </VStack>
        </Box>
      )}

      {/* Package list */}
      {packages.length > 0 ? (
        <Box borderWidth="1px" borderRadius="md" overflow="hidden">
          <Table size="sm">
            <Thead bg="gray.50">
              <Tr>
                <Th>Package</Th>
                <Th>Version</Th>
                {!readOnly && <Th w="60px">Actions</Th>}
              </Tr>
            </Thead>
            <Tbody>
              {packages.map((pkg, index) => (
                <Tr key={`${pkg.name}-${index}`}>
                  <Td fontFamily="mono">{pkg.name}</Td>
                  <Td fontFamily="mono" color={pkg.version ? 'inherit' : 'gray.400'}>
                    {pkg.version || 'latest'}
                  </Td>
                  {!readOnly && (
                    <Td>
                      <Tooltip label="Remove package">
                        <IconButton
                          aria-label="Remove package"
                          icon={<FiTrash2 />}
                          size="xs"
                          variant="ghost"
                          colorScheme="red"
                          onClick={() => handleRemovePackage(index)}
                        />
                      </Tooltip>
                    </Td>
                  )}
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      ) : (
        <Alert status="info" borderRadius="md">
          <AlertIcon />
          <Text fontSize="sm">
            No dependencies specified. Add packages your program needs to run.
          </Text>
        </Alert>
      )}

      {/* Save button */}
      {!readOnly && hasChanges && (
        <HStack justify="flex-end">
          <Button
            leftIcon={isSaving ? <Spinner size="sm" /> : <FiSave />}
            colorScheme="brand"
            onClick={handleSave}
            isLoading={isSaving}
            loadingText="Saving..."
          >
            Save Dependencies
          </Button>
        </HStack>
      )}
    </VStack>
  );
}
