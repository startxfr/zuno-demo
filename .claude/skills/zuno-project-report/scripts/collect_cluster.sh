#!/usr/bin/env bash
# Read-only snapshot of the cluster into the current directory (pods.json, pvc.json, m_*.json, p_*.json).
set -euo pipefail
oc whoami >/dev/null || { echo "oc not logged in" >&2; exit 1; }
H=$(oc -n openshift-monitoring get route thanos-querier -o jsonpath='{.spec.host}'); T=$(oc whoami -t)
q(){ # $1 = promql, $2 = label key(s): ns | pod
  curl -sk -H "Authorization: Bearer $T" --data-urlencode "query=$1" "https://$H/api/v1/query" | python3 -c "
import sys,json
d=json.load(sys.stdin)['data']['result']; m=sys.argv[1]
print(json.dumps({(r['metric'].get('namespace','?')+('/'+r['metric'].get('pod','?') if m=='pod' else '')):float(r['value'][1]) for r in d}))" "$2"; }
RUN='(kube_pod_status_phase{phase="Running"}==1)'
q "sum by (namespace)(kube_pod_container_resource_requests{resource=\"cpu\"}*on(namespace,pod)group_left()$RUN)" ns > m_req_cpu.json
q "sum by (namespace)(kube_pod_container_resource_requests{resource=\"memory\"}*on(namespace,pod)group_left()$RUN)" ns > m_req_mem.json
q 'sum by (namespace)(kube_persistentvolumeclaim_resource_requests_storage_bytes)' ns > m_pvc.json
q 'sum by (namespace,pod)(rate(container_cpu_usage_seconds_total{container!="",container!="POD"}[6h]))' pod > p_cpu.json
q 'sum by (namespace,pod)(container_memory_working_set_bytes{container!="",container!="POD"})' pod > p_mem.json
oc get pods -A -o json > pods.json
oc get pvc -A -o json > pvc.json
