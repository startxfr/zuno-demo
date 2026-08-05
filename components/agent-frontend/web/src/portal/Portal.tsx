import * as React from "react";
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardTitle,
  Content,
  ContentVariants,
  Label,
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
import type { PortalConfig, PortalTile } from "../shared/types";

// Renders the agent portal (one tile per agent, ADR-0044) from the config
// components/agent-frontend/internal/portal/portal.go injects. Tile
// access-gating logic itself (Clickable/Authorized/Status) is unchanged
// from the pre-ADR-0044 Go template - it's still decided server-side from
// the signed-in session's JWT groups, this component only renders it.
export function Portal({ config }: { config: PortalConfig }): React.ReactElement {
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
                  <>
                    <ToolbarItem>
                      <Content component={ContentVariants.small}>{config.subject}</Content>
                    </ToolbarItem>
                    <ToolbarItem>
                      <Button variant="link" component="a" href={config.logoutURL}>
                        Sign out
                      </Button>
                    </ToolbarItem>
                  </>
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
        <Gallery hasGutter minWidths={{ default: "220px" }} maxWidths={{ default: "1fr" }}>
          {config.tiles.map((tile) => (
            <TileCard key={tile.name} tile={tile} />
          ))}
        </Gallery>
      </PageSection>
    </Page>
  );
}

function TileCard({ tile }: { tile: PortalTile }): React.ReactElement {
  return (
    <Card isFullHeight style={{ borderTop: `4px solid ${tile.color || "var(--pf-t--global--color--brand--default)"}` }}>
      <CardTitle>{tile.displayName}</CardTitle>
      <CardBody>
        <Content component={ContentVariants.p}>{tile.tileDescription}</Content>
      </CardBody>
      <CardFooter>
        {tile.status === "placeholder" ? (
          <Label color="grey">Coming soon</Label>
        ) : !tile.authorized ? (
          <Label color="red">Not authorized</Label>
        ) : (
          <Button variant="link" isInline component="a" href={tile.href}>
            Open
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}
