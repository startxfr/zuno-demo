import * as React from "react";
import {
  Button,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  FormSelect,
  FormSelectOption,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Spinner,
  TextInput,
} from "@patternfly/react-core";
import { TimesIcon, UserPlusIcon } from "@patternfly/react-icons";
import {
  getColleagues,
  grantMembership,
  listMembers,
  revokeMembership,
  type Colleague,
  type Member,
  type MembershipRole,
} from "./conversations";

export interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  conversationsURL: string;
  colleaguesURL: string;
  runId: string;
  title: string;
}

const ROLE_LABELS: Record<MembershipRole, string> = {
  reader: "Reader (read-only)",
  actor: "Actor (read + write)",
  cloner: "Cloner (read + clone)",
};

const ROLE_ORDER: MembershipRole[] = ["reader", "actor", "cloner"];

// ADR-0213: share dialog - debounced colleague search (GET
// /api/colleagues, via shared/conversations.ts's getColleagues), a role
// picker, and the member list with revoke. Ineligible candidates are
// rendered greyed out and disabled, never hidden, per the ADR's explicit
// product requirement - eligibility itself is computed server-side
// (agent-bff), this component only reflects it.
export function ShareDialog({
  isOpen,
  onClose,
  conversationsURL,
  colleaguesURL,
  runId,
  title,
}: ShareDialogProps): React.ReactElement {
  const [members, setMembers] = React.useState<Member[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [candidates, setCandidates] = React.useState<Colleague[] | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [selectedRole, setSelectedRole] = React.useState<MembershipRole>("actor");
  const [granting, setGranting] = React.useState<string | null>(null);
  const debounceRef = React.useRef<number | null>(null);

  const refreshMembers = React.useCallback(() => {
    listMembers(conversationsURL, runId)
      .then(setMembers)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [conversationsURL, runId]);

  React.useEffect(() => {
    if (isOpen) {
      refreshMembers();
    } else {
      // Reset search state between opens - a stale result list from a
      // previously-shared conversation must never bleed into this one.
      setQuery("");
      setCandidates(null);
      setError(null);
    }
  }, [isOpen, refreshMembers]);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    if (!value.trim()) {
      setCandidates(null);
      return;
    }
    // ADR-0213 Operational considerations: "colleague search must be
    // client-debounced."
    debounceRef.current = window.setTimeout(() => {
      setSearching(true);
      getColleagues(colleaguesURL, value.trim())
        .then(setCandidates)
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setSearching(false));
    }, 300);
  }

  async function grant(candidate: Colleague) {
    if (!candidate.eligible || granting) {
      return;
    }
    setGranting(candidate.sub);
    try {
      await grantMembership(conversationsURL, runId, candidate.sub, selectedRole);
      setQuery("");
      setCandidates(null);
      refreshMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGranting(null);
    }
  }

  async function revoke(subject: string) {
    try {
      await revokeMembership(conversationsURL, runId, subject);
      refreshMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} aria-label={`Share ${title || "conversation"}`} variant="small">
      <ModalHeader title={`Share "${title || "Untitled conversation"}"`} />
      <ModalBody>
        {error && (
          <div style={{ color: "var(--pf-t--global--color--status--danger--100)", marginBottom: "0.75rem" }}>
            {error}
          </div>
        )}
        <Flex direction={{ default: "column" }} gap={{ default: "gapMd" }}>
          <FlexItem>
            <Flex gap={{ default: "gapSm" }}>
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
                  aria-label="Role to grant"
                  value={selectedRole}
                  onChange={(_e, value) => setSelectedRole(value as MembershipRole)}
                >
                  {ROLE_ORDER.map((role) => (
                    <FormSelectOption key={role} value={role} label={ROLE_LABELS[role]} />
                  ))}
                </FormSelect>
              </FlexItem>
            </Flex>
          </FlexItem>
          {searching && <Spinner size="sm" aria-label="Searching colleagues" />}
          {candidates && candidates.length > 0 && (
            <FlexItem>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {candidates.map((c) => (
                  <button
                    key={c.sub}
                    type="button"
                    disabled={!c.eligible || granting === c.sub}
                    onClick={() => void grant(c)}
                    title={c.eligible ? undefined : "Not eligible for this agent, or no shared business role"}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "0.5rem",
                      border: "1px solid var(--pf-t--global--border--color--default)",
                      borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
                      background: "none",
                      cursor: c.eligible ? "pointer" : "not-allowed",
                      opacity: c.eligible ? 1 : 0.5,
                      textAlign: "left",
                    }}
                  >
                    <span>{c.displayName}</span>
                    {granting === c.sub ? <Spinner size="sm" aria-label="Granting access" /> : <UserPlusIcon />}
                  </button>
                ))}
              </div>
            </FlexItem>
          )}
          <FlexItem>
            <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>People with access</div>
            {members === null ? (
              <Spinner size="sm" aria-label="Loading members" />
            ) : members.length === 0 ? (
              <EmptyState titleText="Not shared yet" headingLevel="h5">
                <EmptyStateBody>Search above to share this conversation with a colleague.</EmptyStateBody>
              </EmptyState>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {members.map((m) => (
                  <div
                    key={m.subject}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "0.25rem 0",
                    }}
                  >
                    <span>
                      {m.subject} · {ROLE_LABELS[m.role]}
                    </span>
                    <button
                      type="button"
                      aria-label={`Revoke ${m.subject}`}
                      onClick={() => void revoke(m.subject)}
                      style={{ background: "none", border: "none", cursor: "pointer", display: "flex" }}
                    >
                      <TimesIcon />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </FlexItem>
        </Flex>
      </ModalBody>
      <ModalFooter>
        <Button variant="link" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
}
