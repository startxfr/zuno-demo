import * as React from "react";
import {
  Alert,
  Button,
  Flex,
  FlexItem,
  FormSelect,
  FormSelectOption,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Spinner,
  Tab,
  Tabs,
  TabTitleText,
  TextArea,
  TextInput,
} from "@patternfly/react-core";
import { TimesIcon, TrashIcon, UserPlusIcon, UsersIcon } from "@patternfly/react-icons";
import {
  PROJECT_CONTEXT_MAX_CHARS,
  ROLE_LABELS,
  ROLE_ORDER,
  can,
  createProject,
  deleteProject,
  deleteProjectPreview,
  getColleagues,
  getProject,
  getRealmGroups,
  saveProject,
  type Colleague,
  type ProjectDetail,
  type ProjectGrant,
  type ProjectRole,
  type RealmGroup,
} from "./projects";

export interface ProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  // Called after a successful save or delete so the sidebar can refetch.
  onSaved: () => void;
  projectsURL: string;
  colleaguesURL: string;
  groupsURL: string;
  // null opens the dialog in create mode.
  projectId: string | null;
  // ADR-0527 clause 3: the caller's own Keycloak subject and display name, so
  // create mode can seed the creator's admin grant. Without it the dialog
  // cannot name the one member it is certain about - agent-bff's colleague
  // search deliberately never returns the caller (main.go's "never offer the
  // caller themselves as a share target"), so the creator could not be added
  // by hand either, and the last-admin guard could never be satisfied.
  subject: string;
  userDisplayName: string;
}

// ADR-0527 clause 9: every change is staged locally and committed by ONE
// request on validation - "tout les changements ne sont validés qu'après
// validation complète de la popup". That is also why the API offers a single
// full-state PUT rather than ADR-0213's five per-member endpoints: there is
// no intermediate state for a per-member call to describe.
export function ProjectDialog({
  isOpen,
  onClose,
  onSaved,
  projectsURL,
  colleaguesURL,
  groupsURL,
  projectId,
  subject,
  userDisplayName,
}: ProjectDialogProps): React.ReactElement {
  const isCreate = projectId === null;

  const [draft, setDraft] = React.useState<ProjectDetail | null>(null);
  const [loading, setLoading] = React.useState(!isCreate);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [activeTab, setActiveTab] = React.useState<string | number>("description");

  // RBAC tab state.
  const [query, setQuery] = React.useState("");
  const [candidates, setCandidates] = React.useState<Colleague[] | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [newUserRole, setNewUserRole] = React.useState<ProjectRole>("read");
  const [groups, setGroups] = React.useState<RealmGroup[] | null>(null);
  // Distinct from `groups === null`: the directory answering 503 is a state
  // the user must SEE, because an empty picker reads as "this realm has no
  // groups" and would silently prevent every group grant.
  const [groupsUnavailable, setGroupsUnavailable] = React.useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = React.useState("");
  const [newGroupRole, setNewGroupRole] = React.useState<ProjectRole>("read");
  const debounceRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    if (!isOpen) {
      return;
    }
    setError(null);
    setActiveTab("description");
    if (isCreate) {
      setDraft({
        project_id: "",
        title: "",
        context: "",
        classification: "C2",
        is_customer: false,
        // The creator is always an admin (ADR-0527 clause 3 - the server
        // merges its own admin grant in regardless, this only makes the
        // dialog render the RBAC tab immediately).
        role: "admin",
        created_by: "",
        created_at: "",
        updated_at: "",
        // Seeded, not empty. `saveDisabled` below refuses a project with no
        // subject-scoped admin (ADR-0527 clause 3's last-admin guard), and
        // with `grants: []` that made the Create button permanently grey: the
        // creator cannot add themselves, because agent-bff's colleague search
        // excludes the caller by design. Seeding the grant the server is
        // going to append anyway (app/main.py merges the creator's admin
        // grant before validating) satisfies the guard honestly and lets the
        // RBAC tab show who will actually administer the project, instead of
        // showing an empty list and adding an admin behind the user's back.
        grants: [{ subject, role: "admin", display_name: userDisplayName }],
        salesforce_opportunity_id: "",
      });
      setLoading(false);
      return;
    }
    setLoading(true);
    getProject(projectsURL, projectId)
      .then((detail) => setDraft({ ...detail, grants: detail.grants ?? [] }))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [isOpen, isCreate, projectId, projectsURL, subject, userDisplayName]);

  const isAdmin = can(draft?.role, "admin");
  const canEditDescription = can(draft?.role, "write");

  // Only an admin ever sees the Groups picker, so only then is the lookup
  // worth making - and its 503 only worth surfacing.
  React.useEffect(() => {
    if (!isOpen || !isAdmin || groups !== null || groupsUnavailable !== null) {
      return;
    }
    getRealmGroups(groupsURL)
      .then(setGroups)
      .catch((err) => setGroupsUnavailable(err instanceof Error ? err.message : String(err)));
  }, [isOpen, isAdmin, groups, groupsUnavailable, groupsURL]);

  React.useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, []);

  function patch(fields: Partial<ProjectDetail>) {
    setDraft((current) => (current === null ? current : { ...current, ...fields }));
  }

  // Same 300 ms debounce ShareDialog used - Keycloak's Admin API is a real
  // operational dependency and a type-ahead must not hammer it.
  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    const trimmed = value.trim();
    if (!trimmed) {
      setCandidates(null);
      return;
    }
    setSearching(true);
    debounceRef.current = window.setTimeout(() => {
      getColleagues(colleaguesURL, trimmed)
        .then(setCandidates)
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setSearching(false));
    }, 300);
  }

  function addUserGrant(candidate: Colleague) {
    if (!candidate.eligible || draft === null) {
      return;
    }
    const others = draft.grants.filter((g) => g.subject !== candidate.sub);
    patch({
      grants: [
        ...others,
        { subject: candidate.sub, role: newUserRole, display_name: candidate.displayName },
      ],
    });
    setQuery("");
    setCandidates(null);
  }

  function addGroupGrant() {
    if (!selectedGroup || draft === null) {
      return;
    }
    const others = draft.grants.filter((g) => g.group_name !== selectedGroup);
    patch({ grants: [...others, { group_name: selectedGroup, role: newGroupRole }] });
    setSelectedGroup("");
  }

  function removeGrant(grant: ProjectGrant) {
    if (draft === null) {
      return;
    }
    patch({
      grants: draft.grants.filter(
        (g) => !(g.subject === grant.subject && g.group_name === grant.group_name),
      ),
    });
  }

  function changeGrantRole(grant: ProjectGrant, role: ProjectRole) {
    if (draft === null) {
      return;
    }
    patch({
      grants: draft.grants.map((g) =>
        g.subject === grant.subject && g.group_name === grant.group_name ? { ...g, role } : g,
      ),
    });
  }

  const userGrants = (draft?.grants ?? []).filter((g) => g.subject);
  const groupGrants = (draft?.grants ?? []).filter((g) => g.group_name);
  // ADR-0527 clause 3: the guard demands a SUBJECT-scoped admin - a
  // group-scoped one leaves the project administrable only for as long as
  // Keycloak keeps somebody in that group. Blocked here for a clear message
  // AND enforced server-side, which is the authority.
  const hasSubjectAdmin = userGrants.some((g) => g.role === "admin");
  const contextTooLong = (draft?.context.length ?? 0) > PROJECT_CONTEXT_MAX_CHARS;
  const titleMissing = !draft?.title.trim();
  const saveDisabled =
    saving || draft === null || titleMissing || contextTooLong || (isAdmin && !hasSubjectAdmin);

  async function commit() {
    if (draft === null) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: draft.title.trim(),
        context: draft.context,
        classification: draft.classification,
        salesforce_opportunity_id: (draft.salesforce_opportunity_id ?? "").trim(),
        // A `write` member may not edit grants, so the field is omitted
        // entirely and the server leaves them untouched - rather than
        // sending a set it would refuse.
        ...(isAdmin ? { grants: draft.grants } : {}),
      };
      if (isCreate) {
        await createProject(projectsURL, payload);
      } else {
        await saveProject(projectsURL, projectId as string, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function removeProject() {
    if (projectId === null) {
      return;
    }
    setError(null);
    try {
      // ADR-0527 clause 7: an admin archiving colleagues' visible work is
      // told the size of what they are doing before it happens.
      const preview = await deleteProjectPreview(projectsURL, projectId);
      const others =
        preview.conversations_other_owners > 0
          ? `, ${preview.conversations_other_owners} of them owned by other members`
          : "";
      const confirmed = window.confirm(
        `Delete "${draft?.title || "this project"}"?\n\n` +
          `${preview.conversations_total} conversation(s)${others} will be archived along with it, ` +
          `and ${preview.members_users} user(s) and ${preview.members_groups} group(s) will lose access.\n\n` +
          "Nothing is erased - archived conversations keep their full history.",
      );
      if (!confirmed) {
        return;
      }
      await deleteProject(projectsURL, projectId);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function grantRow(grant: ProjectGrant, label: string) {
    return (
      <Flex
        key={`${grant.subject ?? ""}|${grant.group_name ?? ""}`}
        alignItems={{ default: "alignItemsCenter" }}
        gap={{ default: "gapSm" }}
        style={{ padding: "0.25rem 0" }}
      >
        <FlexItem grow={{ default: "grow" }} style={{ minWidth: 0 }}>
          <span
            title={label}
            style={{
              display: "block",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {label}
          </span>
        </FlexItem>
        <FlexItem>
          <FormSelect
            aria-label={`Role for ${label}`}
            value={grant.role}
            isDisabled={!isAdmin}
            onChange={(_e, value) => changeGrantRole(grant, value as ProjectRole)}
          >
            {ROLE_ORDER.map((role) => (
              <FormSelectOption key={role} value={role} label={ROLE_LABELS[role]} />
            ))}
          </FormSelect>
        </FlexItem>
        <FlexItem>
          <Button
            variant="plain"
            aria-label={`Remove ${label}`}
            isDisabled={!isAdmin}
            onClick={() => removeGrant(grant)}
          >
            <TrashIcon />
          </Button>
        </FlexItem>
      </Flex>
    );
  }

  const heading = isCreate
    ? "New project"
    : canEditDescription
      ? `Project "${draft?.title || "Untitled"}"`
      : `Project "${draft?.title || "Untitled"}" (read-only)`;

  return (
    <Modal isOpen={isOpen} onClose={onClose} aria-label={heading} variant="medium">
      <ModalHeader title={heading} />
      <ModalBody>
        {error && (
          <Alert variant="danger" isInline title={error} style={{ marginBottom: "0.75rem" }} />
        )}
        {loading || draft === null ? (
          <Spinner size="md" aria-label="Loading project" />
        ) : (
          <Tabs activeKey={activeTab} onSelect={(_e, key) => setActiveTab(key)}>
            <Tab eventKey="description" title={<TabTitleText>Description</TabTitleText>}>
              <Flex
                direction={{ default: "column" }}
                gap={{ default: "gapMd" }}
                style={{ paddingTop: "1rem" }}
              >
                <FlexItem>
                  <TextInput
                    aria-label="Project title"
                    placeholder="Project title"
                    value={draft.title}
                    isDisabled={!canEditDescription}
                    onChange={(_e, value) => patch({ title: value })}
                  />
                </FlexItem>
                <FlexItem>
                  <TextArea
                    aria-label="Project context"
                    placeholder="Standing context for this engagement — carried into every conversation of this project as background."
                    value={draft.context}
                    rows={12}
                    isDisabled={!canEditDescription}
                    onChange={(_e, value) => patch({ context: value })}
                  />
                  <HelperText>
                    <HelperTextItem variant={contextTooLong ? "error" : "default"}>
                      {draft.context.length.toLocaleString()} /{" "}
                      {PROJECT_CONTEXT_MAX_CHARS.toLocaleString()} characters. Sent to the agent as
                      background information, never as instructions, and truncated to a token budget
                      so it cannot crowd out the conversation itself.
                    </HelperTextItem>
                  </HelperText>
                </FlexItem>
                {isAdmin && (
                  <FlexItem>
                    <TextInput
                      aria-label="Salesforce opportunity"
                      placeholder="Salesforce opportunity id or name (optional)"
                      value={draft.salesforce_opportunity_id ?? ""}
                      onChange={(_e, value) => patch({ salesforce_opportunity_id: value })}
                    />
                    <HelperText>
                      <HelperTextItem>
                        {draft.is_customer
                          ? "Customer project — verified against Salesforce under your own identity."
                          : "Free project — no Salesforce link. Fully usable; only tasks that require a customer engagement are unavailable."}
                      </HelperTextItem>
                    </HelperText>
                  </FlexItem>
                )}
              </Flex>
            </Tab>
            {isAdmin && (
              <Tab eventKey="rbac" title={<TabTitleText>RBAC</TabTitleText>}>
                <Flex
                  direction={{ default: "column" }}
                  gap={{ default: "gapLg" }}
                  style={{ paddingTop: "1rem" }}
                >
                  <FlexItem>
                    <b>Users</b>
                    <Flex gap={{ default: "gapSm" }} style={{ margin: "0.5rem 0" }}>
                      <FlexItem grow={{ default: "grow" }}>
                        <TextInput
                          aria-label="Search colleagues"
                          placeholder="Search colleagues by name…"
                          value={query}
                          onChange={(_e, value) => handleQueryChange(value)}
                        />
                      </FlexItem>
                      <FlexItem>
                        <FormSelect
                          aria-label="Role for the next user added"
                          value={newUserRole}
                          onChange={(_e, value) => setNewUserRole(value as ProjectRole)}
                        >
                          {ROLE_ORDER.map((role) => (
                            <FormSelectOption key={role} value={role} label={ROLE_LABELS[role]} />
                          ))}
                        </FormSelect>
                      </FlexItem>
                    </Flex>
                    {searching && <Spinner size="sm" aria-label="Searching colleagues" />}
                    {candidates?.map((c) => (
                      <button
                        key={c.sub}
                        type="button"
                        disabled={!c.eligible}
                        onClick={() => addUserGrant(c)}
                        // ADR-0213's product requirement, kept by ADR-0527:
                        // an ineligible colleague is shown greyed out rather
                        // than hidden, so the user learns WHY they cannot be
                        // added instead of wondering where they went.
                        title={
                          c.eligible
                            ? undefined
                            : "Not entitled to this agent, or shares no business role with you"
                        }
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          width: "100%",
                          textAlign: "left",
                          background: "none",
                          border: "none",
                          padding: "0.25rem",
                          cursor: c.eligible ? "pointer" : "not-allowed",
                          opacity: c.eligible ? 1 : 0.5,
                          color: "var(--pf-t--global--text--color--regular)",
                        }}
                      >
                        <UserPlusIcon />
                        {c.displayName}
                      </button>
                    ))}
                    {userGrants.length === 0 ? (
                      <HelperText>
                        <HelperTextItem variant="warning">
                          A project must keep at least one user with the admin role.
                        </HelperTextItem>
                      </HelperText>
                    ) : (
                      userGrants.map((g) => grantRow(g, g.display_name ?? g.subject ?? ""))
                    )}
                    {userGrants.length > 0 && !hasSubjectAdmin && (
                      <HelperText>
                        <HelperTextItem variant="error">
                          At least one user must keep the admin role, or nobody could administer this
                          project.
                        </HelperTextItem>
                      </HelperText>
                    )}
                  </FlexItem>

                  <FlexItem>
                    <b>Groups</b>
                    {groupsUnavailable !== null ? (
                      <Alert
                        variant="warning"
                        isInline
                        isPlain
                        title="Group directory unavailable — group sharing cannot be changed right now."
                        style={{ margin: "0.5rem 0" }}
                      />
                    ) : (
                      <Flex gap={{ default: "gapSm" }} style={{ margin: "0.5rem 0" }}>
                        <FlexItem grow={{ default: "grow" }}>
                          <FormSelect
                            aria-label="Business-role group to add"
                            value={selectedGroup}
                            isDisabled={groups === null}
                            onChange={(_e, value) => setSelectedGroup(value)}
                          >
                            <FormSelectOption
                              value=""
                              label={groups === null ? "Loading groups…" : "Select a group…"}
                            />
                            {(groups ?? []).map((g) => (
                              <FormSelectOption key={g.name} value={g.name} label={g.name} />
                            ))}
                          </FormSelect>
                        </FlexItem>
                        <FlexItem>
                          <FormSelect
                            aria-label="Role for the next group added"
                            value={newGroupRole}
                            onChange={(_e, value) => setNewGroupRole(value as ProjectRole)}
                          >
                            {ROLE_ORDER.map((role) => (
                              <FormSelectOption key={role} value={role} label={ROLE_LABELS[role]} />
                            ))}
                          </FormSelect>
                        </FlexItem>
                        <FlexItem>
                          <Button
                            variant="secondary"
                            icon={<UsersIcon />}
                            isDisabled={!selectedGroup}
                            onClick={addGroupGrant}
                          >
                            Add
                          </Button>
                        </FlexItem>
                      </Flex>
                    )}
                    {groupGrants.map((g) => grantRow(g, g.group_name ?? ""))}
                  </FlexItem>
                </Flex>
              </Tab>
            )}
          </Tabs>
        )}
      </ModalBody>
      <ModalFooter>
        {canEditDescription && (
          <Button variant="primary" isDisabled={saveDisabled} onClick={() => void commit()}>
            {saving ? "Saving…" : isCreate ? "Create project" : "Save"}
          </Button>
        )}
        <Button variant="link" icon={<TimesIcon />} onClick={onClose}>
          {canEditDescription ? "Cancel" : "Close"}
        </Button>
        {isAdmin && !isCreate && (
          <Button variant="danger" onClick={() => void removeProject()}>
            Delete project
          </Button>
        )}
      </ModalFooter>
    </Modal>
  );
}
