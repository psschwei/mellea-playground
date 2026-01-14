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
  Select,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { credentialsApi } from '@/api';
import type { Credential, CreateCredentialRequest, CredentialType, ModelProvider } from '@/types';

interface CreateCredentialModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (credential: Credential) => void;
}

const credentialTypes: { value: CredentialType; label: string }[] = [
  { value: 'api_key', label: 'API Key' },
  { value: 'registry', label: 'Container Registry' },
  { value: 'database', label: 'Database' },
  { value: 'oauth_token', label: 'OAuth Token' },
  { value: 'ssh_key', label: 'SSH Key' },
  { value: 'custom', label: 'Custom' },
];

const providers: { value: ModelProvider; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'custom', label: 'Custom' },
];

export function CreateCredentialModal({ isOpen, onClose, onCreated }: CreateCredentialModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<CredentialType>('api_key');
  const [provider, setProvider] = useState<ModelProvider | ''>('');
  const [secretKey, setSecretKey] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!secretKey.trim()) {
      newErrors.secretKey = 'Secret key name is required';
    }

    if (!secretValue.trim()) {
      newErrors.secretValue = 'Secret value is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const request: CreateCredentialRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        type,
        provider: provider || undefined,
        secretData: { [secretKey.trim()]: secretValue },
      };

      const credential = await credentialsApi.create(request);
      toast({
        title: 'Credential created',
        description: `${credential.name} has been created successfully.`,
        status: 'success',
        duration: 3000,
      });
      onCreated(credential);
      handleClose();
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to create credential';
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
    setType('api_key');
    setProvider('');
    setSecretKey('');
    setSecretValue('');
    setErrors({});
    onClose();
  };

  const showProvider = type === 'api_key';
  const secretKeyPlaceholder = type === 'api_key' ? 'OPENAI_API_KEY' : 'key_name';
  const secretValuePlaceholder = type === 'api_key' ? 'sk-...' : 'secret value';

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="lg">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Add Credential</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl isInvalid={!!errors.name}>
              <FormLabel>Name</FormLabel>
              <Input
                placeholder="My OpenAI Key"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              <FormErrorMessage>{errors.name}</FormErrorMessage>
            </FormControl>

            <FormControl>
              <FormLabel>Description (optional)</FormLabel>
              <Input
                placeholder="Production API key for GPT-4"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Type</FormLabel>
              <Select
                value={type}
                onChange={(e) => setType(e.target.value as CredentialType)}
              >
                {credentialTypes.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </FormControl>

            {showProvider && (
              <FormControl>
                <FormLabel>Provider (optional)</FormLabel>
                <Select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value as ModelProvider | '')}
                  placeholder="Select provider"
                >
                  {providers.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </FormControl>
            )}

            <FormControl isInvalid={!!errors.secretKey}>
              <FormLabel>Secret Key Name</FormLabel>
              <Input
                placeholder={secretKeyPlaceholder}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                fontFamily="mono"
              />
              <FormErrorMessage>{errors.secretKey}</FormErrorMessage>
            </FormControl>

            <FormControl isInvalid={!!errors.secretValue}>
              <FormLabel>Secret Value</FormLabel>
              <Textarea
                placeholder={secretValuePlaceholder}
                value={secretValue}
                onChange={(e) => setSecretValue(e.target.value)}
                fontFamily="mono"
                rows={3}
              />
              <FormErrorMessage>{errors.secretValue}</FormErrorMessage>
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
            Add Credential
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
