import { Box, Flex } from '@chakra-ui/react';
import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { ImpersonationBanner } from './ImpersonationBanner';
import { Sidebar } from './Sidebar';

export function MainLayout() {
  return (
    <Box minH="100vh">
      <ImpersonationBanner />
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
