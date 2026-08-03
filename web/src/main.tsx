import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "@xyflow/react/dist/style.css";
import "./styles.css";
import "./workbench.css";
import "./ui/foundry/tokens.css";
import "./ui/foundry/workbenches.css";
import "./ui/foundry/resource-table.css";
import "./features/dashboard/dashboard-editor.css";
import "./features/dashboard/dashboard-runtime.css";
import "./features/dashboard/visualization/visualization.css";
import "./features/analysis/analysis-detail.css";
import "./features/ontology/object-explorer-detail.css";
import "./features/auth/auth-control-plane.css";
import "./features/admin/admin-control-plane.css";
import "./ui/foundry/convergence.css";
import "./ui/foundry/interaction-polish.css";
import { installBatchedResizeObserver, installResizeObserverErrorGuard } from "./ui/foundry/resizeObserver";

installBatchedResizeObserver();
installResizeObserverErrorGuard();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
