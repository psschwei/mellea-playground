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
  FormHelperText,
  Input,
  Textarea,
  Select,
  VStack,
  HStack,
  Radio,
  RadioGroup,
  useToast,
  Text,
  Divider,
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

// Provider-specific fields configuration
interface FieldConfig {
  key: string;
  label: string;
  placeholder: string;
  required: boolean;
  isPassword?: boolean;
}

const providerFieldsConfig: Record<string, FieldConfig[]> = {
  openai: [
    { key: 'api_key', label: 'API Key', placeholder: 'sk-...', required: true, isPassword: true },
    { key: 'organization_id', label: 'Organization ID', placeholder: 'org-... (optional)', required: false },
  ],
  anthropic: [
    { key: 'api_key', label: 'API Key', placeholder: 'sk-ant-...', required: true, isPassword: true },
  ],
  ollama: [
    { key: 'api_key', label: 'API Key', placeholder: 'Optional API key', required: false, isPassword: true },
  ],
  custom: [
    { key: 'api_key', label: 'API Key', placeholder: 'Your API key', required: false, isPassword: true },
  ],
};

// Azure has two auth modes
const azureApiKeyFields: FieldConfig[] = [
  { key: 'endpoint', label: 'Endpoint', placeholder: 'https://your-resource.openai.azure.com', required: true },
  { key: 'api_key', label: 'API Key', placeholder: 'Your Azure API key', required: true, isPassword: true },
  { key: 'api_version', label: 'API Version', placeholder: '2024-02-15-preview (optional)', required: false },
];

const azureOAuthFields: FieldConfig[] = [
  { key: 'endpoint', label: 'Endpoint', placeholder: 'https://your-resource.openai.azure.com', required: true },
  { key: 'tenant_id', label: 'Tenant ID', placeholder: 'Your Azure tenant ID', required: true },
  { key: 'client_id', label: 'Client ID', placeholder: 'Your Azure client ID', required: true },
  { key: 'client_secret', label: 'Client Secret', placeholder: 'Your Azure client secret', required: true, isPassword: true },
  { key: 'api_version', label: 'API Version', placeholder: '2024-02-15-preview (optional)', required: false },
];

export function CreateCredentialModal({ isOpen, onClose, onCreated }: CreateCredentialModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<CredentialType>('api_key');
  const [provider, setProvider] = useState<ModelProvider | ''>('');
  const [azureAuthMode, setAzureAuthMode] = useState<'api_key' | 'oauth'>('api_key');
  const [secretData, setSecretData] = useState<Record<string, string>>({});
  // For non-API-key credential types, use generic key/value
  const [genericSecretKey, setGenericSecretKey] = useState('');
  const [genericSecretValue, setGenericSecretValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();

  const getFieldsForProvider = (): FieldConfig[] => {
    if (!provider) return [];
    if (provider === 'azure') {
      return azureAuthMode === 'api_key' ? azureApiKeyFields : azureOAuthFields;
    }
    return providerFieldsConfig[provider] || [];
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (type === 'api_key' && provider) {
      // Validate provider-specific fields
      const fields = getFieldsForProvider();
      for (const field of fields) {
        if (field.required && !secretData[field.key]?.trim()) {
          newErrors[field.key] = `${field.label} is required`;
        }
      }
    } else {
      // Validate generic secret for other types
      if (!genericSecretKey.trim()) {
        newErrors.genericSecretKey = 'Secret key name is required';
      }
      if (!genericSecretValue.trim()) {
        newErrors.genericSecretValue = 'Secret value is required';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      let finalSecretData: Record<string, string>;

      if (type === 'api_key' && provider) {
        // Use provider-specific fields, filter out empty values
        finalSecretData = Object.fromEntries(
          Object.entries(secretData).filter(([_, value]) => value.trim() !== '')
        );
      } else {
        // Use generic key/value
        finalSecretData = { [genericSecretKey.trim()]: genericSecretValue };
      }

      const request: CreateCredentialRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        type,
        provider: provider || undefined,
        secretData: finalSecretData,
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
    setAzureAuthMode('api_key');
    setSecretData({});
    setGenericSecretKey('');
    setGenericSecretValue('');
    setErrors({});
    onClose();
  };

  const handleSecretChange = (key: string, value: string) => {
    setSecretData((prev) => ({ ...prev, [key]: value }));
  };

  const handleProviderChange = (newProvider: ModelProvider | '') => {
    setProvider(newProvider);
    setSecretData({});  // Clear secrets when provider changes
    setAzureAuthMode('api_key');  // Reset Azure auth mode
  };

  const showProviderSelect = type === 'api_key';
  const showProviderFields = type === 'api_key' && provider;
  const showGenericFields = type !== 'api_key' || !provider;

  const fields = getFieldsForProvider();

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

            {showProviderSelect && (
              <FormControl>
                <FormLabel>Provider</FormLabel>
                <Select
                  value={provider}
                  onChange={(e) => handleProviderChange(e.target.value as ModelProvider | '')}
                  placeholder="Select provider"
                >
                  {providers.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </Select>
                <FormHelperText>
                  Provider-specific validation will be applied
                </FormHelperText>
              </FormControl>
            )}

            {showProviderFields && (
              <>
                <Divider />
                <Text fontSize="sm" fontWeight="medium" color="gray.600">
                  {provider === 'azure' ? 'Azure OpenAI' : providers.find(p => p.value === provider)?.label} Credentials
                </Text>

                {provider === 'azure' && (
                  <FormControl>
                    <FormLabel>Authentication Mode</FormLabel>
                    <RadioGroup value={azureAuthMode} onChange={(v) => setAzureAuthMode(v as 'api_key' | 'oauth')}>
                      <HStack spacing={4}>
                        <Radio value="api_key">API Key</Radio>
                        <Radio value="oauth">OAuth (Service Principal)</Radio>
                      </HStack>
                    </RadioGroup>
                    <FormHelperText>
                      {azureAuthMode === 'api_key'
                        ? 'Use API key and endpoint'
                        : 'Use Azure AD service principal credentials'}
                    </FormHelperText>
                  </FormControl>
                )}

                {fields.map((field) => (
                  <FormControl key={field.key} isInvalid={!!errors[field.key]}>
                    <FormLabel>
                      {field.label}
                      {field.required && <Text as="span" color="red.500"> *</Text>}
                    </FormLabel>
                    <Input
                      type={field.isPassword ? 'password' : 'text'}
                      placeholder={field.placeholder}
                      value={secretData[field.key] || ''}
                      onChange={(e) => handleSecretChange(field.key, e.target.value)}
                      fontFamily="mono"
                    />
                    <FormErrorMessage>{errors[field.key]}</FormErrorMessage>
                  </FormControl>
                ))}
              </>
            )}

            {showGenericFields && (
              <>
                <Divider />
                <Text fontSize="sm" fontWeight="medium" color="gray.600">
                  Secret Data
                </Text>
                <FormControl isInvalid={!!errors.genericSecretKey}>
                  <FormLabel>Secret Key Name</FormLabel>
                  <Input
                    placeholder={type === 'database' ? 'connection_string' : 'key_name'}
                    value={genericSecretKey}
                    onChange={(e) => setGenericSecretKey(e.target.value)}
                    fontFamily="mono"
                  />
                  <FormErrorMessage>{errors.genericSecretKey}</FormErrorMessage>
                </FormControl>

                <FormControl isInvalid={!!errors.genericSecretValue}>
                  <FormLabel>Secret Value</FormLabel>
                  <Textarea
                    placeholder="Enter secret value"
                    value={genericSecretValue}
                    onChange={(e) => setGenericSecretValue(e.target.value)}
                    fontFamily="mono"
                    rows={3}
                  />
                  <FormErrorMessage>{errors.genericSecretValue}</FormErrorMessage>
                </FormControl>
              </>
            )}
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
