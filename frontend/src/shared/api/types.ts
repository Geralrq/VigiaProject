import type { components } from "./schema";

/** Alias de los tipos generados por openapi-typescript (`npm run gen:api`). No editar a mano. */
type Schemas = components["schemas"];

export type Role = Schemas["Role"];
export type RiskLevel = Schemas["RiskLevel"];
export type AnomalyType = Schemas["AnomalyType"];
export type AnomalyState = Schemas["AnomalyState"];
export type Profile = Schemas["ProfileOut"];
export type Zone = Schemas["ZoneOut"];
export type ZoneReadings = Schemas["ZoneReadingsOut"];
export type AnomalyCollection = Schemas["AnomalyCollection"];
export type AnomalyFeature = Schemas["AnomalyFeature"];
export type AnomalyImages = Schemas["AnomalyImagesOut"];
export type HotspotCollection = Schemas["HotspotCollection"];
export type AlertCollection = Schemas["AlertCollection"];
export type AlertFeature = Schemas["AlertFeature"];
export type ReportCollection = Schemas["ReportCollection"];
export type ReportFeature = Schemas["ReportFeature"];
export type ScanSummary = Schemas["ScanSummaryOut"];
export type ProblemDetails = Schemas["ProblemDetails"];
export type ReportCategory = Schemas["ReportCategory"];
export type Urgency = Schemas["Urgency"];
export type UserSummary = Schemas["UserSummaryOut"];
export type Mission = Schemas["MissionOut"];
export type MissionAnswer = Schemas["MissionAnswer"];
export type MissionAnswerResult = Schemas["MissionAnswerOut"];
export type LeaderboardEntry = Schemas["LeaderboardEntry"];
export type TelegramLink = Schemas["TelegramLinkOut"];
export type ProfileUpdate = Schemas["ProfileUpdateIn"];
export type Inspection = Schemas["InspectionOut"];
export type InspectionState = Schemas["InspectionState"];
export type InspectionFormIn = Schemas["FormIn"];
export type PublicAlert = Schemas["PublicAlertOut"];
