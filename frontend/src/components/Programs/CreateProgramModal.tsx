import { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Input,
  Textarea,
  VStack,
  useToast,
  Box,
  Text,
  useColorModeValue,
} from '@chakra-ui/react';
import { programsApi } from '@/api';
import type { ProgramAsset, CreateProgramRequest } from '@/types';

interface CreateProgramModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (program: ProgramAsset) => void;
}

const DEFAULT_CODE = `# Your Python program
print("Hello, Mellea!")
`;

export function CreateProgramModal({ isOpen, onClose, onCreated }: CreateProgramModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState(DEFAULT_CODE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();

  const codeBg = useColorModeValue('gray.900', 'gray.800');

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    } else if (!/^[a-z0-9-]+$/.test(name)) {
      newErrors.name = 'Name must be lowercase letters, numbers, and hyphens only';
    }

    if (!code.trim()) {
      newErrors.code = 'Code is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const request: CreateProgramRequest = {
        type: 'program',
        name: name.trim(),
        description: description.trim() || undefined,
        entrypoint: 'main.py',
        sourceCode: code,
      };

      const program = await programsApi.create(request);
      toast({
        title: 'Program created',
        description: `${program.name} has been created successfully.`,
        status: 'success',
        duration: 3000,
      });
      onCreated(program);
      handleClose();
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to create program';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setName('');
    setDescription('');
    setCode(DEFAULT_CODE);
    setErrors({});
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Create Program</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl isInvalid={!!errors.name}>
              <FormLabel>Name</FormLabel>
              <Input
                placeholder="my-program"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              <FormErrorMessage>{errors.name}</FormErrorMessage>
            </FormControl>

            <FormControl>
              <FormLabel>Description (optional)</FormLabel>
              <Input
                placeholder="A simple Python script"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormControl>

            <FormControl isInvalid={!!errors.code}>
              <FormLabel>Code</FormLabel>
              <Box position="relative">
                <Text
                  position="absolute"
                  top={2}
                  right={2}
                  fontSize="xs"
                  color="gray.500"
                  zIndex={1}
                >
                  main.py
                </Text>
                <Textarea
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  fontFamily="mono"
                  fontSize="sm"
                  bg={codeBg}
                  color="green.300"
                  minH="200px"
                  resize="vertical"
                  placeholder="# Your Python code here"
                />
              </Box>
              <FormErrorMessage>{errors.code}</FormErrorMessage>
            </FormControl>
          </VStack>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={handleClose}>
            Cancel
          </Button>
          <Button
            colorScheme="brand"
            onClick={handleSubmit}
            isLoading={isSubmitting}
            loadingText="Creating..."
          >
            Create
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
