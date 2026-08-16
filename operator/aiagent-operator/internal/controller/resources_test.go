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
	"testing"

	"github.com/stretchr/testify/require"
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

func TestDesiredBFFDeployment_NoSecretEnvVars(t *testing.T) {
	agent := sampleAgent()
	cfg := DefaultOperatorConfig()

	deploy := desiredBFFDeployment(agent, cfg)
	require.Equal(t, "tekos-bff", deploy.Name)
	for _, e := range deploy.Spec.Template.Spec.Containers[0].Env {
		require.Nil(t, e.ValueFrom, "bff deployment must never reference a secret directly (it validates JWTs via Keycloak JWKS, holds no secret of its own)")
	}
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
