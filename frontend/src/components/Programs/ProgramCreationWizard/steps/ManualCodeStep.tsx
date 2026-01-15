import {
  VStack,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Textarea,
  Box,
  Text,
  useColorModeValue,
} from '@chakra-ui/react';
import type { StepComponentProps } from '../types';

export function ManualCodeStep({ data, errors, onChange }: StepComponentProps) {
  const codeBg = useColorModeValue('gray.900', 'gray.800');

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Write your Python code
      </Text>

      <FormControl isInvalid={!!errors.sourceCode}>
        <FormLabel>Source Code</FormLabel>
        <Box position="relative">
          <Text position="absolute" top={2} right={2} fontSize="xs" color="gray.500" zIndex={1}>
            {data.entrypoint}
          </Text>
          <Textarea
            value={data.sourceCode}
            onChange={(e) => onChange('sourceCode', e.target.value)}
            fontFamily="mono"
            fontSize="sm"
            bg={codeBg}
            color="green.300"
            minH="300px"
            resize="vertical"
            placeholder="# Your Python code here"
            spellCheck={false}
          />
        </Box>
        <FormErrorMessage>{errors.sourceCode}</FormErrorMessage>
      </FormControl>
    </VStack>
  );
}
