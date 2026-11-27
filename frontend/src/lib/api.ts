export type AqiCategory = "good" | "satisfactory" | "moderate" | "poor" | "very_poor" | "severe";

export type MemberKind = "adult" | "child_u12" | "adult_65p" | "heart_lung" | "outdoor_worker";

export type CommuteMode = "metro" | "bus" | "car" | "scooter" | "auto" | "cycle" | "walk" | "none";

export const HOUSEHOLD_STORAGE_KEY = "purvai.household";

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;
  readonly retryAfterSeconds?: number;

  constructor(
    message: string,
    code: string,
    status: number,
    requestId?: string,
    retryAfterSeconds?: number
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  mode: "local" | "demo";
  ai_available?: boolean;
  database: {
    status: "ok" | "error";
    storage: "persistent" | "temporary";
    schema_revision: string | null;
  };
  time: string;
}

export interface MemberInput {
  kind: MemberKind;
  count: number;
}

export interface LocationPayload {
  label: string;
  lat: number;
  lon: number;
  city?: string | null;
  admin1?: string | null;
  admin2?: string | null;
}

export interface HouseholdSettingsPayload {
  theme: "light" | "dark" | "system";
  commute_mode: CommuteMode;
  ai_enabled: boolean;
  save_chat: boolean;
  reduce_motion: boolean;
}

export interface HouseholdPayload {
  members: MemberInput[];
  location: LocationPayload;
  settings: HouseholdSettingsPayload;
}

export interface HouseholdResponse extends HouseholdPayload {
  id: string;
  mode: "local" | "demo";
  updated_at: string;
}

export interface GeocodingResult {
  label: string;
  lat: number;
  lon: number;
  city: string | null;
  admin1: string | null;
  admin2: string | null;
  nearest_station_km: number | null;
}

export interface VerdictAction {
  action_id: string;
  text: string;
  tag: "rule";
}

export interface Verdict {
  level: AqiCategory;
  household_level: AqiCategory;
  headline: string;
  action_ids: string[];
  actions: VerdictAction[];
}

export interface PollutantReading {
  value: number;
  unit: string;
  sub_index: number;
}

export interface GrapInfo {
  stage: string;
  order_date: string;
  source_url: string;
}

export interface AirQualityResponse {
  aqi: number;
  aqi_is_floor: boolean;
  category: AqiCategory;
  scale: "CPCB_NAQI";
  source_label: "Measured" | "Modelled" | "Estimated";
  source: {
    provider: string;
    station: string | null;
    distance_km: number | null;
  };
  observed_at: string;
  age_minutes: number;
  stale: boolean;
  indicative: boolean;
  served_from_cache: boolean;
  dominant_pollutant: string;
  pollutants: Record<string, PollutantReading>;
  verdict: Verdict;
  grap: GrapInfo | null;
  attribution: string[];
}

export interface ForecastHour {
  time: string;
  aqi: number;
  aqi_is_floor: boolean;
  category: AqiCategory;
  dominant_pollutant: string;
}

export interface AirForecastResponse {
  scale: "CPCB_NAQI";
  source_label: "Modelled";
  indicative: boolean;
  attribution: string[];
  generated_at: string;
  hours: ForecastHour[];
  lowest: {
    time: string;
    aqi: number;
    category: AqiCategory;
  };
}

export interface PlanItem {
  action_id: string;
  text: string;
  why?: string | null;
  tag: "rule" | "ai_wording";
}

export interface PlanPeriod {
  period: "morning" | "afternoon" | "evening" | "night";
  start: string;
  end: string;
  level: AqiCategory;
  aqi: number;
  past: boolean;
  items: PlanItem[];
}

export interface DailyPlanResponse {
  plan_date: string;
  day: "today" | "tomorrow";
  generated_by: "rules" | "gemini" | "groq" | "template";
  generated_at: string;
  source_label: "Measured" | "Modelled" | "Estimated";
  summary?: string | null;
  note?: string | null;
  periods: PlanPeriod[];
}

export interface HomeAirCalcRequest {
  length_m: number;
  width_m: number;
  height_m: number;
  cadr_m3h: number;
}

export interface HomeAirCalcResponse {
  volume_m3: number;
  ach: number;
  target_ach: number;
  meets_target: boolean;
  cadr_needed_m3h: number;
}

export interface HomeAirTip {
  tip_id: string;
  text: string;
  tag?: "rule" | "ai_wording";
}

export interface HomeAirTipsResponse {
  level: AqiCategory;
  generated_by?: "rules" | "gemini" | "groq" | "template";
  tips: HomeAirTip[];
  ventilation_hour: string | null;
}

export type DataCitedKind = "aqi" | "category" | "pollutant" | "forecast" | "grap" | "source";

export interface ChatRecommendation {
  action_id: string;
  title: string;
  why: string;
  tag: "rule" | "ai_wording";
}

export interface ChatResponse {
  schema_version: "1.0";
  verdict_level: AqiCategory;
  answer: string;
  data_cited: DataCitedKind[];
  recommendations: ChatRecommendation[];
  needs_doctor_note: boolean;
  out_of_scope: boolean;
  generated_by: "gemini" | "groq" | "template";
  note?: string | null;
  aqi: number;
  category: AqiCategory;
  source_label: "Measured" | "Modelled" | "Estimated";
  observed_at: string;
  age_minutes: number;
  stale: boolean;
  grap_stage?: string | null;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  generated_by: "user" | "gemini" | "groq" | "template";
  created_at: string;
}

export interface ConversationsResponse {
  messages: ConversationMessage[];
}

const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function getOrCreateDemoHouseholdId(): string {
  try {
    const existing = window.localStorage.getItem(HOUSEHOLD_STORAGE_KEY);
    if (existing && UUID_V4_RE.test(existing)) {
      return existing.toLowerCase();
    }
    const created = window.crypto.randomUUID().toLowerCase();
    window.localStorage.setItem(HOUSEHOLD_STORAGE_KEY, created);
    return created;
  } catch {
    return "00000000-0000-4000-8000-000000000001";
  }
}

const API_BASE = "/api/v1";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const householdId = getOrCreateDemoHouseholdId();
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      "X-Purvai-Household": householdId,
      ...init?.headers,
    },
  });

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const body = parsed as ApiErrorBody | null;
    const code = body?.error?.code ?? `HTTP_${response.status}`;
    const message = body?.error?.message ?? `Request failed with status ${response.status}.`;
    const requestId = body?.error?.request_id;
    const retryRaw = response.headers.get("Retry-After");
    const retryParsed = retryRaw ? Number.parseInt(retryRaw, 10) : Number.NaN;
    const retryAfterSeconds = Number.isFinite(retryParsed) ? retryParsed : undefined;
    throw new ApiError(message, code, response.status, requestId, retryAfterSeconds);
  }

  return parsed as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export function fetchHousehold(): Promise<HouseholdResponse> {
  return apiFetch<HouseholdResponse>("/household");
}

export function saveHousehold(payload: HouseholdPayload): Promise<HouseholdResponse> {
  return apiFetch<HouseholdResponse>("/household", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function searchLocations(query: string): Promise<GeocodingResult[]> {
  return apiFetch<GeocodingResult[]>(`/locations/search?q=${encodeURIComponent(query)}`);
}

export function fetchAir(lat: number, lon: number): Promise<AirQualityResponse> {
  return apiFetch<AirQualityResponse>(`/air?lat=${lat}&lon=${lon}`);
}

export function fetchAirForecast(
  lat: number,
  lon: number,
  hours = 12
): Promise<AirForecastResponse> {
  return apiFetch<AirForecastResponse>(`/air/forecast?lat=${lat}&lon=${lon}&hours=${hours}`);
}

export function buildPlan(day: "today" | "tomorrow", rebuild = false): Promise<DailyPlanResponse> {
  return apiFetch<DailyPlanResponse>("/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day, rebuild }),
  });
}

export function calcHomeAir(payload: HomeAirCalcRequest): Promise<HomeAirCalcResponse> {
  return apiFetch<HomeAirCalcResponse>("/home-air/calc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchHomeAirTips(lat: number, lon: number): Promise<HomeAirTipsResponse> {
  return apiFetch<HomeAirTipsResponse>(`/home-air/tips?lat=${lat}&lon=${lon}`);
}

export function postChat(message: string): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export function fetchConversations(): Promise<ConversationsResponse> {
  return apiFetch<ConversationsResponse>("/conversations");
}

export function deleteConversations(): Promise<void> {
  return apiFetch<unknown>("/conversations", {
    method: "DELETE",
  }).then(() => undefined);
}
