import { Badge, HStack, Spinner } from '@chakra-ui/react';
import type { RunExecutionStatus } from '@/types';

interface RunStatusBadgeProps {
  status: RunExecutionStatus;
  size?: 'sm' | 'md' | 'lg';
}

const statusConfig: Record<
  RunExecutionStatus,
  { label: string; colorScheme: string; isAnimated?: boolean }
> = {
  queued: { label: 'Queued', colorScheme: 'gray' },
  starting: { label: 'Starting', colorScheme: 'blue', isAnimated: true },
  running: { label: 'Running', colorScheme: 'blue', isAnimated: true },
  succeeded: { label: 'Succeeded', colorScheme: 'green' },
  failed: { label: 'Failed', colorScheme: 'red' },
  cancelled: { label: 'Cancelled', colorScheme: 'orange' },
};

export function RunStatusBadge({ status, size = 'md' }: RunStatusBadgeProps) {
  const config = statusConfig[status];
  const fontSize = size === 'sm' ? 'xs' : size === 'lg' ? 'md' : 'sm';
  const spinnerSize = size === 'sm' ? 'xs' : 'sm';

  return (
    <HStack spacing={1}>
      {config.isAnimated && <Spinner size={spinnerSize} color={`${config.colorScheme}.500`} />}
      <Badge colorScheme={config.colorScheme} fontSize={fontSize} variant="subtle">
        {config.label}
      </Badge>
    </HStack>
  );
}
