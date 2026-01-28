import { useState, useEffect } from 'react';
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
  FormHelperText,
  Input,
  VStack,
  HStack,
  Tag,
  TagLabel,
  TagCloseButton,
  Text,
  Divider,
  useToast,
} from '@chakra-ui/react';
import { credentialsApi } from '@/api';
import type { Credential, UpdateCredentialRequest, ModelProvider } from '@/types';

interface EditCredentialModalProps {
  isOpen: boolean;
  onClose: () => void;
  credential: Credential;
  onUpdated: (credential: Credential) => void;
}

// Provider-specific fields configuration
const providerFields: Record<string, { key: string; label: string; placeholder: string; required: boolean }[]> = {
  openai: [
    { key: 'api_key', label: 'API Key', placeholder: 'sk-...', required: true },
    { key: 'organization_id', label: 'Organization ID', placeholder: 'org-...', required: false },
  ],
  anthropic: [
    { key: 'api_key', label: 'API Key', placeholder: 'sk-ant-...', required: true },
  ],
  ollama: [
    { key: 'api_key', label: 'API Key', placeholder: 'Optional API key', required: false },
  ],
  azure: [
    { key: 'endpoint', label: 'Endpoint', placeholder: 'https://your-resource.openai.azure.com', required: true },
    { key: 'api_key', label: 'API Key', placeholder: 'Your Azure API key', required: false },
    { key: 'tenant_id', label: 'Tenant ID', placeholder: 'Azure tenant ID (for OAuth)', required: false },
    { key: 'client_id', label: 'Client ID', placeholder: 'Azure client ID (for OAuth)', required: false },
    { key: 'client_secret', label: 'Client Secret', placeholder: 'Azure client secret (for OAuth)', required: false },
    { key: 'api_version', label: 'API Version', placeholder: '2024-02-15-preview', required: false },
  ],
  custom: [
    { key: 'api_key', label: 'API Key', placeholder: 'Your API key', required: false },
  ],
};

export function EditCredentialModal({ isOpen, onClose, credential, onUpdated }: EditCredentialModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [secretData, setSecretData] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();

  // Initialize form when modal opens or credential changes
  useEffect(() => {
    if (isOpen && credential) {
      setName(credential.name);
      setDescription(credential.description || '');
      setTags(credential.tags || []);
      setSecretData({});
      setErrors({});
    }
  }, [isOpen, credential]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const request: UpdateCredentialRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        tags: tags.length > 0 ? tags : undefined,
      };

      // Only include secretData if any values were entered
      const nonEmptySecrets = Object.fromEntries(
        Object.entries(secretData).filter(([_, value]) => value.trim() !== '')
      );
      if (Object.keys(nonEmptySecrets).length > 0) {
        request.secretData = nonEmptySecrets;
      }

      const updated = await credentialsApi.update(credential.id, request);
      toast({
        title: 'Credential updated',
        description: `${updated.name} has been updated successfully.`,
        status: 'success',
        duration: 3000,
      });
      onUpdated(updated);
      onClose();
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update credential';
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

  const handleAddTag = () => {
    const newTag = tagInput.trim().toLowerCase();
    if (newTag && !tags.includes(newTag)) {
      setTags([...tags, newTag]);
    }
    setTagInput('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t !== tagToRemove));
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      handleAddTag();
    }
  };

  const handleSecretChange = (key: string, value: string) => {
    setSecretData((prev) => ({ ...prev, [key]: value }));
  };

  // Get fields for current provider
  const provider = credential.provider as ModelProvider | undefined;
  const fields = provider && providerFields[provider] ? providerFields[provider] : [];

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Edit Credential</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl isInvalid={!!errors.name}>
              <FormLabel>Name</FormLabel>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              <FormErrorMessage>{errors.name}</FormErrorMessage>
            </FormControl>

            <FormControl>
              <FormLabel>Description</FormLabel>
              <Input
                placeholder="Optional description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Tags</FormLabel>
              <HStack spacing={2} wrap="wrap" mb={2}>
                {tags.map((tag) => (
                  <Tag key={tag} colorScheme="brand" variant="subtle">
                    <TagLabel>{tag}</TagLabel>
                    <TagCloseButton onClick={() => handleRemoveTag(tag)} />
                  </Tag>
                ))}
              </HStack>
              <Input
                placeholder="Add tags (press Enter)"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={handleTagKeyDown}
                onBlur={handleAddTag}
              />
            </FormControl>

            {fields.length > 0 && (
              <>
                <Divider />
                <Text fontSize="sm" fontWeight="medium" color="gray.600">
                  Update Secret Values (leave empty to keep existing)
                </Text>

                {fields.map((field) => (
                  <FormControl key={field.key}>
                    <FormLabel>
                      {field.label}
                      {field.required && <Text as="span" color="red.500"> *</Text>}
                    </FormLabel>
                    <Input
                      type="password"
                      placeholder={field.placeholder}
                      value={secretData[field.key] || ''}
                      onChange={(e) => handleSecretChange(field.key, e.target.value)}
                      fontFamily="mono"
                    />
                    <FormHelperText>
                      {secretData[field.key] ? 'New value entered' : 'Current value will be kept if empty'}
                    </FormHelperText>
                  </FormControl>
                ))}
              </>
            )}
          </VStack>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            Cancel
          </Button>
          <Button
            colorScheme="brand"
            onClick={handleSubmit}
            isLoading={isSubmitting}
            loadingText="Saving..."
          >
            Save Changes
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
