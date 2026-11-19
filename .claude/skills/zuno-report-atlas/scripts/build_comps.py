import json,re,collections,importlib,sys,os
sys.path.insert(0,os.environ['SKILL_DIR']+'/assets')
import components as comps

pods=json.load(open('pods.json'))['items']; pvcs=json.load(open('pvc.json'))['items']
pcpu=json.load(open('p_cpu.json')); pmem=json.load(open('p_mem.json'))
def q(s):
    m=re.match(r'([\d.]+)(m|Ki|Mi|Gi|Ti|G|M|k)?$',str(s)); v=float(m[1]); u=m[2]
    return v/1000 if u=='m' else v*{'Ki':1/1024**2,'Mi':1/1024,'Gi':1,'Ti':1024,'G':1e9/2**30,'M':1e6/2**30,'k':1e3/2**30,None:1/2**30}[u] if u!='m' else v
def cpu(s): s=str(s); return float(s[:-1])/1000 if s.endswith('m') else float(s)
def mem(s):
    s=str(s); m=re.match(r'([\d.]+)(Ki|Mi|Gi|Ti|G|M|k)?$',s); v=float(m[1]); u=m[2]
    return v*{'Ki':1/1024**2,'Mi':1/1024,'Gi':1,'Ti':1024,'G':1e9/2**30,'M':1e6/2**30,'k':1e3/2**30,None:1/2**30}[u]
def size(s): return mem(s)
out={};un=collections.Counter()
for c in comps.C: out[c['id']]=dict(c,cpuReq=0,cpuUse=0,memReq=0,memUse=0,pvcGi=0,gpu={},pods=0,wl=collections.Counter(),pvcs=[],ns=set())
def find(ns,name):
    for c in comps.C:
        for n,r in c['sel']:
            if re.fullmatch(n,ns) and re.search(r,name): return c['id']
for p in pods:
    if p['status']['phase']!='Running': continue
    ns=p['metadata']['namespace']
    own=re.sub(r'-[a-z0-9]{8,10}(-[a-z0-9]{5})?$','',(p['metadata'].get('ownerReferences') or [{}])[0].get('name',p['metadata']['name']))
    cid=find(ns,own)
    if not cid:
        if ns.startswith(('zuno','redhat','rhoai','kuadrant','cert','nvidia','nfs','unifai','openshift-ingress','openshift-operators','openshift-gitops','policy')): un[ns+'/'+own]+=1
        continue
    o=out[cid]; o['pods']+=1; o['wl'][own]+=1; o['ns'].add(ns)
    for k in ('containers','initContainers'):
        for c in p['spec'].get(k,[]):
            r=c.get('resources',{}).get('requests',{})
            if k=='containers':
                o['cpuReq']+=cpu(r.get('cpu',0)); o['memReq']+=mem(r.get('memory',0))
            for rk,v in {**c.get('resources',{}).get('limits',{}),**r}.items():
                if 'mig' in rk or rk=='nvidia.com/gpu':
                    if k=='containers' and rk in r: o['gpu'][rk.replace('nvidia.com/','')]=o['gpu'].get(rk.replace('nvidia.com/',''),0)+int(v)
    key=ns+'/'+p['metadata']['name']
    o['cpuUse']+=pcpu.get(key,0); o['memUse']+=pmem.get(key,0)/2**30
for v in pvcs:
    ns=v['metadata']['namespace']
    for c in comps.C:
        if any(re.fullmatch(n,ns) and re.search(r,v['metadata']['name']) for n,r in c['pvc']):
            out[c['id']]['pvcGi']+=size(v['spec']['resources']['requests']['storage'])
            out[c['id']]['pvcs'].append([v['metadata']['name'],v['spec']['resources']['requests']['storage']]); break
res=[]
for o in out.values():
    o['wl']=[[k,n] for k,n in sorted(o['wl'].items(),key=lambda x:-x[1])]; o['ns']=sorted(o['ns'])
    for k in('cpuReq','cpuUse','memReq','memUse','pvcGi'): o[k]=round(o[k],2)
    del o['sel']; o.pop('pvc')
    res.append(o)
json.dump(res,open('comps.json','w'),ensure_ascii=False)
print(un.most_common(20))
for o in res: print(o['id'],o['pods'],o['cpuReq'],o['cpuUse'],o['memReq'],o['memUse'],o['pvcGi'],o['gpu'])
