import { useState, useEffect, useCallback, useRef } from 'react';
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
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
} from '@chakra-ui/react';
import { FiPlus, FiFile } from 'react-icons/fi';
import { ProgramCard, CreateProgramModal } from '@/components/Programs';
import { programsApi, runsApi } from '@/api';
import type { ProgramAsset } from '@/types';

export function ProgramsPage() {
  const [programs, setPrograms] = useState<ProgramAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [buildingProgramId, setBuildingProgramId] = useState<string | null>(null);
  const [runningProgramId, setRunningProgramId] = useState<string | null>(null);
  const [deletingProgram, setDeletingProgram] = useState<ProgramAsset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteProgramRunCount, setDeleteProgramRunCount] = useState(0);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
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

  const handleDeleteClick = async (program: ProgramAsset) => {
    setDeletingProgram(program);
    // Check for existing runs to warn the user
    try {
      const runs = await runsApi.listByProgram(program.id);
      setDeleteProgramRunCount(runs.length);
    } catch {
      setDeleteProgramRunCount(0);
    }
    onDeleteOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!deletingProgram) return;

    setIsDeleting(true);
    try {
      await programsApi.delete(deletingProgram.id);
      setPrograms((prev) => prev.filter((p) => p.id !== deletingProgram.id));
      toast({
        title: 'Program deleted',
        description: `"${deletingProgram.name}" has been deleted.`,
        status: 'success',
        duration: 3000,
      });
      onDeleteClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete program';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      setDeletingProgram(null);
      setDeleteProgramRunCount(0);
    }
  };

  const handleRunProgram = async (program: ProgramAsset) => {
    // Check if image needs to be built first
    if (!program.imageTag || program.imageBuildStatus !== 'ready') {
      setBuildingProgramId(program.id);
      try {
        toast({
          title: 'Building image...',
          description: 'This may take a minute',
          status: 'info',
          duration: null,
          isClosable: true,
          id: `build-toast-${program.id}`,
        });

        const buildResult = await programsApi.build(program.id);

        toast.close(`build-toast-${program.id}`);

        if (!buildResult.success) {
          toast({
            title: 'Build failed',
            description: buildResult.errorMessage || 'Unknown error',
            status: 'error',
            duration: 5000,
          });
          setBuildingProgramId(null);
          return;
        }

        toast({
          title: 'Build succeeded',
          description: buildResult.cacheHit
            ? 'Used cached image'
            : `Built in ${buildResult.totalDurationSeconds.toFixed(1)}s`,
          status: 'success',
          duration: 3000,
        });

        // Reload programs to get updated imageTag
        await loadPrograms();
      } catch (error: unknown) {
        toast.close(`build-toast-${program.id}`);
        const message = error instanceof Error ? error.message : 'Failed to build image';
        toast({
          title: 'Build error',
          description: message,
          status: 'error',
          duration: 5000,
        });
        setBuildingProgramId(null);
        return;
      } finally {
        setBuildingProgramId(null);
      }
    }

    // Now run the program
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
              onDelete={handleDeleteClick}
              isBuilding={buildingProgramId === program.id}
              isRunning={runningProgramId === program.id}
            />
          ))}
        </VStack>
      )}

      <CreateProgramModal isOpen={isOpen} onClose={onClose} onCreated={handleProgramCreated} />

      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Program
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{deletingProgram?.name}"?
              {deleteProgramRunCount > 0 && (
                <Text mt={2} color="orange.500">
                  This program has {deleteProgramRunCount} run{deleteProgramRunCount !== 1 ? 's' : ''} that will no longer be accessible.
                </Text>
              )}
              <Text mt={2} color="gray.500">
                This action cannot be undone.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDeleteConfirm}
                ml={3}
                isLoading={isDeleting}
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
