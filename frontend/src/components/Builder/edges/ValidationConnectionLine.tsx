/**
 * ValidationConnectionLine - Custom connection line with validation feedback
 *
 * Shows visual feedback while dragging a connection:
 * - Green dashed line when hovering over valid target
 * - Red dashed line when hovering over invalid target
 * - Gray dashed line when not hovering over any target
 */
import { type ConnectionLineComponentProps } from 'reactflow';
import { useConnectionFeedback } from '../ConnectionFeedback';

// Validation state colors
const connectionColors = {
  valid: '#10B981',    // Green
  invalid: '#EF4444',  // Red
  neutral: '#9CA3AF',  // Gray
} as const;

export function ValidationConnectionLine({
  fromX,
  fromY,
  toX,
  toY,
  connectionLineStyle,
}: ConnectionLineComponentProps) {
  const { validationState, isConnecting } = useConnectionFeedback();

  // Determine the color based on validation state
  let strokeColor: string = connectionColors.neutral;
  if (isConnecting) {
    if (validationState.isCurrentTargetValid) {
      // Only show green if we're actually near a target (not just dragging in space)
      // We can detect this by checking if there's no error (which means we validated a real target)
      if (validationState.currentError === undefined) {
        strokeColor = connectionColors.neutral;
      } else {
        strokeColor = connectionColors.valid;
      }
    } else {
      strokeColor = connectionColors.invalid;
    }
  }

  // Check if hovering over a valid target handle
  const isOverValidTarget = isConnecting && validationState.isCurrentTargetValid && validationState.currentError === undefined;

  // Create a bezier curve path
  const deltaX = toX - fromX;
  const controlPointOffset = Math.min(Math.abs(deltaX) * 0.5, 150);

  const path = `M${fromX},${fromY} C${fromX + controlPointOffset},${fromY} ${toX - controlPointOffset},${toY} ${toX},${toY}`;

  return (
    <g>
      {/* Shadow/glow effect for invalid connections */}
      {!validationState.isCurrentTargetValid && (
        <path
          d={path}
          fill="none"
          stroke={connectionColors.invalid}
          strokeWidth={6}
          strokeOpacity={0.3}
          strokeLinecap="round"
        />
      )}

      {/* Main connection line */}
      <path
        d={path}
        fill="none"
        stroke={strokeColor}
        strokeWidth={2}
        strokeDasharray={isOverValidTarget ? undefined : '5,5'}
        strokeLinecap="round"
        style={connectionLineStyle}
      />

      {/* Animated dots for active connection */}
      <circle r={4} fill={strokeColor}>
        <animateMotion dur="1s" repeatCount="indefinite" path={path} />
      </circle>
    </g>
  );
}
