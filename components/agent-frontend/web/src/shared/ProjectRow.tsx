import * as React from "react";
import {
  Badge,
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  MenuToggle,
  type MenuToggleElement,
} from "@patternfly/react-core";
import {
  AngleDownIcon,
  AngleRightIcon,
  EllipsisVIcon,
  PencilAltIcon,
  PlusIcon,
  TrashIcon,
} from "@patternfly/react-icons";
import { can, type Project } from "./projects";

// ADR-0527 clause 9: one project row - fold caret, title (opens the project
// dialog), "+" for a new conversation in this project, and a kebab with
// Modify and Delete. Clicking the title opens the dialog in whatever mode
// the caller's role allows: read-only for read/clone, Description editable
// for write, everything plus deletion for admin.
export interface ProjectRowProps {
  project: Project;
  expanded: boolean;
  onToggleExpanded: () => void;
  onOpenDialog: () => void;
  onNewConversation: () => void;
}

export function ProjectRow({
  project,
  expanded,
  onToggleExpanded,
  onOpenDialog,
  onNewConversation,
}: ProjectRowProps): React.ReactElement {
  const [kebabOpen, setKebabOpen] = React.useState(false);
  const isAdmin = can(project.role, "admin");

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.25rem",
        padding: "0.375rem 0.5rem",
        borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
      }}
    >
      <Button
        variant="plain"
        aria-label={expanded ? `Collapse ${project.title}` : `Expand ${project.title}`}
        aria-expanded={expanded}
        onClick={onToggleExpanded}
        style={{ padding: "0 0.125rem" }}
      >
        {expanded ? <AngleDownIcon /> : <AngleRightIcon />}
      </Button>
      <button
        type="button"
        onClick={onOpenDialog}
        title={
          isAdmin
            ? `${project.title} — manage description and access`
            : can(project.role, "write")
              ? `${project.title} — edit description`
              : `${project.title} — read-only`
        }
        style={{
          flex: 1,
          minWidth: 0,
          textAlign: "left",
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontWeight: 600,
          color: "var(--pf-t--global--text--color--regular)",
        }}
      >
        {project.title || "Untitled project"}
      </button>
      {/* ADR-0528: customer vs free is the project's own distinction, so it
          belongs on the row rather than hidden inside the dialog. */}
      {project.is_customer && (
        <Badge isRead title="Customer project — linked to a verified Salesforce opportunity">
          client
        </Badge>
      )}
      <Button
        variant="plain"
        aria-label={`New conversation in ${project.title}`}
        isDisabled={!can(project.role, "write")}
        onClick={onNewConversation}
        style={{ padding: "0 0.25rem" }}
      >
        <PlusIcon />
      </Button>
      <Dropdown
        isOpen={kebabOpen}
        onOpenChange={setKebabOpen}
        toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
          <MenuToggle
            ref={toggleRef}
            aria-label={`Actions for ${project.title}`}
            variant="plain"
            onClick={() => setKebabOpen((open) => !open)}
            isExpanded={kebabOpen}
          >
            <EllipsisVIcon />
          </MenuToggle>
        )}
      >
        <DropdownList>
          <DropdownItem
            key="modify"
            icon={<PencilAltIcon />}
            onClick={() => {
              setKebabOpen(false);
              onOpenDialog();
            }}
          >
            Modify
          </DropdownItem>
          {/* Delete lives in the dialog's footer, which is where the
              confirmation can name the counts ADR-0527 clause 7 requires -
              so this item simply takes the admin there. */}
          <DropdownItem
            key="delete"
            icon={<TrashIcon />}
            isDanger
            isDisabled={!isAdmin}
            onClick={() => {
              setKebabOpen(false);
              onOpenDialog();
            }}
          >
            Delete…
          </DropdownItem>
        </DropdownList>
      </Dropdown>
    </div>
  );
}
