import apiClient from './client';

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

export const notificationsApi = {
  /**
   * Get notification preferences for the current user
   */
  getPreferences: async (): Promise<NotificationPreferences> => {
    const response = await apiClient.get<NotificationPreferences>('/notifications/preferences');
    return response.data;
  },

  /**
   * Update notification preferences for the current user
   */
  updatePreferences: async (
    update: NotificationPreferencesUpdateRequest
  ): Promise<NotificationPreferences> => {
    const response = await apiClient.put<NotificationPreferences>(
      '/notifications/preferences',
      update
    );
    return response.data;
  },
};

export default notificationsApi;
