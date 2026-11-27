import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  OctagonAlert,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

import type { AqiCategory } from "../lib/api";

export const CATEGORY_LABELS: Record<AqiCategory, string> = {
  good: "Good",
  satisfactory: "Satisfactory",
  moderate: "Moderate",
  poor: "Poor",
  very_poor: "Very Poor",
  severe: "Severe",
};

const CATEGORY_DOT_CLASS: Record<AqiCategory, string> = {
  good: "bg-aqi-good",
  satisfactory: "bg-aqi-satisfactory",
  moderate: "bg-aqi-moderate",
  poor: "bg-aqi-poor",
  very_poor: "bg-aqi-very-poor",
  severe: "bg-aqi-severe",
};

const CATEGORY_ICON: Record<AqiCategory, LucideIcon> = {
  good: CheckCircle2,
  satisfactory: CheckCircle2,
  moderate: CircleAlert,
  poor: AlertTriangle,
  very_poor: ShieldAlert,
  severe: OctagonAlert,
};

interface AqiCategoryChipProps {
  category: AqiCategory;
  showBar?: boolean;
}

export function AqiCategoryChip({ category, showBar = false }: AqiCategoryChipProps) {
  const Icon = CATEGORY_ICON[category];
  const label = CATEGORY_LABELS[category];
  const colorClass = CATEGORY_DOT_CLASS[category];

  return (
    <div className="inline-flex flex-col gap-1.5">
      <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-sm font-medium text-text">
        <span className={`h-2.5 w-2.5 rounded-full ${colorClass}`} aria-hidden="true" />
        <Icon size={16} aria-hidden="true" />
        <span>{label}</span>
      </span>
      {showBar && <div className={`h-1 w-full rounded-full ${colorClass}`} aria-hidden="true" />}
    </div>
  );
}
