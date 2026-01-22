import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  HStack,
  VStack,
  Heading,
  Text,
  Button,
  Icon,
  Center,
  Spinner,
  Badge,
  Card,
  CardBody,
  SimpleGrid,
  useToast,
  useDisclosure,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  IconButton,
  Tooltip,
  useColorModeValue,
  Input,
  InputGroup,
  InputLeftElement,
} from '@chakra-ui/react';
import { FiPlus, FiEdit2, FiTrash2, FiGitMerge, FiSearch, FiEye, FiClock } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import { useRef } from 'react';
import { compositionsApi } from '@/api/assets';
import type { CompositionAsset } from '@/types';

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

interface CompositionCardProps {
  composition: CompositionAsset;
  onEdit: (composition: CompositionAsset) => void;
  onView: (composition: CompositionAsset) => void;
  onDelete: (composition: CompositionAsset) => void;
}

function CompositionCard({ composition, onEdit, onView, onDelete }: CompositionCardProps) {
  const bgHover = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  const nodeCount = composition.graph?.nodes?.length ?? 0;
  const edgeCount = composition.graph?.edges?.length ?? 0;

  return (
    <Card
      variant="outline"
      borderColor={borderColor}
      _hover={{ bg: bgHover }}
      transition="background 0.2s"
    >
      <CardBody>
        <VStack align="stretch" spacing={3}>
          <HStack justify="space-between" align="start">
            <HStack spacing={2}>
              <Icon as={FiGitMerge} color="teal.500" boxSize={5} />
              <VStack align="start" spacing={0}>
                <Heading size="sm" noOfLines={1}>
                  {composition.name}
                </Heading>
                <Text fontSize="xs" color="gray.500">
                  v{composition.version}
                </Text>
              </VStack>
            </HStack>
            <HStack spacing={1}>
              <Tooltip label="Edit in Builder">
                <IconButton
                  aria-label="Edit composition"
                  icon={<FiEdit2 />}
                  size="sm"
                  variant="ghost"
                  onClick={() => onEdit(composition)}
                />
              </Tooltip>
              <Tooltip label="View details">
                <IconButton
                  aria-label="View composition"
                  icon={<FiEye />}
                  size="sm"
                  variant="ghost"
                  onClick={() => onView(composition)}
                />
              </Tooltip>
              <Tooltip label="Delete">
                <IconButton
                  aria-label="Delete composition"
                  icon={<FiTrash2 />}
                  size="sm"
                  variant="ghost"
                  colorScheme="red"
                  onClick={() => onDelete(composition)}
                />
              </Tooltip>
            </HStack>
          </HStack>

          {composition.description && (
            <Text fontSize="sm" color="gray.600" noOfLines={2}>
              {composition.description}
            </Text>
          )}

          <HStack spacing={4} fontSize="xs" color="gray.500">
            <HStack spacing={1}>
              <Icon as={FiGitMerge} boxSize={3} />
              <Text>{nodeCount} nodes</Text>
            </HStack>
            <Text>&bull;</Text>
            <Text>{edgeCount} connections</Text>
          </HStack>

          <HStack justify="space-between" align="center">
            <HStack spacing={2} flexWrap="wrap">
              {composition.tags?.slice(0, 3).map((tag) => (
                <Badge key={tag} variant="subtle" colorScheme="gray" size="sm">
                  {tag}
                </Badge>
              ))}
              {composition.tags && composition.tags.length > 3 && (
                <Badge variant="outline" colorScheme="gray" size="sm">
                  +{composition.tags.length - 3}
                </Badge>
              )}
            </HStack>
            <HStack spacing={1} fontSize="xs" color="gray.400">
              <Icon as={FiClock} boxSize={3} />
              <Text>{formatRelativeTime(composition.updatedAt)}</Text>
            </HStack>
          </HStack>
        </VStack>
      </CardBody>
    </Card>
  );
}

export function CompositionsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const [compositions, setCompositions] = useState<CompositionAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [compositionToDelete, setCompositionToDelete] = useState<CompositionAsset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const { isOpen, onOpen, onClose } = useDisclosure();

  const loadCompositions = useCallback(async () => {
    setIsLoading(true);
    try {
      const list = await compositionsApi.list();
      setCompositions(list);
    } catch (error) {
      console.error('Failed to load compositions:', error);
      toast({
        title: 'Error',
        description: 'Failed to load compositions',
        status: 'error',
        duration: 5000,
      });
      setCompositions([]);
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadCompositions();
  }, [loadCompositions]);

  const filteredCompositions = compositions.filter((c) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      c.name.toLowerCase().includes(query) ||
      c.description?.toLowerCase().includes(query) ||
      c.tags?.some((t) => t.toLowerCase().includes(query))
    );
  });

  const handleNewComposition = () => {
    navigate('/compositions/new');
  };

  const handleEdit = (composition: CompositionAsset) => {
    navigate(`/compositions/${composition.id}/edit`);
  };

  const handleView = (composition: CompositionAsset) => {
    navigate(`/compositions/${composition.id}`);
  };

  const handleDeleteClick = (composition: CompositionAsset) => {
    setCompositionToDelete(composition);
    onOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!compositionToDelete) return;

    setIsDeleting(true);
    try {
      await compositionsApi.delete(compositionToDelete.id);
      toast({
        title: 'Composition deleted',
        description: `${compositionToDelete.name} has been deleted`,
        status: 'success',
        duration: 3000,
      });
      loadCompositions();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete composition';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      setCompositionToDelete(null);
      onClose();
    }
  };

  const renderContent = () => {
    if (isLoading) {
      return (
        <Center h="300px">
          <VStack spacing={4}>
            <Spinner size="lg" color="teal.500" />
            <Text color="gray.500">Loading compositions...</Text>
          </VStack>
        </Center>
      );
    }

    if (filteredCompositions.length === 0) {
      return (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiGitMerge} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            {searchQuery ? 'No matching compositions' : 'No compositions yet'}
          </Text>
          <Text color="gray.400" textAlign="center" maxW="400px" mb={4}>
            {searchQuery
              ? 'Try adjusting your search query'
              : 'Create your first visual workflow composition'}
          </Text>
          {!searchQuery && (
            <Button leftIcon={<FiPlus />} colorScheme="teal" onClick={handleNewComposition}>
              New Composition
            </Button>
          )}
        </Center>
      );
    }

    return (
      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
        {filteredCompositions.map((composition) => (
          <CompositionCard
            key={composition.id}
            composition={composition}
            onEdit={handleEdit}
            onView={handleView}
            onDelete={handleDeleteClick}
          />
        ))}
      </SimpleGrid>
    );
  };

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <VStack align="start" spacing={1}>
          <Heading size="lg">Compositions</Heading>
          <Text color="gray.500" fontSize="sm">
            Visual workflow compositions built with the drag-and-drop builder
          </Text>
        </VStack>
        <Button leftIcon={<FiPlus />} colorScheme="teal" onClick={handleNewComposition}>
          New Composition
        </Button>
      </HStack>

      {/* Search */}
      <HStack mb={6} spacing={4}>
        <InputGroup maxW="400px">
          <InputLeftElement pointerEvents="none">
            <Icon as={FiSearch} color="gray.400" />
          </InputLeftElement>
          <Input
            placeholder="Search compositions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </InputGroup>
        <Badge colorScheme="gray" px={2} py={1}>
          {isLoading ? '...' : filteredCompositions.length} composition
          {filteredCompositions.length !== 1 ? 's' : ''}
        </Badge>
      </HStack>

      {/* Content */}
      {renderContent()}

      {/* Delete Confirmation Dialog */}
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Composition
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{compositionToDelete?.name}"?
              <Text mt={2} color="gray.500">
                This action cannot be undone. The composition and all its configuration will be
                permanently deleted.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose}>
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
