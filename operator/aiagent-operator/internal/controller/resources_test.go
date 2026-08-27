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

package controller

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"

	zunov1alpha1 "github.com/startxfr/zuno-demo/operator/aiagent-operator/api/v1alpha1"
)

func sampleAgent() *zunov1alpha1.AIAgent {
	return &zunov1alpha1.AIAgent{
		Spec: zunov1alpha1.AIAgentSpec{
			AgentName:       "tekos",
			TargetNamespace: "zuno-ai-run",
			OKFBundleRef:    "agents/tekos",
			Frontend: zunov1alpha1.FrontendProfile{
				Image:        zunov1alpha1.ImageRef{Registry: "image-registry.openshift-image-registry.svc:5000", Repository: "zuno-ai-build/agent-frontend", Tag: "latest"},
				Replicas:     1,
				OIDCClientID: "tekos-frontend",
				Resources: zunov1alpha1.ResourceRequirements{
					Requests: zunov1alpha1.ResourceList{CPU: "100m", Memory: "128Mi"},
					Limits:   zunov1alpha1.ResourceList{CPU: "500m", Memory: "256Mi"},
				},
			},
			BFF: zunov1alpha1.BFFProfile{
				Image:        zunov1alpha1.ImageRef{Registry: "image-registry.openshift-image-registry.svc:5000", Repository: "zuno-ai-build/agent-bff", Tag: "latest"},
				Replicas:     1,
				OIDCAudience: "tekos-frontend",
			},
			Groups: zunov1alpha1.GroupBindings{
				EntitlementGroup: "agent_tekos",
				BusinessRoles:    []string{"consultant"},
			},
			KnowledgeDomains: []string{"knowledge.tech", "knowledge.project"},
			ToolCapabilities: []string{"search_confluence", "web_search"},
		},
	}
}

func TestDesiredFrontendDeployment_ImageAndEnv(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	deploy := desiredFrontendDeployment(agent, cfg)

	require.Equal(t, "tekos-frontend", deploy.Name)
	require.Equal(t, "zuno-ai-run", deploy.Namespace)
	require.Len(t, deploy.Spec.Template.Spec.Containers, 1)

	container := deploy.Spec.Template.Spec.Containers[0]
	require.Equal(t, "image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-frontend:latest", container.Image)
	require.True(t, *container.SecurityContext.ReadOnlyRootFilesystem)
	require.False(t, *container.SecurityContext.AllowPrivilegeEscalation)

	env := map[string]string{}
	for _, e := range container.Env {
		if e.Value != "" {
			env[e.Name] = e.Value
		}
	}
	require.Equal(t, "tekos", env["ACTIVE_AGENT"])
	require.Equal(t, "https://tekos.apps.mycluster.example.com", env["SELF_BASE_URL"])
	require.Equal(t, "http://tekos-bff.zuno-ai-run.svc.cluster.local:8080", env["BFF_BASE_URL"])

	var secretEnvNames []string
	for _, e := range container.Env {
		if e.ValueFrom != nil && e.ValueFrom.SecretKeyRef != nil {
			require.Equal(t, "tekos-frontend-secrets", e.ValueFrom.SecretKeyRef.Name)
			secretEnvNames = append(secretEnvNames, e.Name)
		}
	}
	require.ElementsMatch(t, []string{"OIDC_CLIENT_SECRET", "SESSION_HMAC_SECRET", "SESSION_ENCRYPTION_KEY", "REDIS_PASSWORD"}, secretEnvNames)
}

func TestDesiredFrontendDeployment_RouteHostOverride(t *testing.T) {
	agent := sampleAgent()
	agent.Spec.Frontend.RouteHost = "custom.example.com"
	cfg := DefaultOperatorConfig()

	deploy := desiredFrontendDeployment(agent, cfg)
	for _, e := range deploy.Spec.Template.Spec.Containers[0].Env {
		if e.Name == "SELF_BASE_URL" {
			require.Equal(t, "https://custom.example.com", e.Value)
			return
		}
	}
	t.Fatal("SELF_BASE_URL env var not found")
}

// ADR-0411: the frontend, unlike the BFF, must keep dialing Keycloak's
// external Route (browser-facing redirects), so it needs a mounted CA
// bundle + KEYCLOAK_CA_CERT_PATH rather than the BFF's internal-URL
// workaround.
func TestDesiredFrontendDeployment_MountsKeycloakCA(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()
	require.NotEmpty(t, cfg.KeycloakCAConfigMapName, "default config must wire CA trust on by default, matching every hand-authored agent chart")

	deploy := desiredFrontendDeployment(agent, cfg)
	container := deploy.Spec.Template.Spec.Containers[0]

	var caCertPath string
	for _, e := range container.Env {
		if e.Name == "KEYCLOAK_CA_CERT_PATH" {
			caCertPath = e.Value
		}
	}
	require.NotEmpty(t, caCertPath, "KEYCLOAK_CA_CERT_PATH env var not found")

	var mount *corev1.VolumeMount
	for i := range container.VolumeMounts {
		if container.VolumeMounts[i].Name == "keycloak-ca" {
			mount = &container.VolumeMounts[i]
		}
	}
	require.NotNil(t, mount, "keycloak-ca volume mount not found")
	require.True(t, mount.ReadOnly)
	require.Equal(t, caCertPath, mount.MountPath+"/ca.crt")

	var volume *corev1.Volume
	for i := range deploy.Spec.Template.Spec.Volumes {
		if deploy.Spec.Template.Spec.Volumes[i].Name == "keycloak-ca" {
			volume = &deploy.Spec.Template.Spec.Volumes[i]
		}
	}
	require.NotNil(t, volume, "keycloak-ca volume not found")
	require.NotNil(t, volume.ConfigMap)
	require.Equal(t, cfg.KeycloakCAConfigMapName, volume.ConfigMap.Name)
}

// Empty KeycloakCAConfigMapName must disable the volume/mount/env var
// entirely, not just leave it pointing at a nonexistent ConfigMap.
func TestDesiredFrontendDeployment_KeycloakCADisabledWhenConfigMapNameEmpty(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()
	cfg.KeycloakCAConfigMapName = ""

	deploy := desiredFrontendDeployment(agent, cfg)
	container := deploy.Spec.Template.Spec.Containers[0]

	for _, e := range container.Env {
		require.NotEqual(t, "KEYCLOAK_CA_CERT_PATH", e.Name)
	}
	for _, m := range container.VolumeMounts {
		require.NotEqual(t, "keycloak-ca", m.Name)
	}
	for _, v := range deploy.Spec.Template.Spec.Volumes {
		require.NotEqual(t, "keycloak-ca", v.Name)
	}
}

// ADR-0411 follow-up: both generated Deployments must carry a correctly
// shaped image.openshift.io/triggers annotation, or a fresh Build never
// rolls these pods without a manual `oc delete pod`.
func TestDesiredFrontendDeployment_ImageTriggerAnnotation(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	deploy := desiredFrontendDeployment(agent, cfg)
	raw, ok := deploy.Annotations["image.openshift.io/triggers"]
	require.True(t, ok, "image.openshift.io/triggers annotation not found")

	var triggers []imageTrigger
	require.NoError(t, json.Unmarshal([]byte(raw), &triggers))
	require.Len(t, triggers, 1)
	require.Equal(t, "ImageStreamTag", triggers[0].From.Kind)
	require.Equal(t, "agent-frontend:latest", triggers[0].From.Name)
	require.Equal(t, "zuno-ai-build", triggers[0].From.Namespace)
	require.Equal(t, `spec.template.spec.containers[?(@.name=="frontend")].image`, triggers[0].FieldPath)
}

func TestDesiredBFFDeployment_ImageTriggerAnnotation(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	deploy := desiredBFFDeployment(agent, cfg)
	raw, ok := deploy.Annotations["image.openshift.io/triggers"]
	require.True(t, ok, "image.openshift.io/triggers annotation not found")

	var triggers []imageTrigger
	require.NoError(t, json.Unmarshal([]byte(raw), &triggers))
	require.Len(t, triggers, 1)
	require.Equal(t, "agent-bff:latest", triggers[0].From.Name)
	require.Equal(t, `spec.template.spec.containers[?(@.name=="bff")].image`, triggers[0].FieldPath)
}

// The BFF used to hold no secret at all, and this test asserted exactly that.
// ADR-0530/WP-091 knowingly overturns that invariant for one credential: the
// zuno-admin-api client secret, which agent-bff needs to reach Keycloak's
// Admin REST API for GET /api/colleagues and GET /api/groups.
//
// The assertion is narrowed rather than dropped. "Holds no secret" was never
// the real requirement - "holds nothing it does not need" was - so the test
// now names the single permitted secret and still fails on any second one.
func TestDesiredBFFDeployment_OnlySecretIsTheAdminClientCredential(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	deploy := desiredBFFDeployment(agent, cfg)
	require.Equal(t, "tekos-bff", deploy.Name)

	var fromSecret []string
	for _, e := range deploy.Spec.Template.Spec.Containers[0].Env {
		if e.ValueFrom == nil {
			continue
		}
		require.NotNil(t, e.ValueFrom.SecretKeyRef,
			"bff env %q reads from a non-secret source it has no reason to need", e.Name)
		fromSecret = append(fromSecret, e.Name)
	}
	require.Equal(t, []string{"KEYCLOAK_ADMIN_CLIENT_SECRET"}, fromSecret,
		"the admin client credential is the ONLY secret the bff may reference (ADR-0530); anything else is a privilege the BFF was never granted")

	ref := envVarByName(t, deploy.Spec.Template.Spec.Containers[0].Env, "KEYCLOAK_ADMIN_CLIENT_SECRET")
	require.Equal(t, "tekos-bff-admin-secret", ref.ValueFrom.SecretKeyRef.Name)
	require.Equal(t, "KEYCLOAK_ADMIN_CLIENT_SECRET", ref.ValueFrom.SecretKeyRef.Key)

	// The Vault path behind this Secret is seeded by ansible/roles/vault, not
	// by this operator and not by ArgoCD, so the Deployment WILL be reconciled
	// before the Secret exists. Non-optional, that is a
	// CreateContainerConfigError and the BFF stops serving every route.
	// Optional, only the two admin endpoints degrade, to the 503 they already
	// document. This assertion is the difference between a feature that is
	// off and an outage.
	require.NotNil(t, ref.ValueFrom.SecretKeyRef.Optional)
	require.True(t, *ref.ValueFrom.SecretKeyRef.Optional,
		"the admin client secret must be optional - see the comment above")
}

// Blanking the client id must take the whole boundary away - no env vars at
// all, so agent-bff's NewAdminClient returns nil and both endpoints keep
// failing closed with 503 rather than half-configuring themselves into a 500.
func TestDesiredBFFDeployment_AdminBoundaryIsOptional(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()
	cfg.KeycloakAdminClientID = ""

	deploy := desiredBFFDeployment(agent, cfg)
	for _, e := range deploy.Spec.Template.Spec.Containers[0].Env {
		require.NotContains(t, e.Name, "KEYCLOAK_ADMIN_",
			"disabling the boundary must leave no KEYCLOAK_ADMIN_* env behind")
		require.Nil(t, e.ValueFrom)
	}
}

// The credential is shared platform-wide, not minted per agent: Keycloak
// resolves the SAME Vault path through KC_VAULT to validate the client. A
// per-agent path here would authenticate against nothing.
func TestDesiredBFFExternalSecret_SharedVaultPath(t *testing.T) {
	agent := sampleAgent()

	es := desiredBFFExternalSecret(agent)
	require.Equal(t, "external-secrets.io/v1beta1", es.GetAPIVersion())
	require.Equal(t, "ExternalSecret", es.GetKind())
	require.Equal(t, "tekos-bff-admin-secret", es.GetName())

	data, found, err := unstructured.NestedSlice(es.Object, "spec", "data")
	require.NoError(t, err)
	require.True(t, found)
	require.Len(t, data, 1, "the bff needs exactly one secret, not a bundle")

	entry := data[0].(map[string]interface{})
	require.Equal(t, "KEYCLOAK_ADMIN_CLIENT_SECRET", entry["secretKey"])
	remote := entry["remoteRef"].(map[string]interface{})
	require.Equal(t, "keycloak/zuno-admin-api-client", remote["key"])
	require.NotContains(t, remote["key"], agent.Spec.AgentName,
		"the admin client secret is shared with gitops/charts/keycloak; a per-agent path would not match what Keycloak validates against")
}

func envVarByName(t *testing.T, env []corev1.EnvVar, name string) corev1.EnvVar {
	t.Helper()
	for _, e := range env {
		if e.Name == name {
			return e
		}
	}
	t.Fatalf("env var %q not found", name)
	return corev1.EnvVar{}
}

func TestDesiredFrontendRoute_Fields(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	route := desiredFrontendRoute(agent, cfg)
	require.Equal(t, "route.openshift.io/v1", route.GetAPIVersion())
	require.Equal(t, "Route", route.GetKind())
	require.Equal(t, "tekos-frontend", route.GetName())

	host, _, _ := unstructured.NestedString(route.Object, "spec", "host")
	require.Equal(t, "tekos.apps.mycluster.example.com", host)

	termination, _, _ := unstructured.NestedString(route.Object, "spec", "tls", "termination")
	require.Equal(t, "edge", termination)
}

func TestDesiredFrontendExternalSecret_VaultPaths(t *testing.T) {
	agent := sampleAgent()

	es := desiredFrontendExternalSecret(agent)
	data, _, err := unstructured.NestedSlice(es.Object, "spec", "data")
	require.NoError(t, err)
	require.Len(t, data, 4)

	keys := map[string]string{}
	for _, raw := range data {
		entry := raw.(map[string]interface{})
		secretKey := entry["secretKey"].(string)
		remoteRef := entry["remoteRef"].(map[string]interface{})
		keys[secretKey] = remoteRef["key"].(string)
	}
	require.Equal(t, "keycloak/tekos-frontend", keys["OIDC_CLIENT_SECRET"])
	require.Equal(t, "tekos/frontend-session", keys["SESSION_HMAC_SECRET"])
	require.Equal(t, "redis/session-store", keys["REDIS_PASSWORD"])
}

func TestDesiredOKFReferenceConfigMap_CarriesBindings(t *testing.T) {
	agent := sampleAgent()

	cm := desiredOKFReferenceConfigMap(agent)
	require.Equal(t, "agents/tekos", cm.Data["okfBundleRef"])
	require.Equal(t, "knowledge.tech,knowledge.project", cm.Data["knowledgeDomains"])
	require.Equal(t, "search_confluence,web_search", cm.Data["toolCapabilities"])
}

func TestDesiredBFFNetworkPolicy_AllowsFrontendAndAcceptanceGate(t *testing.T) {
	agent := sampleAgent()

	np := desiredBFFNetworkPolicy(agent)
	require.Len(t, np.Spec.Ingress, 1)
	require.Len(t, np.Spec.Ingress[0].From, 2)
	require.Equal(t, "frontend", np.Spec.Ingress[0].From[0].PodSelector.MatchLabels[labelComponent])
	require.Equal(t, agent.Spec.AgentName, np.Spec.Ingress[0].From[0].PodSelector.MatchLabels[labelAgent])
	require.Equal(t, "acceptance-gate", np.Spec.Ingress[0].From[1].PodSelector.MatchLabels["app.kubernetes.io/name"])
}

func TestToCoreResources_EmptyStaysEmpty(t *testing.T) {
	out := toCoreResources(zunov1alpha1.ResourceRequirements{})
	require.Nil(t, out.Requests)
	require.Nil(t, out.Limits)
}

func TestReplicasOrDefault_ZeroBecomesOne(t *testing.T) {
	require.Equal(t, int32(1), *replicasOrDefault(0))
	require.Equal(t, int32(3), *replicasOrDefault(3))
}
