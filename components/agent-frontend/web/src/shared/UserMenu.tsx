import * as React from "react";
import {
  Avatar,
  Dropdown,
  DropdownItem,
  DropdownList,
  MenuToggle,
  type MenuToggleElement,
} from "@patternfly/react-core";

export interface UserMenuProps {
  userDisplayName: string;
  profileURL: string;
  logoutURL: string;
}

// Top-right account menu shown on every authenticated page - replaces the
// duplicated "{subject} + Sign out button" toolbar pattern previously in
// both portal/Portal.tsx and chat/Chat.tsx. Plain prop-driven (no
// context/store): this codebase has no client-side router, so each page
// just gets its own copy of these values via its injected zuno-config.
export function UserMenu({ userDisplayName, profileURL, logoutURL }: UserMenuProps): React.ReactElement {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <Dropdown
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      onSelect={() => setIsOpen(false)}
      popperProps={{ position: "right" }}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          variant="plain"
          isExpanded={isOpen}
          onClick={() => setIsOpen((open) => !open)}
          icon={<Avatar alt="" initials={initials(userDisplayName)} />}
        >
          {userDisplayName}
        </MenuToggle>
      )}
    >
      <DropdownList>
        <DropdownItem key="profile" to={profileURL}>
          Profile
        </DropdownItem>
        <DropdownItem key="signout" to={logoutURL}>
          Sign out
        </DropdownItem>
      </DropdownList>
    </Dropdown>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
