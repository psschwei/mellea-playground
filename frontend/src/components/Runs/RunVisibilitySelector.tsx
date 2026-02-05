import { useState } from 'react';
import {
  HStack,
  IconButton,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Text,
  Tooltip,
  useToast,
  Badge,
} from '@chakra-ui/react';
import { FiLock, FiUsers, FiGlobe, FiChevronDown } from 'react-icons/fi';
import { runsApi } from '@/api';
import type { Run, SharingMode } from '@/types';

interface RunVisibilitySelectorProps {
  run: Run;
  currentUserId: string;
  onUpdate?: (updatedRun: Run) => void;
  size?: 'sm' | 'md';
}

const visibilityConfig: Record<
  SharingMode,
  { label: string; icon: React.ComponentType; colorScheme: string; description: string }
> = {
  private: {
    label: 'Private',
    icon: FiLock,
    colorScheme: 'gray',
    description: 'Only you can view this run',
  },
  shared: {
    label: 'Shared',
    icon: FiUsers,
    colorScheme: 'blue',
    description: 'Shared with specific users',
  },
  public: {
    label: 'Public',
    icon: FiGlobe,
    colorScheme: 'green',
    description: 'All users can view this run',
  },
};

export function RunVisibilitySelector({
  run,
  currentUserId,
  onUpdate,
  size = 'sm',
}: RunVisibilitySelectorProps) {
  const toast = useToast();
  const [isUpdating, setIsUpdating] = useState(false);

  const isOwner = run.ownerId === currentUserId;
  const config = visibilityConfig[run.visibility];
  const Icon = config.icon;

  const handleVisibilityChange = async (newVisibility: SharingMode) => {
    if (newVisibility === run.visibility) return;

    setIsUpdating(true);
    try {
      const updatedRun = await runsApi.updateVisibility(run.id, newVisibility);
      toast({
        title: 'Visibility updated',
        description: `Run is now ${visibilityConfig[newVisibility].label.toLowerCase()}`,
        status: 'success',
        duration: 3000,
      });
      onUpdate?.(updatedRun);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to update visibility';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // If not owner, show read-only badge
  if (!isOwner) {
    return (
      <Tooltip label={config.description}>
        <Badge colorScheme={config.colorScheme} variant="subtle" fontSize={size === 'sm' ? 'xs' : 'sm'}>
          <HStack spacing={1}>
            <Icon />
            <Text>{config.label}</Text>
          </HStack>
        </Badge>
      </Tooltip>
    );
  }

  return (
    <Menu>
      <Tooltip label="Change visibility">
        <MenuButton
          as={IconButton}
          icon={
            <HStack spacing={1}>
              <Icon />
              <FiChevronDown size={12} />
            </HStack>
          }
          aria-label="Change visibility"
          size={size}
          variant="ghost"
          colorScheme={config.colorScheme}
          isLoading={isUpdating}
        />
      </Tooltip>
      <MenuList>
        {(Object.keys(visibilityConfig) as SharingMode[]).map((visibility) => {
          const itemConfig = visibilityConfig[visibility];
          const ItemIcon = itemConfig.icon;
          return (
            <MenuItem
              key={visibility}
              icon={<ItemIcon />}
              onClick={() => handleVisibilityChange(visibility)}
              fontWeight={run.visibility === visibility ? 'bold' : 'normal'}
            >
              <HStack justify="space-between" w="full">
                <Text>{itemConfig.label}</Text>
                {run.visibility === visibility && (
                  <Badge colorScheme={itemConfig.colorScheme} size="sm">
                    Current
                  </Badge>
                )}
              </HStack>
            </MenuItem>
          );
        })}
      </MenuList>
    </Menu>
  );
}
