import {
  VStack,
  SimpleGrid,
  Box,
  Text,
  Icon,
  useColorModeValue,
  FormControl,
  FormErrorMessage,
} from '@chakra-ui/react';
import { FiCode, FiGithub, FiUpload } from 'react-icons/fi';
import type { StepComponentProps, ImportSource } from '../types';

interface SourceOption {
  id: ImportSource;
  title: string;
  description: string;
  icon: typeof FiCode;
  isDisabled?: boolean;
  disabledReason?: string;
}

const SOURCE_OPTIONS: SourceOption[] = [
  {
    id: 'manual',
    title: 'Write Code',
    description: 'Create your program by writing code directly in the editor',
    icon: FiCode,
  },
  {
    id: 'github',
    title: 'Import from GitHub',
    description: 'Import code from a public GitHub repository',
    icon: FiGithub,
    isDisabled: true,
    disabledReason: 'Coming soon',
  },
  {
    id: 'upload',
    title: 'Upload Files',
    description: 'Upload a zip archive or Python file from your computer',
    icon: FiUpload,
    isDisabled: true,
    disabledReason: 'Coming soon',
  },
];

export function ImportSourceStep({ data, errors, onChange }: StepComponentProps) {
  const selectedBg = useColorModeValue('brand.50', 'brand.900');
  const selectedBorder = useColorModeValue('brand.500', 'brand.300');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  const disabledOpacity = 0.5;

  const handleSelect = (source: ImportSource) => {
    const option = SOURCE_OPTIONS.find((o) => o.id === source);
    if (!option?.isDisabled) {
      onChange('importSource', source);
    }
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        How would you like to create your program?
      </Text>

      <FormControl isInvalid={!!errors.importSource}>
        <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
          {SOURCE_OPTIONS.map((option) => {
            const isSelected = data.importSource === option.id;

            return (
              <Box
                key={option.id}
                p={6}
                borderWidth={2}
                borderRadius="lg"
                borderColor={isSelected ? selectedBorder : borderColor}
                bg={isSelected ? selectedBg : 'transparent'}
                cursor={option.isDisabled ? 'not-allowed' : 'pointer'}
                opacity={option.isDisabled ? disabledOpacity : 1}
                onClick={() => handleSelect(option.id)}
                _hover={option.isDisabled ? {} : { bg: isSelected ? selectedBg : hoverBg }}
                transition="all 0.2s"
                position="relative"
              >
                {option.isDisabled && option.disabledReason && (
                  <Text
                    position="absolute"
                    top={2}
                    right={2}
                    fontSize="xs"
                    color="gray.500"
                    fontWeight="medium"
                  >
                    {option.disabledReason}
                  </Text>
                )}

                <VStack spacing={3} align="center" textAlign="center">
                  <Icon
                    as={option.icon}
                    boxSize={10}
                    color={isSelected ? 'brand.500' : 'gray.400'}
                  />
                  <Text fontWeight="semibold" fontSize="md">
                    {option.title}
                  </Text>
                  <Text fontSize="sm" color="gray.500">
                    {option.description}
                  </Text>
                </VStack>
              </Box>
            );
          })}
        </SimpleGrid>
        <FormErrorMessage>{errors.importSource}</FormErrorMessage>
      </FormControl>
    </VStack>
  );
}
