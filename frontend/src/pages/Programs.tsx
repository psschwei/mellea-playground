import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Button,
  Text,
  useDisclosure,
  useToast,
  Spinner,
  Center,
  Icon,
} from '@chakra-ui/react';
import { FiPlus, FiFile } from 'react-icons/fi';
import { ProgramCard, CreateProgramModal } from '@/components/Programs';
import { programsApi, runsApi } from '@/api';
import type { ProgramAsset } from '@/types';

export function ProgramsPage() {
  const [programs, setPrograms] = useState<ProgramAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [runningProgramId, setRunningProgramId] = useState<string | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  const loadPrograms = useCallback(async () => {
    try {
      const data = await programsApi.list();
      setPrograms(data);
    } catch (error) {
      console.error('Failed to load programs:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPrograms();
  }, [loadPrograms]);

  const handleProgramCreated = (program: ProgramAsset) => {
    setPrograms((prev) => [program, ...prev]);
  };

  const handleRunProgram = async (program: ProgramAsset) => {
    setRunningProgramId(program.id);
    try {
      const run = await runsApi.create({ programId: program.id });
      toast({
        title: 'Run started',
        description: `Run ${run.id.slice(0, 8)} is now executing.`,
        status: 'info',
        duration: 3000,
      });

      // Poll for completion (simplified - in production use SSE)
      const completedRun = await runsApi.pollStatus(run.id, run.status, 60000);

      if (completedRun.status === 'succeeded') {
        toast({
          title: 'Run succeeded',
          description: 'Your program executed successfully.',
          status: 'success',
          duration: 5000,
        });
      } else if (completedRun.status === 'failed') {
        toast({
          title: 'Run failed',
          description: completedRun.errorMessage || 'Program execution failed.',
          status: 'error',
          duration: 5000,
        });
      }

      // Reload programs to update last run status
      loadPrograms();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to start run';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setRunningProgramId(null);
    }
  };

  if (isLoading) {
    return (
      <Center h="300px">
        <Spinner size="lg" color="brand.500" />
      </Center>
    );
  }

  return (
    <Box>
      <HStack justify="space-between" mb={6}>
        <Heading size="lg">My Programs</Heading>
        <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
          Create Program
        </Button>
      </HStack>

      {programs.length === 0 ? (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiFile} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            No programs yet
          </Text>
          <Text color="gray.400" mb={4}>
            Create your first Python program to get started.
          </Text>
          <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
            Create Program
          </Button>
        </Center>
      ) : (
        <VStack spacing={4} align="stretch">
          {programs.map((program) => (
            <ProgramCard
              key={program.id}
              program={program}
              onRun={handleRunProgram}
              isRunning={runningProgramId === program.id}
            />
          ))}
        </VStack>
      )}

      <CreateProgramModal isOpen={isOpen} onClose={onClose} onCreated={handleProgramCreated} />
    </Box>
  );
}
