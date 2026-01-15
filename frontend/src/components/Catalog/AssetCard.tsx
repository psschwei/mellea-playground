import {
  Card,
  CardBody,
  HStack,
  VStack,
  Heading,
  Text,
  Button,
  Icon,
  Badge,
  Tooltip,
  useColorModeValue,
} from '@chakra-ui/react';
import {
  FiFile,
  FiCpu,
  FiGitMerge,
  FiChevronRight,
  FiTrash2,
  FiGlobe,
  FiUsers,
  FiLock,
} from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import type { Asset, AssetType } from '@/types';

interface AssetCardProps {
  asset: Asset;
  onDelete?: (asset: Asset) => void;
  showActions?: boolean;
}

const assetTypeConfig: Record<
  AssetType,
  { icon: typeof FiFile; label: string; color: string; route: string }
> = {
  program: { icon: FiFile, label: 'Program', color: 'blue', route: '/programs' },
  model: { icon: FiCpu, label: 'Model', color: 'purple', route: '/models' },
  composition: { icon: FiGitMerge, label: 'Composition', color: 'teal', route: '/compositions' },
};

const sharingConfig = {
  private: { icon: FiLock, label: 'Private', color: 'gray' },
  shared: { icon: FiUsers, label: 'Shared', color: 'blue' },
  public: { icon: FiGlobe, label: 'Public', color: 'green' },
};

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

export function AssetCard({ asset, onDelete, showActions = true }: AssetCardProps) {
  const navigate = useNavigate();
  const bgHover = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  const typeConfig = assetTypeConfig[asset.type];
  const sharing = sharingConfig[asset.sharing];

  const statusColor =
    asset.lastRunStatus === 'succeeded'
      ? 'green'
      : asset.lastRunStatus === 'failed'
        ? 'red'
        : 'gray';

  const statusLabel =
    asset.lastRunStatus === 'succeeded'
      ? 'Succeeded'
      : asset.lastRunStatus === 'failed'
        ? 'Failed'
        : 'Ready';

  const handleCardClick = () => {
    navigate(`${typeConfig.route}/${asset.id}`);
  };

  return (
    <Card
      variant="outline"
      borderColor={borderColor}
      _hover={{ bg: bgHover, cursor: 'pointer' }}
      transition="background 0.2s"
      onClick={handleCardClick}
    >
      <CardBody>
        <HStack justify="space-between" align="start">
          <HStack spacing={3} align="start" flex={1} minW={0}>
            <Icon as={typeConfig.icon} boxSize={5} color={`${typeConfig.color}.500`} mt={1} />
            <VStack align="start" spacing={1} flex={1} minW={0}>
              <HStack spacing={2}>
                <Heading size="sm" noOfLines={1}>
                  {asset.name}
                </Heading>
                <Tooltip label={sharing.label}>
                  <span>
                    <Icon as={sharing.icon} boxSize={3} color={`${sharing.color}.500`} />
                  </span>
                </Tooltip>
              </HStack>
              {asset.description && (
                <Text fontSize="sm" color="gray.500" noOfLines={1}>
                  {asset.description}
                </Text>
              )}
              <Text fontSize="xs" color="gray.400">
                {typeConfig.label} &bull; Updated {formatRelativeTime(asset.updatedAt)}
              </Text>
              <HStack spacing={2} mt={1} flexWrap="wrap">
                <Badge colorScheme={typeConfig.color} variant="subtle" size="sm">
                  {typeConfig.label}
                </Badge>
                {asset.lastRunStatus && (
                  <Badge colorScheme={statusColor} variant="subtle" size="sm">
                    {statusLabel}
                  </Badge>
                )}
                {asset.tags?.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="outline" colorScheme="gray" size="sm">
                    {tag}
                  </Badge>
                ))}
                {asset.tags && asset.tags.length > 3 && (
                  <Badge variant="outline" colorScheme="gray" size="sm">
                    +{asset.tags.length - 3}
                  </Badge>
                )}
              </HStack>
            </VStack>
          </HStack>

          {showActions && (
            <HStack spacing={2} onClick={(e) => e.stopPropagation()}>
              <Button
                size="sm"
                variant="ghost"
                rightIcon={<FiChevronRight />}
                onClick={handleCardClick}
              >
                View
              </Button>
              {onDelete && (
                <Button
                  size="sm"
                  variant="ghost"
                  colorScheme="red"
                  onClick={() => onDelete(asset)}
                  aria-label={`Delete ${asset.name}`}
                >
                  <Icon as={FiTrash2} />
                </Button>
              )}
            </HStack>
          )}
        </HStack>
      </CardBody>
    </Card>
  );
}
