import type { ComponentClass } from "react";
import {
  CalculatorIcon,
  ChartLineIcon,
  ClipboardCheckIcon,
  CodeIcon,
  CompassIcon,
  DraftingCompassIcon,
  HandshakeIcon,
  UsersIcon,
} from "@patternfly/react-icons";
import type { SVGIconProps } from "@patternfly/react-icons/dist/esm/createIcon";

// Maps each agent.okf.md's zuno.ui.icon name to the PatternFly icon it
// names - a new agent's icon needs adding here once. An unrecognized name
// (a typo, or an icon not yet added here) simply renders no icon rather
// than guessing, since these values come from repo-authored OKF content,
// not user input, but there's no guarantee every name here is still a
// live PatternFly icon across a version bump.
export const AGENT_ICONS: Record<string, ComponentClass<SVGIconProps>> = {
  code: CodeIcon,
  compass: CompassIcon,
  "drafting-compass": DraftingCompassIcon,
  handshake: HandshakeIcon,
  calculator: CalculatorIcon,
  "chart-line": ChartLineIcon,
  users: UsersIcon,
  "clipboard-check": ClipboardCheckIcon,
};
