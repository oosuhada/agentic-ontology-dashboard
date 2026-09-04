import type {
  OperationsBootstrapModel,
  OperationsDashboardMode,
  OperationsEventDetailModel,
  OperationsReportTab,
  OperationsRoleLens,
  OperationsSensorWindowId,
} from "../api/operationsContracts";
import { OperationsClassicOverviewPage } from "./OperationsClassicOverviewPage";
import { OperationsWorkflowOverviewPage } from "./OperationsWorkflowOverviewPage";
import type { ReliabilityExperienceKind } from "../../predictive-maintenance/workspace/roleExperience";

export function OperationsOverviewPage({
  model,
  role,
  currentUserId,
  experienceKind,
  dashboard,
  selectedAssetId,
  detail,
  detailLoading,
  detailError,
  sensorWindow,
  canMaterializeAgentSummary,
  canManageWorkflow,
  canExecuteFieldWorkflow,
  onOpenAsset,
  onPreviewAsset,
  onOpenEvent,
  onOpenReport,
  onSensorWindowChange,
  onRefresh,
}: {
  model: OperationsBootstrapModel;
  role: OperationsRoleLens;
  currentUserId: string;
  experienceKind: ReliabilityExperienceKind;
  dashboard: OperationsDashboardMode;
  selectedAssetId: string | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  sensorWindow: OperationsSensorWindowId;
  canMaterializeAgentSummary: boolean;
  canManageWorkflow: boolean;
  canExecuteFieldWorkflow: boolean;
  onOpenAsset: (assetId: string, eventId: string | null) => void;
  onPreviewAsset: (assetId: string, eventId: string | null) => void;
  onOpenEvent: (eventId: string, assetId: string) => void;
  onOpenReport: (eventId: string | null, assetId: string | null, reportTab?: OperationsReportTab) => void;
  onSensorWindowChange: (windowId: OperationsSensorWindowId) => void;
  onRefresh: () => void;
}) {
  return (
    <>
      {dashboard === "classic" ? (
        <OperationsClassicOverviewPage
          model={model}
          onOpenAsset={onOpenAsset}
          onOpenEvent={onOpenEvent}
          onOpenReport={(eventId, assetId) => onOpenReport(eventId, assetId)}
          onRefresh={onRefresh}
        />
      ) : (
        <OperationsWorkflowOverviewPage
          model={model}
          role={role}
          currentUserId={currentUserId}
          experienceKind={experienceKind}
          selectedAssetId={selectedAssetId}
          detail={detail}
          detailLoading={detailLoading}
          detailError={detailError}
          sensorWindow={sensorWindow}
          canMaterializeAgentSummary={canMaterializeAgentSummary}
          canManageWorkflow={canManageWorkflow}
          canExecuteFieldWorkflow={canExecuteFieldWorkflow}
          onSensorWindowChange={onSensorWindowChange}
          onPreviewAsset={onPreviewAsset}
          onOpenReport={onOpenReport}
          onRefresh={onRefresh}
        />
      )}
    </>
  );
}
