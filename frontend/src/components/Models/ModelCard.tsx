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
} from '@chakra-ui/react';
import { FiCpu, FiZap, FiChevronRight, FiTrash2 } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import type { ModelAsset, ModelProvider } from '@/types';

interface ModelCardProps {
  model: ModelAsset;
  onTest?: (model: ModelAsset) => void;
  onDelete?: (model: ModelAsset) => void;
  isTesting?: boolean;
}

const providerColors: Record<ModelProvider, string> = {
  openai: 'green',
  anthropic: 'orange',
  ollama: 'purple',
  azure: 'blue',
  custom: 'gray',
};

const providerLabels: Record<ModelProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  ollama: 'Ollama',
  azure: 'Azure',
  custom: 'Custom',
};

export function ModelCard({ model, onTest, onDelete, isTesting = false }: ModelCardProps) {
  const navigate = useNavigate();
  const bgHover = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  const scopeLabel = model.scope === 'all' ? 'All scopes' : model.scope || 'chat';

  return (
    <Card
      variant="outline"
      borderColor={borderColor}
      _hover={{ bg: bgHover, cursor: 'pointer' }}
      transition="background 0.2s"
      onClick={() => navigate(`/models/${model.id}`)}
    >
      <CardBody>
        <HStack justify="space-between" align="start">
          <HStack spacing={3} align="start">
            <Icon as={FiCpu} boxSize={5} color="brand.500" mt={1} />
            <VStack align="start" spacing={1}>
              <Heading size="sm">{model.name}</Heading>
              <Text fontSize="sm" color="gray.500">
                {model.modelId} &bull; {scopeLabel}
              </Text>
              <HStack spacing={2} mt={1}>
                <Badge colorScheme={providerColors[model.provider]} variant="subtle">
                  {providerLabels[model.provider]}
                </Badge>
                {model.capabilities?.supportsToolCalling && (
                  <Badge colorScheme="purple" variant="outline">
                    Tools
                  </Badge>
                )}
                {model.tags?.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant="outline" colorScheme="gray">
                    {tag}
                  </Badge>
                ))}
                {(model.tags?.length ?? 0) > 2 && (
                  <Badge variant="outline" colorScheme="gray">
                    +{(model.tags?.length ?? 0) - 2}
                  </Badge>
                )}
              </HStack>
            </VStack>
          </HStack>

          <HStack spacing={2} onClick={(e) => e.stopPropagation()}>
            {onTest && (
              <Button
                size="sm"
                colorScheme="brand"
                leftIcon={<FiZap />}
                isLoading={isTesting}
                loadingText="Testing"
                onClick={() => onTest(model)}
              >
                Test
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              rightIcon={<FiChevronRight />}
              onClick={() => navigate(`/models/${model.id}`)}
            >
              View
            </Button>
            {onDelete && (
              <Button
                size="sm"
                variant="ghost"
                colorScheme="red"
                onClick={() => onDelete(model)}
                aria-label="Delete model"
              >
                <Icon as={FiTrash2} />
              </Button>
            )}
          </HStack>
        </HStack>
      </CardBody>
    </Card>
  );
}
