import { useState } from 'react';
import {
  VStack,
  FormControl,
  FormLabel,
  FormErrorMessage,
  FormHelperText,
  Input,
  Textarea,
  Text,
  HStack,
  Tag,
  TagLabel,
  TagCloseButton,
  InputGroup,
  InputRightElement,
  IconButton,
} from '@chakra-ui/react';
import { FiPlus } from 'react-icons/fi';
import type { StepComponentProps } from '../types';

export function MetadataStep({ data, errors, onChange }: StepComponentProps) {
  const [tagInput, setTagInput] = useState('');

  const addTag = () => {
    const trimmed = tagInput.trim().toLowerCase();
    if (trimmed && !data.tags.includes(trimmed)) {
      onChange('tags', [...data.tags, trimmed]);
      setTagInput('');
    }
  };

  const removeTag = (tagToRemove: string) => {
    onChange(
      'tags',
      data.tags.filter((t) => t !== tagToRemove)
    );
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
  };

  return (
    <VStack spacing={6} align="stretch" pt={4}>
      <Text fontSize="lg" fontWeight="medium">
        Program Details
      </Text>

      <FormControl isInvalid={!!errors.name} isRequired>
        <FormLabel>Name</FormLabel>
        <Input
          placeholder="my-program"
          value={data.name}
          onChange={(e) => onChange('name', e.target.value)}
          autoFocus
        />
        <FormHelperText>Lowercase letters, numbers, and hyphens only</FormHelperText>
        <FormErrorMessage>{errors.name}</FormErrorMessage>
      </FormControl>

      <FormControl>
        <FormLabel>Description</FormLabel>
        <Textarea
          placeholder="A brief description of what your program does"
          value={data.description}
          onChange={(e) => onChange('description', e.target.value)}
          rows={3}
        />
      </FormControl>

      <FormControl isInvalid={!!errors.entrypoint} isRequired>
        <FormLabel>Entrypoint</FormLabel>
        <Input
          placeholder="main.py"
          value={data.entrypoint}
          onChange={(e) => onChange('entrypoint', e.target.value)}
          fontFamily="mono"
        />
        <FormHelperText>The Python file to execute when running the program</FormHelperText>
        <FormErrorMessage>{errors.entrypoint}</FormErrorMessage>
      </FormControl>

      <FormControl>
        <FormLabel>Tags</FormLabel>
        <InputGroup>
          <Input
            placeholder="Add a tag..."
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={handleTagKeyDown}
          />
          <InputRightElement>
            <IconButton
              aria-label="Add tag"
              icon={<FiPlus />}
              size="sm"
              variant="ghost"
              onClick={addTag}
              isDisabled={!tagInput.trim()}
            />
          </InputRightElement>
        </InputGroup>

        {data.tags.length > 0 && (
          <HStack spacing={2} mt={3} flexWrap="wrap">
            {data.tags.map((tag) => (
              <Tag key={tag} size="md" colorScheme="brand" variant="subtle">
                <TagLabel>{tag}</TagLabel>
                <TagCloseButton onClick={() => removeTag(tag)} />
              </Tag>
            ))}
          </HStack>
        )}
      </FormControl>
    </VStack>
  );
}
