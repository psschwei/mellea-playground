import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Text,
  Badge,
  Spinner,
  Center,
  Icon,
  Card,
  CardBody,
  useColorModeValue,
} from '@chakra-ui/react';
import { Link as RouterLink } from 'react-router-dom';
import { FiShare2, FiCode, FiCpu, FiGitBranch } from 'react-icons/fi';
import { sharingApi } from '@/api/sharing';
import type { SharedWithMeItem, ResourceType, Permission } from '@/types';

function getResourceIcon(resourceType: ResourceType) {
  switch (resourceType) {
    case 'program':
      return FiCode;
    case 'model':
      return FiCpu;
    case 'composition':
      return FiGitBranch;
    default:
      return FiShare2;
  }
}

function getResourcePath(resourceType: ResourceType, resourceId: string) {
  switch (resourceType) {
    case 'program':
      return `/programs/${resourceId}`;
    case 'model':
      return `/models/${resourceId}`;
    case 'composition':
      return `/compositions/${resourceId}`;
    default:
      return `/assets/${resourceId}`;
  }
}

function getPermissionColor(permission: Permission) {
  switch (permission) {
    case 'view':
      return 'blue';
    case 'run':
      return 'green';
    case 'edit':
      return 'orange';
    default:
      return 'gray';
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function SharedWithMePage() {
  const [items, setItems] = useState<SharedWithMeItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cardBg = useColorModeValue('white', 'gray.800');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');

  const loadSharedItems = useCallback(async () => {
    try {
      setError(null);
      const response = await sharingApi.getSharedWithMe();
      setItems(response.items);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load shared items';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSharedItems();
  }, [loadSharedItems]);

  if (isLoading) {
    return (
      <Center h="300px">
        <Spinner size="lg" color="brand.500" />
      </Center>
    );
  }

  if (error) {
    return (
      <Center h="300px" flexDirection="column">
        <Icon as={FiShare2} boxSize={12} color="red.400" mb={4} />
        <Text color="red.500">{error}</Text>
      </Center>
    );
  }

  return (
    <Box>
      <HStack justify="space-between" mb={6}>
        <Heading size="lg">Shared with Me</Heading>
        {items.length > 0 && (
          <Text color="gray.500" fontSize="sm">
            {items.length} item{items.length !== 1 ? 's' : ''}
          </Text>
        )}
      </HStack>

      {items.length === 0 ? (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiShare2} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            Nothing shared with you yet
          </Text>
          <Text color="gray.400">
            When someone shares a resource with you, it will appear here.
          </Text>
        </Center>
      ) : (
        <VStack spacing={3} align="stretch">
          {items.map((item) => (
            <Card
              key={`${item.resourceType}-${item.resourceId}`}
              as={RouterLink}
              to={getResourcePath(item.resourceType, item.resourceId)}
              bg={cardBg}
              _hover={{ bg: hoverBg, transform: 'translateY(-1px)', shadow: 'md' }}
              transition="all 0.2s"
              cursor="pointer"
            >
              <CardBody py={4}>
                <HStack spacing={4}>
                  <Icon
                    as={getResourceIcon(item.resourceType)}
                    boxSize={8}
                    color="brand.500"
                    p={1.5}
                    bg="brand.50"
                    borderRadius="md"
                  />
                  <Box flex={1}>
                    <HStack mb={1}>
                      <Text fontWeight="medium" fontSize="md">
                        {item.resourceName}
                      </Text>
                      <Badge colorScheme={getPermissionColor(item.permission)} size="sm">
                        {item.permission}
                      </Badge>
                    </HStack>
                    <HStack spacing={4} fontSize="sm" color="gray.500">
                      <Text textTransform="capitalize">{item.resourceType}</Text>
                      <Text>Shared by {item.sharedByName}</Text>
                      <Text>on {formatDate(item.sharedAt)}</Text>
                    </HStack>
                  </Box>
                </HStack>
              </CardBody>
            </Card>
          ))}
        </VStack>
      )}
    </Box>
  );
}
