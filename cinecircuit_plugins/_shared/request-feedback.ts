/** Transport errors already published by the host must not create a second alert. */
export function pluginErrorText(error: unknown, fallback: string): string {
  if (requestErrorNotified(error)) return "";
  return error instanceof Error ? error.message : fallback;
}

export function requestErrorNotified(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "notificationHandled" in error && error.notificationHandled);
}

export function pluginErrorFallback(error: unknown, fallback: string): string {
  return requestErrorNotified(error) ? "" : fallback;
}
