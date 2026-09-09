import { MaintenanceCostDecisionPanel } from "../../operations/maintenance/MaintenanceCostDecisionPanel";
import { MaintenanceWorkflowActionPanel } from "../../operations/maintenance/MaintenanceWorkflowActionPanel";
import { OperationalDecisionSupportPanel } from "../../operations/overview/OperationalDecisionSupportPanel";
import type {
  OperationsAsset,
  OperationsDecisionBriefRole,
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsRoleLens,
} from "../../operations/api/operationsContracts";
import type { ReliabilityExperienceKind } from "./roleExperience";


function operationalDecisionBriefRole(
  value: OperationsRoleLens,
): OperationsDecisionBriefRole {
  return value === "process_manager" ? "process_manager" : "process_engineer";
}


export function GovernedWorkflowActions({
  experienceKind,
  projectId,
  workspaceId,
  datasetVersionId,
  event,
  asset,
  detail,
  role,
  currentUserId,
  canManageWorkflow,
  canExecuteFieldWorkflow,
  canMaterializeAgentSummary,
  english,
  onChanged,
}: {
  experienceKind: ReliabilityExperienceKind;
  projectId: string;
  workspaceId: string;
  datasetVersionId: string;
  event: OperationsEvent;
  asset: OperationsAsset;
  detail: OperationsEventDetailModel | null;
  role: OperationsRoleLens;
  currentUserId: string;
  canManageWorkflow: boolean;
  canExecuteFieldWorkflow: boolean;
  canMaterializeAgentSummary: boolean;
  english: boolean;
  onChanged: () => void;
}) {
  const locale = english ? "en-US" : "ko-KR";
  return (
    <>
      <MaintenanceWorkflowActionPanel
        projectId={projectId}
        workspaceId={workspaceId}
        datasetVersionId={datasetVersionId}
        eventId={event.eventId}
        assetId={asset.assetId}
        assetType={asset.assetType}
        role={role}
        currentUserId={currentUserId}
        snapshotBasis={detail?.snapshotBasis ?? null}
        canManage={canManageWorkflow}
        canFieldExecute={canExecuteFieldWorkflow}
        canMaintenanceExecute={experienceKind === "maintenance" && canExecuteFieldWorkflow}
        estimatedDowntimeMinutes={event.estimatedDowntimeMinutes}
        locale={locale}
        onChanged={onChanged}
      />
      <MaintenanceCostDecisionPanel
        projectId={projectId}
        workspaceId={workspaceId}
        eventId={event.eventId}
        guidance={detail?.inspectionTargets.find((item) => item.inspectionGuidance)?.inspectionGuidance ?? null}
        locale={locale}
        onChanged={onChanged}
      />
      <OperationalDecisionSupportPanel
        assetId={asset.assetId}
        projectId={projectId}
        workspaceId={workspaceId}
        evidenceSnapshotId={detail?.snapshotBasis?.artifactId ?? null}
        decisionAsOf={event.observedAt}
        riskStatus={event.status}
        role={operationalDecisionBriefRole(role)}
        canMaterialize={canMaterializeAgentSummary}
        locale={locale}
      />
    </>
  );
}
