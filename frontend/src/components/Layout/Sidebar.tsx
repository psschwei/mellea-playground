import { Box, VStack, Link, Icon, Text, useColorModeValue } from '@chakra-ui/react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  FiHome,
  FiFolder,
  FiCode,
  FiKey,
  FiCpu,
  FiGitBranch,
  FiPlay,
  FiSettings,
} from 'react-icons/fi';
import type { IconType } from 'react-icons';

interface NavItemProps {
  to: string;
  icon: IconType;
  label: string;
}

function NavItem({ to, icon, label }: NavItemProps) {
  const location = useLocation();
  const isActive = location.pathname === to || location.pathname.startsWith(`${to}/`);
  const activeBg = useColorModeValue('blue.50', 'blue.900');
  const activeColor = useColorModeValue('blue.600', 'blue.200');
  const hoverBg = useColorModeValue('gray.100', 'gray.700');

  return (
    <Link
      as={NavLink}
      to={to}
      w="full"
      px={4}
      py={3}
      borderRadius="md"
      display="flex"
      alignItems="center"
      bg={isActive ? activeBg : 'transparent'}
      color={isActive ? activeColor : 'inherit'}
      fontWeight={isActive ? 'semibold' : 'normal'}
      _hover={{
        bg: isActive ? activeBg : hoverBg,
        textDecoration: 'none',
      }}
    >
      <Icon as={icon} mr={3} />
      <Text>{label}</Text>
    </Link>
  );
}

export function Sidebar() {
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  return (
    <Box
      as="nav"
      w="240px"
      h="calc(100vh - 56px)"
      bg={bgColor}
      borderRightWidth="1px"
      borderColor={borderColor}
      py={4}
      position="sticky"
      top="56px"
      overflowY="auto"
    >
      <VStack spacing={1} align="stretch" px={2}>
        <NavItem to="/dashboard" icon={FiHome} label="Dashboard" />
        <NavItem to="/catalog" icon={FiFolder} label="Catalog" />
        <NavItem to="/programs" icon={FiCode} label="Programs" />
        <NavItem to="/credentials" icon={FiKey} label="Credentials" />
        <NavItem to="/models" icon={FiCpu} label="Models" />
        <NavItem to="/compositions" icon={FiGitBranch} label="Compositions" />
        <NavItem to="/runs" icon={FiPlay} label="Runs" />

        <Box pt={8}>
          <Text
            px={4}
            pb={2}
            fontSize="xs"
            fontWeight="semibold"
            color="gray.500"
            textTransform="uppercase"
          >
            Settings
          </Text>
          <NavItem to="/settings" icon={FiSettings} label="Settings" />
        </Box>
      </VStack>
    </Box>
  );
}
