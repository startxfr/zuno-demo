import * as React from "react";
import {
  Dropdown,
  DropdownItem,
  DropdownList,
  MenuToggle,
  type MenuToggleElement,
  TextInput,
} from "@patternfly/react-core";
import {
  BanIcon,
  CloneIcon,
  EllipsisVIcon,
  GripVerticalIcon,
  OutlinedStarIcon,
  PencilAltIcon,
  StarIcon,
  TrashIcon,
} from "@patternfly/react-icons";
import { type Conversation } from "./conversations";
import { can } from "./projects";

// ADR-0515's conversation row, extracted verbatim from ConversationList.tsx
// by WP-089 so ADR-0527's two sidebar blocks render the SAME row rather than
// two implementations that drift. Layout is unchanged: drag handle, star,
// title (or inline rename input), kebab.
//
// What WP-089 adds is capability gating. A row can now belong to a colleague
// in a shared project, so each kebab action is enabled from the caller's
// effective role (`conversation.role`) rather than assumed - matching the
// server, which refuses the same actions with a 404/403 regardless.
export interface ConversationRowProps {
  conversation: Conversation;
  isActive: boolean;
  dragEnabled: boolean;
  isDragged: boolean;
  isRenaming: boolean;
  renameValue: string;
  isCloning: boolean;
  onRenameValueChange: (value: string) => void;
  onCommitRename: () => void;
  onCancelRename: () => void;
  onStartRename: () => void;
  onOpen: () => void;
  onToggleStar: () => void;
  onClone: () => void;
  onDelete: () => void;
  onHardDelete: () => void;
  onDragStart: () => void;
  onDrop: () => void;
  // Indents rows nested under a project, so the two blocks stay visually
  // distinguishable without changing the row itself.
  indent?: boolean;
}

export function ConversationRow({
  conversation: c,
  isActive,
  dragEnabled,
  isDragged,
  isRenaming,
  renameValue,
  isCloning,
  onRenameValueChange,
  onCommitRename,
  onCancelRename,
  onStartRename,
  onOpen,
  onToggleStar,
  onClone,
  onDelete,
  onHardDelete,
  onDragStart,
  onDrop,
  indent = false,
}: ConversationRowProps): React.ReactElement {
  const [kebabOpen, setKebabOpen] = React.useState(false);
  const renameInputRef = React.useRef<HTMLInputElement | null>(null);
  const label = c.title || "Untitled conversation";

  React.useEffect(() => {
    if (isRenaming) {
      renameInputRef.current?.focus();
    }
  }, [isRenaming]);

  // ADR-0527 clause 4's rights table, mirrored for the UI only - the server
  // enforces the same rules and is the authority.
  const canRename = can(c.role, "write");
  const canClone = can(c.role, "clone");
  const canDelete = can(c.role, "admin");

  return (
    <div
      draggable={dragEnabled}
      onDragStart={() => dragEnabled && onDragStart()}
      onDragOver={(e) => {
        if (dragEnabled) {
          e.preventDefault();
        }
      }}
      onDrop={(e) => {
        if (!dragEnabled) {
          return;
        }
        e.preventDefault();
        onDrop();
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.375rem",
        padding: "0.5rem",
        marginLeft: indent ? "1rem" : undefined,
        borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
        opacity: isDragged ? 0.5 : 1,
        background: isActive
          ? "var(--pf-t--global--background--color--secondary--default)"
          : undefined,
      }}
    >
      {dragEnabled && (
        <span
          aria-hidden="true"
          style={{ cursor: "grab", display: "flex", color: "var(--pf-t--global--icon--color--subtle)" }}
        >
          <GripVerticalIcon />
        </span>
      )}
      {c.starred && (
        <span
          aria-label="Starred"
          style={{ display: "flex", color: "var(--pf-t--global--icon--color--favorite--default)" }}
        >
          <StarIcon />
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        {isRenaming ? (
          <TextInput
            ref={renameInputRef}
            aria-label="Rename conversation"
            value={renameValue}
            onChange={(_e, value) => onRenameValueChange(value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onCommitRename();
              if (e.key === "Escape") onCancelRename();
            }}
            onBlur={onCommitRename}
          />
        ) : (
          <button
            type="button"
            onClick={onOpen}
            title={label}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              color: "var(--pf-t--global--text--color--regular)",
            }}
          >
            {label}
          </button>
        )}
      </div>
      <Dropdown
        isOpen={kebabOpen}
        onOpenChange={setKebabOpen}
        toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
          <MenuToggle
            ref={toggleRef}
            aria-label={`Actions for ${label}`}
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
            key="rename"
            icon={<PencilAltIcon />}
            isDisabled={!canRename}
            onClick={() => {
              setKebabOpen(false);
              onStartRename();
            }}
          >
            Rename
          </DropdownItem>
          {/* A star is personal: anyone who can read the conversation may
              organize their own view of it (ADR-0527 clause 4). */}
          <DropdownItem
            key="star"
            icon={c.starred ? <OutlinedStarIcon /> : <StarIcon />}
            onClick={() => {
              setKebabOpen(false);
              onToggleStar();
            }}
          >
            {c.starred ? "Unstar" : "Star"}
          </DropdownItem>
          <DropdownItem
            key="clone"
            icon={<CloneIcon />}
            isDisabled={!canClone || isCloning}
            onClick={() => {
              setKebabOpen(false);
              onClone();
            }}
          >
            {isCloning ? "Cloning…" : "Clone"}
          </DropdownItem>
          <DropdownItem
            key="delete"
            icon={<TrashIcon />}
            isDisabled={!canDelete}
            onClick={() => {
              setKebabOpen(false);
              onDelete();
            }}
          >
            Delete
          </DropdownItem>
          {/* Irreversible, and owner-only server-side (ADR-0527 clause 4:
              project admins get cascade archival, not the right to destroy
              a colleague's history). The UI cannot tell ownership from role
              alone, so it offers the action and lets the server refuse. */}
          <DropdownItem
            key="hard-delete"
            icon={<BanIcon />}
            isDanger
            onClick={() => {
              setKebabOpen(false);
              onHardDelete();
            }}
          >
            Delete permanently
          </DropdownItem>
        </DropdownList>
      </Dropdown>
    </div>
  );
}
