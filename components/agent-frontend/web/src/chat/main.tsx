import "@patternfly/react-core/dist/styles/base.css";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { Chat } from "./Chat";
import { readConfig } from "../shared/config";
import type { ChatConfig } from "../shared/types";

const config = readConfig<ChatConfig>();
const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing from the page Go rendered");
}

createRoot(container).render(
  <React.StrictMode>
    <Chat config={config} />
  </React.StrictMode>,
);
