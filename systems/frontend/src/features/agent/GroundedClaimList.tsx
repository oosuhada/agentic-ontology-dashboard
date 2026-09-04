import { Button, Card, Tag } from "@blueprintjs/core";
import { CheckCircle2, Link2 } from "lucide-react";
import type { GroundedClaim } from "./types";

interface GroundedClaimListProps {
  claims: GroundedClaim[];
  onSelectEvidence: (evidenceId: string) => void;
}

function confidenceIntent(confidence: GroundedClaim["confidence"]): "success" | "warning" | "none" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "none";
}

export function GroundedClaimList({ claims, onSelectEvidence }: GroundedClaimListProps) {
  if (!claims.length) {
    return <div className="agent-empty-state"><strong>No grounded claims</strong><p>근거가 충분하지 않아 검증된 claim을 만들지 않았습니다.</p></div>;
  }

  return (
    <div className="agent-claim-list" role="list" aria-label="Grounded claims">
      {claims.map((claim) => (
        <Card key={claim.claim_id} elevation={0} role="listitem">
          <header>
            <div>
              <CheckCircle2 size={15} aria-hidden />
              <strong>{claim.claim_id}</strong>
            </div>
            <div>
              <Tag minimal intent={claim.validated ? "success" : "danger"}>
                {claim.validated ? "validated" : "unvalidated"}
              </Tag>
              <Tag minimal intent={confidenceIntent(claim.confidence)}>{claim.confidence}</Tag>
            </div>
          </header>
          <p>{claim.text}</p>
          <div className="agent-claim-evidence-links">
            {claim.evidence_ids.map((evidenceId) => (
              <Button
                key={evidenceId}
                minimal
                small
                icon={<Link2 size={12} />}
                onClick={() => onSelectEvidence(evidenceId)}
              >
                {evidenceId}
              </Button>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
