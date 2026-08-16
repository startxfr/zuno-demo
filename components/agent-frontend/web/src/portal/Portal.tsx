import * as React from "react";
import {
  Button,
  Content,
  ContentVariants,
  EmptyState,
  EmptyStateBody,
  ExpandableSection,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadMain,
  Page,
  PageSection,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from "@patternfly/react-core";
import { Gallery } from "@patternfly/react-core";
import type { PortalConfig } from "../shared/types";
import { TileCard } from "../shared/TileCard";
import { UserMenu } from "../shared/UserMenu";

// Renders the agent portal (one tile per agent, ADR-0044) from the config
// components/agent-frontend/internal/portal/portal.go injects. Tile
// access-gating logic itself (Clickable/Authorized/Status) is unchanged
// from the pre-ADR-0044 Go template - it's still decided server-side from
// the signed-in session's JWT groups, this component only renders it.
export function Portal({ config }: { config: PortalConfig }): React.ReactElement {
  const [otherExpanded, setOtherExpanded] = React.useState(false);

  const myTiles = config.tiles.filter((t) => t.authorized);
  const otherTiles = config.tiles.filter((t) => !t.authorized);

  return (
    <Page
      masthead={
        <Masthead>
          <MastheadMain>
            <MastheadBrand>
              <Content component={ContentVariants.h1}>Zuno Agent Portal</Content>
            </MastheadBrand>
          </MastheadMain>
          <MastheadContent>
            <Toolbar>
              <ToolbarContent>
                {config.signedIn ? (
                  <ToolbarItem>
                    <UserMenu
                      userDisplayName={config.userDisplayName}
                      profileURL={config.profileURL}
                      logoutURL={config.logoutURL}
                    />
                  </ToolbarItem>
                ) : (
                  <ToolbarItem>
                    <Button variant="primary" component="a" href={config.loginURL}>
                      Sign in
                    </Button>
                  </ToolbarItem>
                )}
              </ToolbarContent>
            </Toolbar>
          </MastheadContent>
        </Masthead>
      }
    >
      <PageSection>
        <Content component={ContentVariants.h2}>My agents</Content>
        {myTiles.length === 0 ? (
          <EmptyState titleText="No agents available yet" headingLevel="h3">
            <EmptyStateBody>
              {config.signedIn
                ? "None of your groups grant access to an agent yet. Check “Other agents” below."
                : "Sign in to see which agents you're authorized to use."}
            </EmptyStateBody>
          </EmptyState>
        ) : (
          <Gallery hasGutter minWidths={{ default: "220px" }} maxWidths={{ default: "1fr" }}>
            {myTiles.map((tile) => (
              <TileCard key={tile.name} tile={tile} />
            ))}
          </Gallery>
        )}
      </PageSection>
      {otherTiles.length > 0 && (
        <PageSection>
          <ExpandableSection
            toggleText={otherExpanded ? "Hide other agents" : `Show other agents (${otherTiles.length})`}
            isExpanded={otherExpanded}
            onToggle={(_event, expanded) => setOtherExpanded(expanded)}
          >
            <Gallery
              hasGutter
              minWidths={{ default: "220px" }}
              maxWidths={{ default: "1fr" }}
              style={{ marginTop: "1rem" }}
            >
              {otherTiles.map((tile) => (
                <TileCard key={tile.name} tile={tile} />
              ))}
            </Gallery>
          </ExpandableSection>
        </PageSection>
      )}
    </Page>
  );
}
