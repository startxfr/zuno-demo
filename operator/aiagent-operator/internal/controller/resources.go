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

// Package controller: resources.go builds the desired state for every
// object CONTRACT.md's ownership model lists (frontend/BFF Deployment+
// Service+Route, OKF reference ConfigMap, NetworkPolicy, ServiceAccounts,
// the frontend's ExternalSecret). Every shape here is templated
// field-for-field from gitops/charts/tekos/templates/ (WP-38's own
// instruction: generated resources must match chart-deployed ones where
// the contract covers them) with agentName/spec values substituted in
// place of Tekos's hardcoded literals. Pure builder functions - no
// cluster I/O - so they are unit-testable without envtest.
package controller

import (
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/util/intstr"

	zunov1alpha1 "github.com/startxfr/zuno-demo/operator/aiagent-operator/api/v1alpha1"
)

const (
	labelAgent     = "zuno.io/agent"
	labelComponent = "app.kubernetes.io/component"
	labelManagedBy = "app.kubernetes.io/managed-by"
	managedByValue = "aiagent-operator"
	priorityClass  = "zuno-workload-default"
	containerPort  = 8080
	healthzPath    = "/healthz"
)

func commonLabels(agentName, component string) map[string]string {
	return map[string]string{
		labelAgent:     agentName,
		labelComponent: component,
		labelManagedBy: managedByValue,
	}
}

func routeHost(agent *zunov1alpha1.AIAgent, cfg OperatorConfig) string {
	if agent.Spec.Frontend.RouteHost != "" {
		return agent.Spec.Frontend.RouteHost
	}
	return agent.Spec.AgentName + "." + cfg.ClusterBaseDomain
}

func imageString(ref zunov1alpha1.ImageRef) string {
	return ref.Registry + "/" + ref.Repository + ":" + ref.Tag
}

func vaultOIDCClientSecretPath(agentName string) string {
	return "keycloak/" + agentName + "-frontend"
}

func vaultSessionSecretPath(agentName string) string {
	return agentName + "/frontend-session"
}

const vaultRedisSecretPath = "redis/session-store"

func toCoreResources(rr zunov1alpha1.ResourceRequirements) corev1.ResourceRequirements {
	out := corev1.ResourceRequirements{}
	if rr.Requests.CPU != "" || rr.Requests.Memory != "" {
		out.Requests = corev1.ResourceList{}
		if rr.Requests.CPU != "" {
			out.Requests[corev1.ResourceCPU] = resource.MustParse(rr.Requests.CPU)
		}
		if rr.Requests.Memory != "" {
			out.Requests[corev1.ResourceMemory] = resource.MustParse(rr.Requests.Memory)
		}
	}
	if rr.Limits.CPU != "" || rr.Limits.Memory != "" {
		out.Limits = corev1.ResourceList{}
		if rr.Limits.CPU != "" {
			out.Limits[corev1.ResourceCPU] = resource.MustParse(rr.Limits.CPU)
		}
		if rr.Limits.Memory != "" {
			out.Limits[corev1.ResourceMemory] = resource.MustParse(rr.Limits.Memory)
		}
	}
	return out
}

func replicasOrDefault(r int32) *int32 {
	if r <= 0 {
		r = 1
	}
	return &r
}

// restrictedSecurityContext matches every hand-authored agent chart's own
// pod/container securityContext (ADR-0052 OpenShift restricted +
// SecNumCloud hardening) exactly.
func podSecurityContext() *corev1.PodSecurityContext {
	return &corev1.PodSecurityContext{
		RunAsNonRoot: boolPtr(true),
		SeccompProfile: &corev1.SeccompProfile{
			Type: corev1.SeccompProfileTypeRuntimeDefault,
		},
	}
}

func containerSecurityContext() *corev1.SecurityContext {
	return &corev1.SecurityContext{
		AllowPrivilegeEscalation: boolPtr(false),
		Capabilities:             &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}},
		ReadOnlyRootFilesystem:   boolPtr(true),
	}
}

func boolPtr(b bool) *bool { return &b }

func tmpVolume() ([]corev1.Volume, []corev1.VolumeMount) {
	return []corev1.Volume{{Name: "tmp", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{}}}},
		[]corev1.VolumeMount{{Name: "tmp", MountPath: "/tmp"}}
}

func healthProbes() (*corev1.Probe, *corev1.Probe) {
	liveness := &corev1.Probe{
		ProbeHandler:        corev1.ProbeHandler{HTTPGet: &corev1.HTTPGetAction{Path: healthzPath, Port: intstr.FromString("http")}},
		InitialDelaySeconds: 5,
		PeriodSeconds:       15,
	}
	readiness := &corev1.Probe{
		ProbeHandler:        corev1.ProbeHandler{HTTPGet: &corev1.HTTPGetAction{Path: healthzPath, Port: intstr.FromString("http")}},
		InitialDelaySeconds: 5,
		PeriodSeconds:       10,
	}
	return liveness, readiness
}

func desiredServiceAccount(agent *zunov1alpha1.AIAgent, component string) *corev1.ServiceAccount {
	name := agent.Spec.AgentName + "-" + component
	return &corev1.ServiceAccount{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: agent.Spec.TargetNamespace,
			Labels:    commonLabels(agent.Spec.AgentName, component),
		},
		AutomountServiceAccountToken: boolPtr(false),
	}
}

func desiredFrontendDeployment(agent *zunov1alpha1.AIAgent, cfg OperatorConfig) *appsv1.Deployment {
	name := agent.Spec.AgentName + "-frontend"
	labels := commonLabels(agent.Spec.AgentName, "frontend")
	selector := map[string]string{labelComponent: "frontend", labelAgent: agent.Spec.AgentName}
	volumes, mounts := tmpVolume()
	liveness, readiness := healthProbes()

	env := []corev1.EnvVar{
		{Name: "ACTIVE_AGENT", Value: agent.Spec.AgentName},
		{Name: "KEYCLOAK_ISSUER_URL", Value: cfg.keycloakIssuerURL()},
		{Name: "KEYCLOAK_JWKS_URL", Value: cfg.KeycloakJWKSURL},
		{Name: "OIDC_CLIENT_ID", Value: agent.Spec.Frontend.OIDCClientID},
		{Name: "SELF_BASE_URL", Value: "https://" + routeHost(agent, cfg)},
		{Name: "BFF_BASE_URL", Value: "http://" + agent.Spec.AgentName + "-bff." + agent.Spec.TargetNamespace + ".svc.cluster.local:8080"},
		{Name: "SESSION_MAX_LIFETIME_SECONDS", Value: cfg.SessionMaxLifetimeSeconds},
		{Name: "REDIS_ADDR", Value: cfg.RedisAddr},
		secretEnvVar("OIDC_CLIENT_SECRET", name+"-secrets", "OIDC_CLIENT_SECRET"),
		secretEnvVar("SESSION_HMAC_SECRET", name+"-secrets", "SESSION_HMAC_SECRET"),
		secretEnvVar("SESSION_ENCRYPTION_KEY", name+"-secrets", "SESSION_ENCRYPTION_KEY"),
		secretEnvVar("REDIS_PASSWORD", name+"-secrets", "REDIS_PASSWORD"),
	}

	return &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: agent.Spec.TargetNamespace, Labels: labels},
		Spec: appsv1.DeploymentSpec{
			Replicas: replicasOrDefault(agent.Spec.Frontend.Replicas),
			Selector: &metav1.LabelSelector{MatchLabels: selector},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{Labels: selector},
				Spec: corev1.PodSpec{
					ServiceAccountName:           name,
					PriorityClassName:            priorityClass,
					AutomountServiceAccountToken: boolPtr(false),
					SecurityContext:              podSecurityContext(),
					Volumes:                      volumes,
					Containers: []corev1.Container{{
						Name:            "frontend",
						Image:           imageString(agent.Spec.Frontend.Image),
						ImagePullPolicy: corev1.PullAlways,
						SecurityContext: containerSecurityContext(),
						Ports:           []corev1.ContainerPort{{Name: "http", ContainerPort: containerPort}},
						Env:             env,
						VolumeMounts:    mounts,
						LivenessProbe:   liveness,
						ReadinessProbe:  readiness,
						Resources:       toCoreResources(agent.Spec.Frontend.Resources),
					}},
				},
			},
		},
	}
}

func desiredBFFDeployment(agent *zunov1alpha1.AIAgent, cfg OperatorConfig) *appsv1.Deployment {
	name := agent.Spec.AgentName + "-bff"
	labels := commonLabels(agent.Spec.AgentName, "bff")
	selector := map[string]string{labelComponent: "bff", labelAgent: agent.Spec.AgentName}
	volumes, mounts := tmpVolume()
	liveness, readiness := healthProbes()

	env := []corev1.EnvVar{
		{Name: "AGENT_NAME", Value: agent.Spec.AgentName},
		{Name: "KEYCLOAK_ISSUER_URL", Value: cfg.keycloakIssuerURL()},
		{Name: "KEYCLOAK_JWKS_URL", Value: cfg.KeycloakJWKSURL},
		{Name: "OIDC_AUDIENCE", Value: agent.Spec.BFF.OIDCAudience},
		{Name: "AGENT_RUNTIME_BASE_URL", Value: cfg.AgentRuntimeBaseURL},
	}

	return &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: agent.Spec.TargetNamespace, Labels: labels},
		Spec: appsv1.DeploymentSpec{
			Replicas: replicasOrDefault(agent.Spec.BFF.Replicas),
			Selector: &metav1.LabelSelector{MatchLabels: selector},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{Labels: selector},
				Spec: corev1.PodSpec{
					ServiceAccountName:           name,
					PriorityClassName:            priorityClass,
					AutomountServiceAccountToken: boolPtr(false),
					SecurityContext:              podSecurityContext(),
					Volumes:                      volumes,
					Containers: []corev1.Container{{
						Name:            "bff",
						Image:           imageString(agent.Spec.BFF.Image),
						ImagePullPolicy: corev1.PullAlways,
						SecurityContext: containerSecurityContext(),
						Ports:           []corev1.ContainerPort{{Name: "http", ContainerPort: containerPort}},
						Env:             env,
						VolumeMounts:    mounts,
						LivenessProbe:   liveness,
						ReadinessProbe:  readiness,
						Resources:       toCoreResources(agent.Spec.BFF.Resources),
					}},
				},
			},
		},
	}
}

func secretEnvVar(envName, secretName, key string) corev1.EnvVar {
	return corev1.EnvVar{
		Name: envName,
		ValueFrom: &corev1.EnvVarSource{
			SecretKeyRef: &corev1.SecretKeySelector{
				LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
				Key:                  key,
			},
		},
	}
}

func desiredService(agent *zunov1alpha1.AIAgent, component string) *corev1.Service {
	name := agent.Spec.AgentName + "-" + component
	selector := map[string]string{labelComponent: component, labelAgent: agent.Spec.AgentName}
	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: agent.Spec.TargetNamespace,
			Labels:    commonLabels(agent.Spec.AgentName, component),
		},
		Spec: corev1.ServiceSpec{
			Selector: selector,
			Ports:    []corev1.ServicePort{{Name: "http", Port: containerPort, TargetPort: intstr.FromString("http")}},
		},
	}
}

// desiredBFFNetworkPolicy grants the agent's own frontend (the real chat
// path) and the acceptance-gate Job ingress to the BFF. VERIFIED live
// 2026-08-16 (Tekos incident): this previously only listed acceptance-gate,
// so the frontend's own calls to the BFF were silently dropped by the
// implicit default-deny (Kubernetes denies everything not explicitly
// allowed once any NetworkPolicy selects a pod) - every real chat turn
// timed out at the TCP level. The acceptance-gate suite never caught this
// because it calls the BFF directly, bypassing the frontend.
func desiredBFFNetworkPolicy(agent *zunov1alpha1.AIAgent) *networkingv1.NetworkPolicy {
	name := agent.Spec.AgentName + "-bff"
	podSelector := map[string]string{labelComponent: "bff", labelAgent: agent.Spec.AgentName}
	frontendSelector := map[string]string{labelComponent: "frontend", labelAgent: agent.Spec.AgentName}
	tcp := corev1.ProtocolTCP
	port := intstr.FromInt(containerPort)
	return &networkingv1.NetworkPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: agent.Spec.TargetNamespace,
			Labels:    map[string]string{labelManagedBy: managedByValue},
		},
		Spec: networkingv1.NetworkPolicySpec{
			PodSelector: metav1.LabelSelector{MatchLabels: podSelector},
			PolicyTypes: []networkingv1.PolicyType{networkingv1.PolicyTypeIngress},
			Ingress: []networkingv1.NetworkPolicyIngressRule{{
				From: []networkingv1.NetworkPolicyPeer{
					{PodSelector: &metav1.LabelSelector{MatchLabels: frontendSelector}},
					{PodSelector: &metav1.LabelSelector{MatchLabels: map[string]string{"app.kubernetes.io/name": "acceptance-gate"}}},
				},
				Ports: []networkingv1.NetworkPolicyPort{{Protocol: &tcp, Port: &port}},
			}},
		},
	}
}

// desiredOKFReferenceConfigMap is the "OKF bundle ConfigMap/reference"
// CONTRACT.md's ownership model names: informational metadata only
// (bundle path, declared bindings) - never OKF task/prompt content
// itself, which stays in Git under okfBundleRef and is loaded into the
// shared Agent Runtime image at build time, not mounted per agent
// instance.
func desiredOKFReferenceConfigMap(agent *zunov1alpha1.AIAgent) *corev1.ConfigMap {
	return &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      agent.Spec.AgentName + "-okf-ref",
			Namespace: agent.Spec.TargetNamespace,
			Labels:    commonLabels(agent.Spec.AgentName, "okf-ref"),
		},
		Data: map[string]string{
			"agentName":            agent.Spec.AgentName,
			"okfBundleRef":         agent.Spec.OKFBundleRef,
			"modelPolicyRef":       agent.Spec.ModelPolicyRef,
			"evaluationProfileRef": agent.Spec.EvaluationProfileRef,
			"knowledgeDomains":     joinCSV(agent.Spec.KnowledgeDomains),
			"toolCapabilities":     joinCSV(agent.Spec.ToolCapabilities),
		},
	}
}

func joinCSV(items []string) string {
	out := ""
	for i, item := range items {
		if i > 0 {
			out += ","
		}
		out += item
	}
	return out
}

var routeGVK = schema.GroupVersionKind{Group: "route.openshift.io", Version: "v1", Kind: "Route"}

func desiredFrontendRoute(agent *zunov1alpha1.AIAgent, cfg OperatorConfig) *unstructured.Unstructured {
	name := agent.Spec.AgentName + "-frontend"
	route := &unstructured.Unstructured{}
	route.SetGroupVersionKind(routeGVK)
	route.SetName(name)
	route.SetNamespace(agent.Spec.TargetNamespace)
	route.SetLabels(commonLabels(agent.Spec.AgentName, "frontend"))
	_ = unstructured.SetNestedField(route.Object, routeHost(agent, cfg), "spec", "host")
	_ = unstructured.SetNestedField(route.Object, "Service", "spec", "to", "kind")
	_ = unstructured.SetNestedField(route.Object, name, "spec", "to", "name")
	_ = unstructured.SetNestedField(route.Object, "http", "spec", "port", "targetPort")
	_ = unstructured.SetNestedField(route.Object, "edge", "spec", "tls", "termination")
	_ = unstructured.SetNestedField(route.Object, "Redirect", "spec", "tls", "insecureEdgeTerminationPolicy")
	return route
}

var externalSecretGVK = schema.GroupVersionKind{Group: "external-secrets.io", Version: "v1beta1", Kind: "ExternalSecret"}

func desiredFrontendExternalSecret(agent *zunov1alpha1.AIAgent) *unstructured.Unstructured {
	name := agent.Spec.AgentName + "-frontend-secrets"
	es := &unstructured.Unstructured{}
	es.SetGroupVersionKind(externalSecretGVK)
	es.SetName(name)
	es.SetNamespace(agent.Spec.TargetNamespace)
	es.SetLabels(commonLabels(agent.Spec.AgentName, "frontend"))

	_ = unstructured.SetNestedField(es.Object, "1h", "spec", "refreshInterval")
	_ = unstructured.SetNestedMap(es.Object, map[string]interface{}{
		"name": "vault-backend",
		"kind": "ClusterSecretStore",
	}, "spec", "secretStoreRef")
	_ = unstructured.SetNestedMap(es.Object, map[string]interface{}{
		"name":           name,
		"creationPolicy": "Owner",
	}, "spec", "target")

	data := []interface{}{
		map[string]interface{}{
			"secretKey": "OIDC_CLIENT_SECRET",
			"remoteRef": map[string]interface{}{"key": vaultOIDCClientSecretPath(agent.Spec.AgentName), "property": "client_secret"},
		},
		map[string]interface{}{
			"secretKey": "SESSION_HMAC_SECRET",
			"remoteRef": map[string]interface{}{"key": vaultSessionSecretPath(agent.Spec.AgentName), "property": "hmac_secret"},
		},
		map[string]interface{}{
			"secretKey": "SESSION_ENCRYPTION_KEY",
			"remoteRef": map[string]interface{}{"key": vaultSessionSecretPath(agent.Spec.AgentName), "property": "encryption_key"},
		},
		map[string]interface{}{
			"secretKey": "REDIS_PASSWORD",
			"remoteRef": map[string]interface{}{"key": vaultRedisSecretPath, "property": "password"},
		},
	}
	_ = unstructured.SetNestedSlice(es.Object, data, "spec", "data")

	return es
}
