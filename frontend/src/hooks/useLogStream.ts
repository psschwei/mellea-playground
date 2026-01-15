import { useState, useEffect, useCallback, useRef } from 'react';
import { getToken } from '@/api/client';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

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
  const eventSourceRef = useRef<EventSource | null>(null);
  const { onComplete, onError } = options;

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!runId) return;

    // Clean up any existing connection
    disconnect();

    // Reset state
    setLogs('');
    setError(null);
    setFinalRunStatus(null);
    setStatus('connecting');

    const token = getToken();
    if (!token) {
      const authError = new Error('Not authenticated');
      setError(authError);
      setStatus('error');
      onError?.(authError);
      return;
    }

    // EventSource doesn't support custom headers, so we pass token as query param
    const url = `${API_BASE_URL}/runs/${runId}/logs/stream?token=${encodeURIComponent(token)}`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setStatus('connected');
    };

    eventSource.addEventListener('log', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as {
          run_id: string;
          content: string;
          timestamp: string | null;
          is_complete: boolean;
        };

        // Append new content to existing logs
        setLogs((prev) => {
          if (!prev) return data.content;
          // If content already includes previous content (full output), replace
          if (data.content.startsWith(prev)) return data.content;
          // Otherwise append with newline
          return prev + '\n' + data.content;
        });
      } catch (e) {
        console.error('Failed to parse log event:', e);
      }
    });

    eventSource.addEventListener('complete', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as { status: string };
        setFinalRunStatus(data.status);
        setStatus('completed');
        onComplete?.(data.status);
      } catch (e) {
        console.error('Failed to parse complete event:', e);
      }
      disconnect();
    });

    eventSource.onerror = () => {
      const streamError = new Error('Log stream connection failed');
      setError(streamError);
      setStatus('error');
      onError?.(streamError);
      disconnect();
    };
  }, [runId, disconnect, onComplete, onError]);

  // Auto-connect when runId changes
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
