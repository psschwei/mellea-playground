import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Heading,
  Grid,
  GridItem,
  Card,
  CardHeader,
  CardBody,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Avatar,
  HStack,
  VStack,
  Text,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  Button,
  IconButton,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  MenuDivider,
  useToast,
  Spinner,
  Alert,
  AlertIcon,
  Flex,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  useDisclosure,
  RadioGroup,
  Radio,
  Stack,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Progress,
} from '@chakra-ui/react';
import { FiSearch, FiMoreVertical, FiUsers, FiUserCheck, FiUserX, FiClock, FiShield, FiActivity, FiAlertTriangle } from 'react-icons/fi';
import { useAuth } from '@/hooks';
import { adminApi, AdminUser, AdminUserStats, AdminUserListParams, QuotaUsageStats } from '@/api/admin';
import type { UserRole, UserStatus } from '@/types';

const roleColorMap: Record<UserRole, string> = {
  admin: 'purple',
  developer: 'blue',
  end_user: 'gray',
};

const statusColorMap: Record<UserStatus, string> = {
  active: 'green',
  suspended: 'red',
  pending: 'yellow',
};

const roleLabelMap: Record<UserRole, string> = {
  admin: 'Admin',
  developer: 'Developer',
  end_user: 'End User',
};

export function AdminDashboardPage() {
  const { user } = useAuth();
  const toast = useToast();
  const { isOpen: isRoleModalOpen, onOpen: onRoleModalOpen, onClose: onRoleModalClose } = useDisclosure();

  const [stats, setStats] = useState<AdminUserStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<UserRole | ''>('');
  const [statusFilter, setStatusFilter] = useState<UserStatus | ''>('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  // Role assignment state
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [newRole, setNewRole] = useState<UserRole>('end_user');
  const [isUpdatingRole, setIsUpdatingRole] = useState(false);

  // Quota monitoring state
  const [quotaStats, setQuotaStats] = useState<QuotaUsageStats | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(false);

  // Check if current user is admin
  const isAdmin = user?.role === 'admin';

  const fetchStats = useCallback(async () => {
    try {
      const statsData = await adminApi.getUserStats();
      setStats(statsData);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params: AdminUserListParams = {
        page,
        limit: 10,
        search: searchQuery || undefined,
        role: roleFilter || undefined,
        status: statusFilter || undefined,
        sortBy: 'createdAt',
        sortOrder: 'desc',
      };

      const response = await adminApi.listUsers(params);
      setUsers(response.users);
      setTotalPages(response.totalPages);
      setTotal(response.total);
    } catch (err) {
      setError('Failed to load users. Please try again.');
      console.error('Failed to fetch users:', err);
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, roleFilter, statusFilter]);

  const fetchQuotaStats = useCallback(async () => {
    setQuotaLoading(true);
    try {
      const quotaData = await adminApi.getQuotaUsageStats();
      setQuotaStats(quotaData);
    } catch (err) {
      console.error('Failed to fetch quota stats:', err);
    } finally {
      setQuotaLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) {
      fetchStats();
      fetchUsers();
      fetchQuotaStats();
    }
  }, [isAdmin, fetchStats, fetchUsers, fetchQuotaStats]);

  const handleSuspendUser = async (userId: string) => {
    try {
      await adminApi.suspendUser(userId);
      toast({
        title: 'User suspended',
        status: 'success',
        duration: 3000,
      });
      fetchUsers();
      fetchStats();
    } catch {
      toast({
        title: 'Failed to suspend user',
        status: 'error',
        duration: 3000,
      });
    }
  };

  const handleActivateUser = async (userId: string) => {
    try {
      await adminApi.activateUser(userId);
      toast({
        title: 'User activated',
        status: 'success',
        duration: 3000,
      });
      fetchUsers();
      fetchStats();
    } catch {
      toast({
        title: 'Failed to activate user',
        status: 'error',
        duration: 3000,
      });
    }
  };

  const handleOpenRoleModal = (targetUser: AdminUser) => {
    setSelectedUser(targetUser);
    setNewRole(targetUser.role);
    onRoleModalOpen();
  };

  const handleRoleChange = async () => {
    if (!selectedUser || newRole === selectedUser.role) {
      onRoleModalClose();
      return;
    }

    setIsUpdatingRole(true);
    try {
      await adminApi.updateUser(selectedUser.id, { role: newRole });
      toast({
        title: 'Role updated',
        description: `${selectedUser.displayName}'s role has been changed to ${roleLabelMap[newRole]}.`,
        status: 'success',
        duration: 3000,
      });
      fetchUsers();
      fetchStats();
      onRoleModalClose();
    } catch {
      toast({
        title: 'Failed to update role',
        description: 'Please try again.',
        status: 'error',
        duration: 3000,
      });
    } finally {
      setIsUpdatingRole(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Show access denied if not admin
  if (!isAdmin) {
    return (
      <Box p={8}>
        <Alert status="error">
          <AlertIcon />
          Access denied. This page is only available to administrators.
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Heading size="lg" mb={6}>
        Admin Dashboard
      </Heading>

      <Tabs colorScheme="blue" mb={6}>
        <TabList>
          <Tab>User Management</Tab>
          <Tab>Quota Monitoring</Tab>
        </TabList>

        <TabPanels>
          {/* User Management Tab */}
          <TabPanel px={0}>
            {/* Statistics Cards */}
            <Grid templateColumns="repeat(4, 1fr)" gap={6} mb={8}>
        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <HStack>
                  <Box color="blue.500">
                    <FiUsers size={24} />
                  </Box>
                  <Box>
                    <StatLabel>Total Users</StatLabel>
                    <StatNumber>{stats?.totalUsers ?? '-'}</StatNumber>
                    <StatHelpText>All registered users</StatHelpText>
                  </Box>
                </HStack>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <HStack>
                  <Box color="green.500">
                    <FiUserCheck size={24} />
                  </Box>
                  <Box>
                    <StatLabel>Active Users</StatLabel>
                    <StatNumber>{stats?.activeUsers ?? '-'}</StatNumber>
                    <StatHelpText>Currently active</StatHelpText>
                  </Box>
                </HStack>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <HStack>
                  <Box color="red.500">
                    <FiUserX size={24} />
                  </Box>
                  <Box>
                    <StatLabel>Suspended</StatLabel>
                    <StatNumber>{stats?.suspendedUsers ?? '-'}</StatNumber>
                    <StatHelpText>Accounts suspended</StatHelpText>
                  </Box>
                </HStack>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <HStack>
                  <Box color="yellow.500">
                    <FiClock size={24} />
                  </Box>
                  <Box>
                    <StatLabel>Pending</StatLabel>
                    <StatNumber>{stats?.pendingUsers ?? '-'}</StatNumber>
                    <StatHelpText>Awaiting approval</StatHelpText>
                  </Box>
                </HStack>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>

      {/* Filters */}
      <Card mb={6}>
        <CardBody>
          <HStack spacing={4}>
            <InputGroup maxW="300px">
              <InputLeftElement pointerEvents="none">
                <FiSearch color="gray.300" />
              </InputLeftElement>
              <Input
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
              />
            </InputGroup>

            <Select
              placeholder="All roles"
              maxW="150px"
              value={roleFilter}
              onChange={(e) => {
                setRoleFilter(e.target.value as UserRole | '');
                setPage(1);
              }}
            >
              <option value="admin">Admin</option>
              <option value="developer">Developer</option>
              <option value="end_user">End User</option>
            </Select>

            <Select
              placeholder="All statuses"
              maxW="150px"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as UserStatus | '');
                setPage(1);
              }}
            >
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="pending">Pending</option>
            </Select>

            <Text color="gray.500" fontSize="sm">
              {total} user{total !== 1 ? 's' : ''} found
            </Text>
          </HStack>
        </CardBody>
      </Card>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <Heading size="md">Users</Heading>
        </CardHeader>
        <CardBody>
          {error && (
            <Alert status="error" mb={4}>
              <AlertIcon />
              {error}
            </Alert>
          )}

          {loading ? (
            <Flex justify="center" py={8}>
              <Spinner size="lg" />
            </Flex>
          ) : users.length === 0 ? (
            <Text color="gray.500" textAlign="center" py={8}>
              No users found matching your criteria.
            </Text>
          ) : (
            <>
              <Table variant="simple">
                <Thead>
                  <Tr>
                    <Th>User</Th>
                    <Th>Role</Th>
                    <Th>Status</Th>
                    <Th>Created</Th>
                    <Th>Last Login</Th>
                    <Th width="50px"></Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {users.map((u) => (
                    <Tr key={u.id}>
                      <Td>
                        <HStack>
                          <Avatar size="sm" name={u.displayName} src={u.avatarUrl} />
                          <VStack align="start" spacing={0}>
                            <Text fontWeight="medium">{u.displayName}</Text>
                            <Text fontSize="sm" color="gray.500">
                              {u.email}
                            </Text>
                          </VStack>
                        </HStack>
                      </Td>
                      <Td>
                        <Badge colorScheme={roleColorMap[u.role]}>
                          {roleLabelMap[u.role]}
                        </Badge>
                      </Td>
                      <Td>
                        <Badge colorScheme={statusColorMap[u.status]}>
                          {u.status}
                        </Badge>
                      </Td>
                      <Td>{formatDate(u.createdAt)}</Td>
                      <Td>{formatDate(u.lastLoginAt)}</Td>
                      <Td>
                        <Menu>
                          <MenuButton
                            as={IconButton}
                            icon={<FiMoreVertical />}
                            variant="ghost"
                            size="sm"
                            aria-label="Actions"
                            isDisabled={u.id === user?.id}
                          />
                          <MenuList>
                            <MenuItem
                              icon={<FiShield />}
                              onClick={() => handleOpenRoleModal(u)}
                            >
                              Change Role
                            </MenuItem>
                            <MenuDivider />
                            {u.status === 'active' ? (
                              <MenuItem onClick={() => handleSuspendUser(u.id)}>
                                Suspend User
                              </MenuItem>
                            ) : (
                              <MenuItem onClick={() => handleActivateUser(u.id)}>
                                Activate User
                              </MenuItem>
                            )}
                          </MenuList>
                        </Menu>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <HStack justify="center" mt={4} spacing={2}>
                  <Button
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    isDisabled={page === 1}
                  >
                    Previous
                  </Button>
                  <Text fontSize="sm" color="gray.600">
                    Page {page} of {totalPages}
                  </Text>
                  <Button
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    isDisabled={page === totalPages}
                  >
                    Next
                  </Button>
                </HStack>
              )}
            </>
          )}
        </CardBody>
      </Card>

          </TabPanel>

          {/* Quota Monitoring Tab */}
          <TabPanel px={0}>
            {/* Quota Summary Cards */}
            <Grid templateColumns="repeat(4, 1fr)" gap={6} mb={8}>
              <GridItem>
                <Card>
                  <CardBody>
                    <Stat>
                      <HStack>
                        <Box color="blue.500">
                          <FiUsers size={24} />
                        </Box>
                        <Box>
                          <StatLabel>Active Users</StatLabel>
                          <StatNumber>{quotaStats?.totalUsers ?? '-'}</StatNumber>
                          <StatHelpText>With quota tracking</StatHelpText>
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>
              </GridItem>

              <GridItem>
                <Card>
                  <CardBody>
                    <Stat>
                      <HStack>
                        <Box color="orange.500">
                          <FiAlertTriangle size={24} />
                        </Box>
                        <Box>
                          <StatLabel>Users at Limit</StatLabel>
                          <StatNumber>{quotaStats?.usersAtLimit ?? '-'}</StatNumber>
                          <StatHelpText>Quota exceeded</StatHelpText>
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>
              </GridItem>

              <GridItem>
                <Card>
                  <CardBody>
                    <Stat>
                      <HStack>
                        <Box color="purple.500">
                          <FiActivity size={24} />
                        </Box>
                        <Box>
                          <StatLabel>CPU Hours (Month)</StatLabel>
                          <StatNumber>{quotaStats?.totalCpuHoursUsed?.toFixed(1) ?? '-'}</StatNumber>
                          <StatHelpText>Total consumed</StatHelpText>
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>
              </GridItem>

              <GridItem>
                <Card>
                  <CardBody>
                    <Stat>
                      <HStack>
                        <Box color="green.500">
                          <FiClock size={24} />
                        </Box>
                        <Box>
                          <StatLabel>Runs Today</StatLabel>
                          <StatNumber>{quotaStats?.totalRunsToday ?? '-'}</StatNumber>
                          <StatHelpText>All users combined</StatHelpText>
                        </Box>
                      </HStack>
                    </Stat>
                  </CardBody>
                </Card>
              </GridItem>
            </Grid>

            {quotaLoading ? (
              <Flex justify="center" py={8}>
                <Spinner size="lg" />
              </Flex>
            ) : (
              <Grid templateColumns="repeat(2, 1fr)" gap={6}>
                {/* Top Users by CPU Hours */}
                <GridItem>
                  <Card>
                    <CardHeader>
                      <Heading size="md">Top Users by CPU Hours (Month)</Heading>
                    </CardHeader>
                    <CardBody>
                      {quotaStats?.topUsersByCpu && quotaStats.topUsersByCpu.length > 0 ? (
                        <Table variant="simple" size="sm">
                          <Thead>
                            <Tr>
                              <Th>User</Th>
                              <Th isNumeric>Used</Th>
                              <Th isNumeric>Limit</Th>
                              <Th width="150px">Usage</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {quotaStats.topUsersByCpu.slice(0, 5).map((u) => (
                              <Tr key={u.userId}>
                                <Td>
                                  <VStack align="start" spacing={0}>
                                    <Text fontWeight="medium" fontSize="sm">{u.displayName}</Text>
                                    <Text fontSize="xs" color="gray.500">{u.email}</Text>
                                  </VStack>
                                </Td>
                                <Td isNumeric>{u.cpuHoursUsed?.toFixed(1)}</Td>
                                <Td isNumeric>{u.cpuHoursLimit}</Td>
                                <Td>
                                  <VStack align="stretch" spacing={1}>
                                    <Progress
                                      value={u.percentUsed}
                                      size="sm"
                                      colorScheme={u.percentUsed >= 90 ? 'red' : u.percentUsed >= 70 ? 'yellow' : 'green'}
                                      borderRadius="md"
                                    />
                                    <Text fontSize="xs" color="gray.500" textAlign="right">
                                      {u.percentUsed.toFixed(0)}%
                                    </Text>
                                  </VStack>
                                </Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      ) : (
                        <Text color="gray.500" textAlign="center" py={4}>
                          No usage data available
                        </Text>
                      )}
                    </CardBody>
                  </Card>
                </GridItem>

                {/* Top Users by Daily Runs */}
                <GridItem>
                  <Card>
                    <CardHeader>
                      <Heading size="md">Top Users by Runs Today</Heading>
                    </CardHeader>
                    <CardBody>
                      {quotaStats?.topUsersByRuns && quotaStats.topUsersByRuns.length > 0 ? (
                        <Table variant="simple" size="sm">
                          <Thead>
                            <Tr>
                              <Th>User</Th>
                              <Th isNumeric>Runs</Th>
                              <Th isNumeric>Limit</Th>
                              <Th width="150px">Usage</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {quotaStats.topUsersByRuns.slice(0, 5).map((u) => (
                              <Tr key={u.userId}>
                                <Td>
                                  <VStack align="start" spacing={0}>
                                    <Text fontWeight="medium" fontSize="sm">{u.displayName}</Text>
                                    <Text fontSize="xs" color="gray.500">{u.email}</Text>
                                  </VStack>
                                </Td>
                                <Td isNumeric>{u.runsToday}</Td>
                                <Td isNumeric>{u.runsLimit}</Td>
                                <Td>
                                  <VStack align="stretch" spacing={1}>
                                    <Progress
                                      value={u.percentUsed}
                                      size="sm"
                                      colorScheme={u.percentUsed >= 90 ? 'red' : u.percentUsed >= 70 ? 'yellow' : 'green'}
                                      borderRadius="md"
                                    />
                                    <Text fontSize="xs" color="gray.500" textAlign="right">
                                      {u.percentUsed.toFixed(0)}%
                                    </Text>
                                  </VStack>
                                </Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      ) : (
                        <Text color="gray.500" textAlign="center" py={4}>
                          No runs today
                        </Text>
                      )}
                    </CardBody>
                  </Card>
                </GridItem>
              </Grid>
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Role Assignment Modal */}
      <Modal isOpen={isRoleModalOpen} onClose={onRoleModalClose}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Change User Role</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {selectedUser && (
              <VStack align="stretch" spacing={4}>
                <HStack>
                  <Avatar size="md" name={selectedUser.displayName} src={selectedUser.avatarUrl} />
                  <VStack align="start" spacing={0}>
                    <Text fontWeight="medium">{selectedUser.displayName}</Text>
                    <Text fontSize="sm" color="gray.500">{selectedUser.email}</Text>
                  </VStack>
                </HStack>

                <Box>
                  <Text fontWeight="medium" mb={2}>Current Role</Text>
                  <Badge colorScheme={roleColorMap[selectedUser.role]} size="lg">
                    {roleLabelMap[selectedUser.role]}
                  </Badge>
                </Box>

                <Box>
                  <Text fontWeight="medium" mb={3}>New Role</Text>
                  <RadioGroup value={newRole} onChange={(value) => setNewRole(value as UserRole)}>
                    <Stack spacing={3}>
                      <Radio value="end_user">
                        <VStack align="start" spacing={0}>
                          <Text fontWeight="medium">End User</Text>
                          <Text fontSize="sm" color="gray.500">
                            Basic access to run programs and view results
                          </Text>
                        </VStack>
                      </Radio>
                      <Radio value="developer">
                        <VStack align="start" spacing={0}>
                          <Text fontWeight="medium">Developer</Text>
                          <Text fontSize="sm" color="gray.500">
                            Create and manage programs, models, and compositions
                          </Text>
                        </VStack>
                      </Radio>
                      <Radio value="admin">
                        <VStack align="start" spacing={0}>
                          <Text fontWeight="medium">Admin</Text>
                          <Text fontSize="sm" color="gray.500">
                            Full access including user management and system settings
                          </Text>
                        </VStack>
                      </Radio>
                    </Stack>
                  </RadioGroup>
                </Box>

                {newRole !== selectedUser.role && (
                  <Alert status="warning" borderRadius="md">
                    <AlertIcon />
                    <Text fontSize="sm">
                      Changing role to <strong>{roleLabelMap[newRole]}</strong> will modify this user's permissions immediately.
                    </Text>
                  </Alert>
                )}
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onRoleModalClose}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={handleRoleChange}
              isLoading={isUpdatingRole}
              isDisabled={!selectedUser || newRole === selectedUser?.role}
            >
              Update Role
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}
