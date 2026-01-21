/**
 * NodePalette - Sidebar component for adding nodes to the Visual Builder canvas
 *
 * Features:
 * - Recently Used section showing most recently added node types
 * - Categories: Program, Model, Primitive, Utility
 * - Drag-and-drop or click to add nodes
 */
import {
  Box,
  VStack,
  Text,
  Heading,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  useColorModeValue,
  Tooltip,
  Badge,
  HStack,
  Icon,
} from '@chakra-ui/react';
import {
  FiBox,
  FiCpu,
  FiGitMerge,
  FiTool,
  FiClock,
  FiTerminal,
  FiFilter,
  FiRepeat,
  FiEdit3,
  FiHash,
  FiZap,
} from 'react-icons/fi';
import type { IconType } from 'react-icons';
import { nodeColors, type NodeCategory } from './theme';
import type { MelleaNodeType } from './nodes';

// Node template definition
interface NodeTemplate {
  type: MelleaNodeType;
  label: string;
  description: string;
  icon: IconType;
  category: NodeCategory;
  /** Additional properties for node data */
  defaultData?: Record<string, unknown>;
}

// Available node templates organized by category
const nodeTemplates: Record<NodeCategory, NodeTemplate[]> = {
  program: [
    {
      type: 'program',
      label: 'Program',
      description: 'Reference a composition or function',
      icon: FiBox,
      category: 'program',
    },
  ],
  model: [
    {
      type: 'model',
      label: 'Model',
      description: 'AI model inference node',
      icon: FiCpu,
      category: 'model',
    },
  ],
  primitive: [
    {
      type: 'primitive',
      label: 'Loop',
      description: 'Iterate over items',
      icon: FiRepeat,
      category: 'primitive',
      defaultData: { primitiveType: 'loop' },
    },
    {
      type: 'primitive',
      label: 'Conditional',
      description: 'Branch based on condition',
      icon: FiGitMerge,
      category: 'primitive',
      defaultData: { primitiveType: 'conditional' },
    },
    {
      type: 'primitive',
      label: 'Merge',
      description: 'Combine multiple inputs',
      icon: FiGitMerge,
      category: 'primitive',
      defaultData: { primitiveType: 'merge' },
    },
    {
      type: 'primitive',
      label: 'Map',
      description: 'Transform each item',
      icon: FiFilter,
      category: 'primitive',
      defaultData: { primitiveType: 'map' },
    },
    {
      type: 'primitive',
      label: 'Filter',
      description: 'Filter items by condition',
      icon: FiFilter,
      category: 'primitive',
      defaultData: { primitiveType: 'filter' },
    },
  ],
  utility: [
    {
      type: 'utility',
      label: 'Input',
      description: 'Composition input node',
      icon: FiTerminal,
      category: 'utility',
      defaultData: { utilityType: 'input' },
    },
    {
      type: 'utility',
      label: 'Output',
      description: 'Composition output node',
      icon: FiTerminal,
      category: 'utility',
      defaultData: { utilityType: 'output' },
    },
    {
      type: 'utility',
      label: 'Note',
      description: 'Documentation note',
      icon: FiEdit3,
      category: 'utility',
      defaultData: { utilityType: 'note' },
    },
    {
      type: 'utility',
      label: 'Constant',
      description: 'Fixed value node',
      icon: FiHash,
      category: 'utility',
      defaultData: { utilityType: 'constant' },
    },
    {
      type: 'utility',
      label: 'Debug',
      description: 'Debug/inspect values',
      icon: FiZap,
      category: 'utility',
      defaultData: { utilityType: 'debug' },
    },
  ],
  error: [], // Error category has no templates
};

// Get all templates as a flat array
const allTemplates = Object.values(nodeTemplates).flat();

// Find a template by type and optional label
function findTemplate(
  nodeType: MelleaNodeType,
  label?: string
): NodeTemplate | undefined {
  const templates = allTemplates.filter((t) => t.type === nodeType);
  if (label) {
    return templates.find((t) => t.label === label) || templates[0];
  }
  return templates[0];
}

// Category metadata
const categoryMeta: Record<
  Exclude<NodeCategory, 'error'>,
  { label: string; icon: IconType }
> = {
  program: { label: 'Programs', icon: FiBox },
  model: { label: 'Models', icon: FiCpu },
  primitive: { label: 'Primitives', icon: FiGitMerge },
  utility: { label: 'Utilities', icon: FiTool },
};

interface NodePaletteItemProps {
  template: NodeTemplate;
  onClick: (template: NodeTemplate) => void;
}

function NodePaletteItem({ template, onClick }: NodePaletteItemProps) {
  const bgColor = useColorModeValue('white', 'gray.700');
  const hoverBgColor = useColorModeValue('gray.50', 'gray.600');
  const borderColor = nodeColors[template.category];

  return (
    <Tooltip label={template.description} placement="right" hasArrow>
      <Box
        p={2}
        bg={bgColor}
        borderRadius="md"
        borderLeft="3px solid"
        borderColor={borderColor}
        cursor="pointer"
        _hover={{ bg: hoverBgColor }}
        onClick={() => onClick(template)}
        transition="background 0.15s"
      >
        <HStack spacing={2}>
          <Icon as={template.icon} color={borderColor} />
          <Text fontSize="sm" fontWeight="medium">
            {template.label}
          </Text>
        </HStack>
      </Box>
    </Tooltip>
  );
}

interface RecentlyUsedEntry {
  nodeType: MelleaNodeType;
  label?: string;
}

interface NodePaletteProps {
  /** Recently used node types */
  recentlyUsed?: RecentlyUsedEntry[];
  /** Callback when a node template is selected */
  onNodeSelect: (template: NodeTemplate) => void;
}

export function NodePalette({ recentlyUsed = [], onNodeSelect }: NodePaletteProps) {
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  // Get templates for recently used nodes
  const recentTemplates = recentlyUsed
    .map((entry) => findTemplate(entry.nodeType, entry.label))
    .filter((t): t is NodeTemplate => t !== undefined)
    .slice(0, 5); // Show at most 5 recent items

  return (
    <VStack
      w="220px"
      h="full"
      p={3}
      borderRight="1px"
      borderColor={borderColor}
      bg={bgColor}
      align="stretch"
      spacing={3}
      overflow="auto"
    >
      <Heading size="sm">Node Palette</Heading>

      {/* Recently Used Section */}
      {recentTemplates.length > 0 && (
        <Box>
          <HStack spacing={1} mb={2}>
            <Icon as={FiClock} color="gray.500" boxSize={3} />
            <Text fontSize="xs" fontWeight="medium" color="gray.500">
              Recently Used
            </Text>
          </HStack>
          <VStack align="stretch" spacing={1}>
            {recentTemplates.map((template, index) => (
              <NodePaletteItem
                key={`recent-${template.type}-${template.label}-${index}`}
                template={template}
                onClick={onNodeSelect}
              />
            ))}
          </VStack>
        </Box>
      )}

      {/* Category Accordion */}
      <Accordion allowMultiple defaultIndex={[0, 1, 2, 3]}>
        {(
          Object.keys(categoryMeta) as Array<Exclude<NodeCategory, 'error'>>
        ).map((category) => {
          const templates = nodeTemplates[category];
          if (templates.length === 0) return null;

          const meta = categoryMeta[category];
          return (
            <AccordionItem key={category} border="none">
              <AccordionButton px={0} py={2} _hover={{ bg: 'transparent' }}>
                <HStack flex="1" spacing={2}>
                  <Icon as={meta.icon} color={nodeColors[category]} boxSize={4} />
                  <Text fontSize="sm" fontWeight="medium">
                    {meta.label}
                  </Text>
                  <Badge
                    colorScheme={
                      category === 'program'
                        ? 'purple'
                        : category === 'model'
                          ? 'pink'
                          : category === 'primitive'
                            ? 'blue'
                            : 'green'
                    }
                    fontSize="xs"
                  >
                    {templates.length}
                  </Badge>
                </HStack>
                <AccordionIcon />
              </AccordionButton>
              <AccordionPanel px={0} py={1}>
                <VStack align="stretch" spacing={1}>
                  {templates.map((template) => (
                    <NodePaletteItem
                      key={`${template.type}-${template.label}`}
                      template={template}
                      onClick={onNodeSelect}
                    />
                  ))}
                </VStack>
              </AccordionPanel>
            </AccordionItem>
          );
        })}
      </Accordion>
    </VStack>
  );
}

// Export template types for use in other components
export type { NodeTemplate, RecentlyUsedEntry };
export { findTemplate, allTemplates, nodeTemplates };
