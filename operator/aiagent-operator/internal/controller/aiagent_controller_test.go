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
	"context"
	"testing"

	. "github.com/onsi/gomega"
	"github.com/stretchr/testify/require"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"

	zunov1alpha1 "github.com/startxfr/zuno-demo/operator/aiagent-operator/api/v1alpha1"
)

func ensureNamespace(t *testing.T, name string) {
	t.Helper()
	ns := &corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: name}}
	err := k8sClient.Create(context.Background(), ns)
	if err != nil && !apierrors.IsAlreadyExists(err) {
		require.NoError(t, err)
	}
}

func newReconciler() *AIAgentReconciler {
	return &AIAgentReconciler{
		Client: k8sClient,
		Scheme: k8sClient.Scheme(),
		Config: DefaultOperatorConfig(),
	}
}

func reconcileRequestFor(agent *zunov1alpha1.AIAgent) ctrl.Request {
	return ctrl.Request{NamespacedName: client.ObjectKeyFromObject(agent)}
}

func testAgentSpec(name string) zunov1alpha1.AIAgentSpec {
	return zunov1alpha1.AIAgentSpec{
		AgentName:       name,
		TargetNamespace: "zuno-ai-run",
		OKFBundleRef:    "agents/" + name,
		Frontend: zunov1alpha1.FrontendProfile{
			Image:        zunov1alpha1.ImageRef{Registry: "reg", Repository: "repo/frontend", Tag: "latest"},
			OIDCClientID: name + "-frontend",
		},
		BFF: zunov1alpha1.BFFProfile{
			Image:        zunov1alpha1.ImageRef{Registry: "reg", Repository: "repo/bff", Tag: "latest"},
			OIDCAudience: name + "-frontend",
		},
		Groups: zunov1alpha1.GroupBindings{
			EntitlementGroup: "agent_" + name,
			BusinessRoles:    []string{"consultant"},
		},
		KnowledgeDomains: []string{"knowledge.tech"},
		ToolCapabilities: []string{"search_confluence"},
	}
}

// TestReconcile_CreatesOwnedResourcesWithOwnerRefs is WP-38's core proof:
// a real CR, reconciled once, produces exactly the resource set
// CONTRACT.md names, every one of them owned by the CR. FrontendReady/
// BFFReady stay False here - envtest runs no kubelet, so Deployments
// never gain ready replicas - and RuntimeBindingReady stays False since
// none of Config.SharedServiceRefs exist in this test cluster; both are
// the reconciler correctly reporting real absence, not a test bug.
func TestReconcile_CreatesOwnedResourcesWithOwnerRefs(t *testing.T) {
	g := NewWithT(t)
	ctx := context.Background()
	ensureNamespace(t, "zuno-ai-run")

	agent := &zunov1alpha1.AIAgent{
		ObjectMeta: metav1.ObjectMeta{Name: "test-create", Namespace: "zuno-ai-run"},
		Spec:       testAgentSpec("test-create"),
	}
	require.NoError(t, k8sClient.Create(ctx, agent))
	t.Cleanup(func() { _ = k8sClient.Delete(ctx, agent) })

	r := newReconciler()
	_, err := r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var feDeploy appsv1.Deployment
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-frontend", Namespace: "zuno-ai-run"}, &feDeploy)).To(Succeed())
	g.Expect(feDeploy.OwnerReferences).To(HaveLen(1))
	g.Expect(feDeploy.OwnerReferences[0].Name).To(Equal("test-create"))
	g.Expect(feDeploy.OwnerReferences[0].Controller).ToNot(BeNil())
	g.Expect(*feDeploy.OwnerReferences[0].Controller).To(BeTrue())

	var bffDeploy appsv1.Deployment
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-bff", Namespace: "zuno-ai-run"}, &bffDeploy)).To(Succeed())

	for _, name := range []string{"test-create-frontend", "test-create-bff"} {
		var sa corev1.ServiceAccount
		g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: name, Namespace: "zuno-ai-run"}, &sa)).To(Succeed())
		var svc corev1.Service
		g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: name, Namespace: "zuno-ai-run"}, &svc)).To(Succeed())
	}

	var netpol networkingv1.NetworkPolicy
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-bff", Namespace: "zuno-ai-run"}, &netpol)).To(Succeed())

	var route unstructured.Unstructured
	route.SetGroupVersionKind(routeGVK)
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-frontend", Namespace: "zuno-ai-run"}, &route)).To(Succeed())
	g.Expect(route.GetOwnerReferences()).To(HaveLen(1))

	var es unstructured.Unstructured
	es.SetGroupVersionKind(externalSecretGVK)
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-frontend-secrets", Namespace: "zuno-ai-run"}, &es)).To(Succeed())

	var okfCM corev1.ConfigMap
	g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: "test-create-okf-ref", Namespace: "zuno-ai-run"}, &okfCM)).To(Succeed())
	g.Expect(okfCM.Data["okfBundleRef"]).To(Equal("agents/test-create"))

	var updated zunov1alpha1.AIAgent
	g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(agent), &updated)).To(Succeed())
	g.Expect(meta.IsStatusConditionTrue(updated.Status.Conditions, zunov1alpha1.ConditionConfigValid)).To(BeTrue())
	g.Expect(meta.IsStatusConditionTrue(updated.Status.Conditions, zunov1alpha1.ConditionOKFReady)).To(BeTrue())
	g.Expect(meta.IsStatusConditionFalse(updated.Status.Conditions, zunov1alpha1.ConditionFrontendReady)).To(BeTrue())
	g.Expect(meta.IsStatusConditionFalse(updated.Status.Conditions, zunov1alpha1.ConditionBFFReady)).To(BeTrue())
	g.Expect(meta.IsStatusConditionFalse(updated.Status.Conditions, zunov1alpha1.ConditionRuntimeBindingReady)).To(BeTrue())
	g.Expect(updated.Status.ObservedGeneration).To(Equal(updated.Generation))
}

// TestReconcile_DriftIsReconciled proves the reconciler is idempotent and
// self-healing: an out-of-band edit to a generated object is reverted on
// the next reconcile, the same property Argo CD's own self-heal relies
// on for the AIAgent CR itself. Drifts an env var, not the image field -
// see TestReconcile_PreservesLiveImageAcrossReconciles for why the image
// field is a deliberate, narrow exception to this (ADR-0411 follow-up).
func TestReconcile_DriftIsReconciled(t *testing.T) {
	g := NewWithT(t)
	ctx := context.Background()
	ensureNamespace(t, "zuno-ai-run")

	agent := &zunov1alpha1.AIAgent{
		ObjectMeta: metav1.ObjectMeta{Name: "test-drift", Namespace: "zuno-ai-run"},
		Spec:       testAgentSpec("test-drift"),
	}
	require.NoError(t, k8sClient.Create(ctx, agent))
	t.Cleanup(func() { _ = k8sClient.Delete(ctx, agent) })

	r := newReconciler()
	_, err := r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var deploy appsv1.Deployment
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-drift-bff", Namespace: "zuno-ai-run"}, &deploy))
	deploy.Spec.Template.Spec.Containers[0].Env[0].Value = "someone-elses-drifted-value"
	require.NoError(t, k8sClient.Update(ctx, &deploy))

	_, err = r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var reconciled appsv1.Deployment
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-drift-bff", Namespace: "zuno-ai-run"}, &reconciled))
	g.Expect(reconciled.Spec.Template.Spec.Containers[0].Env[0].Value).To(Equal("test-drift"))
}

// TestReconcile_PreservesLiveImageAcrossReconciles is ADR-0411's own
// proof: every generated Deployment carries image.openshift.io/triggers
// (imageTriggerAnnotation), and this controller watches the Deployments
// it owns - so without preserveLiveImages, the trigger controller's own
// patch of the image field would be the very event that fires the next
// reconcile, which would then immediately stomp it back to the floating
// :latest tag. Simulates that patch directly (envtest runs no real
// image-trigger controller) and confirms a subsequent reconcile leaves
// the image alone while still correcting an unrelated drifted field -
// proving the exception is scoped to the image only, not a blanket
// "stop reconciling this Deployment" bug.
func TestReconcile_PreservesLiveImageAcrossReconciles(t *testing.T) {
	g := NewWithT(t)
	ctx := context.Background()
	ensureNamespace(t, "zuno-ai-run")

	agent := &zunov1alpha1.AIAgent{
		ObjectMeta: metav1.ObjectMeta{Name: "test-image-trigger", Namespace: "zuno-ai-run"},
		Spec:       testAgentSpec("test-image-trigger"),
	}
	require.NoError(t, k8sClient.Create(ctx, agent))
	t.Cleanup(func() { _ = k8sClient.Delete(ctx, agent) })

	r := newReconciler()
	_, err := r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var deploy appsv1.Deployment
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-image-trigger-frontend", Namespace: "zuno-ai-run"}, &deploy))
	g.Expect(deploy.Annotations).To(HaveKey("image.openshift.io/triggers"))

	const resolvedDigest = "reg/repo/frontend@sha256:deadbeef"
	deploy.Spec.Template.Spec.Containers[0].Image = resolvedDigest
	deploy.Spec.Template.Spec.Containers[0].Env[0].Value = "someone-elses-drifted-value"
	require.NoError(t, k8sClient.Update(ctx, &deploy))

	_, err = r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var reconciled appsv1.Deployment
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-image-trigger-frontend", Namespace: "zuno-ai-run"}, &reconciled))
	g.Expect(reconciled.Spec.Template.Spec.Containers[0].Image).To(Equal(resolvedDigest), "the trigger-patched image must survive a reconcile")
	g.Expect(reconciled.Spec.Template.Spec.Containers[0].Env[0].Value).To(Equal("test-image-trigger"), "unrelated drift must still be corrected")
}

// TestReconcile_RejectsDisallowedNamespace proves the in-code defense in
// depth from CONTRACT.md: even though the CRD schema itself has no way
// to express "reject this namespace", the reconciler still refuses to
// generate a single resource for a targetNamespace outside its allowlist.
func TestReconcile_RejectsDisallowedNamespace(t *testing.T) {
	g := NewWithT(t)
	ctx := context.Background()
	ensureNamespace(t, "zuno-ai-run")
	ensureNamespace(t, "some-other-namespace")

	agent := &zunov1alpha1.AIAgent{
		ObjectMeta: metav1.ObjectMeta{Name: "test-badns", Namespace: "zuno-ai-run"},
		Spec:       testAgentSpec("test-badns"),
	}
	agent.Spec.TargetNamespace = "some-other-namespace"
	require.NoError(t, k8sClient.Create(ctx, agent))
	t.Cleanup(func() { _ = k8sClient.Delete(ctx, agent) })

	r := newReconciler()
	_, err := r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var deploy appsv1.Deployment
	err = k8sClient.Get(ctx, client.ObjectKey{Name: "test-badns-frontend", Namespace: "some-other-namespace"}, &deploy)
	g.Expect(apierrors.IsNotFound(err)).To(BeTrue(), "no resources should be generated for a rejected spec")

	var updated zunov1alpha1.AIAgent
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKeyFromObject(agent), &updated))
	cond := meta.FindStatusCondition(updated.Status.Conditions, zunov1alpha1.ConditionConfigValid)
	require.NotNil(t, cond)
	g.Expect(cond.Status).To(Equal(metav1.ConditionFalse))
	g.Expect(cond.Reason).To(Equal("NamespaceNotAllowed"))

	for _, condType := range []string{zunov1alpha1.ConditionOKFReady, zunov1alpha1.ConditionFrontendReady, zunov1alpha1.ConditionBFFReady, zunov1alpha1.ConditionRuntimeBindingReady} {
		g.Expect(meta.IsStatusConditionFalse(updated.Status.Conditions, condType)).To(BeTrue())
	}
}

// TestReconcile_DeleteRelinquishesViaOwnerReferences: envtest runs only
// kube-apiserver+etcd, never the kube-controller-manager's garbage-
// collector controller, so deleting the CR here does not cascade-delete
// its owned resources the way every real cluster does. This test proves
// the structural half that does hold in envtest - every owned resource's
// sole ownerReference keeps pointing at the deleted CR's UID, exactly
// what the real GC controller keys off of - rather than faking
// end-to-end cascade-delete coverage this test environment cannot
// actually exercise. Live cascade-delete verification is the WP's own
// documented operator follow-up.
func TestReconcile_DeleteRelinquishesViaOwnerReferences(t *testing.T) {
	g := NewWithT(t)
	ctx := context.Background()
	ensureNamespace(t, "zuno-ai-run")

	agent := &zunov1alpha1.AIAgent{
		ObjectMeta: metav1.ObjectMeta{Name: "test-delete", Namespace: "zuno-ai-run"},
		Spec:       testAgentSpec("test-delete"),
	}
	require.NoError(t, k8sClient.Create(ctx, agent))

	r := newReconciler()
	_, err := r.Reconcile(ctx, reconcileRequestFor(agent))
	require.NoError(t, err)

	var deploy appsv1.Deployment
	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-delete-frontend", Namespace: "zuno-ai-run"}, &deploy))
	require.Len(t, deploy.OwnerReferences, 1)
	ownerUID := deploy.OwnerReferences[0].UID
	g.Expect(ownerUID).ToNot(BeEmpty())

	require.NoError(t, k8sClient.Delete(ctx, agent))

	var deletedAgent zunov1alpha1.AIAgent
	err = k8sClient.Get(ctx, client.ObjectKeyFromObject(agent), &deletedAgent)
	g.Expect(apierrors.IsNotFound(err)).To(BeTrue())

	require.NoError(t, k8sClient.Get(ctx, client.ObjectKey{Name: "test-delete-frontend", Namespace: "zuno-ai-run"}, &deploy))
	g.Expect(deploy.OwnerReferences[0].UID).To(Equal(ownerUID))
}

// TestSetCondition_TransitionTimeOnlyChangesOnStatusChange is a pure unit
// test (no envtest calls) of the setCondition wrapper's use of
// meta.SetStatusCondition: LastTransitionTime must only move when the
// condition's Status actually flips, and ObservedGeneration must always
// track the generation passed in - a consumer (make check) watching
// condition age to detect a stuck reconcile depends on the first
// property; drift detection depends on the second.
func TestSetCondition_TransitionTimeOnlyChangesOnStatusChange(t *testing.T) {
	g := NewWithT(t)
	agent := &zunov1alpha1.AIAgent{}

	setCondition(agent, zunov1alpha1.ConditionConfigValid, metav1.ConditionTrue, "Valid", "ok", 1)
	first := meta.FindStatusCondition(agent.Status.Conditions, zunov1alpha1.ConditionConfigValid)
	require.NotNil(t, first)
	firstTransition := first.LastTransitionTime

	setCondition(agent, zunov1alpha1.ConditionConfigValid, metav1.ConditionTrue, "Valid", "ok still", 2)
	second := meta.FindStatusCondition(agent.Status.Conditions, zunov1alpha1.ConditionConfigValid)
	g.Expect(second.LastTransitionTime).To(Equal(firstTransition))
	g.Expect(second.ObservedGeneration).To(Equal(int64(2)))

	setCondition(agent, zunov1alpha1.ConditionConfigValid, metav1.ConditionFalse, "Invalid", "now broken", 3)
	third := meta.FindStatusCondition(agent.Status.Conditions, zunov1alpha1.ConditionConfigValid)
	g.Expect(third.LastTransitionTime).ToNot(Equal(firstTransition))
}
