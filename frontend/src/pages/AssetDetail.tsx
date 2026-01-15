import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Button,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Spinner,
  Center,
  IconButton,
  Badge,
  Icon,
  useToast,
  useDisclosure,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Divider,
  SimpleGrid,
  Card,
  CardBody,
  Tooltip,
} from '@chakra-ui/react';
import {
  FiArrowLeft,
  FiFile,
  FiCpu,
  FiGitMerge,
  FiTrash2,
  FiEdit2,
  FiGlobe,
  FiUsers,
  FiLock,
  FiClock,
  FiTag,
} from 'react-icons/fi';
import { CodeViewer } from '@/components/Programs';
import { MetadataEditModal } from '@/components/Catalog';
import { assetsApi } from '@/api/assets';
import type { Asset, ProgramAsset, ModelAsset, AssetType } from '@/types';

const assetTypeConfig: Record<AssetType, { icon: typeof FiFile; label: string; color: string }> = {
  program: { icon: FiFile, label: 'Program', color: 'blue' },
  model: { icon: FiCpu, label: 'Model', color: 'purple' },
  composition: { icon: FiGitMerge, label: 'Composition', color: 'teal' },
};

const sharingConfig = {
  private: { icon: FiLock, label: 'Private', color: 'gray' },
  shared: { icon: FiUsers, label: 'Shared', color: 'blue' },
  public: { icon: FiGlobe, label: 'Public', color: 'green' },
};

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString();
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

interface InfoRowProps {
  label: string;
  value: React.ReactNode;
  icon?: typeof FiClock;
}

function InfoRow({ label, value, icon }: InfoRowProps) {
  return (
    <HStack justify="space-between" py={2}>
      <HStack spacing={2}>
        {icon && <Icon as={icon} color="gray.500" boxSize={4} />}
        <Text color="gray.600" fontSize="sm">
          {label}
        </Text>
      </HStack>
      <Text fontSize="sm" fontWeight="medium">
        {value}
      </Text>
    </HStack>
  );
}

export function AssetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const [asset, setAsset] = useState<Asset | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);

  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const { isOpen: isEditOpen, onOpen: onEditOpen, onClose: onEditClose } = useDisclosure();

  const loadAsset = useCallback(async () => {
    if (!id) return;
    try {
      const data = await assetsApi.get(id);
      setAsset(data);
    } catch (error) {
      console.error('Failed to load asset:', error);
      toast({
        title: 'Error',
        description: 'Failed to load asset',
        status: 'error',
        duration: 5000,
      });
      navigate('/catalog');
    } finally {
      setIsLoading(false);
    }
  }, [id, navigate, toast]);

  useEffect(() => {
    loadAsset();
  }, [loadAsset]);

  const handleDelete = async () => {
    if (!asset) return;

    setIsDeleting(true);
    try {
      await assetsApi.delete(asset.id);
      toast({
        title: 'Asset deleted',
        description: `"${asset.name}" has been deleted.`,
        status: 'success',
        duration: 3000,
      });
      navigate('/catalog');
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
      onDeleteClose();
    }
  };

  const handleSaveMetadata = (updatedAsset: Asset) => {
    setAsset(updatedAsset);
  };

  const handleBack = () => {
    navigate('/catalog');
  };

  if (isLoading) {
    return (
      <Center h="300px">
        <Spinner size="lg" color="brand.500" />
      </Center>
    );
  }

  if (!asset) {
    return (
      <Center h="300px">
        <Text color="gray.500">Asset not found</Text>
      </Center>
    );
  }

  const typeConfig = assetTypeConfig[asset.type];
  const sharing = sharingConfig[asset.sharing];

  // Type guards for specific asset types
  const isProgram = (a: Asset): a is ProgramAsset => a.type === 'program';
  const isModel = (a: Asset): a is ModelAsset => a.type === 'model';

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <HStack spacing={4}>
          <IconButton
            aria-label="Back"
            icon={<FiArrowLeft />}
            variant="ghost"
            onClick={handleBack}
          />
          <HStack spacing={3}>
            <Icon as={typeConfig.icon} boxSize={6} color={`${typeConfig.color}.500`} />
            <VStack align="start" spacing={0}>
              <Heading size="lg">{asset.name}</Heading>
              {asset.description && (
                <Text color="gray.500" fontSize="sm">
                  {asset.description}
                </Text>
              )}
            </VStack>
          </HStack>
        </HStack>
        <HStack spacing={2}>
          <Button leftIcon={<FiEdit2 />} variant="outline" onClick={onEditOpen}>
            Edit
          </Button>
          {asset.type === 'program' && (
            <Button
              colorScheme="brand"
              onClick={() => navigate(`/programs/${asset.id}`)}
            >
              View Full Details
            </Button>
          )}
        </HStack>
      </HStack>

      {/* Badges */}
      <HStack spacing={3} mb={6} flexWrap="wrap">
        <Badge colorScheme={typeConfig.color} variant="subtle">
          {typeConfig.label}
        </Badge>
        <Tooltip label={sharing.label}>
          <Badge variant="outline" colorScheme={sharing.color}>
            <HStack spacing={1}>
              <Icon as={sharing.icon} boxSize={3} />
              <Text>{sharing.label}</Text>
            </HStack>
          </Badge>
        </Tooltip>
        <Badge variant="outline">v{asset.version}</Badge>
        {asset.lastRunStatus && (
          <Badge
            colorScheme={
              asset.lastRunStatus === 'succeeded'
                ? 'green'
                : asset.lastRunStatus === 'failed'
                  ? 'red'
                  : 'gray'
            }
          >
            {asset.lastRunStatus === 'succeeded'
              ? 'Last Run Succeeded'
              : asset.lastRunStatus === 'failed'
                ? 'Last Run Failed'
                : 'Never Run'}
          </Badge>
        )}
      </HStack>

      {/* Tags */}
      {asset.tags && asset.tags.length > 0 && (
        <HStack spacing={2} mb={6} flexWrap="wrap">
          <Icon as={FiTag} color="gray.500" boxSize={4} />
          {asset.tags.map((tag) => (
            <Badge key={tag} variant="outline" colorScheme="gray">
              {tag}
            </Badge>
          ))}
        </HStack>
      )}

      {/* Tabs */}
      <Tabs colorScheme="brand" variant="enclosed">
        <TabList>
          <Tab>Overview</Tab>
          <Tab>Files</Tab>
          <Tab>Settings</Tab>
        </TabList>

        <TabPanels>
          {/* Overview Tab */}
          <TabPanel px={0}>
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={6}>
              {/* Basic Info Card */}
              <Card>
                <CardBody>
                  <Heading size="sm" mb={4}>
                    Basic Information
                  </Heading>
                  <VStack align="stretch" divider={<Divider />}>
                    <InfoRow label="ID" value={asset.id} />
                    <InfoRow label="Owner" value={asset.owner} />
                    <InfoRow label="Version" value={asset.version} />
                    <InfoRow
                      label="Created"
                      value={formatDate(asset.createdAt)}
                      icon={FiClock}
                    />
                    <InfoRow
                      label="Updated"
                      value={formatRelativeTime(asset.updatedAt)}
                      icon={FiClock}
                    />
                  </VStack>
                </CardBody>
              </Card>

              {/* Type-Specific Info Card */}
              <Card>
                <CardBody>
                  <Heading size="sm" mb={4}>
                    {typeConfig.label} Details
                  </Heading>
                  <VStack align="stretch" divider={<Divider />}>
                    {isProgram(asset) && (
                      <>
                        <InfoRow label="Entrypoint" value={asset.entrypoint} />
                        <InfoRow
                          label="Image Status"
                          value={
                            <Badge
                              colorScheme={
                                asset.imageBuildStatus === 'ready'
                                  ? 'green'
                                  : asset.imageBuildStatus === 'failed'
                                    ? 'red'
                                    : 'gray'
                              }
                            >
                              {asset.imageBuildStatus || 'Not Built'}
                            </Badge>
                          }
                        />
                        {asset.dependencies && (
                          <InfoRow
                            label="Dependencies"
                            value={`${asset.dependencies.packages.length} packages`}
                          />
                        )}
                        {asset.resourceProfile && (
                          <InfoRow
                            label="Resources"
                            value={`${asset.resourceProfile.cpuLimit} CPU, ${asset.resourceProfile.memoryLimit}`}
                          />
                        )}
                      </>
                    )}
                    {isModel(asset) && (
                      <>
                        <InfoRow label="Provider" value={asset.provider} />
                        <InfoRow label="Model ID" value={asset.modelId} />
                        {asset.scope && <InfoRow label="Scope" value={asset.scope} />}
                        {asset.capabilities && (
                          <InfoRow
                            label="Context Window"
                            value={`${asset.capabilities.contextWindow.toLocaleString()} tokens`}
                          />
                        )}
                      </>
                    )}
                  </VStack>
                </CardBody>
              </Card>
            </SimpleGrid>
          </TabPanel>

          {/* Files Tab */}
          <TabPanel px={0}>
            <VStack spacing={4} align="stretch">
              {isProgram(asset) && asset.sourceCode ? (
                <>
                  <HStack justify="space-between">
                    <Heading size="sm">Source Code</Heading>
                    <Text color="gray.500" fontSize="sm">
                      {asset.entrypoint}
                    </Text>
                  </HStack>
                  <CodeViewer
                    code={asset.sourceCode}
                    filename={asset.entrypoint}
                    maxHeight="500px"
                  />
                </>
              ) : (
                <Center py={12}>
                  <VStack spacing={3}>
                    <Icon as={FiFile} boxSize={12} color="gray.400" />
                    <Text color="gray.500">No files available</Text>
                    <Text color="gray.400" fontSize="sm">
                      {asset.type === 'model'
                        ? 'Models reference external providers and do not have local files'
                        : 'Files for this asset are not available'}
                    </Text>
                  </VStack>
                </Center>
              )}
            </VStack>
          </TabPanel>

          {/* Settings Tab */}
          <TabPanel px={0}>
            <VStack align="stretch" spacing={6}>
              {/* Metadata Section */}
              <Card>
                <CardBody>
                  <Heading size="sm" mb={4}>
                    Metadata
                  </Heading>
                  <VStack align="stretch" spacing={4}>
                    <Box>
                      <Text fontWeight="medium" mb={1}>
                        Name
                      </Text>
                      <Text color="gray.600">{asset.name}</Text>
                    </Box>
                    <Box>
                      <Text fontWeight="medium" mb={1}>
                        Description
                      </Text>
                      <Text color={asset.description ? 'gray.600' : 'gray.400'}>
                        {asset.description || 'No description'}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontWeight="medium" mb={1}>
                        Tags
                      </Text>
                      {asset.tags && asset.tags.length > 0 ? (
                        <HStack spacing={2} flexWrap="wrap">
                          {asset.tags.map((tag) => (
                            <Badge key={tag} variant="outline">
                              {tag}
                            </Badge>
                          ))}
                        </HStack>
                      ) : (
                        <Text color="gray.400">No tags</Text>
                      )}
                    </Box>
                    <Box>
                      <Text fontWeight="medium" mb={1}>
                        Visibility
                      </Text>
                      <HStack spacing={2}>
                        <Icon as={sharing.icon} color={`${sharing.color}.500`} />
                        <Text color="gray.600">{sharing.label}</Text>
                      </HStack>
                    </Box>
                  </VStack>
                </CardBody>
              </Card>

              {/* Danger Zone */}
              <Card borderColor="red.200">
                <CardBody>
                  <Heading size="sm" mb={2} color="red.500">
                    Danger Zone
                  </Heading>
                  <Text color="gray.500" mb={4} fontSize="sm">
                    Permanently delete this {typeConfig.label.toLowerCase()} and all associated
                    data.
                  </Text>
                  <Button
                    colorScheme="red"
                    variant="outline"
                    leftIcon={<FiTrash2 />}
                    onClick={onDeleteOpen}
                  >
                    Delete {typeConfig.label}
                  </Button>
                </CardBody>
              </Card>
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete {typeConfig.label}
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{asset.name}"?
              <Text mt={2} color="gray.500">
                This action cannot be undone. All associated data will be permanently removed.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDelete}
                ml={3}
                isLoading={isDeleting}
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Metadata Edit Modal */}
      <MetadataEditModal
        asset={asset}
        isOpen={isEditOpen}
        onClose={onEditClose}
        onSave={handleSaveMetadata}
      />
    </Box>
  );
}
