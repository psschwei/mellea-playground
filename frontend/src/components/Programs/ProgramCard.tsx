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
  useColorModeValue,
} from '@chakra-ui/react';
import { FiFile, FiPlay, FiChevronRight, FiTrash2 } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import type { ProgramAsset } from '@/types';

interface ProgramCardProps {
  program: ProgramAsset;
  onRun?: (program: ProgramAsset) => void;
  onDelete?: (program: ProgramAsset) => void;
  isBuilding?: boolean;
  isRunning?: boolean;
}

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

export function ProgramCard({ program, onRun, onDelete, isBuilding = false, isRunning = false }: ProgramCardProps) {
  const navigate = useNavigate();
  const bgHover = useColorModeValue('gray.50', 'gray.700');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  const lastRunText = program.lastRunAt
    ? `Last run: ${formatRelativeTime(program.lastRunAt)}`
    : 'Never run';

  const statusColor =
    program.lastRunStatus === 'succeeded'
      ? 'green'
      : program.lastRunStatus === 'failed'
        ? 'red'
        : 'gray';

  const statusLabel =
    program.lastRunStatus === 'succeeded'
      ? 'Succeeded'
      : program.lastRunStatus === 'failed'
        ? 'Failed'
        : 'Ready';

  return (
    <Card
      variant="outline"
      borderColor={borderColor}
      _hover={{ bg: bgHover, cursor: 'pointer' }}
      transition="background 0.2s"
      onClick={() => navigate(`/programs/${program.id}`)}
    >
      <CardBody>
        <HStack justify="space-between" align="start">
          <HStack spacing={3} align="start">
            <Icon as={FiFile} boxSize={5} color="brand.500" mt={1} />
            <VStack align="start" spacing={1}>
              <Heading size="sm">{program.name}</Heading>
              <Text fontSize="sm" color="gray.500">
                Python program &bull; {lastRunText}
              </Text>
              <HStack spacing={2} mt={1}>
                <Badge colorScheme={statusColor} variant="subtle">
                  {statusLabel}
                </Badge>
                {program.tags?.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="outline" colorScheme="gray">
                    {tag}
                  </Badge>
                ))}
              </HStack>
            </VStack>
          </HStack>

          <HStack spacing={2} onClick={(e) => e.stopPropagation()}>
            <Button
              size="sm"
              colorScheme="brand"
              leftIcon={<FiPlay />}
              isLoading={isBuilding || isRunning}
              loadingText={isBuilding ? 'Building' : 'Running'}
              onClick={() => onRun?.(program)}
            >
              Run
            </Button>
            <Button
              size="sm"
              variant="ghost"
              rightIcon={<FiChevronRight />}
              onClick={() => navigate(`/programs/${program.id}`)}
            >
              View
            </Button>
            {onDelete && (
              <Button
                size="sm"
                variant="ghost"
                colorScheme="red"
                onClick={() => onDelete(program)}
                aria-label="Delete program"
              >
                <Icon as={FiTrash2} />
              </Button>
            )}
          </HStack>
        </HStack>
      </CardBody>
    </Card>
  );
}
