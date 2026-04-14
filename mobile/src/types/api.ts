export type HydrationStatus = "well" | "mild" | "dehydrated" | "severe";
export type ActivityLevel = "light" | "moderate" | "heavy" | "very_heavy";
export type RiskLabel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export interface WorkerProfile {
  name?: string;
  age: number;
  work_type: string;
  activity_level: ActivityLevel;
  acclimatized: boolean;
  supervisor_phone?: string | null;
  fcm_token?: string | null;
}

export interface RegisterWorkerResponse {
  worker_id: number;
  message: string;
}

export interface PredictRequest {
  lat: number;
  lon: number;
  worker_id: number;
  hours_worked: number;
  hydration_status: HydrationStatus;
  activity_level: ActivityLevel;
  acclimatized: boolean;
  hr_bpm?: number | null;
}

export interface PredictResponse {
  risk_score: number;
  risk_label: RiskLabel;
  risk_label_int: number;
  alert_color: "green" | "yellow" | "orange" | "red";
  action_message: string;
  time_to_danger: string;
  notify_supervisor: boolean;
  trigger_emergency: boolean;
  tdb: number;
  rh: number;
  wbgt: number;
  climate_zone: string;
  timestamp: string;
}

export interface CheckInRequest {
  worker_id: number;
  hydration_status: HydrationStatus;
  activity_level: ActivityLevel;
  hours_worked: number;
  acclimatized: boolean;
}

export interface MessageResponse {
  message: string;
}

export interface HistoryItem {
  id: number;
  worker_id: number;
  tdb: number;
  rh: number;
  v: number;
  wbgt: number;
  heat_index: number;
  hours_worked: number;
  hydration_status: string;
  risk_score: number;
  risk_label: RiskLabel;
  risk_label_int: number;
  lat: number | null;
  lon: number | null;
  climate_zone: string;
  timestamp: string;
}

export interface SupervisorWorker {
  worker_id: number;
  name: string;
  risk_label: RiskLabel;
  risk_score: number;
  last_updated: string;
  lat: number | null;
  lon: number | null;
}

export interface SOSRequest {
  worker_id: number;
  lat: number;
  lon: number;
  risk_score?: number;
}

export interface SOSResponse {
  message: string;
  supervisor_phone?: string | null;
  location: {
    lat: number;
    lon: number;
  };
}

export interface WorkerSettingsResponse {
  id: number;
  name: string;
  age: number;
  work_type: string;
  activity_level: ActivityLevel;
  acclimatized: boolean;
  supervisor_phone?: string | null;
  fcm_token?: string | null;
  created_at: string;
}
