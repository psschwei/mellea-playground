import { useState, useEffect, useCallback, useRef } from 'react';
import { isAuthenticated } from '@/api/client';
import { runLogs, runs } from '@/api/mock-store';

export type LogStreamStatus = 'idle' | 'connecting' | 'connected' | 'completed' | 'error';

interface UseLogStreamOptions {
  onComplete?: (status: string) => void;
  onError?: (error: Error) => void;
}

interface UseLogStreamReturn {
  logs: string;
  status: LogStreamStatus;
  finalRunStatus: string | null;
  error: Error | null;
  connect: () => void;
  disconnect: () => void;
}

export function useLogStream(
  runId: string | null | undefined,
  options: UseLogStreamOptions = {}
): UseLogStreamReturn {
  const [logs, setLogs] = useState<string>('');
  const [status, setStatus] = useState<LogStreamStatus>('idle');
  const [finalRunStatus, setFinalRunStatus] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { onComplete, onError } = options;

  const disconnect = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!runId) return;

    disconnect();
    setLogs('');
    setError(null);
    setFinalRunStatus(null);
    setStatus('connecting');

    if (!isAuthenticated()) {
      const authError = new Error('Not authenticated');
      setError(authError);
      setStatus('error');
      onError?.(authError);
      return;
    }

    // Brief delay to simulate connection establishment
    setTimeout(() => {
      setStatus('connected');
    }, 100);

    // Poll the mock store for log updates
    let lastLineCount = 0;

    intervalRef.current = setInterval(() => {
      const logLines = runLogs.get(runId) || [];
      const run = runs.get(runId);

      if (logLines.length > lastLineCount) {
        const newContent = logLines.slice(lastLineCount).join('\n');
        setLogs((prev) => (prev ? prev + '\n' + newContent : newContent));
        lastLineCount = logLines.length;
      }

      // Check if the run has reached a terminal state
      if (run && ['succeeded', 'failed', 'cancelled'].includes(run.status)) {
        // Give a moment for the last logs to arrive
        setTimeout(() => {
          // Grab any final log lines
          const finalLines = runLogs.get(runId) || [];
          if (finalLines.length > lastLineCount) {
            const remaining = finalLines.slice(lastLineCount).join('\n');
            setLogs((prev) => (prev ? prev + '\n' + remaining : remaining));
          }
          setFinalRunStatus(run.status);
          setStatus('completed');
          onComplete?.(run.status);
          disconnect();
        }, 500);

        // Clear the polling interval immediately to prevent duplicate completion
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    }, 400);
  }, [runId, disconnect, onComplete, onError]);

  useEffect(() => {
    if (runId) {
      connect();
    } else {
      disconnect();
      setLogs('');
      setStatus('idle');
    }

    return () => {
      disconnect();
    };
  }, [runId, connect, disconnect]);

  return {
    logs,
    status,
    finalRunStatus,
    error,
    connect,
    disconnect,
  };
}
