import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./app.css";
import { installBatchedResizeObserver, installResizeObserverErrorGuard } from "./ui/foundry/resizeObserver";

installBatchedResizeObserver();
installResizeObserverErrorGuard();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
