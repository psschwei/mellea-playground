import { useState, useEffect } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Input,
  Textarea,
  VStack,
  HStack,
  Tag,
  TagLabel,
  TagCloseButton,
  Wrap,
  WrapItem,
  useToast,
} from '@chakra-ui/react';
import { assetsApi, UpdateAssetRequest } from '@/api/assets';
import type { Asset } from '@/types';

interface MetadataEditModalProps {
  asset: Asset;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updatedAsset: Asset) => void;
}

interface FormData {
  name: string;
  description: string;
  tags: string[];
  version: string;
}

interface FormErrors {
  name?: string;
}

export function MetadataEditModal({ asset, isOpen, onClose, onSave }: MetadataEditModalProps) {
  const toast = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    tags: [],
    version: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});

  // Reset form when modal opens with new asset
  useEffect(() => {
    if (isOpen && asset) {
      setFormData({
        name: asset.name,
        description: asset.description || '',
        tags: asset.tags || [],
        version: asset.version,
      });
      setErrors({});
      setTagInput('');
    }
  }, [isOpen, asset]);

  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      // Only include changed fields
      const updates: UpdateAssetRequest = {};
      if (formData.name !== asset.name) updates.name = formData.name;
      if (formData.description !== (asset.description || '')) updates.description = formData.description;
      if (JSON.stringify(formData.tags) !== JSON.stringify(asset.tags || [])) updates.tags = formData.tags;
      if (formData.version !== asset.version) updates.version = formData.version;

      // Skip if nothing changed
      if (Object.keys(updates).length === 0) {
        onClose();
        return;
      }

      const updatedAsset = await assetsApi.update(asset.id, updates);
      toast({
        title: 'Changes saved',
        status: 'success',
        duration: 3000,
      });
      onSave(updatedAsset);
      onClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to save changes';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAddTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !formData.tags.includes(tag)) {
      setFormData((prev) => ({
        ...prev,
        tags: [...prev.tags, tag],
      }));
    }
    setTagInput('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setFormData((prev) => ({
      ...prev,
      tags: prev.tags.filter((tag) => tag !== tagToRemove),
    }));
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTag();
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Edit Metadata</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl isRequired isInvalid={!!errors.name}>
              <FormLabel>Name</FormLabel>
              <Input
                value={formData.name}
                onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="Asset name"
              />
              <FormErrorMessage>{errors.name}</FormErrorMessage>
            </FormControl>

            <FormControl>
              <FormLabel>Description</FormLabel>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="Brief description of the asset"
                rows={3}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Version</FormLabel>
              <Input
                value={formData.version}
                onChange={(e) => setFormData((prev) => ({ ...prev, version: e.target.value }))}
                placeholder="e.g., 1.0.0"
              />
            </FormControl>

            <FormControl>
              <FormLabel>Tags</FormLabel>
              <HStack mb={2}>
                <Input
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={handleTagKeyDown}
                  placeholder="Add a tag and press Enter"
                  flex={1}
                />
                <Button onClick={handleAddTag} isDisabled={!tagInput.trim()}>
                  Add
                </Button>
              </HStack>
              {formData.tags.length > 0 && (
                <Wrap spacing={2}>
                  {formData.tags.map((tag) => (
                    <WrapItem key={tag}>
                      <Tag size="md" variant="subtle" colorScheme="brand">
                        <TagLabel>{tag}</TagLabel>
                        <TagCloseButton onClick={() => handleRemoveTag(tag)} />
                      </Tag>
                    </WrapItem>
                  ))}
                </Wrap>
              )}
            </FormControl>
          </VStack>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            Cancel
          </Button>
          <Button colorScheme="brand" onClick={handleSubmit} isLoading={isSubmitting}>
            Save Changes
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
