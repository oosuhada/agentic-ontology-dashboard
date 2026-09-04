export type OperationalFocusTone = "critical" | "warning" | "attention" | "normal" | "neutral";

export interface OperationalFocusAssetViewModel {
  id: string;
  name: string;
  contextLabel?: string | null;
}

export interface OperationalFocusRiskViewModel {
  label: string;
  valueLabel?: string | null;
  previousValueLabel?: string | null;
}

export interface OperationalFocusSituationViewModel {
  statusLabel: string;
  headline?: string | null;
  detail?: string | null;
  tone?: OperationalFocusTone;
  risk?: OperationalFocusRiskViewModel | null;
  operationalImpact?: string | null;
}

export interface OperationalFocusEvidenceViewModel {
  id: string;
  label: string;
  value?: string | null;
  detail?: string | null;
}

export interface OperationalFocusLifecycleViewModel {
  currentLabel: string;
  nextLabel?: string | null;
  ownerLabel?: string | null;
}

export interface OperationalFocusPrimaryActionViewModel {
  label: string;
  ownerLabel?: string | null;
  disabled?: boolean;
  disabledReason?: string | null;
}

export interface OperationalFocusFreshnessViewModel {
  observedAt?: string | null;
  label?: string | null;
  sourceLabel?: string | null;
}

export interface OperationalFocusViewModel {
  asset: OperationalFocusAssetViewModel;
  situation: OperationalFocusSituationViewModel;
  evidence: OperationalFocusEvidenceViewModel[];
  lifecycle: OperationalFocusLifecycleViewModel;
  primaryAction?: OperationalFocusPrimaryActionViewModel | null;
  freshness?: OperationalFocusFreshnessViewModel | null;
}
