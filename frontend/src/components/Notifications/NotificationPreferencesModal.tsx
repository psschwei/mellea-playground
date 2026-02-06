import { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  VStack,
  HStack,
  Switch,
  FormControl,
  FormLabel,
  Text,
  Divider,
  Box,
  Spinner,
  useToast,
  Input,
  Collapse,
  Badge,
} from '@chakra-ui/react';
import { notificationsApi } from '@/api/notifications';
import type { NotificationPreferences, NotificationTypePreference } from '@/api/notifications';

interface NotificationPreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// Notification type metadata for display
const notificationTypeInfo: Record<string, { label: string; description: string; category: string }> = {
  'run.started': { label: 'Run Started', description: 'When a program run begins', category: 'Runs' },
  'run.completed': { label: 'Run Completed', description: 'When a run finishes successfully', category: 'Runs' },
  'run.failed': { label: 'Run Failed', description: 'When a run fails with an error', category: 'Runs' },
  'asset.shared': { label: 'Asset Shared', description: 'When someone shares an asset with you', category: 'Sharing' },
  'asset.access_revoked': { label: 'Access Revoked', description: 'When access to a shared asset is revoked', category: 'Sharing' },
  'system.announcement': { label: 'Announcements', description: 'System-wide announcements', category: 'System' },
  'system.maintenance': { label: 'Maintenance', description: 'Scheduled maintenance notifications', category: 'System' },
  'comment.added': { label: 'New Comment', description: 'When someone comments on your assets', category: 'Collaboration' },
  'mention': { label: 'Mentions', description: 'When someone mentions you', category: 'Collaboration' },
};

// Group notification types by category
const categorizedTypes = Object.entries(notificationTypeInfo).reduce(
  (acc, [type, info]) => {
    if (!acc[info.category]) {
      acc[info.category] = [];
    }
    acc[info.category].push({ type, ...info });
    return acc;
  },
  {} as Record<string, Array<{ type: string; label: string; description: string }>>
);

export function NotificationPreferencesModal({ isOpen, onClose }: NotificationPreferencesModalProps) {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);

  const loadPreferences = useCallback(async () => {
    setLoading(true);
    try {
      const prefs = await notificationsApi.getPreferences();
      setPreferences(prefs);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load preferences';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (isOpen) {
      loadPreferences();
    }
  }, [isOpen, loadPreferences]);

  const handleGlobalToggle = (enabled: boolean) => {
    if (preferences) {
      setPreferences({ ...preferences, globalEnabled: enabled });
    }
  };

  const handleTypeToggle = (type: string, field: keyof NotificationTypePreference, value: boolean) => {
    if (!preferences) return;

    const currentPref = preferences.typePreferences[type] || {
      enabled: true,
      pushEnabled: true,
      emailEnabled: false,
    };

    setPreferences({
      ...preferences,
      typePreferences: {
        ...preferences.typePreferences,
        [type]: {
          ...currentPref,
          [field]: value,
        },
      },
    });
  };

  const handleQuietHoursChange = (field: 'quietHoursStart' | 'quietHoursEnd', value: string) => {
    if (preferences) {
      setPreferences({ ...preferences, [field]: value || null });
    }
  };

  const handleSave = async () => {
    if (!preferences) return;

    setSaving(true);
    try {
      await notificationsApi.updatePreferences({
        globalEnabled: preferences.globalEnabled,
        quietHoursStart: preferences.quietHoursStart,
        quietHoursEnd: preferences.quietHoursEnd,
        typePreferences: preferences.typePreferences,
      });
      toast({
        title: 'Preferences saved',
        status: 'success',
        duration: 3000,
      });
      onClose();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save preferences';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  const getTypePref = (type: string): NotificationTypePreference => {
    return preferences?.typePreferences[type] || {
      enabled: true,
      pushEnabled: true,
      emailEnabled: false,
    };
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg" scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Notification Preferences</ModalHeader>
        <ModalCloseButton />

        <ModalBody>
          {loading ? (
            <Box textAlign="center" py={8}>
              <Spinner size="lg" />
              <Text mt={4} color="gray.500">Loading preferences...</Text>
            </Box>
          ) : preferences ? (
            <VStack spacing={6} align="stretch">
              {/* Global toggle */}
              <FormControl display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <FormLabel mb={0}>Enable Notifications</FormLabel>
                  <Text fontSize="sm" color="gray.500">
                    Master switch for all notifications
                  </Text>
                </Box>
                <Switch
                  isChecked={preferences.globalEnabled}
                  onChange={(e) => handleGlobalToggle(e.target.checked)}
                  colorScheme="blue"
                  size="lg"
                />
              </FormControl>

              <Collapse in={preferences.globalEnabled} animateOpacity>
                <VStack spacing={6} align="stretch">
                  <Divider />

                  {/* Quiet hours */}
                  <Box>
                    <Text fontWeight="medium" mb={2}>Quiet Hours</Text>
                    <Text fontSize="sm" color="gray.500" mb={3}>
                      Pause push notifications during these hours
                    </Text>
                    <HStack spacing={4}>
                      <FormControl>
                        <FormLabel fontSize="sm">Start</FormLabel>
                        <Input
                          type="time"
                          size="sm"
                          value={preferences.quietHoursStart || ''}
                          onChange={(e) => handleQuietHoursChange('quietHoursStart', e.target.value)}
                        />
                      </FormControl>
                      <FormControl>
                        <FormLabel fontSize="sm">End</FormLabel>
                        <Input
                          type="time"
                          size="sm"
                          value={preferences.quietHoursEnd || ''}
                          onChange={(e) => handleQuietHoursChange('quietHoursEnd', e.target.value)}
                        />
                      </FormControl>
                    </HStack>
                  </Box>

                  <Divider />

                  {/* Per-type settings */}
                  {Object.entries(categorizedTypes).map(([category, types]) => (
                    <Box key={category}>
                      <HStack mb={3}>
                        <Text fontWeight="medium">{category}</Text>
                        <Badge colorScheme="gray" fontSize="xs">{types.length}</Badge>
                      </HStack>
                      <VStack spacing={3} align="stretch" pl={2}>
                        {types.map(({ type, label, description }) => {
                          const pref = getTypePref(type);
                          return (
                            <Box
                              key={type}
                              p={3}
                              borderWidth={1}
                              borderRadius="md"
                              borderColor="gray.200"
                              bg={pref.enabled ? 'white' : 'gray.50'}
                            >
                              <HStack justify="space-between" mb={2}>
                                <Box>
                                  <Text fontWeight="medium" fontSize="sm">{label}</Text>
                                  <Text fontSize="xs" color="gray.500">{description}</Text>
                                </Box>
                                <Switch
                                  isChecked={pref.enabled}
                                  onChange={(e) => handleTypeToggle(type, 'enabled', e.target.checked)}
                                  colorScheme="blue"
                                  size="sm"
                                />
                              </HStack>
                              <Collapse in={pref.enabled} animateOpacity>
                                <HStack spacing={6} mt={2} pt={2} borderTopWidth={1} borderColor="gray.100">
                                  <FormControl display="flex" alignItems="center">
                                    <FormLabel fontSize="xs" mb={0} mr={2}>Push</FormLabel>
                                    <Switch
                                      isChecked={pref.pushEnabled}
                                      onChange={(e) => handleTypeToggle(type, 'pushEnabled', e.target.checked)}
                                      colorScheme="green"
                                      size="sm"
                                    />
                                  </FormControl>
                                  <FormControl display="flex" alignItems="center">
                                    <FormLabel fontSize="xs" mb={0} mr={2}>Email</FormLabel>
                                    <Switch
                                      isChecked={pref.emailEnabled}
                                      onChange={(e) => handleTypeToggle(type, 'emailEnabled', e.target.checked)}
                                      colorScheme="purple"
                                      size="sm"
                                    />
                                  </FormControl>
                                </HStack>
                              </Collapse>
                            </Box>
                          );
                        })}
                      </VStack>
                    </Box>
                  ))}
                </VStack>
              </Collapse>
            </VStack>
          ) : (
            <Text color="gray.500" textAlign="center" py={4}>
              Failed to load preferences
            </Text>
          )}
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            Cancel
          </Button>
          <Button
            colorScheme="blue"
            onClick={handleSave}
            isLoading={saving}
            isDisabled={loading || !preferences}
          >
            Save Preferences
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

export default NotificationPreferencesModal;
