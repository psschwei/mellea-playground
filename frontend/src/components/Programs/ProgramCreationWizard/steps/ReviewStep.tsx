import {
  VStack,
  HStack,
  Box,
  Text,
  Badge,
  Divider,
  useColorModeValue,
  Tag,
  Heading,
  Textarea,
} from '@chakra-ui/react';
import type { StepComponentProps } from '../types';

export function ReviewStep({ data }: StepComponentProps) {
  const labelColor = useColorModeValue('gray.600', 'gray.400');
  const boxBg = useColorModeValue('gray.50', 'gray.700');
  const codeBg = useColorModeValue('gray.900', 'gray.800');

  const getSourceLabel = () => {
    switch (data.importSource) {
      case 'manual':
        return 'Manual Entry';
      case 'github':
        return `GitHub: ${data.github.url}`;
      case 'upload':
        return `Upload: ${data.upload.file?.name || 'Unknown'}`;
      default:
        return 'Unknown';
    }
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Review your program
      </Text>

      <Box p={4} bg={boxBg} borderRadius="md">
        <VStack spacing={4} align="stretch">
          <Box>
            <Heading size="sm" mb={2}>
              Program Information
            </Heading>
            <VStack align="stretch" spacing={2}>
              <HStack justify="space-between">
                <Text color={labelColor}>Name</Text>
                <Text fontWeight="medium">{data.name || '(not set)'}</Text>
              </HStack>
              <HStack justify="space-between">
                <Text color={labelColor}>Description</Text>
                <Text fontWeight="medium" noOfLines={1}>
                  {data.description || '(none)'}
                </Text>
              </HStack>
              <HStack justify="space-between">
                <Text color={labelColor}>Entrypoint</Text>
                <Text fontFamily="mono" fontSize="sm">
                  {data.entrypoint}
                </Text>
              </HStack>
              <HStack justify="space-between">
                <Text color={labelColor}>Source</Text>
                <Badge colorScheme="brand">{getSourceLabel()}</Badge>
              </HStack>
            </VStack>
          </Box>

          {data.tags.length > 0 && (
            <>
              <Divider />
              <Box>
                <Text color={labelColor} mb={2}>
                  Tags
                </Text>
                <HStack spacing={2} flexWrap="wrap">
                  {data.tags.map((tag) => (
                    <Tag key={tag} size="sm" colorScheme="gray">
                      {tag}
                    </Tag>
                  ))}
                </HStack>
              </Box>
            </>
          )}
        </VStack>
      </Box>

      {data.importSource === 'manual' && (
        <Box>
          <Text fontWeight="medium" mb={2}>
            Code Preview
          </Text>
          <Textarea
            value={data.sourceCode}
            readOnly
            fontFamily="mono"
            fontSize="sm"
            bg={codeBg}
            color="green.300"
            maxH="200px"
            resize="none"
          />
        </Box>
      )}
    </VStack>
  );
}
