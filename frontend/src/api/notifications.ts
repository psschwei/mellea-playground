import { delay, notificationPrefs, currentUserId } from './mock-store';

export interface NotificationTypePreference {
  enabled: boolean;
  pushEnabled: boolean;
  emailEnabled: boolean;
}

export interface NotificationPreferences {
  userId: string;
  globalEnabled: boolean;
  quietHoursStart: string | null;
  quietHoursEnd: string | null;
  typePreferences: Record<string, NotificationTypePreference>;
}

export interface NotificationPreferencesUpdateRequest {
  globalEnabled?: boolean;
  quietHoursStart?: string | null;
  quietHoursEnd?: string | null;
  typePreferences?: Record<string, NotificationTypePreference>;
}

function getOrCreatePrefs(): NotificationPreferences {
  const userId = currentUserId || 'unknown';
  let prefs = notificationPrefs.get(userId);
  if (!prefs) {
    prefs = {
      userId,
      globalEnabled: true,
      quietHoursStart: null,
      quietHoursEnd: null,
      typePreferences: {
        run_completed: { enabled: true, pushEnabled: true, emailEnabled: false },
        run_failed: { enabled: true, pushEnabled: true, emailEnabled: true },
        share_received: { enabled: true, pushEnabled: true, emailEnabled: false },
      },
    };
    notificationPrefs.set(userId, prefs);
  }
  return prefs;
}

export const notificationsApi = {
  getPreferences: async (): Promise<NotificationPreferences> => {
    await delay();
    return getOrCreatePrefs();
  },

  updatePreferences: async (
    update: NotificationPreferencesUpdateRequest
  ): Promise<NotificationPreferences> => {
    await delay();
    const prefs = getOrCreatePrefs();
    if (update.globalEnabled !== undefined) prefs.globalEnabled = update.globalEnabled;
    if (update.quietHoursStart !== undefined) prefs.quietHoursStart = update.quietHoursStart;
    if (update.quietHoursEnd !== undefined) prefs.quietHoursEnd = update.quietHoursEnd;
    if (update.typePreferences) {
      prefs.typePreferences = { ...prefs.typePreferences, ...update.typePreferences };
    }
    return prefs;
  },
};

export default notificationsApi;
