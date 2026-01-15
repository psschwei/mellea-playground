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
  Select,
  VStack,
  HStack,
  Collapse,
  Box,
  Text,
  useToast,
  Spinner,
  Alert,
  AlertIcon,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  NumberIncrementStepper,
  NumberDecrementStepper,
} from '@chakra-ui/react';
import { FiChevronDown, FiChevronUp } from 'react-icons/fi';
import { modelsApi, credentialsApi } from '@/api';
import type {
  ModelAsset,
  CreateModelRequest,
  ModelProvider,
  Credential,
  ModelScope,
} from '@/types';

interface CreateModelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (model: ModelAsset) => void;
}

const providers: { value: ModelProvider; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'custom', label: 'Custom' },
];

const modelSuggestions: Record<ModelProvider, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo', 'o1', 'o1-mini'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  ollama: ['llama3.2', 'llama3.1', 'mistral', 'mixtral', 'codellama', 'phi3'],
  azure: ['gpt-4o', 'gpt-4', 'gpt-35-turbo'],
  custom: [],
};

const scopes: { value: ModelScope; label: string }[] = [
  { value: 'all', label: 'All (Chat, Agent, Composition)' },
  { value: 'chat', label: 'Chat only' },
  { value: 'agent', label: 'Agent only' },
  { value: 'composition', label: 'Composition only' },
];

export function CreateModelModal({ isOpen, onClose, onCreated }: CreateModelModalProps) {
  // Basic fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [provider, setProvider] = useState<ModelProvider>('openai');
  const [modelId, setModelId] = useState('');
  const [credentialsRef, setCredentialsRef] = useState('');
  const [scope, setScope] = useState<ModelScope>('all');

  // Endpoint config (for custom providers)
  const [baseUrl, setBaseUrl] = useState('');
  const [apiVersion, setApiVersion] = useState('');

  // Advanced params
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [temperature, setTemperature] = useState<number | undefined>(undefined);
  const [maxTokens, setMaxTokens] = useState<number | undefined>(undefined);
  const [contextWindow, setContextWindow] = useState<number | undefined>(undefined);

  // State
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loadingCredentials, setLoadingCredentials] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const toast = useToast();

  // Fetch credentials when provider changes
  useEffect(() => {
    const fetchCredentials = async () => {
      setLoadingCredentials(true);
      try {
        const creds = await credentialsApi.list({
          type: 'api_key',
          provider: provider,
        });
        setCredentials(creds);
        // Reset credential selection if not matching
        if (credentialsRef && !creds.some((c) => c.id === credentialsRef)) {
          setCredentialsRef('');
        }
      } catch (error) {
        console.error('Failed to fetch credentials:', error);
      } finally {
        setLoadingCredentials(false);
      }
    };

    if (isOpen) {
      fetchCredentials();
    }
  }, [provider, isOpen]);

  // Auto-generate name from provider + model
  useEffect(() => {
    if (modelId && !name) {
      const providerLabel = providers.find((p) => p.value === provider)?.label || provider;
      setName(`${providerLabel} ${modelId}`);
    }
  }, [modelId, provider]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!modelId.trim()) {
      newErrors.modelId = 'Model ID is required';
    }

    if (provider !== 'ollama' && !credentialsRef) {
      newErrors.credentialsRef = 'Credentials are required for this provider';
    }

    if ((provider === 'custom' || provider === 'azure') && !baseUrl.trim()) {
      newErrors.baseUrl = 'Base URL is required for this provider';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const request: CreateModelRequest = {
        type: 'model',
        name: name.trim(),
        description: description.trim() || undefined,
        provider,
        modelId: modelId.trim(),
        credentialsRef: credentialsRef || undefined,
        scope,
      };

      // Add endpoint config if needed
      if (baseUrl.trim()) {
        request.endpoint = {
          baseUrl: baseUrl.trim(),
          apiVersion: apiVersion.trim() || undefined,
        };
      }

      // Add default params if set
      if (temperature !== undefined || maxTokens !== undefined) {
        request.defaultParams = {
          temperature,
          maxTokens,
        };
      }

      // Add capabilities if set
      if (contextWindow !== undefined) {
        request.capabilities = {
          contextWindow,
        };
      }

      const model = await modelsApi.create(request);
      toast({
        title: 'Model created',
        description: `${model.name} has been configured successfully.`,
        status: 'success',
        duration: 3000,
      });
      onCreated(model);
      handleClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to create model';
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

  const handleTest = async () => {
    if (!credentialsRef && provider !== 'ollama') {
      toast({
        title: 'Cannot test',
        description: 'Please select credentials first',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      // For testing before creation, we'd need a different endpoint
      // For now, just validate the credentials
      const validation = await credentialsApi.validate(credentialsRef);
      if (validation.valid) {
        setTestResult({
          success: true,
          message: 'Credentials validated successfully',
        });
      } else {
        setTestResult({
          success: false,
          message: 'Credential validation failed',
        });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Test failed';
      setTestResult({
        success: false,
        message,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleClose = () => {
    setName('');
    setDescription('');
    setProvider('openai');
    setModelId('');
    setCredentialsRef('');
    setScope('all');
    setBaseUrl('');
    setApiVersion('');
    setTemperature(undefined);
    setMaxTokens(undefined);
    setContextWindow(undefined);
    setShowAdvanced(false);
    setTestResult(null);
    setErrors({});
    onClose();
  };

  const suggestions = modelSuggestions[provider] || [];
  const needsEndpoint = provider === 'custom' || provider === 'azure';
  const needsCredentials = provider !== 'ollama';

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Add Model Configuration</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <VStack spacing={4} align="stretch">
            {/* Provider Selection */}
            <FormControl>
              <FormLabel>Provider</FormLabel>
              <Select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value as ModelProvider);
                  setModelId('');
                  setCredentialsRef('');
                }}
              >
                {providers.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </FormControl>

            {/* Model ID */}
            <FormControl isInvalid={!!errors.modelId}>
              <FormLabel>Model ID</FormLabel>
              {suggestions.length > 0 ? (
                <Select
                  value={modelId}
                  onChange={(e) => setModelId(e.target.value)}
                  placeholder="Select a model"
                >
                  {suggestions.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value="__custom__">Custom model ID...</option>
                </Select>
              ) : (
                <Input
                  placeholder="Enter model identifier"
                  value={modelId}
                  onChange={(e) => setModelId(e.target.value)}
                />
              )}
              {modelId === '__custom__' && (
                <Input
                  mt={2}
                  placeholder="Enter custom model ID"
                  onChange={(e) => setModelId(e.target.value)}
                />
              )}
              <FormErrorMessage>{errors.modelId}</FormErrorMessage>
            </FormControl>

            {/* Credential Reference Picker */}
            {needsCredentials && (
              <FormControl isInvalid={!!errors.credentialsRef}>
                <FormLabel>API Credentials</FormLabel>
                {loadingCredentials ? (
                  <HStack>
                    <Spinner size="sm" />
                    <Text fontSize="sm" color="gray.500">
                      Loading credentials...
                    </Text>
                  </HStack>
                ) : credentials.length === 0 ? (
                  <Alert status="warning" size="sm">
                    <AlertIcon />
                    <Text fontSize="sm">
                      No credentials found for {provider}. Create one in the Credentials page first.
                    </Text>
                  </Alert>
                ) : (
                  <Select
                    value={credentialsRef}
                    onChange={(e) => setCredentialsRef(e.target.value)}
                    placeholder="Select credentials"
                  >
                    {credentials.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} {c.isExpired && '(expired)'}
                      </option>
                    ))}
                  </Select>
                )}
                <FormHelperText>
                  Credentials are securely stored and used for API authentication
                </FormHelperText>
                <FormErrorMessage>{errors.credentialsRef}</FormErrorMessage>
              </FormControl>
            )}

            {/* Endpoint Config for custom/azure */}
            {needsEndpoint && (
              <>
                <FormControl isInvalid={!!errors.baseUrl}>
                  <FormLabel>Base URL</FormLabel>
                  <Input
                    placeholder={
                      provider === 'azure'
                        ? 'https://your-resource.openai.azure.com'
                        : 'https://api.example.com/v1'
                    }
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                  />
                  <FormErrorMessage>{errors.baseUrl}</FormErrorMessage>
                </FormControl>

                {provider === 'azure' && (
                  <FormControl>
                    <FormLabel>API Version</FormLabel>
                    <Input
                      placeholder="2024-02-15-preview"
                      value={apiVersion}
                      onChange={(e) => setApiVersion(e.target.value)}
                    />
                  </FormControl>
                )}
              </>
            )}

            {/* Name (auto-filled but editable) */}
            <FormControl isInvalid={!!errors.name}>
              <FormLabel>Display Name</FormLabel>
              <Input
                placeholder="GPT-4o Production"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <FormErrorMessage>{errors.name}</FormErrorMessage>
            </FormControl>

            {/* Description */}
            <FormControl>
              <FormLabel>Description (optional)</FormLabel>
              <Input
                placeholder="Primary model for chat completions"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormControl>

            {/* Scope */}
            <FormControl>
              <FormLabel>Usage Scope</FormLabel>
              <Select value={scope} onChange={(e) => setScope(e.target.value as ModelScope)}>
                {scopes.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </FormControl>

            {/* Advanced Settings */}
            <Box>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAdvanced(!showAdvanced)}
                rightIcon={showAdvanced ? <FiChevronUp /> : <FiChevronDown />}
              >
                Advanced Settings
              </Button>
              <Collapse in={showAdvanced}>
                <VStack spacing={4} mt={4} align="stretch" pl={4}>
                  <FormControl>
                    <FormLabel>Default Temperature</FormLabel>
                    <NumberInput
                      value={temperature ?? ''}
                      onChange={(_, val) => setTemperature(isNaN(val) ? undefined : val)}
                      min={0}
                      max={2}
                      step={0.1}
                    >
                      <NumberInputField placeholder="0.7" />
                      <NumberInputStepper>
                        <NumberIncrementStepper />
                        <NumberDecrementStepper />
                      </NumberInputStepper>
                    </NumberInput>
                  </FormControl>

                  <FormControl>
                    <FormLabel>Default Max Tokens</FormLabel>
                    <NumberInput
                      value={maxTokens ?? ''}
                      onChange={(_, val) => setMaxTokens(isNaN(val) ? undefined : val)}
                      min={1}
                      max={200000}
                    >
                      <NumberInputField placeholder="4096" />
                      <NumberInputStepper>
                        <NumberIncrementStepper />
                        <NumberDecrementStepper />
                      </NumberInputStepper>
                    </NumberInput>
                  </FormControl>

                  <FormControl>
                    <FormLabel>Context Window Size</FormLabel>
                    <NumberInput
                      value={contextWindow ?? ''}
                      onChange={(_, val) => setContextWindow(isNaN(val) ? undefined : val)}
                      min={1024}
                      max={2000000}
                    >
                      <NumberInputField placeholder="128000" />
                      <NumberInputStepper>
                        <NumberIncrementStepper />
                        <NumberDecrementStepper />
                      </NumberInputStepper>
                    </NumberInput>
                  </FormControl>
                </VStack>
              </Collapse>
            </Box>

            {/* Test Result */}
            {testResult && (
              <Alert status={testResult.success ? 'success' : 'error'}>
                <AlertIcon />
                {testResult.message}
              </Alert>
            )}
          </VStack>
        </ModalBody>

        <ModalFooter>
          <HStack spacing={3}>
            <Button variant="ghost" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              variant="outline"
              onClick={handleTest}
              isLoading={isTesting}
              loadingText="Testing..."
              isDisabled={!credentialsRef && needsCredentials}
            >
              Test Connection
            </Button>
            <Button
              colorScheme="brand"
              onClick={handleSubmit}
              isLoading={isSubmitting}
              loadingText="Creating..."
            >
              Add Model
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
