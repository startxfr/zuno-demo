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
	"fmt"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	zunov1alpha1 "github.com/startxfr/zuno-demo/operator/aiagent-operator/api/v1alpha1"
)

// AIAgentReconciler reconciles an AIAgent object into the resource set
// CONTRACT.md's ownership model enumerates - nothing more. It never
// installs shared platform services, never writes OKF task content, and
// never touches any resource without this CR's own controller
// OwnerReference on it (ADR-0327's boundary, restated in
// operator/aiagent-operator/CONTRACT.md).
type AIAgentReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	Config OperatorConfig
}

// +kubebuilder:rbac:groups=zuno.zuno.ai,resources=aiagents,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=zuno.zuno.ai,resources=aiagents/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=zuno.zuno.ai,resources=aiagents/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services;serviceaccounts;configmaps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch
// +kubebuilder:rbac:groups=networking.k8s.io,resources=networkpolicies,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=route.openshift.io,resources=routes,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=external-secrets.io,resources=externalsecrets,verbs=get;list;watch;create;update;patch;delete

// Reconcile drives one AIAgent CR toward the resource set CONTRACT.md
// names. Every generated object carries a controller OwnerReference back
// to this CR, so delete/suspend is standard Kubernetes garbage collection
// - no finalizer needed, and nothing outside what this reconciler itself
// created is ever touched (shared platform Services/Secrets/Vault
// content included).
func (r *AIAgentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := logf.FromContext(ctx)

	var agent zunov1alpha1.AIAgent
	if err := r.Get(ctx, req.NamespacedName, &agent); err != nil {
		if apierrors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	cfg := r.Config

	// Defense in depth over the CRD schema (ADR-0327): the schema has no
	// field to smuggle a cross-namespace or secret-shaped value through,
	// but the one namespace-intent field the schema DOES expose
	// (targetNamespace) is re-checked here against an explicit allowlist
	// before a single resource is generated.
	if !cfg.namespaceAllowed(agent.Spec.TargetNamespace) {
		msg := fmt.Sprintf("targetNamespace %q is not in this operator's allowed namespace list %v", agent.Spec.TargetNamespace, cfg.AllowedTargetNamespaces)
		setCondition(&agent, zunov1alpha1.ConditionConfigValid, metav1.ConditionFalse, "NamespaceNotAllowed", msg, agent.Generation)
		for _, cond := range []string{zunov1alpha1.ConditionOKFReady, zunov1alpha1.ConditionFrontendReady, zunov1alpha1.ConditionBFFReady, zunov1alpha1.ConditionRuntimeBindingReady} {
			setCondition(&agent, cond, metav1.ConditionFalse, "ConfigInvalid", "skipped: spec failed in-code validation", agent.Generation)
		}
		agent.Status.ObservedGeneration = agent.Generation
		if err := r.Status().Update(ctx, &agent); err != nil {
			return ctrl.Result{}, err
		}
		logger.Info("rejected AIAgent spec", "reason", "NamespaceNotAllowed", "targetNamespace", agent.Spec.TargetNamespace)
		return ctrl.Result{}, nil
	}
	setCondition(&agent, zunov1alpha1.ConditionConfigValid, metav1.ConditionTrue, "Valid", "spec passed in-code validation", agent.Generation)

	for _, component := range []string{"frontend", "bff"} {
		if err := r.applyOwned(ctx, &agent, desiredServiceAccount(&agent, component)); err != nil {
			return ctrl.Result{}, fmt.Errorf("reconciling %s service account: %w", component, err)
		}
	}

	feDeploy := desiredFrontendDeployment(&agent, cfg)
	if err := r.applyOwned(ctx, &agent, feDeploy); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling frontend deployment: %w", err)
	}
	if err := r.applyOwned(ctx, &agent, desiredService(&agent, "frontend")); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling frontend service: %w", err)
	}
	routeErr := r.applyOwned(ctx, &agent, desiredFrontendRoute(&agent, cfg))
	if routeErr != nil && !meta.IsNoMatchError(routeErr) {
		return ctrl.Result{}, fmt.Errorf("reconciling frontend route: %w", routeErr)
	}
	esErr := r.applyOwned(ctx, &agent, desiredFrontendExternalSecret(&agent))
	if esErr != nil && !meta.IsNoMatchError(esErr) {
		return ctrl.Result{}, fmt.Errorf("reconciling frontend external secret: %w", esErr)
	}

	bffDeploy := desiredBFFDeployment(&agent, cfg)
	if err := r.applyOwned(ctx, &agent, bffDeploy); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling bff deployment: %w", err)
	}
	if err := r.applyOwned(ctx, &agent, desiredService(&agent, "bff")); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling bff service: %w", err)
	}
	if err := r.applyOwned(ctx, &agent, desiredBFFNetworkPolicy(&agent)); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling bff network policy: %w", err)
	}
	if err := r.applyOwned(ctx, &agent, desiredOKFReferenceConfigMap(&agent)); err != nil {
		return ctrl.Result{}, fmt.Errorf("reconciling okf reference configmap: %w", err)
	}

	feReady := deploymentReady(ctx, r.Client, feDeploy)
	bffReady := deploymentReady(ctx, r.Client, bffDeploy)

	if feReady && routeErr == nil {
		setCondition(&agent, zunov1alpha1.ConditionFrontendReady, metav1.ConditionTrue, "Ready", "frontend deployment, service and route reconciled and ready", agent.Generation)
	} else if routeErr != nil {
		setCondition(&agent, zunov1alpha1.ConditionFrontendReady, metav1.ConditionFalse, "RouteUnavailable", "route.openshift.io is not available in this cluster: "+routeErr.Error(), agent.Generation)
	} else {
		setCondition(&agent, zunov1alpha1.ConditionFrontendReady, metav1.ConditionFalse, "Reconciling", "waiting for the frontend deployment to become ready", agent.Generation)
	}

	if bffReady {
		setCondition(&agent, zunov1alpha1.ConditionBFFReady, metav1.ConditionTrue, "Ready", "bff deployment and service reconciled and ready", agent.Generation)
	} else {
		setCondition(&agent, zunov1alpha1.ConditionBFFReady, metav1.ConditionFalse, "Reconciling", "waiting for the bff deployment to become ready", agent.Generation)
	}

	// OKFReady only covers reference bookkeeping (this operator is never
	// the source of OKF semantics - ADR-0327's own boundary): the actual
	// bundle is validated by platform/supply-chain/validate_okf_bundle.py
	// at CI time and loaded by Agent Runtime at its own startup.
	setCondition(&agent, zunov1alpha1.ConditionOKFReady, metav1.ConditionTrue, "Referenced",
		fmt.Sprintf("okfBundleRef %q recorded in the generated reference ConfigMap", agent.Spec.OKFBundleRef), agent.Generation)

	missing := missingSharedServices(ctx, r.Client, cfg)
	switch {
	case esErr != nil:
		setCondition(&agent, zunov1alpha1.ConditionRuntimeBindingReady, metav1.ConditionFalse, "NotBound", "external-secrets.io is not available in this cluster: "+esErr.Error(), agent.Generation)
	case len(missing) > 0:
		setCondition(&agent, zunov1alpha1.ConditionRuntimeBindingReady, metav1.ConditionFalse, "NotBound", fmt.Sprintf("shared platform service(s) not found: %v", missing), agent.Generation)
	default:
		setCondition(&agent, zunov1alpha1.ConditionRuntimeBindingReady, metav1.ConditionTrue, "Bound", "shared platform services present and secret binding reconciled", agent.Generation)
	}

	agent.Status.ObservedGeneration = agent.Generation
	if err := r.Status().Update(ctx, &agent); err != nil {
		return ctrl.Result{}, err
	}

	if !feReady || !bffReady {
		return ctrl.Result{RequeueAfter: 15 * time.Second}, nil
	}
	return ctrl.Result{}, nil
}

func setCondition(agent *zunov1alpha1.AIAgent, condType string, status metav1.ConditionStatus, reason, message string, generation int64) {
	meta.SetStatusCondition(&agent.Status.Conditions, metav1.Condition{
		Type:               condType,
		Status:             status,
		Reason:             reason,
		Message:            message,
		ObservedGeneration: generation,
	})
}

// applyOwned sets the controller owner reference then creates or updates
// desired - the single code path every generated resource goes through,
// so every one of them is garbage-collected on CR delete with no
// finalizer required.
func (r *AIAgentReconciler) applyOwned(ctx context.Context, agent *zunov1alpha1.AIAgent, desired client.Object) error {
	if err := controllerutil.SetControllerReference(agent, desired, r.Scheme); err != nil {
		return err
	}
	existing, ok := desired.DeepCopyObject().(client.Object)
	if !ok {
		return fmt.Errorf("object %T does not implement client.Object", desired)
	}
	err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing)
	if apierrors.IsNotFound(err) {
		return r.Create(ctx, desired)
	}
	if err != nil {
		return err
	}
	desired.SetResourceVersion(existing.GetResourceVersion())
	return r.Update(ctx, desired)
}

func deploymentReady(ctx context.Context, c client.Client, desired *appsv1.Deployment) bool {
	var live appsv1.Deployment
	if err := c.Get(ctx, client.ObjectKeyFromObject(desired), &live); err != nil {
		return false
	}
	want := int32(1)
	if desired.Spec.Replicas != nil {
		want = *desired.Spec.Replicas
	}
	return live.Status.ReadyReplicas >= want
}

func missingSharedServices(ctx context.Context, c client.Client, cfg OperatorConfig) []string {
	var missing []string
	for _, ref := range cfg.SharedServiceRefs {
		var svc corev1.Service
		if err := c.Get(ctx, client.ObjectKey{Name: ref.Name, Namespace: ref.Namespace}, &svc); err != nil {
			missing = append(missing, ref.Namespace+"/"+ref.Name)
		}
	}
	return missing
}

// SetupWithManager sets up the controller with the Manager.
func (r *AIAgentReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&zunov1alpha1.AIAgent{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.ServiceAccount{}).
		Owns(&corev1.ConfigMap{}).
		Named("aiagent").
		Complete(r)
}
