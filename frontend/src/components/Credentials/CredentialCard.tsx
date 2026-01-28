import { useState } from 'react';
import {
  Card,
  CardBody,
  HStack,
  VStack,
  Heading,
  Text,
  Button,
  Icon,
  Badge,
  useColorModeValue,
  useToast,
  Spinner,
} from '@chakra-ui/react';
import { FiKey, FiEdit2, FiTrash2, FiCheckCircle } from 'react-icons/fi';
import { credentialsApi } from '@/api';
import type { Credential, CredentialType, ModelProvider } from '@/types';

interface CredentialCardProps {
  credential: Credential;
  onEdit?: (credential: Credential) => void;
  onDelete?: (credential: Credential) => void;
}

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

const typeLabels: Record<CredentialType, string> = {
  api_key: 'API Key',
  registry: 'Registry',
  database: 'Database',
  oauth_token: 'OAuth Token',
  ssh_key: 'SSH Key',
  custom: 'Custom',
};

const providerLabels: Record<ModelProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  ollama: 'Ollama',
  azure: 'Azure',
  custom: 'Custom',
};

export function CredentialCard({ credential, onEdit, onDelete }: CredentialCardProps) {
  const [isValidating, setIsValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<boolean | null>(null);
  const bgHover = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  const toast = useToast();

  const typeLabel = typeLabels[credential.type] || credential.type;
  const providerLabel = credential.provider
    ? providerLabels[credential.provider as ModelProvider] || credential.provider
    : null;

  const statusColor = credential.isExpired ? 'red' : 'green';
  const statusLabel = credential.isExpired ? 'Expired' : 'Active';

  const handleValidate = async () => {
    setIsValidating(true);
    setValidationResult(null);
    try {
      const result = await credentialsApi.validate(credential.id);
      setValidationResult(result.valid);
      toast({
        title: result.valid ? 'Credential valid' : 'Credential invalid',
        description: result.valid
          ? `${credential.name} is valid and not expired.`
          : `${credential.name} is invalid or expired.`,
        status: result.valid ? 'success' : 'warning',
        duration: 3000,
      });
    } catch (error: unknown) {
      setValidationResult(false);
      const message =
        error instanceof Error ? error.message : 'Failed to validate credential';
      toast({
        title: 'Validation failed',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsValidating(false);
    }
  };

  return (
    <Card
      variant="outline"
      borderColor={borderColor}
      _hover={{ bg: bgHover }}
      transition="background 0.2s"
    >
      <CardBody>
        <HStack justify="space-between" align="start">
          <HStack spacing={3} align="start">
            <Icon as={FiKey} boxSize={5} color="brand.500" mt={1} />
            <VStack align="start" spacing={1}>
              <Heading size="sm">{credential.name}</Heading>
              <Text fontSize="sm" color="gray.500">
                {typeLabel}
                {providerLabel && ` \u2022 ${providerLabel}`}
                {' \u2022 '}
                Updated {formatRelativeTime(credential.updatedAt)}
              </Text>
              <HStack spacing={2} mt={1}>
                <Badge colorScheme={statusColor} variant="subtle">
                  {statusLabel}
                </Badge>
                {validationResult !== null && (
                  <Badge
                    colorScheme={validationResult ? 'green' : 'red'}
                    variant="solid"
                  >
                    {validationResult ? 'Validated' : 'Invalid'}
                  </Badge>
                )}
                {credential.tags?.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="outline" colorScheme="gray">
                    {tag}
                  </Badge>
                ))}
              </HStack>
              {credential.description && (
                <Text fontSize="sm" color="gray.600" mt={1}>
                  {credential.description}
                </Text>
              )}
            </VStack>
          </HStack>

          <HStack spacing={2}>
            <Button
              size="sm"
              variant="ghost"
              leftIcon={isValidating ? <Spinner size="xs" /> : <FiCheckCircle />}
              onClick={handleValidate}
              isDisabled={isValidating}
            >
              {isValidating ? 'Checking...' : 'Validate'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              leftIcon={<FiEdit2 />}
              onClick={() => onEdit?.(credential)}
            >
              Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              colorScheme="red"
              leftIcon={<FiTrash2 />}
              onClick={() => onDelete?.(credential)}
            >
              Delete
            </Button>
          </HStack>
        </HStack>
      </CardBody>
    </Card>
  );
}
