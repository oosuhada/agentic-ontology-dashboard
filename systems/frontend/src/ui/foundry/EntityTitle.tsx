import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EntityTitleProps {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  subtitle?: string;
  headingLevel?: 1 | 2;
  trailing?: ReactNode;
}

export function EntityTitle({ icon: Icon, eyebrow, title, subtitle, headingLevel = 1, trailing }: EntityTitleProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <div className="fd-entity-title">
      <span className="fd-entity-title__icon" aria-hidden="true"><Icon size={15} /></span>
      <div className="fd-entity-title__text">
        <span className="fd-entity-title__eyebrow">{eyebrow}</span>
        <Heading>{title}</Heading>
        {subtitle ? <span className="fd-entity-title__subtitle">{subtitle}</span> : null}
      </div>
      {trailing}
    </div>
  );
}
