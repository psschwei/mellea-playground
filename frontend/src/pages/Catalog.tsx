import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  HStack,
  VStack,
  Heading,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  Button,
  Icon,
  Center,
  Spinner,
  Tag,
  TagLabel,
  TagCloseButton,
  Wrap,
  WrapItem,
  useToast,
  useDisclosure,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Badge,
} from '@chakra-ui/react';
import { FiSearch, FiFolder, FiPlus, FiFilter, FiX } from 'react-icons/fi';
import { AssetCard } from '@/components/Catalog';
import { assetsApi } from '@/api/assets';
import type { Asset, AssetType, SharingMode } from '@/types';
import { useRef } from 'react';

type TabKey = 'my' | 'shared' | 'public';

interface CatalogFilters {
  search: string;
  type: AssetType | 'all';
  selectedTags: string[];
}

const tabSharingMap: Record<TabKey, SharingMode | undefined> = {
  my: 'private',
  shared: 'shared',
  public: 'public',
};

export function CatalogPage() {
  const toast = useToast();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const [assets, setAssets] = useState<Asset[]>([]);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('my');
  const [filters, setFilters] = useState<CatalogFilters>({
    search: '',
    type: 'all',
    selectedTags: [],
  });
  const [assetToDelete, setAssetToDelete] = useState<Asset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const { isOpen, onOpen, onClose } = useDisclosure();

  const loadAssets = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await assetsApi.list({
        type: filters.type !== 'all' ? filters.type : undefined,
        tags: filters.selectedTags.length > 0 ? filters.selectedTags : undefined,
        q: filters.search || undefined,
        sharing: tabSharingMap[activeTab],
      });
      setAssets(response.assets);
    } catch (error) {
      console.error('Failed to load assets:', error);
      toast({
        title: 'Error',
        description: 'Failed to load assets',
        status: 'error',
        duration: 5000,
      });
      setAssets([]);
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, filters.type, filters.selectedTags, filters.search, toast]);

  const loadTags = useCallback(async () => {
    try {
      const tags = await assetsApi.getTags();
      setAvailableTags(tags);
    } catch {
      // Tags are optional, ignore errors
    }
  }, []);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  // Extract unique tags from current assets as fallback
  const allTags = useMemo(() => {
    if (availableTags.length > 0) return availableTags;
    const tagSet = new Set<string>();
    assets.forEach((asset) => {
      asset.tags?.forEach((tag) => tagSet.add(tag));
    });
    return Array.from(tagSet).sort();
  }, [assets, availableTags]);

  const handleTabChange = (index: number) => {
    const tabs: TabKey[] = ['my', 'shared', 'public'];
    setActiveTab(tabs[index]);
  };

  const handleAddTag = (tag: string) => {
    if (!filters.selectedTags.includes(tag)) {
      setFilters((prev) => ({
        ...prev,
        selectedTags: [...prev.selectedTags, tag],
      }));
    }
  };

  const handleRemoveTag = (tag: string) => {
    setFilters((prev) => ({
      ...prev,
      selectedTags: prev.selectedTags.filter((t) => t !== tag),
    }));
  };

  const handleClearFilters = () => {
    setFilters({
      search: '',
      type: 'all',
      selectedTags: [],
    });
  };

  const handleDeleteAsset = (asset: Asset) => {
    setAssetToDelete(asset);
    onOpen();
  };

  const handleDeleteConfirm = async () => {
    if (!assetToDelete) return;

    setIsDeleting(true);
    try {
      await assetsApi.delete(assetToDelete.id);
      toast({
        title: 'Asset deleted',
        description: `${assetToDelete.name} has been deleted`,
        status: 'success',
        duration: 3000,
      });
      loadAssets();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete asset';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      setAssetToDelete(null);
      onClose();
    }
  };

  const hasActiveFilters = filters.search || filters.type !== 'all' || filters.selectedTags.length > 0;

  const tabLabels: Record<TabKey, string> = {
    my: 'My Assets',
    shared: 'Shared',
    public: 'Public',
  };

  const renderAssetList = () => {
    if (isLoading) {
      return (
        <Center h="300px">
          <Spinner size="lg" color="brand.500" />
        </Center>
      );
    }

    if (assets.length === 0) {
      return (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiFolder} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            No assets found
          </Text>
          <Text color="gray.400" textAlign="center" maxW="400px">
            {hasActiveFilters
              ? 'Try adjusting your filters or search query'
              : activeTab === 'my'
                ? 'Create a program or model to get started'
                : `No ${tabLabels[activeTab].toLowerCase()} assets available`}
          </Text>
        </Center>
      );
    }

    return (
      <VStack spacing={3} align="stretch">
        {assets.map((asset) => (
          <AssetCard
            key={asset.id}
            asset={asset}
            onDelete={activeTab === 'my' ? handleDeleteAsset : undefined}
          />
        ))}
      </VStack>
    );
  };

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <Heading size="lg">Catalog</Heading>
        <Button leftIcon={<FiPlus />} colorScheme="brand">
          New Asset
        </Button>
      </HStack>

      {/* Tabs */}
      <Tabs
        variant="enclosed"
        colorScheme="brand"
        index={['my', 'shared', 'public'].indexOf(activeTab)}
        onChange={handleTabChange}
      >
        <TabList>
          <Tab>My Assets</Tab>
          <Tab>Shared</Tab>
          <Tab>Public</Tab>
        </TabList>

        {/* Filters - outside TabPanels so they persist across tabs */}
        <Box py={4}>
          {/* Search and Type Filter Row */}
          <HStack spacing={4} mb={4}>
            <InputGroup maxW="400px">
              <InputLeftElement pointerEvents="none">
                <Icon as={FiSearch} color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search by name or description..."
                value={filters.search}
                onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
              />
            </InputGroup>

            <Select
              w="180px"
              value={filters.type}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  type: e.target.value as CatalogFilters['type'],
                }))
              }
            >
              <option value="all">All Types</option>
              <option value="program">Programs</option>
              <option value="model">Models</option>
              <option value="composition">Compositions</option>
            </Select>

            {hasActiveFilters && (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<FiX />}
                onClick={handleClearFilters}
              >
                Clear filters
              </Button>
            )}
          </HStack>

          {/* Tag Filter Row */}
          {allTags.length > 0 && (
            <Box>
              <HStack spacing={2} mb={2}>
                <Icon as={FiFilter} color="gray.500" boxSize={4} />
                <Text fontSize="sm" color="gray.500">
                  Filter by tags:
                </Text>
              </HStack>
              <Wrap spacing={2}>
                {allTags.map((tag) => {
                  const isSelected = filters.selectedTags.includes(tag);
                  return (
                    <WrapItem key={tag}>
                      <Tag
                        size="md"
                        variant={isSelected ? 'solid' : 'outline'}
                        colorScheme={isSelected ? 'brand' : 'gray'}
                        cursor="pointer"
                        onClick={() => (isSelected ? handleRemoveTag(tag) : handleAddTag(tag))}
                      >
                        <TagLabel>{tag}</TagLabel>
                        {isSelected && <TagCloseButton />}
                      </Tag>
                    </WrapItem>
                  );
                })}
              </Wrap>
            </Box>
          )}

          {/* Active filters summary */}
          {filters.selectedTags.length > 0 && (
            <HStack mt={3} spacing={2}>
              <Text fontSize="sm" color="gray.600">
                Filtering by:
              </Text>
              {filters.selectedTags.map((tag) => (
                <Badge key={tag} colorScheme="brand" variant="subtle">
                  {tag}
                </Badge>
              ))}
            </HStack>
          )}
        </Box>

        {/* Stats */}
        <HStack mb={4} spacing={4}>
          <Badge colorScheme="gray" px={2} py={1}>
            {isLoading ? '...' : assets.length} asset{assets.length !== 1 ? 's' : ''}
          </Badge>
        </HStack>

        <TabPanels>
          <TabPanel px={0}>{renderAssetList()}</TabPanel>
          <TabPanel px={0}>{renderAssetList()}</TabPanel>
          <TabPanel px={0}>{renderAssetList()}</TabPanel>
        </TabPanels>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Asset
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{assetToDelete?.name}"?
              <Text mt={2} color="gray.500">
                This action cannot be undone. Any associated runs or configurations may also be
                affected.
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
