/**
 * CodePreviewPanel - Displays generated Python code from the composition graph
 *
 * Features:
 * - Real-time code generation as graph changes
 * - Syntax highlighting for Python
 * - Copy to clipboard
 * - Collapsible panel
 * - Shows warnings from code generation
 */
import { useMemo, useState, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Text,
  IconButton,
  Tooltip,
  Button,
  useColorModeValue,
  useToast,
  Badge,
  Collapse,
  Code,
  Divider,
} from '@chakra-ui/react';
import { FiCopy, FiChevronDown, FiChevronUp, FiAlertTriangle, FiCode, FiDownload } from 'react-icons/fi';
import { useComposition } from './CompositionContext';
import { generateCode, generateStandaloneScript, downloadAsFile, type GeneratedCode, type CodeGeneratorOptions } from './utils';

interface CodePreviewPanelProps {
  /** Whether the panel is expanded */
  isExpanded?: boolean;
  /** Callback when expand state changes */
  onToggle?: () => void;
  /** Code generation options */
  options?: CodeGeneratorOptions;
  /** Panel width */
  width?: string | number;
}

export function CodePreviewPanel({
  isExpanded = true,
  onToggle,
  options,
  width = '400px',
}: CodePreviewPanelProps) {
  const { nodes, edges } = useComposition();
  const toast = useToast();
  const [showWarnings, setShowWarnings] = useState(true);

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const codeBg = useColorModeValue('gray.50', 'gray.900');
  const codeTextColor = useColorModeValue('gray.800', 'gray.100');

  // Generate code whenever nodes or edges change
  const generatedCode: GeneratedCode | null = useMemo(() => {
    if (nodes.length === 0) {
      return null;
    }

    try {
      return generateCode(nodes, edges, {
        includeComments: true,
        async: true,
        indent: '    ',
        typeHints: true,
        ...options,
      });
    } catch (error) {
      console.error('Code generation error:', error);
      return null;
    }
  }, [nodes, edges, options]);

  // Copy code to clipboard
  const handleCopy = useCallback(async () => {
    if (!generatedCode?.code) return;

    try {
      await navigator.clipboard.writeText(generatedCode.code);
      toast({
        title: 'Copied to clipboard',
        status: 'success',
        duration: 2000,
      });
    } catch {
      toast({
        title: 'Failed to copy',
        description: 'Could not copy code to clipboard',
        status: 'error',
        duration: 3000,
      });
    }
  }, [generatedCode?.code, toast]);

  // Export as standalone Python script
  const handleExport = useCallback(() => {
    if (nodes.length === 0) return;

    try {
      const standaloneCode = generateStandaloneScript(nodes, edges, {
        includeComments: true,
        async: true,
        indent: '    ',
        typeHints: true,
        ...options,
      });

      // Generate filename from composition or use default
      const timestamp = new Date().toISOString().slice(0, 10);
      const filename = `workflow_${timestamp}.py`;

      downloadAsFile(standaloneCode, filename, 'text/x-python');

      toast({
        title: 'Script exported',
        description: `Downloaded as ${filename}`,
        status: 'success',
        duration: 3000,
      });
    } catch {
      toast({
        title: 'Export failed',
        description: 'Could not export script',
        status: 'error',
        duration: 3000,
      });
    }
  }, [nodes, edges, options, toast]);

  // Empty state
  if (!generatedCode) {
    return (
      <Box
        w={width}
        borderLeft="1px"
        borderColor={borderColor}
        bg={bgColor}
        display="flex"
        flexDirection="column"
      >
        <HStack
          px={4}
          py={3}
          borderBottom="1px"
          borderColor={borderColor}
          justify="space-between"
        >
          <HStack spacing={2}>
            <FiCode />
            <Text fontWeight="semibold" fontSize="sm">
              Generated Code
            </Text>
          </HStack>
          {onToggle && (
            <IconButton
              aria-label="Toggle panel"
              icon={isExpanded ? <FiChevronDown /> : <FiChevronUp />}
              size="xs"
              variant="ghost"
              onClick={onToggle}
            />
          )}
        </HStack>
        <Box p={4} flex="1" display="flex" alignItems="center" justifyContent="center">
          <VStack spacing={2} color="gray.500">
            <FiCode size={24} />
            <Text fontSize="sm" textAlign="center">
              Add nodes to your composition to see generated code
            </Text>
          </VStack>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      w={width}
      borderLeft="1px"
      borderColor={borderColor}
      bg={bgColor}
      display="flex"
      flexDirection="column"
      maxH="100%"
      overflow="hidden"
    >
      {/* Header */}
      <HStack
        px={4}
        py={3}
        borderBottom="1px"
        borderColor={borderColor}
        justify="space-between"
        flexShrink={0}
      >
        <HStack spacing={2}>
          <FiCode />
          <Text fontWeight="semibold" fontSize="sm">
            Generated Code
          </Text>
          <Badge colorScheme="green" fontSize="xs">
            {generatedCode.executionOrder.length} nodes
          </Badge>
        </HStack>
        <HStack spacing={1}>
          <Tooltip label="Copy code">
            <IconButton
              aria-label="Copy code"
              icon={<FiCopy />}
              size="xs"
              variant="ghost"
              onClick={handleCopy}
            />
          </Tooltip>
          <Tooltip label="Export as standalone Python script">
            <IconButton
              aria-label="Export script"
              icon={<FiDownload />}
              size="xs"
              variant="ghost"
              onClick={handleExport}
            />
          </Tooltip>
          {onToggle && (
            <IconButton
              aria-label="Toggle panel"
              icon={isExpanded ? <FiChevronDown /> : <FiChevronUp />}
              size="xs"
              variant="ghost"
              onClick={onToggle}
            />
          )}
        </HStack>
      </HStack>

      <Collapse in={isExpanded} animateOpacity>
        <Box display="flex" flexDirection="column" maxH="calc(100vh - 180px)" overflow="hidden">
          {/* Warnings section */}
          {generatedCode.warnings.length > 0 && (
            <Box px={4} py={2} borderBottom="1px" borderColor={borderColor} flexShrink={0}>
              <HStack
                spacing={2}
                cursor="pointer"
                onClick={() => setShowWarnings(!showWarnings)}
              >
                <FiAlertTriangle color="orange" />
                <Text fontSize="xs" color="orange.500" fontWeight="medium">
                  {generatedCode.warnings.length} warning
                  {generatedCode.warnings.length !== 1 ? 's' : ''}
                </Text>
                <IconButton
                  aria-label="Toggle warnings"
                  icon={showWarnings ? <FiChevronUp /> : <FiChevronDown />}
                  size="xs"
                  variant="ghost"
                />
              </HStack>
              <Collapse in={showWarnings}>
                <VStack align="stretch" mt={2} spacing={1}>
                  {generatedCode.warnings.map((warning, i) => (
                    <Text key={i} fontSize="xs" color="orange.600">
                      {warning}
                    </Text>
                  ))}
                </VStack>
              </Collapse>
            </Box>
          )}

          {/* Inputs/Outputs summary */}
          {(generatedCode.inputs.length > 0 || generatedCode.outputs.length > 0) && (
            <Box px={4} py={2} borderBottom="1px" borderColor={borderColor} flexShrink={0}>
              <HStack spacing={4} fontSize="xs">
                {generatedCode.inputs.length > 0 && (
                  <HStack spacing={1}>
                    <Text color="gray.500">Inputs:</Text>
                    {generatedCode.inputs.map((input, i) => (
                      <Badge key={i} colorScheme="blue" size="sm">
                        {input.name}
                      </Badge>
                    ))}
                  </HStack>
                )}
                {generatedCode.outputs.length > 0 && (
                  <HStack spacing={1}>
                    <Text color="gray.500">Outputs:</Text>
                    {generatedCode.outputs.map((output, i) => (
                      <Badge key={i} colorScheme="green" size="sm">
                        {output.name}
                      </Badge>
                    ))}
                  </HStack>
                )}
              </HStack>
            </Box>
          )}

          {/* Code content */}
          <Box flex="1" overflow="auto" p={2}>
            <Box
              bg={codeBg}
              borderRadius="md"
              p={3}
              fontFamily="mono"
              fontSize="xs"
              whiteSpace="pre"
              overflowX="auto"
              lineHeight="1.6"
            >
              <Code
                display="block"
                whiteSpace="pre"
                bg="transparent"
                fontSize="xs"
                color={codeTextColor}
              >
                {generatedCode.code}
              </Code>
            </Box>
          </Box>

          {/* Footer with execution order */}
          <Divider />
          <Box px={4} py={2} flexShrink={0}>
            <Text fontSize="xs" color="gray.500" fontWeight="medium" mb={1}>
              Execution Order
            </Text>
            <HStack spacing={1} flexWrap="wrap">
              {generatedCode.executionOrder.map((nodeId, i) => (
                <Badge key={nodeId} variant="outline" fontSize="xs" mb={1}>
                  {i + 1}. {nodeId.split('-')[0]}
                </Badge>
              ))}
            </HStack>
          </Box>
        </Box>
      </Collapse>
    </Box>
  );
}

/**
 * Compact code preview button with popover
 * Can be used in the toolbar for a smaller footprint
 */
interface CodePreviewButtonProps {
  /** Callback to show full panel */
  onShowPanel?: () => void;
}

export function CodePreviewButton({ onShowPanel }: CodePreviewButtonProps) {
  const { nodes, edges } = useComposition();
  const toast = useToast();

  const generatedCode = useMemo(() => {
    if (nodes.length === 0) return null;
    try {
      return generateCode(nodes, edges);
    } catch {
      return null;
    }
  }, [nodes, edges]);

  const handleCopy = useCallback(async () => {
    if (!generatedCode?.code) return;
    try {
      await navigator.clipboard.writeText(generatedCode.code);
      toast({
        title: 'Copied to clipboard',
        status: 'success',
        duration: 2000,
      });
    } catch {
      toast({
        title: 'Failed to copy',
        status: 'error',
        duration: 3000,
      });
    }
  }, [generatedCode?.code, toast]);

  return (
    <HStack spacing={1}>
      <Tooltip label="Copy generated code">
        <IconButton
          aria-label="Copy code"
          icon={<FiCopy />}
          size="sm"
          variant="outline"
          onClick={handleCopy}
          isDisabled={!generatedCode}
        />
      </Tooltip>
      {onShowPanel && (
        <Tooltip label="View generated code">
          <Button
            leftIcon={<FiCode />}
            size="sm"
            variant="outline"
            onClick={onShowPanel}
            isDisabled={!generatedCode}
          >
            Code
          </Button>
        </Tooltip>
      )}
    </HStack>
  );
}
