import { useState } from 'react';
import {
  Box,
  Button,
  Container,
  FormControl,
  FormLabel,
  Heading,
  Input,
  Link,
  Stack,
  Text,
  useToast,
  FormErrorMessage,
} from '@chakra-ui/react';
import { Link as RouterLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks';
import { AxiosError } from 'axios';
import type { ApiError } from '@/types';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      toast({
        title: 'Welcome back!',
        status: 'success',
        duration: 3000,
      });
      navigate(from, { replace: true });
    } catch (err) {
      const axiosError = err as AxiosError<ApiError>;
      setError(axiosError.response?.data?.detail || 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container maxW="md" py={12}>
      <Stack spacing={8}>
        <Stack align="center">
          <Heading fontSize="3xl">Sign in to Mellea</Heading>
          <Text color="gray.600">
            to continue to Mellea Playground
          </Text>
        </Stack>

        <Box
          rounded="lg"
          bg="white"
          boxShadow="lg"
          p={8}
        >
          <form onSubmit={handleSubmit}>
            <Stack spacing={4}>
              <FormControl isRequired isInvalid={!!error}>
                <FormLabel>Email address</FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </FormControl>

              <FormControl isRequired isInvalid={!!error}>
                <FormLabel>Password</FormLabel>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                />
                {error && <FormErrorMessage>{error}</FormErrorMessage>}
              </FormControl>

              <Button
                type="submit"
                colorScheme="blue"
                size="lg"
                fontSize="md"
                isLoading={isLoading}
              >
                Sign in
              </Button>
            </Stack>
          </form>

          <Stack pt={6}>
            <Text align="center">
              Don't have an account?{' '}
              <Link as={RouterLink} to="/register" color="blue.500">
                Sign up
              </Link>
            </Text>
          </Stack>
        </Box>

        <Text align="center" fontSize="sm" color="gray.500">
          Development accounts: admin@mellea.local / admin123
        </Text>
      </Stack>
    </Container>
  );
}
