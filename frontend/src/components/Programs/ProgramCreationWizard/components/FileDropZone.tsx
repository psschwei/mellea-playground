import { useCallback, useState, useRef } from 'react';
import { Box, VStack, Text, Icon, useColorModeValue, HStack, IconButton } from '@chakra-ui/react';
import { FiUpload, FiFile, FiX } from 'react-icons/fi';

interface FileDropZoneProps {
  file: File | null;
  onFileSelect: (file: File | null) => void;
  acceptedTypes: string[];
  maxSizeMB: number;
  isDisabled?: boolean;
}

export function FileDropZone({
  file,
  onFileSelect,
  acceptedTypes,
  maxSizeMB,
  isDisabled = false,
}: FileDropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const borderColor = useColorModeValue('gray.300', 'gray.600');
  const dragBorderColor = useColorModeValue('brand.500', 'brand.300');
  const bgColor = useColorModeValue('gray.50', 'gray.700');
  const dragBgColor = useColorModeValue('brand.50', 'brand.900');

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (!isDisabled) setIsDragging(true);
    },
    [isDisabled]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (isDisabled) return;

      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) {
        onFileSelect(droppedFile);
      }
    },
    [isDisabled, onFileSelect]
  );

  const handleClick = () => {
    if (!isDisabled) {
      fileInputRef.current?.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    onFileSelect(selectedFile);
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    onFileSelect(null);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <Box
      p={8}
      borderWidth={2}
      borderStyle="dashed"
      borderRadius="lg"
      borderColor={isDragging ? dragBorderColor : borderColor}
      bg={isDragging ? dragBgColor : bgColor}
      cursor={isDisabled ? 'not-allowed' : 'pointer'}
      opacity={isDisabled ? 0.5 : 1}
      transition="all 0.2s"
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedTypes.join(',')}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        disabled={isDisabled}
      />

      {file ? (
        <HStack justify="center" spacing={4}>
          <Icon as={FiFile} boxSize={6} color="brand.500" />
          <VStack spacing={0} align="start">
            <Text fontWeight="medium">{file.name}</Text>
            <Text fontSize="sm" color="gray.500">
              {formatFileSize(file.size)}
            </Text>
          </VStack>
          <IconButton
            aria-label="Remove file"
            icon={<FiX />}
            size="sm"
            variant="ghost"
            onClick={handleRemove}
          />
        </HStack>
      ) : (
        <VStack spacing={3}>
          <Icon as={FiUpload} boxSize={10} color="gray.400" />
          <VStack spacing={1}>
            <Text fontWeight="medium">
              {isDragging ? 'Drop file here' : 'Drag & drop or click to upload'}
            </Text>
            <Text fontSize="sm" color="gray.500">
              {acceptedTypes.join(', ')} (max {maxSizeMB}MB)
            </Text>
          </VStack>
        </VStack>
      )}
    </Box>
  );
}
