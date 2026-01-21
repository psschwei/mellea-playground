/**
 * BuilderSidebar - Enhanced sidebar component for the Visual Builder
 *
 * Features:
 * - Search/filter across all categories
 * - Recently Used section
 * - Dynamic assets (programs, models) fetched from API
 * - Static primitives and utilities
 * - Categorized accordion sections
 */
import { useState, useEffect, useMemo } from 'react';
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
  Input,
  InputGroup,
  InputLeftElement,
  Spinner,
} from '@chakra-ui/react';
import {
  FiBox,
  FiCpu,
  FiGitMerge,
  FiTool,
  FiClock,
  FiSearch,
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
import { assetsApi } from '@/api/assets';
import type { ProgramAsset, ModelAsset } from '@/types';

// Sidebar item definition (combines templates and dynamic assets)
export interface SidebarItem {
  id: string;
  type: MelleaNodeType;
  label: string;
  description: string;
  icon: IconType;
  category: NodeCategory;
  /** Asset reference for dynamic items */
  assetId?: string;
  /** Additional properties for node data */
  defaultData?: Record<string, unknown>;
}

// Static primitives (built-in control flow nodes)
const primitiveItems: SidebarItem[] = [
  {
    id: 'primitive-loop',
    type: 'primitive',
    label: 'Loop',
    description: 'Iterate over items',
    icon: FiRepeat,
    category: 'primitive',
    defaultData: { primitiveType: 'loop' },
  },
  {
    id: 'primitive-conditional',
    type: 'primitive',
    label: 'Conditional',
    description: 'Branch based on condition',
    icon: FiGitMerge,
    category: 'primitive',
    defaultData: { primitiveType: 'conditional' },
  },
  {
    id: 'primitive-merge',
    type: 'primitive',
    label: 'Merge',
    description: 'Combine multiple inputs',
    icon: FiGitMerge,
    category: 'primitive',
    defaultData: { primitiveType: 'merge' },
  },
  {
    id: 'primitive-map',
    type: 'primitive',
    label: 'Map',
    description: 'Transform each item',
    icon: FiFilter,
    category: 'primitive',
    defaultData: { primitiveType: 'map' },
  },
  {
    id: 'primitive-filter',
    type: 'primitive',
    label: 'Filter',
    description: 'Filter items by condition',
    icon: FiFilter,
    category: 'primitive',
    defaultData: { primitiveType: 'filter' },
  },
];

// Static utilities (built-in utility nodes)
const utilityItems: SidebarItem[] = [
  {
    id: 'utility-input',
    type: 'utility',
    label: 'Input',
    description: 'Composition input node',
    icon: FiTerminal,
    category: 'utility',
    defaultData: { utilityType: 'input' },
  },
  {
    id: 'utility-output',
    type: 'utility',
    label: 'Output',
    description: 'Composition output node',
    icon: FiTerminal,
    category: 'utility',
    defaultData: { utilityType: 'output' },
  },
  {
    id: 'utility-note',
    type: 'utility',
    label: 'Note',
    description: 'Documentation note',
    icon: FiEdit3,
    category: 'utility',
    defaultData: { utilityType: 'note' },
  },
  {
    id: 'utility-constant',
    type: 'utility',
    label: 'Constant',
    description: 'Fixed value node',
    icon: FiHash,
    category: 'utility',
    defaultData: { utilityType: 'constant' },
  },
  {
    id: 'utility-debug',
    type: 'utility',
    label: 'Debug',
    description: 'Debug/inspect values',
    icon: FiZap,
    category: 'utility',
    defaultData: { utilityType: 'debug' },
  },
];

// Category metadata for display
const categoryMeta: Record<
  Exclude<NodeCategory, 'error'>,
  { label: string; icon: IconType; colorScheme: string }
> = {
  program: { label: 'Programs', icon: FiBox, colorScheme: 'purple' },
  model: { label: 'Models', icon: FiCpu, colorScheme: 'pink' },
  primitive: { label: 'Primitives', icon: FiGitMerge, colorScheme: 'blue' },
  utility: { label: 'Utilities', icon: FiTool, colorScheme: 'green' },
};

// Convert Program asset to SidebarItem
function programToSidebarItem(asset: ProgramAsset): SidebarItem {
  return {
    id: `program-${asset.id}`,
    type: 'program',
    label: asset.name,
    description: asset.description || `Program: ${asset.entrypoint}`,
    icon: FiBox,
    category: 'program',
    assetId: asset.id,
    defaultData: {
      assetRef: asset.id,
      version: asset.version,
      entrypoint: asset.entrypoint,
    },
  };
}

// Convert Model asset to SidebarItem
function modelToSidebarItem(asset: ModelAsset): SidebarItem {
  return {
    id: `model-${asset.id}`,
    type: 'model',
    label: asset.name,
    description: asset.description || `${asset.provider}: ${asset.modelId}`,
    icon: FiCpu,
    category: 'model',
    assetId: asset.id,
    defaultData: {
      assetRef: asset.id,
      provider: asset.provider,
      modelId: asset.modelId,
    },
  };
}

interface SidebarItemProps {
  item: SidebarItem;
  onClick: (item: SidebarItem) => void;
}

function SidebarItemComponent({ item, onClick }: SidebarItemProps) {
  const bgColor = useColorModeValue('white', 'gray.700');
  const hoverBgColor = useColorModeValue('gray.50', 'gray.600');
  const borderColor = nodeColors[item.category];

  return (
    <Tooltip label={item.description} placement="right" hasArrow>
      <Box
        p={2}
        bg={bgColor}
        borderRadius="md"
        borderLeft="3px solid"
        borderColor={borderColor}
        cursor="pointer"
        _hover={{ bg: hoverBgColor }}
        onClick={() => onClick(item)}
        transition="background 0.15s"
      >
        <HStack spacing={2}>
          <Icon as={item.icon} color={borderColor} />
          <Text fontSize="sm" fontWeight="medium" noOfLines={1}>
            {item.label}
          </Text>
        </HStack>
      </Box>
    </Tooltip>
  );
}

export interface RecentlyUsedEntry {
  itemId: string;
  nodeType: string;
  label?: string;
}

interface BuilderSidebarProps {
  /** Recently used items */
  recentlyUsed?: RecentlyUsedEntry[];
  /** Callback when a sidebar item is selected */
  onItemSelect: (item: SidebarItem) => void;
}

export function BuilderSidebar({
  recentlyUsed = [],
  onItemSelect,
}: BuilderSidebarProps) {
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const inputBgColor = useColorModeValue('gray.50', 'gray.700');

  // State for dynamic assets
  const [programs, setPrograms] = useState<SidebarItem[]>([]);
  const [models, setModels] = useState<SidebarItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch assets on mount
  useEffect(() => {
    async function fetchAssets() {
      setIsLoading(true);
      try {
        const [programsResponse, modelsResponse] = await Promise.all([
          assetsApi.list({ type: 'program' }),
          assetsApi.list({ type: 'model' }),
        ]);

        setPrograms(
          programsResponse.assets
            .filter((a): a is ProgramAsset => a.type === 'program')
            .map(programToSidebarItem)
        );
        setModels(
          modelsResponse.assets
            .filter((a): a is ModelAsset => a.type === 'model')
            .map(modelToSidebarItem)
        );
      } catch (error) {
        console.error('Failed to fetch assets:', error);
        // Keep empty arrays on error - show static items only
      } finally {
        setIsLoading(false);
      }
    }

    fetchAssets();
  }, []);

  // Combine all items for search
  const allItems = useMemo(() => {
    return [...programs, ...models, ...primitiveItems, ...utilityItems];
  }, [programs, models]);

  // Filter items by search query
  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) {
      return {
        program: programs,
        model: models,
        primitive: primitiveItems,
        utility: utilityItems,
      };
    }

    const query = searchQuery.toLowerCase();
    const matchItem = (item: SidebarItem) =>
      item.label.toLowerCase().includes(query) ||
      item.description.toLowerCase().includes(query);

    return {
      program: programs.filter(matchItem),
      model: models.filter(matchItem),
      primitive: primitiveItems.filter(matchItem),
      utility: utilityItems.filter(matchItem),
    };
  }, [searchQuery, programs, models]);

  // Get items for recently used section
  const recentItems = useMemo(() => {
    return recentlyUsed
      .map((entry) => allItems.find((item) => item.id === entry.itemId))
      .filter((item): item is SidebarItem => item !== undefined)
      .slice(0, 5);
  }, [recentlyUsed, allItems]);

  // Calculate total matches for each category
  const totalMatches = useMemo(() => {
    return {
      program: filteredItems.program.length,
      model: filteredItems.model.length,
      primitive: filteredItems.primitive.length,
      utility: filteredItems.utility.length,
    };
  }, [filteredItems]);

  const hasAnyResults = Object.values(totalMatches).some((count) => count > 0);

  return (
    <VStack
      w="240px"
      h="full"
      p={3}
      borderRight="1px"
      borderColor={borderColor}
      bg={bgColor}
      align="stretch"
      spacing={3}
      overflow="auto"
    >
      <Heading size="sm">Assets</Heading>

      {/* Search Input */}
      <InputGroup size="sm">
        <InputLeftElement>
          <Icon as={FiSearch} color="gray.400" />
        </InputLeftElement>
        <Input
          placeholder="Search assets..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          bg={inputBgColor}
          borderRadius="md"
        />
      </InputGroup>

      {/* Loading State */}
      {isLoading && (
        <HStack justify="center" py={4}>
          <Spinner size="sm" />
          <Text fontSize="sm" color="gray.500">
            Loading assets...
          </Text>
        </HStack>
      )}

      {/* No Results */}
      {!isLoading && searchQuery && !hasAnyResults && (
        <Box py={4} textAlign="center">
          <Text fontSize="sm" color="gray.500">
            No assets match "{searchQuery}"
          </Text>
        </Box>
      )}

      {/* Recently Used Section (only when not searching) */}
      {!searchQuery && recentItems.length > 0 && (
        <Box>
          <HStack spacing={1} mb={2}>
            <Icon as={FiClock} color="gray.500" boxSize={3} />
            <Text fontSize="xs" fontWeight="medium" color="gray.500">
              Recently Used
            </Text>
          </HStack>
          <VStack align="stretch" spacing={1}>
            {recentItems.map((item) => (
              <SidebarItemComponent
                key={`recent-${item.id}`}
                item={item}
                onClick={onItemSelect}
              />
            ))}
          </VStack>
        </Box>
      )}

      {/* Category Accordion */}
      {!isLoading && (
        <Accordion allowMultiple defaultIndex={[0, 1, 2, 3]}>
          {(
            Object.keys(categoryMeta) as Array<Exclude<NodeCategory, 'error'>>
          ).map((category) => {
            const items = filteredItems[category];
            const meta = categoryMeta[category];

            // Hide empty categories when searching
            if (searchQuery && items.length === 0) return null;

            return (
              <AccordionItem key={category} border="none">
                <AccordionButton px={0} py={2} _hover={{ bg: 'transparent' }}>
                  <HStack flex="1" spacing={2}>
                    <Icon
                      as={meta.icon}
                      color={nodeColors[category]}
                      boxSize={4}
                    />
                    <Text fontSize="sm" fontWeight="medium">
                      {meta.label}
                    </Text>
                    <Badge colorScheme={meta.colorScheme} fontSize="xs">
                      {items.length}
                    </Badge>
                  </HStack>
                  <AccordionIcon />
                </AccordionButton>
                <AccordionPanel px={0} py={1}>
                  {items.length === 0 ? (
                    <Text fontSize="xs" color="gray.500" py={2}>
                      No {meta.label.toLowerCase()} available
                    </Text>
                  ) : (
                    <VStack align="stretch" spacing={1}>
                      {items.map((item) => (
                        <SidebarItemComponent
                          key={item.id}
                          item={item}
                          onClick={onItemSelect}
                        />
                      ))}
                    </VStack>
                  )}
                </AccordionPanel>
              </AccordionItem>
            );
          })}
        </Accordion>
      )}
    </VStack>
  );
}

// Export helpers
export { programToSidebarItem, modelToSidebarItem, primitiveItems, utilityItems };
