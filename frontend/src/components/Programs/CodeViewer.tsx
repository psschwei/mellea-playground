import { Box, HStack, Text, useColorModeValue } from '@chakra-ui/react';

interface CodeViewerProps {
  code: string;
  filename?: string;
  maxHeight?: string;
}

export function CodeViewer({ code, filename, maxHeight = '400px' }: CodeViewerProps) {
  const bg = useColorModeValue('gray.900', 'gray.800');
  const lineNumberColor = useColorModeValue('gray.500', 'gray.600');
  const codeColor = useColorModeValue('gray.100', 'gray.200');
  const headerBg = useColorModeValue('gray.800', 'gray.700');

  const lines = code.split('\n');

  return (
    <Box borderRadius="md" overflow="hidden" border="1px solid" borderColor="gray.700">
      {filename && (
        <Box bg={headerBg} px={4} py={2}>
          <Text fontSize="sm" color="gray.400" fontFamily="mono">
            {filename}
          </Text>
        </Box>
      )}
      <Box bg={bg} p={4} maxH={maxHeight} overflowY="auto" fontFamily="mono" fontSize="sm">
        {lines.map((line, index) => (
          <HStack key={index} spacing={4} align="start">
            <Text
              color={lineNumberColor}
              minW="30px"
              textAlign="right"
              userSelect="none"
              flexShrink={0}
            >
              {index + 1}
            </Text>
            <Text color={codeColor} whiteSpace="pre" flex={1}>
              {line || ' '}
            </Text>
          </HStack>
        ))}
      </Box>
    </Box>
  );
}
