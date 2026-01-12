import {
  Box,
  Flex,
  HStack,
  IconButton,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  Text,
  Avatar,
  useColorModeValue,
} from '@chakra-ui/react';
import { FiBell, FiChevronDown, FiLogOut, FiSettings, FiUser } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks';

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <Box
      as="header"
      bg={bgColor}
      borderBottomWidth="1px"
      borderColor={borderColor}
      px={4}
      py={2}
      position="sticky"
      top={0}
      zIndex={10}
    >
      <Flex justify="space-between" align="center" h="12">
        <HStack spacing={4}>
          <Text fontSize="xl" fontWeight="bold" color="blue.500">
            Mellea Playground
          </Text>
        </HStack>

        <HStack spacing={4}>
          <IconButton
            aria-label="Notifications"
            icon={<FiBell />}
            variant="ghost"
            size="sm"
          />

          <Menu>
            <MenuButton>
              <HStack spacing={2} cursor="pointer">
                <Avatar size="sm" name={user?.displayName} />
                <Text fontSize="sm" display={{ base: 'none', md: 'block' }}>
                  {user?.displayName}
                </Text>
                <FiChevronDown />
              </HStack>
            </MenuButton>
            <MenuList>
              <MenuItem icon={<FiUser />}>Profile</MenuItem>
              <MenuItem icon={<FiSettings />}>Settings</MenuItem>
              <MenuDivider />
              <MenuItem icon={<FiLogOut />} onClick={handleLogout}>
                Logout
              </MenuItem>
            </MenuList>
          </Menu>
        </HStack>
      </Flex>
    </Box>
  );
}
