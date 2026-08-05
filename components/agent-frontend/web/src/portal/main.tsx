import "@patternfly/react-core/dist/styles/base.css";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { Portal } from "./Portal";
import { readConfig } from "../shared/config";
import type { PortalConfig } from "../shared/types";

const config = readConfig<PortalConfig>();
const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from the page Go rendered");
}

createRoot(container).render(
  <React.StrictMode>
    <Portal config={config} />
  </React.StrictMode>,
);
