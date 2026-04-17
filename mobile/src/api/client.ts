import {
  CheckInRequest,
  HistoryItem,
  MessageResponse,
  PredictRequest,
  PredictResponse,
  RegisterWorkerResponse,
  SOSRequest,
  SOSResponse,
  SupervisorWorker,
  WorkerProfile,
  WorkerSettingsResponse,
} from "../types/api";
import { fetchJson } from "../utils/http";

export class HeatGuardApi {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
  }

  async registerWorker(profile: WorkerProfile): Promise<RegisterWorkerResponse> {
    return fetchJson<RegisterWorkerResponse>(this.url("/worker/register"), {
      method: "POST",
      body: profile,
    });
  }

  async predict(payload: PredictRequest): Promise<PredictResponse> {
    return fetchJson<PredictResponse>(this.url("/predict"), {
      method: "POST",
      body: payload,
    });
  }

  async checkIn(payload: CheckInRequest): Promise<MessageResponse> {
    return fetchJson<MessageResponse>(this.url("/checkin"), {
      method: "POST",
      body: payload,
    });
  }

  async getHistory(workerId: number, limit = 50): Promise<HistoryItem[]> {
    return fetchJson<HistoryItem[]>(
      this.url(`/history/${workerId}`, { limit })
    );
  }

  async getSupervisorWorkers(): Promise<SupervisorWorker[]> {
    return fetchJson<SupervisorWorker[]>(this.url("/supervisor/workers"));
  }

  async sendSOS(payload: SOSRequest): Promise<SOSResponse> {
    return fetchJson<SOSResponse>(this.url("/sos"), {
      method: "POST",
      body: payload,
    });
  }

  async getSettings(workerId: number): Promise<WorkerSettingsResponse> {
    return fetchJson<WorkerSettingsResponse>(this.url(`/settings/${workerId}`));
  }

  async updateSettings(
    workerId: number,
    profile: WorkerProfile
  ): Promise<MessageResponse> {
    return fetchJson<MessageResponse>(this.url(`/settings/${workerId}`), {
      method: "PUT",
      body: profile,
    });
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  private url(
    path: string,
    query?: Record<string, string | number | undefined>
  ): string {
    const basePath = `${this.baseUrl}${path}`;
    if (!query) {
      return basePath;
    }

    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        params.set(key, String(value));
      }
    });

    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}
