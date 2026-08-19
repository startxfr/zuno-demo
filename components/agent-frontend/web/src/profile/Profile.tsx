import * as React from "react";
import {
  Brand,
  Card,
  CardBody,
  CardTitle,
  Content,
  ContentVariants,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  Gallery,
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
import logoPlaceholder from "../assets/logo-placeholder.svg";
import type { ProfileConfig } from "../shared/types";
import { Footer } from "../shared/Footer";
import { UserMenu } from "../shared/UserMenu";
import { TileCard } from "../shared/TileCard";

// Read-only account page (ADR-0044 pattern): the signed-in user's identity
// and the same per-agent entitlement computation the portal uses
// (internal/portal/portal.go's BuildTiles), for transparency into why the
// portal shows what it shows. No editing - group membership and access
// grants are managed in Keycloak, not here.
export function Profile({ config }: { config: ProfileConfig }): React.ReactElement {
  return (
    <Page
      masthead={
        <Masthead>
          <MastheadMain>
            <MastheadBrand>
              <Brand src={logoPlaceholder} alt="Zuno" heights={{ default: "32px" }} style={{ marginRight: "0.75rem" }} />
              <Content component={ContentVariants.h1}>
                <a href={config.homeURL} style={{ color: "inherit", textDecoration: "none" }}>
                  Zuno
                </a>{" "}
                / Profile
              </Content>
            </MastheadBrand>
          </MastheadMain>
          <MastheadContent>
            <Toolbar>
              <ToolbarContent>
                <ToolbarItem>
                  <UserMenu
                    userDisplayName={config.userDisplayName}
                    profileURL={config.profileURL}
                    logoutURL={config.logoutURL}
                  />
                </ToolbarItem>
              </ToolbarContent>
            </Toolbar>
          </MastheadContent>
        </Masthead>
      }
    >
      <PageSection>
        <Card>
          <CardTitle>Your account</CardTitle>
          <CardBody>
            <DescriptionList isHorizontal>
              <DescriptionListGroup>
                <DescriptionListTerm>Name</DescriptionListTerm>
                <DescriptionListDescription>{config.userDisplayName}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Email</DescriptionListTerm>
                <DescriptionListDescription>{config.email || "—"}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Groups</DescriptionListTerm>
                <DescriptionListDescription>
                  {config.groups.length === 0 ? (
                    "No group memberships"
                  ) : (
                    <Flex gap={{ default: "gapXs" }}>
                      {config.groups.map((g) => (
                        <FlexItem key={g}>
                          <Label color="blue" isCompact>
                            {g}
                          </Label>
                        </FlexItem>
                      ))}
                    </Flex>
                  )}
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Subject (sub)</DescriptionListTerm>
                <DescriptionListDescription>{config.subject}</DescriptionListDescription>
              </DescriptionListGroup>
            </DescriptionList>
          </CardBody>
        </Card>
      </PageSection>
      <PageSection>
        <Content component={ContentVariants.h2}>Your agent access</Content>
        {config.tiles.length === 0 ? (
          <EmptyState titleText="No agents configured" headingLevel="h3">
            <EmptyStateBody>No agents are defined for this deployment.</EmptyStateBody>
          </EmptyState>
        ) : (
          <Gallery hasGutter minWidths={{ default: "220px" }} maxWidths={{ default: "1fr" }}>
            {config.tiles.map((tile) => (
              <TileCard key={tile.name} tile={tile} />
            ))}
          </Gallery>
        )}
      </PageSection>
      <Footer />
    </Page>
  );
}
