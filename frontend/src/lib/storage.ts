const TASK_ID_KEY = "videomk_task_id";

export function getTaskId(): string | null {
  try {
    return sessionStorage.getItem(TASK_ID_KEY);
  } catch {
    return null;
  }
}

export function setTaskId(id: string): void {
  try {
    sessionStorage.setItem(TASK_ID_KEY, id);
  } catch {
    /* storage unavailable (private mode) */
  }
}
