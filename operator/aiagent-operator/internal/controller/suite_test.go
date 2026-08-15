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

// Package controller: suite_test.go bootstraps a real envtest control
// plane (a genuine kube-apiserver + etcd, no Kubernetes controllers
// running on top - so no built-in garbage-collector controller either,
// see TestReconcile_Delete's own comment for what that does and does not
// let us prove) for the tests in this package.
//
// D8 (roadmap plan): plain `testing` + envtest, not a Ginkgo BDD suite -
// this repo's Go components stay close to stdlib testing wherever a real
// envtest setup allows it (kubebuilder's own default scaffold uses
// Ginkgo; this file replaces that default). Assertions use Gomega's
// matcher library directly against *testing.T via gomega.NewWithT, which
// is Gomega's own supported way to use its matchers outside Ginkgo.
package controller

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/envtest"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"

	zunov1alpha1 "github.com/startxfr/zuno-demo/operator/aiagent-operator/api/v1alpha1"
)

var (
	testEnv   *envtest.Environment
	testCfg   *rest.Config
	k8sClient client.Client
)

func TestMain(m *testing.M) {
	logf.SetLogger(zap.New(zap.WriteTo(os.Stderr), zap.UseDevMode(true)))

	testEnv = &envtest.Environment{
		CRDDirectoryPaths: []string{
			filepath.Join("..", "..", "config", "crd", "bases"),
			filepath.Join("..", "..", "config", "crd", "test-fixtures"),
		},
		ErrorIfCRDPathMissing: true,
	}
	if dir := firstEnvtestBinaryDir(); dir != "" {
		testEnv.BinaryAssetsDirectory = dir
	}

	var err error
	testCfg, err = testEnv.Start()
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to start envtest environment:", err)
		os.Exit(1)
	}

	if err := zunov1alpha1.AddToScheme(scheme.Scheme); err != nil {
		fmt.Fprintln(os.Stderr, "failed to register AIAgent scheme:", err)
		_ = testEnv.Stop()
		os.Exit(1)
	}

	k8sClient, err = client.New(testCfg, client.Options{Scheme: scheme.Scheme})
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to create test client:", err)
		_ = testEnv.Stop()
		os.Exit(1)
	}

	code := m.Run()

	if err := testEnv.Stop(); err != nil {
		fmt.Fprintln(os.Stderr, "failed to stop envtest environment:", err)
	}
	os.Exit(code)
}

// firstEnvtestBinaryDir locates the kube-apiserver/etcd binaries `make
// setup-envtest` downloads, mirroring kubebuilder's own generated helper
// so `go test ./...` works the same whether invoked via `make test` or
// directly from an IDE/CLI.
func firstEnvtestBinaryDir() string {
	basePath := filepath.Join("..", "..", "bin", "k8s")
	entries, err := os.ReadDir(basePath)
	if err != nil {
		return ""
	}
	for _, entry := range entries {
		if entry.IsDir() {
			return filepath.Join(basePath, entry.Name())
		}
	}
	return ""
}
