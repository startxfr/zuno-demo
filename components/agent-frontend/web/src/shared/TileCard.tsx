import * as React from "react";
import { Button, Card, CardBody, CardFooter, CardTitle, Content, ContentVariants, Label } from "@patternfly/react-core";
import type { PortalTile } from "./types";

// One agent's tile, shared between the portal grid (portal/Portal.tsx) and
// the profile page's "your agent access" section (profile/Profile.tsx) -
// both render the same server-computed access decision
// (internal/portal/portal.go's BuildTiles).
export function TileCard({ tile }: { tile: PortalTile }): React.ReactElement {
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
