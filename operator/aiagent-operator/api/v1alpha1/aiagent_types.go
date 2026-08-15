/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

// ADR-0327 status condition types. status.conditions must expose at
// least these five; the controller (WP-38) may add more but must not
// drop any of them.
const (
	ConditionConfigValid         = "ConfigValid"
	ConditionOKFReady            = "OKFReady"
	ConditionFrontendReady       = "FrontendReady"
	ConditionBFFReady            = "BFFReady"
	ConditionRuntimeBindingReady = "RuntimeBindingReady"
)

// ImageRef is a registry-relative image reference. Deliberately has no
// pull-secret field: cross-namespace image pulls rely on the existing
// system:image-puller RoleBinding (gitops/charts/tekos and every sibling
// agent chart already depend on this), never a credential embedded here.
type ImageRef struct {
	// registry is the image registry host, e.g. the in-cluster
	// ImageStream registry service.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Registry string `json:"registry"`

	// repository is the registry-relative image repository, e.g.
	// "zuno-ai-build/agent-frontend".
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Repository string `json:"repository"`

	// tag is the image tag to deploy.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Tag string `json:"tag"`
}

// ResourceList is a CPU/memory pair matching every hand-authored agent
// chart's own requests/limits shape (no arbitrary resource names).
type ResourceList struct {
	// +optional
	CPU string `json:"cpu,omitempty"`
	// +optional
	Memory string `json:"memory,omitempty"`
}

// ResourceRequirements mirrors corev1.ResourceRequirements for CPU/memory
// only.
type ResourceRequirements struct {
	// +optional
	Requests ResourceList `json:"requests,omitempty"`
	// +optional
	Limits ResourceList `json:"limits,omitempty"`
}

// FrontendProfile is the frontend Deployment/Service/Route deployment
// binding. Deployment shape only: no session content, no OIDC client
// secret (resolved via the existing Vault/External Secrets convention,
// keyed by agentName).
type FrontendProfile struct {
	// +kubebuilder:validation:Required
	Image ImageRef `json:"image"`

	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=1
	// +optional
	Replicas int32 `json:"replicas,omitempty"`

	// +optional
	Resources ResourceRequirements `json:"resources,omitempty"`

	// routeHost overrides the default "<agentName>.<clusterBaseDomain>"
	// Route hostname (matches gitops/charts/*/values.yaml's own
	// frontend.route.host convention). Empty means "use the default".
	// +optional
	RouteHost string `json:"routeHost,omitempty"`

	// oidcClientId is the Keycloak client id this frontend authenticates
	// as, e.g. "tekos-frontend". The client secret itself is never in
	// this CR.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	OIDCClientID string `json:"oidcClientId"`
}

// BFFProfile is the BFF Deployment/Service deployment binding.
type BFFProfile struct {
	// +kubebuilder:validation:Required
	Image ImageRef `json:"image"`

	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=1
	// +optional
	Replicas int32 `json:"replicas,omitempty"`

	// +optional
	Resources ResourceRequirements `json:"resources,omitempty"`

	// oidcAudience is the JWT audience the BFF validates incoming tokens
	// against (matches FrontendProfile.oidcClientId by convention; kept
	// as a separate field since they are logically distinct concerns).
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	OIDCAudience string `json:"oidcAudience"`
}

// GroupBindings references existing Keycloak groups (ADR-0040): the
// agent entitlement group is orthogonal to the business role(s) that
// govern tool/data permissions inside the agent. Neither field grants
// anything by itself — both are enforced by the realm/policy
// configuration this CR only points at, never duplicates.
type GroupBindings struct {
	// entitlementGroup is the ADR-0040 agent-entitlement Keycloak group,
	// e.g. "agent_tekos".
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	EntitlementGroup string `json:"entitlementGroup"`

	// businessRoles are the ADR-0040 business-role groups authorized to
	// use this agent's tools/data, e.g. ["consultant"], ["sales"],
	// ["board"]. Reference only — the actual grants live in
	// policies/tools/tool-policy.yaml and
	// policies/knowledge/knowledge-policy.yaml.
	// +kubebuilder:validation:MinItems=1
	BusinessRoles []string `json:"businessRoles"`
}

// AIAgentSpec defines the desired state of an AIAgent instance:
// deployment bindings and references only (ADR-0327). It never carries
// OKF task behavior, prompts, document bodies, OAuth refresh tokens or
// raw credentials — those stay in the OKF bundle (Git, referenced by
// okfBundleRef) and Vault/External Secrets, respectively. The generated
// CRD is a structural schema with unknown fields pruned, so an
// accidental secret-shaped field added here is rejected rather than
// silently accepted (validate_contract.py proves this against a scratch
// sample).
type AIAgentSpec struct {
	// agentName identifies the agent instance. Must match the OKF
	// bundle's own `zuno.name` (agents/<agentName>/agent.okf.md) and the
	// Keycloak client id prefix. Renaming an agent is a new instance, not
	// an update to this field.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Pattern=`^[a-z]([-a-z0-9]*[a-z0-9])?$`
	// +kubebuilder:validation:MaxLength=63
	AgentName string `json:"agentName"`

	// targetNamespace is the namespace intent for this agent's generated
	// workloads. Every agent shares "zuno-ai-run" today (ADR-0329
	// supersedes the earlier per-agent-namespace ADR-0023); the field
	// stays explicit so a future per-agent-namespace policy is a CR
	// change, not a controller rewrite. The operator only ever creates
	// resources inside this one namespace — no other field on this spec
	// carries a namespace, so there is no way to construct a
	// cross-namespace reference through an AIAgent CR at all.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	TargetNamespace string `json:"targetNamespace"`

	// okfBundleRef is the Git-relative path to this agent's OKF bundle,
	// e.g. "agents/tekos". A reference only: OKF remains the sole source
	// of task/prompt/behavioral content (ADR-0005/ADR-0039), never
	// mirrored into this CR.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Pattern=`^agents/[a-z][-a-z0-9]*$`
	OKFBundleRef string `json:"okfBundleRef"`

	// +kubebuilder:validation:Required
	Frontend FrontendProfile `json:"frontend"`

	// +kubebuilder:validation:Required
	BFF BFFProfile `json:"bff"`

	// +kubebuilder:validation:Required
	Groups GroupBindings `json:"groups"`

	// knowledgeDomains are the logical RAG domain ids (ADR-0202) this
	// instance binds to, e.g. ["knowledge.tech", "knowledge.project"].
	// Physical collection endpoints are never listed here (ADR-0204) —
	// only logical ids the operator resolves via the existing RAG
	// platform bindings. This is the deployment-time binding
	// requirement, not a grant: actual per-task authorization stays
	// governed by policies/knowledge/knowledge-policy.yaml and each OKF
	// task's own `allowed_knowledge` (ADR-0203).
	// +optional
	KnowledgeDomains []string `json:"knowledgeDomains,omitempty"`

	// toolCapabilities are the logical MCP/tool capability ids
	// (ADR-0116) this instance binds to, e.g. ["search_confluence",
	// "web_search"]. Physical MCP server endpoints/credentials are never
	// listed here — only logical ids the operator resolves via the
	// existing MCP Gateway bindings. This is the deployment-time binding
	// requirement, not a grant: actual per-task authorization stays
	// governed by policies/tools/tool-policy.yaml and each OKF task's own
	// `allowed_tools`.
	// +optional
	ToolCapabilities []string `json:"toolCapabilities,omitempty"`

	// modelPolicyRef names the model-routing/classification policy this
	// instance uses (policies/model-routing, ADR-0303). Empty means "the
	// platform default policy".
	// +optional
	ModelPolicyRef string `json:"modelPolicyRef,omitempty"`

	// evaluationProfileRef names the evaluations/<agentName> acceptance
	// profile (ADR-0027/ADR-0028) `make check` consults for this
	// instance's readiness. Empty means "same as agentName".
	// +optional
	EvaluationProfileRef string `json:"evaluationProfileRef,omitempty"`
}

// AIAgentStatus defines the observed state of AIAgent.
type AIAgentStatus struct {
	// conditions surfaces reconciliation state. Must include at least
	// ConditionConfigValid, ConditionOKFReady, ConditionFrontendReady,
	// ConditionBFFReady and ConditionRuntimeBindingReady (ADR-0327's
	// status contract) — the controller (WP-38) may add more but must
	// not drop any of these five.
	// +listType=map
	// +listMapKey=type
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// observedGeneration is the .metadata.generation last reconciled by
	// the controller, the standard way to detect stale status.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Agent",type=string,JSONPath=`.spec.agentName`
// +kubebuilder:printcolumn:name="Namespace",type=string,JSONPath=`.spec.targetNamespace`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// AIAgent is the Schema for the aiagents API
type AIAgent struct {
	metav1.TypeMeta `json:",inline"`

	// metadata is a standard object metadata
	// +optional
	metav1.ObjectMeta `json:"metadata,omitzero"`

	// spec defines the desired state of AIAgent
	// +required
	Spec AIAgentSpec `json:"spec"`

	// status defines the observed state of AIAgent
	// +optional
	Status AIAgentStatus `json:"status,omitzero"`
}

// +kubebuilder:object:root=true

// AIAgentList contains a list of AIAgent
type AIAgentList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitzero"`
	Items           []AIAgent `json:"items"`
}

func init() {
	SchemeBuilder.Register(func(s *runtime.Scheme) error {
		s.AddKnownTypes(SchemeGroupVersion, &AIAgent{}, &AIAgentList{})
		return nil
	})
}
