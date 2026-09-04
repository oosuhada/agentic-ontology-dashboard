import type { ReactNode } from "react";

export interface InspectorTab<T extends string> {
  id: T;
  label: string;
  count?: number;
  icon?: ReactNode;
}

interface InspectorTabsProps<T extends string> {
  tabs: InspectorTab<T>[];
  activeTab: T;
  onChange: (tab: T) => void;
  label?: string;
  className?: string;
}

export function InspectorTabs<T extends string>({
  tabs,
  activeTab,
  onChange,
  label = "Inspector sections",
  className = "",
}: InspectorTabsProps<T>) {
  return (
    <nav className={`fd-inspector-tabs ${className}`.trim()} aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={activeTab === tab.id ? "active" : ""}
          aria-current={activeTab === tab.id ? "page" : undefined}
          onClick={() => onChange(tab.id)}
        >
          {tab.icon}
          <span>{tab.label}</span>
          {tab.count !== undefined ? <small>{tab.count}</small> : null}
        </button>
      ))}
    </nav>
  );
}
