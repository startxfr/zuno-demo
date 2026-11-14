import json,subprocess,re,datetime,os
raw=json.load(open('raw.json')); comps=json.load(open('comps.json'))
sh=lambda c:subprocess.run(c,shell=True,capture_output=True,text=True,cwd=os.environ.get('REPO','.')).stdout
tags=[l.split() for l in sh("git tag --sort=creatordate --format='%(refname:short) %(creatordate:short)' | grep '^v'").splitlines()]
daily={}
for d in sh("git log --format=%ad --date=short").split(): daily[d]=daily.get(d,0)+1
goals={'v0':"Tranche verticale interne de 7 jours et démo à cinq agents, Tekos en premier.",
'v0.1':"Industrialisation : services partagés HA, workflows reprenables, ingestion et évaluation automatisées, signature renforcée, durcissement SecNumCloud.",
'v0.2':"Gouvernance des connaissances : domaines logiques, autorisation par intersection de politiques, RAG multi-domaines. AAP devient un composant de jour 1.",
'v0.3':"Déploiement multi-agents : quatre agents, formes de graphes, CRD AIAgent et opérateur, LoRA/PEFT, routage par benchmark.",
'v0.4':"Agent-à-agent : A2A, identité propagée, mémoire partagée contrôlée, traçabilité des délégations, flotte de modèles et observabilité.",
'v0.5':"Plan de gouvernance MaaS d'OpenShift AI en service, et pile de monitoring RHOAI (Perses, traces par run).",
'v0.6':"Clôture du lot de repriorisation : cadences d'ingestion, séparation Salesforce, partage de conversations.",
'v0.7':"Automatisation release et supply-chain, surfaces RHOAI 3.5, TrustyAI, autoscaling des modèles, ExternalModels.",
'v0.8':"Preuve de portabilité : redéploiement complet sur demo333 (jours 0 à 3), migration S3, valeurs de cluster paramétrées.",
'v0.9':"RHTAS comme chaîne de confiance, registre de releases dans le cluster, modes interne/externe des composants.",
'v0.10':"Chaîne d'extraction OKF, dépassée par v0.12 avant d'avoir démarré.",
'v0.11':"UnifAI et unifai-operator deviennent la plateforme d'agents et de RAG ; OKF reste la source de vérité des agents.",
'v0.12':"Les définitions d'agents quittent le dépôt (zuno-demo-agents) : bundles OCI signés, OKF 0.3, promotion par pull request.",
'v0.13':"Trois expériences sur la même chaîne gouvernée : UnifAI, Open WebUI, OpenClaw.",
'v0.14':"Deux expériences de plus sur la même chaîne : Dify pour les métiers, kagent pour les ops.",
'v0.15':"Rendre la démo fiable : plancher de classification dans l'ai-gateway, golden path, fenêtre de gel.",
'v0.16':"Durcir et gouverner : sécurité (ADR-0602, 0603), cycle de vie des agents, règles de livraison, world model.",
'v0.17':"Modes interne/externe des services de jour 0, ArgoCD distant, expérience Blender 3D.",
'OKF v0.1':"Ligne de version autonome du format Open Knowledge Format."}
order=['v0','v0.1','v0.2','v0.3','v0.4','v0.5','v0.6','v0.7','v0.8','v0.9','v0.10','v0.11','v0.12','v0.13','v0.14','v0.15','v0.16','v0.17','OKF v0.1']
adr=[dict(i=a['id'],b=a['band'],s=a['status'],c=a['cls'],t=a['title'],d=a['date'],r=a['retired']) for a in raw['adr']]
amap={a['i']:a for a in adr}
wp=[]
for w in raw['wp']:
    b=next((amap[x]['b'] for x in w['adrs'] if x in amap and not amap[x]['r']),None) or next((amap[x]['b'] for x in w['adrs'] if x in amap),None) or 'Hors bande'
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
