import * as React from "react";
import { Content, ContentVariants, Flex, FlexItem, PageSection } from "@patternfly/react-core";

const REPO_URL = "https://github.com/startxfr/zuno-demo";

// Shared footer (ADR-0214) rendered as the last PageSection on chat/Chat.tsx,
// portal/Portal.tsx and profile/Profile.tsx - same prop-less, no-context
// pattern as shared/UserMenu.tsx: one implementation, imported verbatim by
// all three pages rather than copied.
export function Footer(): React.ReactElement {
  return (
    <PageSection variant="secondary" hasShadowTop>
      <Flex justifyContent={{ default: "justifyContentCenter" }} gap={{ default: "gapMd" }}>
        <FlexItem>
          <Content component={ContentVariants.a} href="https://startx.fr" target="_blank" rel="noreferrer">
            startx.fr
          </Content>
        </FlexItem>
        <FlexItem>
          <Content component={ContentVariants.a} href={REPO_URL} target="_blank" rel="noreferrer">
            zuno-demo on GitHub
          </Content>
        </FlexItem>
        <FlexItem>
          <Content component={ContentVariants.a} href={`${REPO_URL}/issues/new`} target="_blank" rel="noreferrer">
            Report a bug
          </Content>
        </FlexItem>
      </Flex>
    </PageSection>
  );
}
