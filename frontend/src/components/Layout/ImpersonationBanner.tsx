import {
  Box,
  Button,
  Flex,
  HStack,
  Text,
  useToast,
} from '@chakra-ui/react';
import { FiEye, FiX } from 'react-icons/fi';
import { useAuth } from '@/hooks';

export function ImpersonationBanner() {
  const { impersonationStatus, stopImpersonation, user } = useAuth();
  const toast = useToast();

  if (!impersonationStatus?.isImpersonating) {
    return null;
  }

  const handleStopImpersonation = async () => {
    try {
      await stopImpersonation();
      toast({
        title: 'Impersonation ended',
        description: 'You are now back to your admin session.',
        status: 'info',
        duration: 3000,
      });
    } catch {
      toast({
        title: 'Failed to stop impersonation',
        status: 'error',
        duration: 3000,
      });
    }
  };

  return (
    <Box
      bg="orange.500"
      color="white"
      py={2}
      px={4}
      position="sticky"
      top={0}
      zIndex={20}
    >
      <Flex justify="center" align="center">
        <HStack spacing={4}>
          <HStack spacing={2}>
            <FiEye />
            <Text fontWeight="medium">
              Impersonating: {user?.displayName} ({user?.email})
            </Text>
          </HStack>
          <Text fontSize="sm" opacity={0.9}>
            Acting as {impersonationStatus.impersonatorEmail}
          </Text>
          <Button
            size="sm"
            variant="solid"
            bg="orange.600"
            _hover={{ bg: 'orange.700' }}
            leftIcon={<FiX />}
            onClick={handleStopImpersonation}
          >
            Stop Impersonating
          </Button>
        </HStack>
      </Flex>
    </Box>
  );
}
