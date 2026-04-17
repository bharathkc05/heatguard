import AsyncStorage from "@react-native-async-storage/async-storage";

const WORKER_ID_KEY = "heatguard.worker_id";
const API_BASE_KEY = "heatguard.api_base";

export async function getStoredWorkerId(): Promise<number | null> {
  const raw = await AsyncStorage.getItem(WORKER_ID_KEY);
  if (!raw) {
    return null;
  }

  const parsed = Number.parseInt(raw, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

export async function setStoredWorkerId(workerId: number): Promise<void> {
  await AsyncStorage.setItem(WORKER_ID_KEY, String(workerId));
}

export async function clearStoredWorkerId(): Promise<void> {
  await AsyncStorage.removeItem(WORKER_ID_KEY);
}

export async function getStoredApiBase(): Promise<string | null> {
  return AsyncStorage.getItem(API_BASE_KEY);
}

export async function setStoredApiBase(baseUrl: string): Promise<void> {
  await AsyncStorage.setItem(API_BASE_KEY, baseUrl);
}
