import "@patternfly/react-core/dist/styles/base.css";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { Profile } from "./Profile";
import { readConfig } from "../shared/config";
import type { ProfileConfig } from "../shared/types";

const config = readConfig<ProfileConfig>();
const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from the page Go rendered");
}

createRoot(container).render(
  <React.StrictMode>
    <Profile config={config} />
  </React.StrictMode>,
);
