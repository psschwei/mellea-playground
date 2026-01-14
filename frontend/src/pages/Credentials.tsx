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
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
} from '@chakra-ui/react';
import { useRef } from 'react';
import { FiPlus, FiKey } from 'react-icons/fi';
import { CredentialCard, CreateCredentialModal } from '@/components/Credentials';
import { credentialsApi } from '@/api';
import type { Credential } from '@/types';

export function CredentialsPage() {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingCredential, setDeletingCredential] = useState<Credential | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const toast = useToast();

  const loadCredentials = useCallback(async () => {
    try {
      const data = await credentialsApi.list();
      setCredentials(data);
    } catch (error) {
      console.error('Failed to load credentials:', error);
      toast({
        title: 'Error',
        description: 'Failed to load credentials',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadCredentials();
  }, [loadCredentials]);

  const handleCredentialCreated = (credential: Credential) => {
    setCredentials((prev) => [credential, ...prev]);
  };

  const handleEdit = (_credential: Credential) => {
    toast({
      title: 'Edit credential',
      description: 'Credential editing coming soon',
      status: 'info',
      duration: 3000,
    });
  };

  const handleDeleteClick = (credential: Credential) => {
    setDeletingCredential(credential);
    onDeleteOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!deletingCredential) return;

    setIsDeleting(true);
    try {
      await credentialsApi.delete(deletingCredential.id);
      setCredentials((prev) => prev.filter((c) => c.id !== deletingCredential.id));
      toast({
        title: 'Credential deleted',
        description: `${deletingCredential.name} has been deleted.`,
        status: 'success',
        duration: 3000,
      });
      onDeleteClose();
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to delete credential';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      setDeletingCredential(null);
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
        <Heading size="lg">Credentials</Heading>
        <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
          Add Credential
        </Button>
      </HStack>

      {credentials.length === 0 ? (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiKey} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            No credentials yet
          </Text>
          <Text color="gray.400" mb={4}>
            Add API keys and secrets to use with your programs.
          </Text>
          <Button colorScheme="brand" leftIcon={<FiPlus />} onClick={onOpen}>
            Add Credential
          </Button>
        </Center>
      ) : (
        <VStack spacing={4} align="stretch">
          {credentials.map((credential) => (
            <CredentialCard
              key={credential.id}
              credential={credential}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
            />
          ))}
        </VStack>
      )}

      <CreateCredentialModal
        isOpen={isOpen}
        onClose={onClose}
        onCreated={handleCredentialCreated}
      />

      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Credential
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{deletingCredential?.name}"? This action
              cannot be undone.
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
