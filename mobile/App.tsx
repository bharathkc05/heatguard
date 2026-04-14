import { StatusBar } from "expo-status-bar";
import Constants from "expo-constants";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from "react-native-svg";

import { HeatGuardApi } from "./src/api/client";
import {
  ActivityLevel,
  CheckInRequest,
  HistoryItem,
  HydrationStatus,
  PredictResponse,
  RiskLabel,
  SupervisorWorker,
  WorkerProfile,
} from "./src/types/api";
import {
  getStoredApiBase,
  getStoredWorkerId,
  setStoredApiBase,
  setStoredWorkerId,
} from "./src/storage/session";
import { ApiError, fetchJson } from "./src/utils/http";
import { FALLBACK_COORDINATES, getCurrentCoordinates } from "./src/utils/location";

type TabKey = "dashboard" | "alerts" | "analytics" | "profile";
type AlertFilter = "today" | "week" | "critical";
type RangeKey = "daily" | "weekly";

const colors = {
  background: "#f7f9fb",
  surface: "#ffffff",
  surfaceSoft: "#f2f4f6",
  text: "#191c1e",
  textMuted: "#5f6572",
  border: "#d8dde4",
  primary: "#0058be",
  primarySoft: "#2170e4",
  success: "#0f9a6a",
  warning: "#d68000",
  danger: "#c22b32",
  info: "#2e9ed7",
};

const envApiBase = process.env["EXPO_PUBLIC_API_BASE_URL"];
const inferredLanApiBase = inferLanApiBaseFromExpoHost();
const platformFallbackApiBase =
  Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000";
const DEFAULT_API_BASE =
  envApiBase && envApiBase.trim().length > 0
    ? envApiBase.trim()
    : inferredLanApiBase ?? platformFallbackApiBase;

const EMPTY_PROFILE: WorkerProfile = {
  name: "Worker",
  age: 30,
  work_type: "construction",
  activity_level: "moderate",
  acclimatized: false,
  supervisor_phone: "",
  fcm_token: "",
};

const HYDRATION_OPTIONS: Array<{ label: string; value: HydrationStatus }> = [
  { label: "Well", value: "well" },
  { label: "Mild", value: "mild" },
  { label: "Low", value: "dehydrated" },
  { label: "Severe", value: "severe" },
];

const ACTIVITY_OPTIONS: Array<{ label: string; value: ActivityLevel }> = [
  { label: "Light", value: "light" },
  { label: "Moderate", value: "moderate" },
  { label: "Heavy", value: "heavy" },
  { label: "Very Heavy", value: "very_heavy" },
];

const WORK_TYPES = ["construction", "agriculture", "warehouse", "maintenance", "utilities"];

export default function App(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>("dashboard");
  const [isBooting, setIsBooting] = useState(true);

  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiBaseInput, setApiBaseInput] = useState(DEFAULT_API_BASE);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);

  const [workerId, setWorkerId] = useState<number | null>(null);
  const [profileForm, setProfileForm] = useState<WorkerProfile>(EMPTY_PROFILE);

  const [checkin, setCheckin] = useState({
    hydration_status: "well" as HydrationStatus,
    activity_level: "moderate" as ActivityLevel,
    hours_worked: 2,
    acclimatized: false,
  });

  const [prediction, setPrediction] = useState<PredictResponse | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [supervisorWorkers, setSupervisorWorkers] = useState<SupervisorWorker[]>([]);
  const [expandedAlertId, setExpandedAlertId] = useState<number | null>(null);
  const [alertFilter, setAlertFilter] = useState<AlertFilter>("today");
  const [analyticsRange, setAnalyticsRange] = useState<RangeKey>("daily");

  const [warningThreshold, setWarningThreshold] = useState(60);
  const [dangerThreshold, setDangerThreshold] = useState(80);
  const [pushEnabled, setPushEnabled] = useState(true);
  const [criticalEnabled, setCriticalEnabled] = useState(true);

  const [isPredicting, setIsPredicting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingSupervisor, setIsLoadingSupervisor] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSendingSOS, setIsSendingSOS] = useState(false);

  const [locationText, setLocationText] = useState(formatCoordinates(FALLBACK_COORDINATES.lat, FALLBACK_COORDINATES.lon));
  const [errorText, setErrorText] = useState<string | null>(null);
  const [noticeText, setNoticeText] = useState<string | null>(null);

  const api = useMemo(() => new HeatGuardApi(apiBase), [apiBase]);

  const bootstrap = useCallback(async () => {
    setIsBooting(true);
    try {
      const [storedWorkerId, storedApiBase] = await Promise.all([
        getStoredWorkerId(),
        getStoredApiBase(),
      ]);

      if (storedApiBase && storedApiBase.trim().length > 0) {
        const normalized = trimUrl(storedApiBase);
        setApiBase(normalized);
        setApiBaseInput(normalized);
      }

      if (storedWorkerId) {
        setWorkerId(storedWorkerId);
      } else {
        setWorkerId(1);
      }
    } finally {
      setIsBooting(false);
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const checkApiHealth = useCallback(
    async (targetBase?: string): Promise<boolean> => {
      const candidate = trimUrl(targetBase ?? apiBase);
      try {
        await fetchJson<Record<string, unknown>>(`${candidate}/openapi.json`, {
          timeoutMs: 5000,
        });
        setApiReachable(true);
        return true;
      } catch {
        setApiReachable(false);
        return false;
      }
    },
    [apiBase]
  );

  const refreshPrediction = useCallback(async () => {
    if (!workerId) {
      setErrorText("Worker ID not set. Configure profile first.");
      return;
    }

    setErrorText(null);
    setNoticeText(null);
    setIsPredicting(true);

    try {
      const coords = await getCurrentCoordinates();
      setLocationText(formatCoordinates(coords.lat, coords.lon));

      const result = await api.predict({
        worker_id: workerId,
        lat: coords.lat,
        lon: coords.lon,
        hydration_status: checkin.hydration_status,
        activity_level: checkin.activity_level,
        hours_worked: checkin.hours_worked,
        acclimatized: checkin.acclimatized,
      });

      setPrediction(result);
      setNoticeText(result.action_message);
      await checkApiHealth();
    } catch (error) {
      setErrorText(toErrorMessage(error));
    } finally {
      setIsPredicting(false);
    }
  }, [api, checkApiHealth, checkin.acclimatized, checkin.activity_level, checkin.hours_worked, checkin.hydration_status, workerId]);

  const loadHistory = useCallback(async () => {
    if (!workerId) {
      return;
    }

    setErrorText(null);
    setIsLoadingHistory(true);
    try {
      const records = await api.getHistory(workerId, 80);
      setHistory(records);
      await checkApiHealth();
    } catch (error) {
      setErrorText(toErrorMessage(error));
    } finally {
      setIsLoadingHistory(false);
    }
  }, [api, checkApiHealth, workerId]);

  const loadSupervisorWorkers = useCallback(async () => {
    setIsLoadingSupervisor(true);
    try {
      const workers = await api.getSupervisorWorkers();
      setSupervisorWorkers(workers);
    } catch {
      // Keep the analytics screen usable even if this feed fails.
      setSupervisorWorkers([]);
    } finally {
      setIsLoadingSupervisor(false);
    }
  }, [api]);

  const loadProfile = useCallback(async () => {
    if (!workerId) {
      return;
    }

    try {
      const settings = await api.getSettings(workerId);
      setProfileForm({
        name: settings.name,
        age: settings.age,
        work_type: settings.work_type,
        activity_level: settings.activity_level,
        acclimatized: settings.acclimatized,
        supervisor_phone: settings.supervisor_phone ?? "",
        fcm_token: settings.fcm_token ?? "",
      });
      setCheckin((previous) => ({
        ...previous,
        activity_level: settings.activity_level,
        acclimatized: settings.acclimatized,
      }));
    } catch {
      // Profile can be loaded later.
    }
  }, [api, workerId]);

  useEffect(() => {
    if (isBooting || !workerId) {
      return;
    }

    void refreshPrediction();
    void loadHistory();
    void loadSupervisorWorkers();
    void loadProfile();
  }, [isBooting, loadHistory, loadProfile, loadSupervisorWorkers, refreshPrediction, workerId]);

  useEffect(() => {
    if (activeTab !== "analytics") {
      return;
    }

    void loadSupervisorWorkers();
  }, [activeTab, loadSupervisorWorkers]);

  const handleSaveApiBase = useCallback(async () => {
    const candidate = trimUrl(apiBaseInput);
    if (!candidate.startsWith("http://") && !candidate.startsWith("https://")) {
      Alert.alert("Invalid API URL", "API URL must start with http:// or https://");
      return;
    }

    await setStoredApiBase(candidate);
    setApiBase(candidate);

    const reachable = await checkApiHealth(candidate);
    if (reachable) {
      setNoticeText("API URL saved and reachable.");
      return;
    }

    const localhostHint =
      candidate.includes("localhost") || candidate.includes("127.0.0.1")
        ? " Use your computer LAN IP for physical devices."
        : "";
    setNoticeText(`API URL saved, but connectivity check failed.${localhostHint}`);
  }, [apiBaseInput, checkApiHealth]);

  const handleSaveProfile = useCallback(async () => {
    const normalized = sanitizeProfile(profileForm);
    setErrorText(null);
    setNoticeText(null);
    setIsSavingProfile(true);

    try {
      let currentWorkerId = workerId;

      if (!currentWorkerId) {
        const registered = await api.registerWorker(normalized);
        currentWorkerId = registered.worker_id;
        await setStoredWorkerId(currentWorkerId);
        setWorkerId(currentWorkerId);
      } else {
        await api.updateSettings(currentWorkerId, normalized);
      }

      setProfileForm(normalized);
      setCheckin((previous) => ({
        ...previous,
        activity_level: normalized.activity_level,
        acclimatized: normalized.acclimatized,
      }));

      setNoticeText("Profile and settings saved.");
      await refreshPrediction();
      await loadHistory();
    } catch (error) {
      setErrorText(toErrorMessage(error));
    } finally {
      setIsSavingProfile(false);
    }
  }, [api, loadHistory, profileForm, refreshPrediction, workerId]);

  const handleCheckin = useCallback(async () => {
    if (!workerId) {
      setErrorText("Set worker profile before check-in.");
      return;
    }

    setErrorText(null);
    setNoticeText(null);

    try {
      const payload: CheckInRequest = {
        worker_id: workerId,
        hydration_status: checkin.hydration_status,
        activity_level: checkin.activity_level,
        hours_worked: checkin.hours_worked,
        acclimatized: checkin.acclimatized,
      };

      await api.checkIn(payload);
      setNoticeText("Check-in saved. Updating risk...");
      await refreshPrediction();
      await loadHistory();
    } catch (error) {
      setErrorText(toErrorMessage(error));
    }
  }, [api, checkin.acclimatized, checkin.activity_level, checkin.hours_worked, checkin.hydration_status, loadHistory, refreshPrediction, workerId]);

  const handleSOS = useCallback(async () => {
    if (!workerId) {
      setErrorText("Worker profile is required before SOS.");
      return;
    }

    setErrorText(null);
    setIsSendingSOS(true);

    try {
      const coords = await getCurrentCoordinates();
      setLocationText(formatCoordinates(coords.lat, coords.lon));

      const result = await api.sendSOS({
        worker_id: workerId,
        lat: coords.lat,
        lon: coords.lon,
        risk_score: prediction?.risk_score,
      });

      setNoticeText(result.message);
    } catch (error) {
      setErrorText(toErrorMessage(error));
    } finally {
      setIsSendingSOS(false);
    }
  }, [api, prediction?.risk_score, workerId]);

  const filteredAlerts = useMemo(() => {
    const now = new Date();

    return history.filter((item) => {
      const timestamp = new Date(item.timestamp);
      if (Number.isNaN(timestamp.valueOf())) {
        return true;
      }

      if (alertFilter === "critical") {
        return item.risk_label === "CRITICAL";
      }

      if (alertFilter === "today") {
        return timestamp.toDateString() === now.toDateString();
      }

      const sevenDaysAgo = new Date(now);
      sevenDaysAgo.setDate(now.getDate() - 7);
      return timestamp >= sevenDaysAgo;
    });
  }, [alertFilter, history]);

  const trendSeries = useMemo(() => {
    const source = [...history]
      .sort((a, b) => new Date(a.timestamp).valueOf() - new Date(b.timestamp).valueOf())
      .slice(-12);

    if (source.length === 0) {
      return {
        risk: [35, 42, 37, 48, 44, 52, 60],
        heart: [84, 90, 88, 97, 102, 98, 94],
        hydration: [82, 80, 78, 76, 73, 72, 70],
      };
    }

    return {
      risk: source.map((item) => item.risk_score),
      heart: source.map((item) => clampNumber(72 + item.risk_score * 0.7, 60, 165)),
      hydration: source.map((item) => clampNumber(96 - item.risk_score * 0.5, 40, 100)),
    };
  }, [history]);

  if (isBooting) {
    return (
      <SafeAreaView style={styles.centerScreen}>
        <StatusBar style="dark" />
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Loading HeatGuard...</Text>
      </SafeAreaView>
    );
  }

  const riskLabel = prediction?.risk_label ?? "MODERATE";
  const riskScore = prediction?.risk_score ?? 0;
  const topBanner = getRiskPalette(riskLabel);
  const hydrationPercent = hydrationPercentFromStatus(checkin.hydration_status);
  const heartRateApprox = Math.round(72 + riskScore * 0.7 + checkin.hours_worked * 2);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="dark" />

      <View style={[styles.riskBanner, { backgroundColor: topBanner.soft }]}> 
        <View style={styles.bannerLeft}>
          <Text style={[styles.bannerDot, { color: topBanner.strong }]}>!</Text>
          <Text style={[styles.bannerText, { color: topBanner.strong }]}>{riskLabel} RISK</Text>
        </View>

        <View style={styles.bannerIndicators}>
          <View style={[styles.chip, { backgroundColor: "#ffffff" }]}> 
            <Text style={styles.chipText}>Wearable Connected</Text>
          </View>
          <View style={[styles.chip, { backgroundColor: apiReachable === false ? "#ffe4e2" : "#e5f7ef" }]}> 
            <Text style={[styles.chipText, { color: apiReachable === false ? colors.danger : colors.success }]}>
              {apiReachable === false ? "Offline" : "Online"}
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.topBar}>
        <View style={styles.profileRow}>
          <View style={styles.avatarPlaceholder}>
            <Text style={styles.avatarText}>{(profileForm.name ?? "W").slice(0, 1).toUpperCase()}</Text>
          </View>
          <Text style={styles.title}>HEATGUARD AI</Text>
        </View>
        <Text style={styles.workerId}>Worker #{workerId ?? "-"}</Text>
      </View>

      {errorText ? <MessageBox text={errorText} tone="error" /> : null}
      {noticeText ? <MessageBox text={noticeText} tone="notice" /> : null}

      <ScrollView contentContainerStyle={styles.content}>
        {activeTab === "dashboard" ? (
          <DashboardScreen
            prediction={prediction}
            riskScore={riskScore}
            riskLabel={riskLabel}
            hydrationPercent={hydrationPercent}
            heartRateApprox={heartRateApprox}
            checkin={checkin}
            locationText={locationText}
            onHydrationChange={(value) => setCheckin((prev) => ({ ...prev, hydration_status: value }))}
            onActivityChange={(value) => setCheckin((prev) => ({ ...prev, activity_level: value }))}
            onHoursDelta={(delta) =>
              setCheckin((prev) => ({ ...prev, hours_worked: clampNumber(prev.hours_worked + delta, 0, 8) }))
            }
            onToggleAcclimatized={() =>
              setCheckin((prev) => ({ ...prev, acclimatized: !prev.acclimatized }))
            }
            onTakeAction={() =>
              Alert.alert("Recommended Action", prediction?.action_message ?? "Hydrate and take a short cool-down break.")
            }
            onPredict={() => void refreshPrediction()}
            onCheckin={() => void handleCheckin()}
            onSOS={() => void handleSOS()}
            isPredicting={isPredicting}
            isSendingSOS={isSendingSOS}
          />
        ) : null}

        {activeTab === "alerts" ? (
          <AlertsScreen
            isLoading={isLoadingHistory}
            records={filteredAlerts}
            filter={alertFilter}
            expandedAlertId={expandedAlertId}
            onFilterChange={setAlertFilter}
            onToggleExpand={(id) => setExpandedAlertId((prev) => (prev === id ? null : id))}
            onReload={() => void loadHistory()}
          />
        ) : null}

        {activeTab === "analytics" ? (
          <AnalyticsScreen
            range={analyticsRange}
            onRangeChange={setAnalyticsRange}
            riskSeries={trendSeries.risk}
            heartSeries={trendSeries.heart}
            hydrationSeries={trendSeries.hydration}
            latestRisk={riskScore}
            latestHydration={hydrationPercent}
            latestHeart={heartRateApprox}
            supervisorWorkers={supervisorWorkers}
            isLoadingSupervisor={isLoadingSupervisor}
            onReloadSupervisor={() => void loadSupervisorWorkers()}
          />
        ) : null}

        {activeTab === "profile" ? (
          <ProfileScreen
            profile={profileForm}
            apiBaseInput={apiBaseInput}
            pushEnabled={pushEnabled}
            criticalEnabled={criticalEnabled}
            warningThreshold={warningThreshold}
            dangerThreshold={dangerThreshold}
            apiReachable={apiReachable}
            onProfileChange={setProfileForm}
            onApiChange={setApiBaseInput}
            onSaveProfile={() => void handleSaveProfile()}
            onSaveApi={() => void handleSaveApiBase()}
            onSyncWearable={() => Alert.alert("Sync", "Wearable sync request queued.")}
            onPushEnabled={setPushEnabled}
            onCriticalEnabled={setCriticalEnabled}
            onWarningThreshold={setWarningThreshold}
            onDangerThreshold={setDangerThreshold}
            isSaving={isSavingProfile}
          />
        ) : null}
      </ScrollView>

      <Pressable style={styles.fab} onPress={() => void handleSOS()} disabled={isSendingSOS}>
        <Text style={styles.fabText}>{isSendingSOS ? "..." : "SOS"}</Text>
      </Pressable>

      <View style={styles.bottomNav}>
        <NavButton label="Dashboard" active={activeTab === "dashboard"} onPress={() => setActiveTab("dashboard")} />
        <NavButton label="Alerts" active={activeTab === "alerts"} onPress={() => setActiveTab("alerts")} />
        <NavButton label="Analytics" active={activeTab === "analytics"} onPress={() => setActiveTab("analytics")} />
        <NavButton label="Profile" active={activeTab === "profile"} onPress={() => setActiveTab("profile")} />
      </View>
    </SafeAreaView>
  );
}

function DashboardScreen(props: {
  prediction: PredictResponse | null;
  riskScore: number;
  riskLabel: RiskLabel;
  hydrationPercent: number;
  heartRateApprox: number;
  locationText: string;
  checkin: {
    hydration_status: HydrationStatus;
    activity_level: ActivityLevel;
    hours_worked: number;
    acclimatized: boolean;
  };
  onHydrationChange: (value: HydrationStatus) => void;
  onActivityChange: (value: ActivityLevel) => void;
  onHoursDelta: (delta: number) => void;
  onToggleAcclimatized: () => void;
  onTakeAction: () => void;
  onPredict: () => void;
  onCheckin: () => void;
  onSOS: () => void;
  isPredicting: boolean;
  isSendingSOS: boolean;
}): React.JSX.Element {
  const ring = useMemo(() => computeGauge(props.riskScore), [props.riskScore]);
  const palette = getRiskPalette(props.riskLabel);

  return (
    <>
      <Card>
        <Text style={styles.sectionTitle}>Heat Stress Indicator</Text>
        <View style={styles.gaugeWrap}>
          <Svg width={250} height={250}>
            <Defs>
              <LinearGradient id="riskGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <Stop offset="0%" stopColor="#12b981" />
                <Stop offset="50%" stopColor="#f59e0b" />
                <Stop offset="100%" stopColor="#dc2626" />
              </LinearGradient>
            </Defs>
            <Circle cx={125} cy={125} r={102} stroke="#e8ebef" strokeWidth={16} fill="transparent" />
            <Circle
              cx={125}
              cy={125}
              r={102}
              stroke="url(#riskGradient)"
              strokeWidth={18}
              fill="transparent"
              strokeLinecap="round"
              strokeDasharray={`${ring.circumference} ${ring.circumference}`}
              strokeDashoffset={ring.offset}
              rotation={-90}
              origin="125, 125"
            />
          </Svg>
          <View style={styles.gaugeCenter}>
            <Text style={styles.gaugeValue}>{Math.round(props.riskScore)}</Text>
            <Text style={styles.gaugeLabel}>HEAT INDEX</Text>
          </View>
        </View>

        <View style={[styles.actionStrip, { backgroundColor: palette.soft }]}> 
          <Text style={[styles.actionStripTitle, { color: palette.strong }]}>{props.riskLabel} STATUS</Text>
          <Text style={styles.actionStripText}>{props.prediction?.time_to_danger ?? "Monitoring"}</Text>
        </View>

        <Text style={styles.explainerText}>
          {props.prediction?.action_message ?? "Live prediction updates when you tap refresh."}
        </Text>

        <ActionButton label="Take Action" onPress={props.onTakeAction} />
      </Card>

      <View style={styles.metricGrid}>
        <MetricCard
          title="Temperature"
          value={`${props.prediction?.tdb.toFixed(1) ?? "--"} C`}
          badge={props.prediction ? "LIVE" : "-"}
          badgeTone="danger"
        />
        <MetricCard title="Humidity" value={`${props.prediction?.rh.toFixed(0) ?? "--"} %`} />
        <MetricCard title="Heart Rate" value={`${props.heartRateApprox} BPM`} />
        <MetricCard title="Hydration" value={`${props.hydrationPercent}%`} badge={hydrationLabel(props.hydrationPercent)} />
      </View>

      <Card>
        <Text style={styles.sectionTitle}>Quick Controls</Text>

        <ControlLabel text="Hydration" />
        <View style={styles.inlineWrap}>
          {HYDRATION_OPTIONS.map((item) => (
            <Chip
              key={item.value}
              label={item.label}
              selected={props.checkin.hydration_status === item.value}
              onPress={() => props.onHydrationChange(item.value)}
            />
          ))}
        </View>

        <ControlLabel text="Activity" />
        <View style={styles.inlineWrap}>
          {ACTIVITY_OPTIONS.map((item) => (
            <Chip
              key={item.value}
              label={item.label}
              selected={props.checkin.activity_level === item.value}
              onPress={() => props.onActivityChange(item.value)}
            />
          ))}
        </View>

        <ControlLabel text="Hours Worked" />
        <View style={styles.stepperRow}>
          <MiniButton label="-0.5" onPress={() => props.onHoursDelta(-0.5)} />
          <Text style={styles.stepperValue}>{props.checkin.hours_worked.toFixed(1)} h</Text>
          <MiniButton label="+0.5" onPress={() => props.onHoursDelta(0.5)} />
        </View>

        <View style={styles.toggleRow}>
          <Text style={styles.toggleLabel}>Acclimatized</Text>
          <Switch value={props.checkin.acclimatized} onValueChange={props.onToggleAcclimatized} />
        </View>

        <View style={styles.quickActionRow}>
          <ActionButton
            label={props.isPredicting ? "Refreshing..." : "Refresh"}
            onPress={props.onPredict}
            variant="ghost"
            compact
          />
          <ActionButton label="Check-In" onPress={props.onCheckin} compact />
          <ActionButton
            label={props.isSendingSOS ? "Sending..." : "SOS"}
            onPress={props.onSOS}
            variant="danger"
            compact
          />
        </View>

        <Text style={styles.locationText}>Location: {props.locationText}</Text>
      </Card>
    </>
  );
}

function AlertsScreen(props: {
  records: HistoryItem[];
  isLoading: boolean;
  filter: AlertFilter;
  expandedAlertId: number | null;
  onFilterChange: (value: AlertFilter) => void;
  onToggleExpand: (id: number) => void;
  onReload: () => void;
}): React.JSX.Element {
  return (
    <>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.sectionTitle}>Alert History</Text>
          <Text style={styles.sectionSubtitle}>Review recent incidents and recommendations</Text>
        </View>
        <Pressable onPress={props.onReload}>
          <Text style={styles.linkText}>Reload</Text>
        </Pressable>
      </View>

      <View style={styles.inlineWrap}>
        <Chip label="Today" selected={props.filter === "today"} onPress={() => props.onFilterChange("today")} />
        <Chip label="Week" selected={props.filter === "week"} onPress={() => props.onFilterChange("week")} />
        <Chip
          label="Critical"
          selected={props.filter === "critical"}
          onPress={() => props.onFilterChange("critical")}
        />
      </View>

      {props.isLoading ? (
        <Card>
          <ActivityIndicator color={colors.primary} />
        </Card>
      ) : null}

      {!props.isLoading && props.records.length === 0 ? (
        <Card>
          <Text style={styles.emptyText}>No alerts for the selected filter.</Text>
        </Card>
      ) : null}

      {!props.isLoading
        ? props.records.map((item) => {
            const isExpanded = props.expandedAlertId === item.id;
            const palette = getRiskPalette(item.risk_label);
            return (
              <Card key={item.id} borderedColor={palette.strong}>
                <Pressable onPress={() => props.onToggleExpand(item.id)}>
                  <View style={styles.rowBetween}>
                    <View>
                      <Text style={[styles.alertTitle, { color: palette.strong }]}>{item.risk_label} ALERT</Text>
                      <Text style={styles.alertHeadline}>Heat Index {Math.round(item.heat_index)}</Text>
                      <Text style={styles.alertMeta}>{formatDateTime(item.timestamp)}</Text>
                    </View>
                    <Text style={styles.expandText}>{isExpanded ? "Hide" : "View"}</Text>
                  </View>
                </Pressable>

                {isExpanded ? (
                  <View style={styles.alertDetails}>
                    <Text style={styles.alertDetailText}>Risk Score: {item.risk_score.toFixed(1)}</Text>
                    <Text style={styles.alertDetailText}>Temperature: {item.tdb.toFixed(1)} C</Text>
                    <Text style={styles.alertDetailText}>Humidity: {item.rh.toFixed(0)} %</Text>
                    <Text style={styles.alertDetailText}>Recommendation: {recommendationForRisk(item.risk_label)}</Text>
                  </View>
                ) : null}
              </Card>
            );
          })
        : null}
    </>
  );
}

function AnalyticsScreen(props: {
  range: RangeKey;
  onRangeChange: (value: RangeKey) => void;
  riskSeries: number[];
  heartSeries: number[];
  hydrationSeries: number[];
  latestRisk: number;
  latestHeart: number;
  latestHydration: number;
  supervisorWorkers: SupervisorWorker[];
  isLoadingSupervisor: boolean;
  onReloadSupervisor: () => void;
}): React.JSX.Element {
  return (
    <>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.sectionTitle}>Analytics</Text>
          <Text style={styles.sectionSubtitle}>Vitals and heat trend intelligence</Text>
        </View>
        <View style={styles.segmentedControl}>
          <SegmentButton label="Daily" active={props.range === "daily"} onPress={() => props.onRangeChange("daily")} />
          <SegmentButton label="Weekly" active={props.range === "weekly"} onPress={() => props.onRangeChange("weekly")} />
        </View>
      </View>

      <Card>
        <Text style={styles.sectionTitle}>Shift Summary</Text>
        <Text style={styles.heroMetric}>Average Risk: {Math.round(average(props.riskSeries))}</Text>
        <Text style={styles.sectionSubtitle}>Heat risk stayed in manageable range for most of the shift.</Text>

        <View style={styles.summaryPills}>
          <SummaryPill label="WBGT" value={`${Math.max(...props.riskSeries).toFixed(0)} idx`} />
          <SummaryPill label="Max HR" value={`${Math.max(...props.heartSeries).toFixed(0)} BPM`} />
          <SummaryPill label="Hydration" value={`${props.latestHydration}%`} />
        </View>
      </Card>

      <ChartCard title="Heat Index Trend" lineColor={colors.primary} values={props.riskSeries} max={100} min={0} />
      <ChartCard title="Heart Rate Trend" lineColor={colors.danger} values={props.heartSeries} max={170} min={55} />
      <ChartCard title="Hydration Trend" lineColor={colors.info} values={props.hydrationSeries} max={100} min={40} />

      <Card>
        <View style={styles.rowBetween}>
          <Text style={styles.sectionTitle}>Supervisor Feed</Text>
          <Pressable onPress={props.onReloadSupervisor}>
            <Text style={styles.linkText}>Reload</Text>
          </Pressable>
        </View>

        {props.isLoadingSupervisor ? <ActivityIndicator color={colors.primary} /> : null}

        {!props.isLoadingSupervisor && props.supervisorWorkers.length === 0 ? (
          <Text style={styles.emptyText}>No supervisor feed entries available.</Text>
        ) : null}

        {!props.isLoadingSupervisor
          ? props.supervisorWorkers.slice(0, 6).map((item) => {
              const palette = getRiskPalette(item.risk_label);
              return (
                <View key={item.worker_id} style={styles.supervisorRow}>
                  <View>
                    <Text style={styles.supervisorName}>{item.name}</Text>
                    <Text style={styles.supervisorMeta}>{formatDateTime(item.last_updated)}</Text>
                  </View>
                  <View style={[styles.badge, { backgroundColor: `${palette.strong}22` }]}>
                    <Text style={[styles.badgeText, { color: palette.strong }]}>
                      {item.risk_label} {Math.round(item.risk_score)}
                    </Text>
                  </View>
                </View>
              );
            })
          : null}
      </Card>

      <View style={styles.metricGrid}>
        <MetricCard title="Current Risk" value={Math.round(props.latestRisk).toString()} />
        <MetricCard title="Current HR" value={`${props.latestHeart} BPM`} />
      </View>
    </>
  );
}

function ProfileScreen(props: {
  profile: WorkerProfile;
  apiBaseInput: string;
  apiReachable: boolean | null;
  pushEnabled: boolean;
  criticalEnabled: boolean;
  warningThreshold: number;
  dangerThreshold: number;
  isSaving: boolean;
  onProfileChange: React.Dispatch<React.SetStateAction<WorkerProfile>>;
  onApiChange: (value: string) => void;
  onSaveProfile: () => void;
  onSaveApi: () => void;
  onSyncWearable: () => void;
  onPushEnabled: (value: boolean) => void;
  onCriticalEnabled: (value: boolean) => void;
  onWarningThreshold: (value: number) => void;
  onDangerThreshold: (value: number) => void;
}): React.JSX.Element {
  return (
    <>
      <Card>
        <Text style={styles.sectionTitle}>Profile</Text>
        <ControlLabel text="Name" />
        <TextInput
          value={props.profile.name ?? ""}
          onChangeText={(value) => props.onProfileChange((prev) => ({ ...prev, name: value }))}
          style={styles.input}
          placeholder="Worker"
          placeholderTextColor={colors.textMuted}
        />

        <ControlLabel text="Age" />
        <TextInput
          value={String(props.profile.age)}
          onChangeText={(value) =>
            props.onProfileChange((prev) => ({
              ...prev,
              age: clampInt(value, prev.age, 18, 60),
            }))
          }
          keyboardType="numeric"
          style={styles.input}
          placeholderTextColor={colors.textMuted}
        />

        <ControlLabel text="Work Type" />
        <View style={styles.inlineWrap}>
          {WORK_TYPES.map((item) => (
            <Chip
              key={item}
              label={item}
              selected={props.profile.work_type === item}
              onPress={() => props.onProfileChange((prev) => ({ ...prev, work_type: item }))}
            />
          ))}
        </View>

        <ControlLabel text="Activity Level" />
        <View style={styles.inlineWrap}>
          {ACTIVITY_OPTIONS.map((item) => (
            <Chip
              key={item.value}
              label={item.label}
              selected={props.profile.activity_level === item.value}
              onPress={() => props.onProfileChange((prev) => ({ ...prev, activity_level: item.value }))}
            />
          ))}
        </View>

        <View style={styles.toggleRow}>
          <Text style={styles.toggleLabel}>Acclimatized</Text>
          <Switch
            value={props.profile.acclimatized}
            onValueChange={() =>
              props.onProfileChange((prev) => ({ ...prev, acclimatized: !prev.acclimatized }))
            }
          />
        </View>

        <ActionButton
          label={props.isSaving ? "Saving..." : "Save Profile"}
          onPress={props.onSaveProfile}
          disabled={props.isSaving}
        />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Notification Preferences</Text>
        <View style={styles.toggleRow}>
          <Text style={styles.toggleLabel}>Push Notifications</Text>
          <Switch value={props.pushEnabled} onValueChange={props.onPushEnabled} />
        </View>
        <View style={styles.toggleRow}>
          <Text style={styles.toggleLabel}>Critical Alerts</Text>
          <Switch value={props.criticalEnabled} onValueChange={props.onCriticalEnabled} />
        </View>
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Threshold Customization</Text>
        <ThresholdRow label="Warning Level" value={props.warningThreshold} onMinus={() => props.onWarningThreshold(clampNumber(props.warningThreshold - 1, 10, 95))} onPlus={() => props.onWarningThreshold(clampNumber(props.warningThreshold + 1, 10, 95))} />
        <ThresholdRow label="Danger Level" value={props.dangerThreshold} onMinus={() => props.onDangerThreshold(clampNumber(props.dangerThreshold - 1, 20, 99))} onPlus={() => props.onDangerThreshold(clampNumber(props.dangerThreshold + 1, 20, 99))} />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Device & Connectivity</Text>
        <ControlLabel text="API Base URL" />
        <TextInput
          value={props.apiBaseInput}
          onChangeText={props.onApiChange}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
          placeholder="http://192.168.x.x:8000"
          placeholderTextColor={colors.textMuted}
        />

        <View style={styles.connectivityRow}>
          <Text style={styles.toggleLabel}>API Status</Text>
          <Text style={[styles.statusValue, { color: props.apiReachable === false ? colors.danger : colors.success }]}>
            {props.apiReachable === false ? "Disconnected" : "Connected"}
          </Text>
        </View>

        <View style={styles.quickActionRow}>
          <ActionButton label="Save API" onPress={props.onSaveApi} variant="ghost" compact />
          <ActionButton label="Sync Wearable" onPress={props.onSyncWearable} compact />
        </View>
      </Card>
    </>
  );
}

function ChartCard(props: {
  title: string;
  values: number[];
  min: number;
  max: number;
  lineColor: string;
}): React.JSX.Element {
  const path = useMemo(() => buildLinePath(props.values, 320, 120, props.min, props.max), [props.max, props.min, props.values]);

  return (
    <Card>
      <Text style={styles.sectionTitle}>{props.title}</Text>
      <View style={styles.chartWrap}>
        <Svg width={320} height={120}>
          <Path d={path} fill="none" stroke={props.lineColor} strokeWidth={3} />
        </Svg>
      </View>
    </Card>
  );
}

function SummaryPill(props: { label: string; value: string }): React.JSX.Element {
  return (
    <View style={styles.summaryPill}>
      <Text style={styles.summaryLabel}>{props.label}</Text>
      <Text style={styles.summaryValue}>{props.value}</Text>
    </View>
  );
}

function ThresholdRow(props: { label: string; value: number; onMinus: () => void; onPlus: () => void }): React.JSX.Element {
  return (
    <View style={styles.thresholdRow}>
      <Text style={styles.toggleLabel}>{props.label}</Text>
      <View style={styles.thresholdControl}>
        <MiniButton label="-" onPress={props.onMinus} />
        <Text style={styles.thresholdValue}>{props.value}</Text>
        <MiniButton label="+" onPress={props.onPlus} />
      </View>
    </View>
  );
}

function MetricCard(props: { title: string; value: string; badge?: string; badgeTone?: "danger" | "warning" | "safe" }): React.JSX.Element {
  const badgeColor =
    props.badgeTone === "danger"
      ? colors.danger
      : props.badgeTone === "warning"
        ? colors.warning
        : colors.success;

  return (
    <View style={styles.metricCard}>
      <View style={styles.rowBetween}>
        <Text style={styles.metricTitle}>{props.title}</Text>
        {props.badge ? (
          <View style={[styles.badge, { backgroundColor: `${badgeColor}22` }]}> 
            <Text style={[styles.badgeText, { color: badgeColor }]}>{props.badge}</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.metricValue}>{props.value}</Text>
    </View>
  );
}

function Card(props: { children: React.ReactNode; borderedColor?: string }): React.JSX.Element {
  return (
    <View
      style={[
        styles.card,
        props.borderedColor
          ? {
              borderLeftWidth: 6,
              borderLeftColor: props.borderedColor,
            }
          : null,
      ]}
    >
      {props.children}
    </View>
  );
}

function ControlLabel(props: { text: string }): React.JSX.Element {
  return <Text style={styles.controlLabel}>{props.text}</Text>;
}

function ActionButton(props: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  compact?: boolean;
  variant?: "primary" | "ghost" | "danger";
}): React.JSX.Element {
  const variant = props.variant ?? "primary";
  return (
    <Pressable
      disabled={props.disabled}
      onPress={props.onPress}
      style={({ pressed }) => [
        styles.actionButton,
        props.compact ? styles.actionCompact : null,
        variant === "ghost" ? styles.actionGhost : null,
        variant === "danger" ? styles.actionDanger : null,
        pressed ? styles.actionPressed : null,
        props.disabled ? { opacity: 0.55 } : null,
      ]}
    >
      <Text
        style={[
          styles.actionText,
          variant === "ghost" ? { color: colors.primary } : null,
          variant === "danger" ? { color: "#ffffff" } : null,
        ]}
      >
        {props.label}
      </Text>
    </Pressable>
  );
}

function MiniButton(props: { label: string; onPress: () => void }): React.JSX.Element {
  return (
    <Pressable style={styles.miniButton} onPress={props.onPress}>
      <Text style={styles.miniButtonText}>{props.label}</Text>
    </Pressable>
  );
}

function Chip(props: { label: string; selected: boolean; onPress: () => void }): React.JSX.Element {
  return (
    <Pressable style={[styles.chipBase, props.selected ? styles.chipSelected : null]} onPress={props.onPress}>
      <Text style={[styles.chipBaseText, props.selected ? styles.chipSelectedText : null]}>{props.label}</Text>
    </Pressable>
  );
}

function SegmentButton(props: { label: string; active: boolean; onPress: () => void }): React.JSX.Element {
  return (
    <Pressable style={[styles.segmentButton, props.active ? styles.segmentActive : null]} onPress={props.onPress}>
      <Text style={[styles.segmentText, props.active ? styles.segmentTextActive : null]}>{props.label}</Text>
    </Pressable>
  );
}

function NavButton(props: { label: string; active: boolean; onPress: () => void }): React.JSX.Element {
  return (
    <Pressable style={[styles.navButton, props.active ? styles.navButtonActive : null]} onPress={props.onPress}>
      <Text style={[styles.navText, props.active ? styles.navTextActive : null]}>{props.label}</Text>
    </Pressable>
  );
}

function MessageBox(props: { text: string; tone: "error" | "notice" }): React.JSX.Element {
  const isError = props.tone === "error";
  return (
    <View
      style={[
        styles.message,
        {
          backgroundColor: isError ? "#ffe9e8" : "#eaf5ff",
          borderColor: isError ? "#ffcbc7" : "#c9e3ff",
        },
      ]}
    >
      <Text style={[styles.messageText, { color: isError ? colors.danger : colors.primary }]}>{props.text}</Text>
    </View>
  );
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function computeGauge(riskScore: number): { circumference: number; offset: number } {
  const radius = 102;
  const circumference = 2 * Math.PI * radius;
  const progress = clampNumber(riskScore, 0, 100) / 100;
  const offset = circumference * (1 - progress);

  return { circumference, offset };
}

function buildLinePath(values: number[], width: number, height: number, min: number, max: number): string {
  if (values.length <= 1) {
    return `M0 ${height / 2} L${width} ${height / 2}`;
  }

  const safeRange = Math.max(1, max - min);
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / safeRange) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Number.parseFloat(value.toFixed(1))));
}

function clampInt(value: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function trimUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function hydrationPercentFromStatus(status: HydrationStatus): number {
  if (status === "well") {
    return 92;
  }
  if (status === "mild") {
    return 78;
  }
  if (status === "dehydrated") {
    return 62;
  }
  return 45;
}

function hydrationLabel(percent: number): string {
  if (percent >= 85) {
    return "GOOD";
  }
  if (percent >= 70) {
    return "FAIR";
  }
  if (percent >= 55) {
    return "LOW";
  }
  return "CRITICAL";
}

function formatCoordinates(lat: number, lon: number): string {
  const latDir = lat >= 0 ? "N" : "S";
  const lonDir = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)} ${latDir}, ${Math.abs(lon).toFixed(4)} ${lonDir}`;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }
  return date.toLocaleString();
}

function getRiskPalette(label: string): { strong: string; soft: string } {
  const normalized = label.toUpperCase();
  if (normalized === "LOW") {
    return { strong: colors.success, soft: "#e5f7ef" };
  }
  if (normalized === "MODERATE") {
    return { strong: colors.warning, soft: "#fff3df" };
  }
  if (normalized === "HIGH") {
    return { strong: "#c36200", soft: "#ffe8cb" };
  }
  return { strong: colors.danger, soft: "#ffe4e2" };
}

function recommendationForRisk(label: RiskLabel): string {
  if (label === "LOW") {
    return "Maintain hydration and continue routine monitoring.";
  }
  if (label === "MODERATE") {
    return "Take a short shade break and hydrate.";
  }
  if (label === "HIGH") {
    return "Stop work for cool-down and notify supervisor.";
  }
  return "Emergency response: move to cool area and trigger medical protocol.";
}

function inferLanApiBaseFromExpoHost(): string | null {
  const constants = Constants as unknown as {
    expoConfig?: { hostUri?: string };
    expoGoConfig?: { debuggerHost?: string };
  };

  const hostUri = constants.expoConfig?.hostUri ?? constants.expoGoConfig?.debuggerHost;
  if (!hostUri) {
    return null;
  }

  const host = hostUri.split(":")[0]?.trim();
  if (!host || host === "localhost" || host === "127.0.0.1") {
    return null;
  }

  return `http://${host}:8000`;
}

function sanitizeProfile(profile: WorkerProfile): WorkerProfile {
  return {
    name: (profile.name ?? "Worker").trim() || "Worker",
    age: clampInt(String(profile.age), 30, 18, 60),
    work_type: profile.work_type.trim() || "construction",
    activity_level: profile.activity_level,
    acclimatized: profile.acclimatized,
    supervisor_phone: (profile.supervisor_phone ?? "").trim() || null,
    fcm_token: (profile.fcm_token ?? "").trim() || null,
  };
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error occurred.";
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centerScreen: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
    gap: 10,
  },
  loadingText: {
    fontSize: 14,
    color: colors.textMuted,
    fontWeight: "700",
  },
  riskBanner: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  bannerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  bannerDot: {
    fontSize: 18,
    fontWeight: "900",
  },
  bannerText: {
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 0.8,
  },
  bannerIndicators: {
    flexDirection: "row",
    gap: 8,
  },
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  chipText: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.textMuted,
  },
  topBar: {
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: "#f9fbfd",
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  profileRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  avatarPlaceholder: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "#dce8fa",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontWeight: "900",
    color: colors.primary,
  },
  title: {
    fontSize: 18,
    fontWeight: "900",
    letterSpacing: 0.6,
    color: colors.primary,
  },
  workerId: {
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: "700",
  },
  content: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 130,
    gap: 12,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 10,
  },
  message: {
    borderWidth: 1,
    marginTop: 8,
    marginHorizontal: 16,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  messageText: {
    fontSize: 12,
    fontWeight: "700",
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "900",
    color: colors.text,
  },
  sectionSubtitle: {
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: "600",
  },
  gaugeWrap: {
    alignSelf: "center",
    width: 250,
    height: 250,
    alignItems: "center",
    justifyContent: "center",
  },
  gaugeCenter: {
    position: "absolute",
    alignItems: "center",
  },
  gaugeValue: {
    fontSize: 52,
    fontWeight: "900",
    color: colors.text,
    letterSpacing: -1,
  },
  gaugeLabel: {
    marginTop: 4,
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "800",
    letterSpacing: 1,
  },
  actionStrip: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  actionStripTitle: {
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 0.6,
  },
  actionStripText: {
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "700",
    marginTop: 2,
  },
  explainerText: {
    fontSize: 13,
    color: colors.textMuted,
    fontWeight: "600",
    lineHeight: 20,
  },
  actionButton: {
    height: 48,
    borderRadius: 999,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  actionCompact: {
    flex: 1,
    height: 42,
  },
  actionGhost: {
    backgroundColor: "#e8f1ff",
  },
  actionDanger: {
    backgroundColor: colors.danger,
  },
  actionText: {
    fontSize: 14,
    fontWeight: "800",
    color: "#ffffff",
  },
  actionPressed: {
    transform: [{ scale: 0.98 }],
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  metricCard: {
    width: "48.5%",
    backgroundColor: colors.surface,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
    gap: 8,
  },
  metricTitle: {
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  metricValue: {
    fontSize: 26,
    color: colors.text,
    fontWeight: "900",
    letterSpacing: -0.4,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
  },
  badgeText: {
    fontSize: 9,
    fontWeight: "900",
  },
  controlLabel: {
    marginTop: 4,
    marginBottom: 4,
    fontSize: 11,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontWeight: "800",
  },
  inlineWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chipBase: {
    backgroundColor: colors.surfaceSoft,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipSelected: {
    backgroundColor: "#dcebff",
    borderColor: colors.primarySoft,
  },
  chipBaseText: {
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  chipSelectedText: {
    color: colors.primary,
  },
  stepperRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 6,
  },
  stepperValue: {
    fontSize: 20,
    fontWeight: "900",
    color: colors.text,
  },
  miniButton: {
    minWidth: 58,
    borderRadius: 12,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 10,
    alignItems: "center",
  },
  miniButtonText: {
    fontSize: 13,
    fontWeight: "800",
    color: colors.primary,
  },
  toggleRow: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  toggleLabel: {
    fontSize: 14,
    color: colors.text,
    fontWeight: "700",
  },
  quickActionRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8,
  },
  locationText: {
    marginTop: 6,
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: "600",
  },
  rowBetween: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  linkText: {
    fontSize: 12,
    fontWeight: "800",
    color: colors.primary,
  },
  emptyText: {
    fontSize: 13,
    color: colors.textMuted,
    fontWeight: "600",
  },
  alertTitle: {
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  alertHeadline: {
    fontSize: 20,
    fontWeight: "900",
    color: colors.text,
    marginTop: 2,
  },
  alertMeta: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
    fontWeight: "600",
  },
  expandText: {
    fontSize: 12,
    color: colors.primary,
    fontWeight: "800",
  },
  alertDetails: {
    marginTop: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 10,
    gap: 4,
  },
  alertDetailText: {
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: "600",
  },
  supervisorRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  supervisorName: {
    fontSize: 14,
    color: colors.text,
    fontWeight: "800",
  },
  supervisorMeta: {
    marginTop: 2,
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "600",
  },
  segmentedControl: {
    backgroundColor: colors.surfaceSoft,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    flexDirection: "row",
    padding: 4,
  },
  segmentButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
  },
  segmentActive: {
    backgroundColor: colors.surface,
  },
  segmentText: {
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: "800",
  },
  segmentTextActive: {
    color: colors.primary,
  },
  heroMetric: {
    fontSize: 32,
    fontWeight: "900",
    color: colors.primary,
    marginTop: 2,
    letterSpacing: -0.7,
  },
  summaryPills: {
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
  },
  summaryPill: {
    flex: 1,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    padding: 10,
  },
  summaryLabel: {
    fontSize: 10,
    color: colors.textMuted,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  summaryValue: {
    fontSize: 14,
    color: colors.text,
    fontWeight: "900",
    marginTop: 3,
  },
  chartWrap: {
    borderRadius: 12,
    overflow: "hidden",
    backgroundColor: "#f8fafc",
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 10,
    alignItems: "center",
  },
  input: {
    height: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSoft,
    color: colors.text,
    paddingHorizontal: 12,
    fontSize: 14,
  },
  thresholdRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 8,
  },
  thresholdControl: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  thresholdValue: {
    minWidth: 36,
    textAlign: "center",
    fontSize: 16,
    fontWeight: "900",
    color: colors.text,
  },
  connectivityRow: {
    marginTop: 6,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  statusValue: {
    fontSize: 13,
    fontWeight: "900",
  },
  fab: {
    position: "absolute",
    right: 18,
    bottom: 94,
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.danger,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: colors.danger,
    shadowOpacity: 0.35,
    shadowOffset: { width: 0, height: 10 },
    shadowRadius: 16,
    elevation: 6,
  },
  fabText: {
    color: "#ffffff",
    fontSize: 18,
    fontWeight: "900",
    letterSpacing: 0.6,
  },
  bottomNav: {
    position: "absolute",
    left: 10,
    right: 10,
    bottom: 10,
    flexDirection: "row",
    gap: 6,
    borderRadius: 24,
    backgroundColor: "#ffffffee",
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  navButton: {
    flex: 1,
    borderRadius: 16,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  navButtonActive: {
    backgroundColor: "#dcebff",
  },
  navText: {
    fontSize: 10,
    fontWeight: "800",
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  navTextActive: {
    color: colors.primary,
  },
});
