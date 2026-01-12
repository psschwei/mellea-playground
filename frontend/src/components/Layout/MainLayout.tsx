import { Box, Flex } from '@chakra-ui/react';
import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

export function MainLayout() {
  return (
    <Box minH="100vh">
      <Header />
      <Flex>
        <Sidebar />
        <Box flex={1} p={6} bg="gray.50" minH="calc(100vh - 56px)">
          <Outlet />
        </Box>
      </Flex>
    </Box>
  );
}
