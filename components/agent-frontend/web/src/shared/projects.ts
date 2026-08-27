// ADR-0527: the project is the sharing and context boundary. Thin fetch
// wrappers for this page's own project proxy routes, same shape and same
// JSON-error handling as shared/conversations.ts.
//
// Colleague search lives here rather than in conversations.ts because it is
// a project-RBAC concern now: ADR-0213's per-conversation sharing, and the
// ShareDialog that used it, are gone.

export type ProjectRole = "read" | "clone" | "write" | "admin";

// ADR-0527 clause 2: read < clone < write < admin, a TOTAL order - cloning
// exposes nothing a reader cannot already see. Mirrors ROLE_RANK in
// app/conversations.py and app/projects.py; the server is the authority,
// this is only for enabling/disabling controls.
export const ROLE_RANK: Record<ProjectRole, number> = {
  read: 1,
  clone: 2,
  write: 3,
  admin: 4,
};

export const ROLE_ORDER: ProjectRole[] = ["read", "clone", "write", "admin"];

export const ROLE_LABELS: Record<ProjectRole, string> = {
  read: "Read — view conversations only",
  clone: "Clone — read, and fork a conversation to continue privately",
  write: "Write — send messages, edit the title and context",
  admin: "Admin — manage people, the Salesforce link, and deletion",
};

export function rankOf(role: ProjectRole | null | undefined): number {
  return role ? ROLE_RANK[role] : 0;
}

export function can(role: ProjectRole | null | undefined, minimum: ProjectRole): boolean {
  return rankOf(role) >= ROLE_RANK[minimum];
}

// ADR-0527 clause 5. Mirrored in app/projects.py, app/schemas.py, agent-bff's
// projectContextMaxChars and the projects DDL's own CHECK - a value that
// passes one but not another is a bug in whichever drifted.
export const PROJECT_CONTEXT_MAX_CHARS = 54000;

export interface Project {
  project_id: string;
  title: string;
  classification: string;
  // ADR-0528: true when a verified Salesforce opportunity is linked. False
  // is a "free" project - fully usable, and still drawing its own quota.
  is_customer: boolean;
  starred: boolean;
  role: ProjectRole;
  conversation_count: number;
  updated_at: string;
}

export interface ProjectGrant {
  // Exactly one of these is set, mirroring project_grants' own XOR.
  subject?: string;
  group_name?: string;
  role: ProjectRole;
  granted_by?: string;
  created_at?: string;
  // Client-side only: the display name resolved from the colleague search,
  // so a member list can show a name instead of a raw Keycloak subject.
  // Never sent back - the server ignores unknown fields, but there is no
  // reason to send it.
  display_name?: string;
}

export interface ProjectDetail {
  project_id: string;
  title: string;
  context: string;
  classification: string;
  is_customer: boolean;
  role: ProjectRole;
  created_by: string;
  created_at: string;
  updated_at: string;
  // Populated by the server only for an admin caller.
  grants: ProjectGrant[];
  salesforce_opportunity_id?: string;
  salesforce_verified_at?: string;
}

export interface DeletePreview {
  conversations_total: number;
  conversations_other_owners: number;
  members_users: number;
  members_groups: number;
}

export interface RealmGroup {
  name: string;
  path: string;
}

export interface Colleague {
  sub: string;
  displayName: string;
  // Ineligible candidates are still returned so the caller can render them
  // greyed out rather than hide them - an ADR-0213 product requirement
  // ADR-0527 keeps.
  eligible: boolean;
}

async function parseOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    let detail = body;
    try {
      detail = JSON.parse(body).error ?? body;
    } catch {
      // body wasn't JSON - use it verbatim
    }
    throw new Error(detail || `request failed with status ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listProjects(projectsURL: string): Promise<Project[]> {
  return parseOrThrow<Project[]>(await fetch(projectsURL));
}

export async function getProject(projectsURL: string, projectId: string): Promise<ProjectDetail> {
  return parseOrThrow<ProjectDetail>(await fetch(`${projectsURL}/${encodeURIComponent(projectId)}`));
}

// The whole desired state in one request - ADR-0527's dialog stages every
// change locally and commits on a single validation, which is why there are
// no per-member endpoints to call here.
export interface ProjectPayload {
  title: string;
  context: string;
  classification: string;
  salesforce_opportunity_id: string;
  // Omitted entirely by a `write` member editing only the Description tab:
  // the server then leaves grants untouched. A present array is the FULL
  // desired set, so anything absent from it is revoked.
  grants?: ProjectGrant[];
}

function toWire(payload: ProjectPayload): Record<string, unknown> {
  const body: Record<string, unknown> = {
    title: payload.title,
    context: payload.context,
    classification: payload.classification,
    salesforce_opportunity_id: payload.salesforce_opportunity_id,
  };
  if (payload.grants !== undefined) {
    body.grants = payload.grants.map((g) => ({
      subject: g.subject ?? "",
      group_name: g.group_name ?? "",
      role: g.role,
    }));
  }
  return body;
}

export async function createProject(projectsURL: string, payload: ProjectPayload): Promise<string> {
  const result = await parseOrThrow<{ project_id: string }>(
    await fetch(projectsURL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toWire(payload)),
    }),
  );
  return result.project_id;
}

export async function saveProject(
  projectsURL: string,
  projectId: string,
  payload: ProjectPayload,
): Promise<void> {
  await parseOrThrow(
    await fetch(`${projectsURL}/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toWire(payload)),
    }),
  );
}

export async function deleteProjectPreview(
  projectsURL: string,
  projectId: string,
): Promise<DeletePreview> {
  return parseOrThrow<DeletePreview>(
    await fetch(`${projectsURL}/${encodeURIComponent(projectId)}/delete-preview`),
  );
}

// ADR-0527 clause 7: a cascade SOFT-delete. Nothing is erased - the
// irreversible purge stays per-conversation and owner-only.
export async function deleteProject(
  projectsURL: string,
  projectId: string,
): Promise<{ conversations_archived: number }> {
  return parseOrThrow<{ conversations_archived: number }>(
    await fetch(`${projectsURL}/${encodeURIComponent(projectId)}`, { method: "DELETE" }),
  );
}

export async function setProjectStar(
  projectsURL: string,
  projectId: string,
  starred: boolean,
): Promise<void> {
  await parseOrThrow(
    await fetch(`${projectsURL}/${encodeURIComponent(projectId)}/star`, {
      method: starred ? "PUT" : "DELETE",
    }),
  );
}

// Both of the Keycloak-Admin-backed lookups the RBAC tab needs. Each fails
// closed with 503 until the zuno-admin-api client is provisioned, and the
// dialog must SAY so rather than render an empty picker - an empty group
// list reads as "this realm has no groups" and would quietly prevent every
// group grant.

export async function getRealmGroups(groupsURL: string): Promise<RealmGroup[]> {
  return parseOrThrow<RealmGroup[]>(await fetch(groupsURL));
}

// Debounced by the caller (ProjectDialog.tsx) - a plain type-ahead wrapper,
// no debounce logic of its own.
export async function getColleagues(colleaguesURL: string, query: string): Promise<Colleague[]> {
  const url = query ? `${colleaguesURL}?q=${encodeURIComponent(query)}` : colleaguesURL;
  return parseOrThrow<Colleague[]>(await fetch(url));
}
