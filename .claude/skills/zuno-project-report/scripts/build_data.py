import json,subprocess,re,datetime,os
raw=json.load(open('raw.json')); comps=json.load(open('comps.json'))
sh=lambda c:subprocess.run(c,shell=True,capture_output=True,text=True,cwd=os.environ.get('REPO','.')).stdout
tags=[l.split() for l in sh("git tag --sort=creatordate --format='%(refname:short) %(creatordate:short)' | grep '^v'").splitlines()]
daily={}
for d in sh("git log --format=%ad --date=short").split(): daily[d]=daily.get(d,0)+1
goals={'v0':"Seven-day internal vertical slice and a five-agent demo, Tekos first.",
'v0.1':"Industrialisation: HA shared services, resumable workflows, automated ingestion and evaluation, stronger signing, SecNumCloud hardening.",
'v0.2':"Knowledge governance: logical domains, authorisation by intersection of policies, multi-domain RAG. AAP becomes a day-1 component.",
'v0.3':"Multi-agent deployment: four agents, graph shapes, AIAgent CRD and operator, LoRA/PEFT, benchmark-driven routing.",
'v0.4':"Agent-to-agent: A2A, propagated identity, controlled shared memory, delegation traceability, model fleet and observability.",
'v0.5':"OpenShift AI's MaaS governance plane in service, and the RHOAI monitoring stack (Perses, traces per run).",
'v0.6':"Close of the reprioritisation batch: ingestion cadences, Salesforce separation, conversation sharing.",
'v0.7':"Release and supply-chain automation, RHOAI 3.5 surfaces, TrustyAI, model autoscaling, ExternalModels.",
'v0.8':"Proof of portability: full redeployment on demo333 (days 0 to 3), S3 migration, parameterised cluster values.",
'v0.9':"RHTAS as the chain of trust, release registry in the cluster, internal/external modes of the components.",
'v0.10':"OKF extraction chain, superseded by v0.12 before it started.",
'v0.11':"UnifAI and unifai-operator become the agent and RAG platform; OKF stays the source of truth of the agents.",
'v0.12':"The agent definitions leave the repository (zuno-demo-agents): signed OCI bundles, OKF 0.3, promotion by pull request.",
'v0.13':"Three experiences on the same governed chain: UnifAI, Open WebUI, OpenClaw.",
'v0.14':"Two more experiences on the same chain: Dify for business teams, kagent for ops.",
'v0.15':"Make the demo dependable: classification floor in the ai-gateway, golden path, freeze window.",
'v0.16':"Harden and govern: security (ADR-0602, 0603), agent lifecycle, delivery rules, world model.",
'v0.17':"Internal/external modes of the day-0 services, remote ArgoCD, Blender 3D experience.",
'OKF v0.1':"Standalone version line of the Open Knowledge Format."}
order=['v0','v0.1','v0.2','v0.3','v0.4','v0.5','v0.6','v0.7','v0.8','v0.9','v0.10','v0.11','v0.12','v0.13','v0.14','v0.15','v0.16','v0.17','OKF v0.1']
adr=[dict(i=a['id'],b=a['band'],s=a['status'],c=a['cls'],t=a['title'],d=a['date'],r=a['retired']) for a in raw['adr']]
amap={a['i']:a for a in adr}
wp=[]
for w in raw['wp']:
    b=next((amap[x]['b'] for x in w['adrs'] if x in amap and not amap[x]['r']),None) or next((amap[x]['b'] for x in w['adrs'] if x in amap),None) or 'No band'
    st=w['state']; k='done' if st=='Done' else 'prog' if st in('Repo work merged','Operator pending','Repo work in review') else 'todo' if st=='Not started' else 'drop'
    wp.append(dict(i=w['id'],b=b,s=st,k=k,t=w['title'],d=w['date'],p=w['phase'],a=w['adrs']))
rc=json.load(open('m_req_cpu.json'))
nodes=json.loads(sh("oc get nodes -o json"))['items']
alloc=sum(float(n['status']['allocatable']['cpu'].replace('m',''))/(1000 if n['status']['allocatable']['cpu'].endswith('m') else 1) for n in nodes)
def gi(s): 
    m=re.match(r'(\d+)(Ki|Mi|Gi)?',s); return int(m[1])/{'Ki':1024**2,'Mi':1024,'Gi':1,None:2**30}[m[2]]
memal=sum(gi(n['status']['allocatable']['memory']) for n in nodes)
mig={}
for n in nodes:
    for k,v in n['status']['capacity'].items():
        if k.startswith('nvidia.com/mig'): mig[k.split('/')[1]]=mig.get(k.split('/')[1],0)+int(v)
cluster=dict(nodes=len(nodes),gpuNodes=sum(1 for n in nodes if 'g7e' in n['metadata']['labels'].get('node.kubernetes.io/instance-type','')),cpuAlloc=round(alloc,1),memAlloc=round(memal),mig=mig,
 cpuReqAll=round(sum(rc.values()),1),memReqAll=round(sum(json.load(open('m_req_mem.json')).values())/2**30),pvcAll=round(sum(json.load(open('m_pvc.json')).values())/2**30),
 commits=int(sh('git rev-list --count HEAD')),snap=datetime.date.today().isoformat())
print(cluster,len(tags))
data=dict(adr=adr,wp=wp,tags=tags,daily=daily,goals=goals,order=order,comps=comps,cluster=cluster)
json.dump(data,open('data.json','w'),ensure_ascii=False,separators=(',',':'))
print(len(open('data.json').read()))
