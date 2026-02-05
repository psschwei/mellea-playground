import { useState, useEffect, useCallback } from 'react';
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
  Input,
  Select,
  VStack,
  HStack,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  IconButton,
  Badge,
  Text,
  useToast,
  useClipboard,
  Tooltip,
  Spinner,
  Box,
  InputGroup,
  InputRightElement,
} from '@chakra-ui/react';
import { FiCopy, FiCheck, FiTrash2, FiX } from 'react-icons/fi';
import { sharingApi } from '@/api/sharing';
import type {
  Permission,
  ResourceType,
  ShareLink,
  SharedUser,
  CreateShareLinkRequest,
  ShareWithUserRequest,
} from '@/types';

interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  resourceId: string;
  resourceType: ResourceType;
  resourceName: string;
}

const permissionOptions: { value: Permission; label: string; description: string }[] = [
  { value: 'view', label: 'View', description: 'Can view the resource' },
  { value: 'run', label: 'Run', description: 'Can view and execute' },
  { value: 'edit', label: 'Edit', description: 'Full access to modify' },
];

const expirationOptions = [
  { value: 1, label: '1 hour' },
  { value: 24, label: '1 day' },
  { value: 168, label: '1 week' },
  { value: 720, label: '30 days' },
  { value: 0, label: 'Never expires' },
];

export function ShareDialog({
  isOpen,
  onClose,
  resourceId,
  resourceType,
  resourceName,
}: ShareDialogProps) {
  const toast = useToast();

  // Share Link state
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([]);
  const [linksLoading, setLinksLoading] = useState(false);
  const [linkPermission, setLinkPermission] = useState<Permission>('view');
  const [linkExpiration, setLinkExpiration] = useState<number>(168);
  const [linkLabel, setLinkLabel] = useState('');
  const [creatingLink, setCreatingLink] = useState(false);

  // User sharing state
  const [sharedUsers, setSharedUsers] = useState<SharedUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [userEmail, setUserEmail] = useState('');
  const [userPermission, setUserPermission] = useState<Permission>('view');
  const [sharingWithUser, setSharingWithUser] = useState(false);

  // Clipboard for the most recently created link
  const [recentLinkUrl, setRecentLinkUrl] = useState('');
  const { hasCopied, onCopy } = useClipboard(recentLinkUrl);

  const loadShareLinks = useCallback(async () => {
    setLinksLoading(true);
    try {
      const response = await sharingApi.listShareLinks({
        resourceId,
        resourceType,
        includeInactive: false,
      });
      setShareLinks(response.links);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load share links';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLinksLoading(false);
    }
  }, [resourceId, resourceType, toast]);

  const loadSharedUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const response = await sharingApi.listSharedUsers(resourceType, resourceId);
      setSharedUsers(response.users);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load shared users';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setUsersLoading(false);
    }
  }, [resourceId, resourceType, toast]);

  useEffect(() => {
    if (isOpen) {
      loadShareLinks();
      loadSharedUsers();
    }
  }, [isOpen, loadShareLinks, loadSharedUsers]);

  const handleCreateLink = async () => {
    setCreatingLink(true);
    try {
      const request: CreateShareLinkRequest = {
        resourceId,
        resourceType,
        permission: linkPermission,
        expiresInHours: linkExpiration || undefined,
        label: linkLabel.trim() || undefined,
      };

      const newLink = await sharingApi.createShareLink(request);
      setShareLinks((prev) => [newLink, ...prev]);
      setRecentLinkUrl(newLink.shareUrl);
      setLinkLabel('');

      toast({
        title: 'Link created',
        description: 'Share link has been created. Click to copy.',
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create share link';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setCreatingLink(false);
    }
  };

  const handleDeactivateLink = async (linkId: string) => {
    try {
      await sharingApi.deactivateShareLink(linkId);
      setShareLinks((prev) => prev.filter((link) => link.id !== linkId));
      toast({
        title: 'Link deactivated',
        description: 'The share link has been deactivated.',
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to deactivate link';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleShareWithUser = async () => {
    if (!userEmail.trim()) {
      toast({
        title: 'Email required',
        description: 'Please enter a user email or ID.',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setSharingWithUser(true);
    try {
      const request: ShareWithUserRequest = {
        resourceId,
        resourceType,
        userId: userEmail.trim(),
        permission: userPermission,
      };

      await sharingApi.shareWithUser(request);
      await loadSharedUsers();
      setUserEmail('');

      toast({
        title: 'Shared successfully',
        description: `Resource shared with ${userEmail}.`,
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to share with user';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSharingWithUser(false);
    }
  };

  const handleRevokeAccess = async (userId: string) => {
    try {
      await sharingApi.revokeUserAccess(resourceType, resourceId, userId);
      setSharedUsers((prev) => prev.filter((user) => user.userId !== userId));
      toast({
        title: 'Access revoked',
        description: 'User access has been revoked.',
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to revoke access';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleClose = () => {
    setLinkLabel('');
    setUserEmail('');
    setRecentLinkUrl('');
    onClose();
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleDateString();
  };

  const getPermissionColor = (permission: Permission) => {
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
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Share "{resourceName}"</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          <Tabs>
            <TabList>
              <Tab>Share Link</Tab>
              <Tab>Share with Users</Tab>
            </TabList>

            <TabPanels>
              {/* Share Link Tab */}
              <TabPanel px={0}>
                <VStack spacing={4} align="stretch">
                  <Text fontSize="sm" color="gray.600">
                    Create a link that anyone with access can use to view or interact with this{' '}
                    {resourceType}.
                  </Text>

                  <HStack spacing={4}>
                    <FormControl flex={1}>
                      <FormLabel fontSize="sm">Permission</FormLabel>
                      <Select
                        size="sm"
                        value={linkPermission}
                        onChange={(e) => setLinkPermission(e.target.value as Permission)}
                      >
                        {permissionOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl flex={1}>
                      <FormLabel fontSize="sm">Expires</FormLabel>
                      <Select
                        size="sm"
                        value={linkExpiration}
                        onChange={(e) => setLinkExpiration(Number(e.target.value))}
                      >
                        {expirationOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                  </HStack>

                  <FormControl>
                    <FormLabel fontSize="sm">Label (optional)</FormLabel>
                    <Input
                      size="sm"
                      placeholder="e.g., For reviewers"
                      value={linkLabel}
                      onChange={(e) => setLinkLabel(e.target.value)}
                    />
                  </FormControl>

                  <Button
                    colorScheme="brand"
                    size="sm"
                    onClick={handleCreateLink}
                    isLoading={creatingLink}
                    loadingText="Creating..."
                  >
                    Create Link
                  </Button>

                  {recentLinkUrl && (
                    <Box p={3} bg="green.50" borderRadius="md" borderWidth={1} borderColor="green.200">
                      <Text fontSize="sm" fontWeight="medium" mb={2}>
                        Link created! Click to copy:
                      </Text>
                      <InputGroup size="sm">
                        <Input
                          value={recentLinkUrl}
                          isReadOnly
                          fontFamily="mono"
                          fontSize="xs"
                          pr="4rem"
                        />
                        <InputRightElement width="4rem">
                          <Button
                            h="1.5rem"
                            size="xs"
                            onClick={onCopy}
                            leftIcon={hasCopied ? <FiCheck /> : <FiCopy />}
                          >
                            {hasCopied ? 'Copied' : 'Copy'}
                          </Button>
                        </InputRightElement>
                      </InputGroup>
                    </Box>
                  )}

                  {/* Existing Links */}
                  {linksLoading ? (
                    <Box textAlign="center" py={4}>
                      <Spinner size="sm" />
                    </Box>
                  ) : shareLinks.length > 0 ? (
                    <Box>
                      <Text fontSize="sm" fontWeight="medium" mb={2}>
                        Active Links ({shareLinks.length})
                      </Text>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th>Label</Th>
                            <Th>Permission</Th>
                            <Th>Expires</Th>
                            <Th>Uses</Th>
                            <Th></Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {shareLinks.map((link) => (
                            <Tr key={link.id}>
                              <Td>
                                <CopyableLinkCell url={link.shareUrl} label={link.label} />
                              </Td>
                              <Td>
                                <Badge colorScheme={getPermissionColor(link.permission)}>
                                  {link.permission}
                                </Badge>
                              </Td>
                              <Td fontSize="xs">{formatDate(link.expiresAt)}</Td>
                              <Td fontSize="xs">{link.accessCount}</Td>
                              <Td>
                                <Tooltip label="Deactivate link">
                                  <IconButton
                                    aria-label="Deactivate link"
                                    icon={<FiX />}
                                    size="xs"
                                    variant="ghost"
                                    colorScheme="red"
                                    onClick={() => handleDeactivateLink(link.id)}
                                  />
                                </Tooltip>
                              </Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </Box>
                  ) : (
                    <Text fontSize="sm" color="gray.500" textAlign="center" py={4}>
                      No active share links
                    </Text>
                  )}
                </VStack>
              </TabPanel>

              {/* Share with Users Tab */}
              <TabPanel px={0}>
                <VStack spacing={4} align="stretch">
                  <Text fontSize="sm" color="gray.600">
                    Share directly with specific users by their email or user ID.
                  </Text>

                  <HStack spacing={4}>
                    <FormControl flex={2}>
                      <FormLabel fontSize="sm">User email or ID</FormLabel>
                      <Input
                        size="sm"
                        placeholder="user@example.com"
                        value={userEmail}
                        onChange={(e) => setUserEmail(e.target.value)}
                      />
                    </FormControl>

                    <FormControl flex={1}>
                      <FormLabel fontSize="sm">Permission</FormLabel>
                      <Select
                        size="sm"
                        value={userPermission}
                        onChange={(e) => setUserPermission(e.target.value as Permission)}
                      >
                        {permissionOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                  </HStack>

                  <Button
                    colorScheme="brand"
                    size="sm"
                    onClick={handleShareWithUser}
                    isLoading={sharingWithUser}
                    loadingText="Sharing..."
                  >
                    Share
                  </Button>

                  {/* Shared Users List */}
                  {usersLoading ? (
                    <Box textAlign="center" py={4}>
                      <Spinner size="sm" />
                    </Box>
                  ) : sharedUsers.length > 0 ? (
                    <Box>
                      <Text fontSize="sm" fontWeight="medium" mb={2}>
                        Shared with ({sharedUsers.length})
                      </Text>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th>User</Th>
                            <Th>Permission</Th>
                            <Th></Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {sharedUsers.map((user) => (
                            <Tr key={user.userId}>
                              <Td>
                                <Text fontSize="sm">
                                  {user.displayName || user.username || user.userId}
                                </Text>
                                {user.displayName && user.username && (
                                  <Text fontSize="xs" color="gray.500">
                                    @{user.username}
                                  </Text>
                                )}
                              </Td>
                              <Td>
                                <Badge colorScheme={getPermissionColor(user.permission)}>
                                  {user.permission}
                                </Badge>
                              </Td>
                              <Td>
                                <Tooltip label="Revoke access">
                                  <IconButton
                                    aria-label="Revoke access"
                                    icon={<FiTrash2 />}
                                    size="xs"
                                    variant="ghost"
                                    colorScheme="red"
                                    onClick={() => handleRevokeAccess(user.userId)}
                                  />
                                </Tooltip>
                              </Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </Box>
                  ) : (
                    <Text fontSize="sm" color="gray.500" textAlign="center" py={4}>
                      Not shared with any users yet
                    </Text>
                  )}
                </VStack>
              </TabPanel>
            </TabPanels>
          </Tabs>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" onClick={handleClose}>
            Done
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

// Helper component for copyable link cell
function CopyableLinkCell({ url, label }: { url: string; label?: string }) {
  const { hasCopied, onCopy } = useClipboard(url);

  return (
    <HStack spacing={1}>
      <Text fontSize="sm" noOfLines={1} maxW="150px">
        {label || 'Unnamed link'}
      </Text>
      <Tooltip label={hasCopied ? 'Copied!' : 'Copy link'}>
        <IconButton
          aria-label="Copy link"
          icon={hasCopied ? <FiCheck /> : <FiCopy />}
          size="xs"
          variant="ghost"
          onClick={onCopy}
        />
      </Tooltip>
    </HStack>
  );
}

export default ShareDialog;
