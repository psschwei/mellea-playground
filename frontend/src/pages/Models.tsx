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
import { FiPlus, FiCpu } from 'react-icons/fi';
import { ModelCard, CreateModelModal } from '@/components/Models';
import { modelsApi } from '@/api';
import type { ModelAsset } from '@/types';

export function ModelsPage() {
  const [models, setModels] = useState<ModelAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [testingModelId, setTestingModelId] = useState<string | null>(null);
  const [deletingModel, setDeletingModel] = useState<ModelAsset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const toast = useToast();

  const loadModels = useCallback(async () => {
    try {
      const data = await modelsApi.list();
      setModels(data);
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const handleModelCreated = (model: ModelAsset) => {
    setModels((prev) => [model, ...prev]);
  };

  const handleDeleteClick = (model: ModelAsset) => {
    setDeletingModel(model);
    onDeleteOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!deletingModel) return;

    setIsDeleting(true);
    try {
      await modelsApi.delete(deletingModel.id);
      setModels((prev) => prev.filter((m) => m.id !== deletingModel.id));
      toast({
        title: 'Model deleted',
        description: `"${deletingModel.name}" has been deleted.`,
        status: 'success',
        duration: 3000,
      });
      onDeleteClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete model';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      setDeletingModel(null);
    }
  };

  const handleTestModel = async (model: ModelAsset) => {
    setTestingModelId(model.id);
    try {
      const result = await modelsApi.test(model.id);

      if (result.success) {
        toast({
          title: 'Model test passed',
          description: result.latencyMs
            ? `Response received in ${result.latencyMs}ms`
            : 'Model is configured correctly',
          status: 'success',
          duration: 5000,
        });
      } else {
        toast({
          title: 'Model test failed',
          description: result.error || 'Could not connect to model',
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to test model';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setTestingModelId(null);
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
        <Heading size="lg">My Models</Heading>
        <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
          Add Model
        </Button>
      </HStack>

      {models.length === 0 ? (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiCpu} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            No models configured
          </Text>
          <Text color="gray.400" mb={4}>
            Add your first model to start using AI capabilities.
          </Text>
          <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
            Add Model
          </Button>
        </Center>
      ) : (
        <VStack spacing={4} align="stretch">
          {models.map((model) => (
            <ModelCard
              key={model.id}
              model={model}
              onTest={handleTestModel}
              onDelete={handleDeleteClick}
              isTesting={testingModelId === model.id}
            />
          ))}
        </VStack>
      )}

      <CreateModelModal isOpen={isOpen} onClose={onClose} onCreated={handleModelCreated} />

      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Model
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{deletingModel?.name}"?
              <Text mt={2} color="gray.500">
                This action cannot be undone. Any programs using this model may stop working.
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
