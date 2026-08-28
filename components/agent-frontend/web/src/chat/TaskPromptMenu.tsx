import * as React from "react";
import { Button, Menu, MenuContainer, MenuContent, MenuItem, MenuList } from "@patternfly/react-core";
import type { TaskPrompts } from "../shared/types";

// ADR-0515: the composer's slash menu. Each of this agent's tasks that
// declares zuno.prompt_examples in its OKF bundle (agents/<agent>/tasks/
// <task>.md) becomes a menu entry; hovering it flies out its examples, and
// choosing one drops the text into the message box.
//
// This is a writing aid and nothing else. It does NOT select which task the
// agent runs: agent-runtime takes no task from the request, and the chat route
// always executes primary_task (ADR-0342). The text is inserted unsent, on
// purpose - an example is a starting point the user is meant to edit.
//
// The two-level structure is PatternFly's own (Menu containsFlyout +
// MenuItem flyoutMenu, driven by MenuContainer), not hand-rolled: MenuContainer
// already handles the popper, the outside click, Escape, and arrow-key focus
// across both levels. Rebuilding any of that by hand would mean rebuilding its
// keyboard accessibility too.

export function TaskPromptMenu({
  tasks,
  onPick,
  isDisabled,
}: {
  tasks: TaskPrompts[];
  onPick: (example: string) => void;
  isDisabled?: boolean;
}): React.ReactElement | null {
  const [isOpen, setIsOpen] = React.useState(false);
  const toggleRef = React.useRef<HTMLButtonElement>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);

  // An agent whose tasks declare no examples gets no trigger at all, rather
  // than a button that opens an empty menu.
  if (tasks.length === 0) {
    return null;
  }

  const pick = (example: string) => {
    setIsOpen(false);
    onPick(example);
  };

  const toggle = (
    <Button
      ref={toggleRef}
      variant="plain"
      aria-label="Insert an example prompt"
      title="Insert an example prompt"
      isDisabled={isDisabled}
      onClick={() => setIsOpen((open) => !open)}
    >
      {/* A literal "/" rather than @patternfly/react-icons' SlashIcon: that
          icon is the diagonal stroke used to overlay a "prohibited" state, and
          it reads as a backslash at button size. The character is the
          affordance users already know from command palettes. */}
      <span aria-hidden="true" style={{ fontWeight: "bold", lineHeight: 1 }}>
        /
      </span>
    </Button>
  );

  const menu = (
    <Menu ref={menuRef} containsFlyout onActionClick={() => setIsOpen(false)}>
      <MenuContent>
        <MenuList>
          {tasks.map((task) => (
            <MenuItem
              key={task.name}
              itemId={task.name}
              flyoutMenu={
                <Menu key={`${task.name}-flyout`} className="zuno-prompt-flyout" containsFlyout={false}>
                  <MenuContent>
                    <MenuList>
                      {task.examples.map((example, i) => (
                        <MenuItem key={`${task.name}-${i}`} itemId={`${task.name}-${i}`} onClick={() => pick(example)}>
                          {example}
                        </MenuItem>
                      ))}
                    </MenuList>
                  </MenuContent>
                </Menu>
              }
            >
              {task.title}
            </MenuItem>
          ))}
        </MenuList>
      </MenuContent>
    </Menu>
  );

  return (
    <MenuContainer
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      menu={menu}
      menuRef={menuRef}
      toggle={toggle}
      toggleRef={toggleRef}
      popperProps={{ position: "left", direction: "up" }}
    />
  );
}
