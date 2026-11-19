"""Builds data.json for the todo report from raw.json (shared parser) + priorities.json (hand-set tags).
Run from a work dir with raw.json. --write-priorities adds proposed tags for open items missing from priorities.json."""
import json,re,sys,os,datetime,collections
sys.path.insert(0,os.path.join(os.environ['SKILL_DIR'],'..','_zuno-report-common'))
from common import *
PRIO=os.path.join(os.environ['SKILL_DIR'],'priorities.json')
amap,wps=load_raw()
prio=json.load(open(PRIO)) if os.path.exists(PRIO) else {}
wmap={wpkey(w['id']):w for w in wps}
today=datetime.date.today()
def planned(note):
    m=re.search(r'(?:planned|dated|before)[^0-9]{0,20}(\d{4}-\d\d-\d\d)',note or '');return m[1] if m else None
# who depends on whom (open WPs only), then transitive "unblocks"
rev=collections.defaultdict(set)
for w in wps:
    if w['open']:
        for d in w['deps']: rev[wpkey(d)].add(wpkey(w['id']))
def unblocks(k,seen=None):
    seen=seen if seen is not None else set()
    for c in rev.get(k,()):
        if c not in seen: seen.add(c); unblocks(c,seen)
    return seen
def propose(w):
    n=w['note'] or ''
    if re.search(r"owner'?s? (decision|go)",n): return 'P3','waits for the owner'
    if w['state']!='Not started': return 'P1','work started, closing it removes an open item'
    p=planned(n)
    if p and p<='2026-12-31': return 'P2','planned '+p
    return 'P3','not started, no near date'
items=[]
for w in wps:
    if not w['open']: continue
    k=wpkey(w['id']); pr=prio.get(k)
    t,why=propose(w)
    if pr: t,why=pr['tag'],pr.get('why','')
    ub=unblocks(k)
    ob=[wpkey(d) for d in w['deps'] if wpkey(d) in wmap and wmap[wpkey(d)]['open']]
    items.append(dict(id=k,kind='WP',band=w['band'],title=w['title'],state=w['state'],tag=t,why=why,proposed=not pr,demo=bool(pr and pr.get('demo')),
        note=w['note'],planned=planned(w['note']),unblocks=sorted(ub),blockedBy=ob,adrs=w['adrs']))
# open / partial ADRs
cited=collections.defaultdict(list)
for w in wps:
    for a in w['adrs']: cited[a].append(wpkey(w['id']))
for a in amap.values():
    if a['cls'] in('open','partial'):
        k='ADR-'+a['id']; pr=prio.get(k)
        ws=[x for x in cited.get(a['id'],[]) if x in wmap and wmap[x]['open']]
        t='P3';why='no open work package'
        if ws: t=min(next(i['tag'] for i in items if i['id']==x) for x in ws);why='best tag of its open WPs'
        if pr: t,why=pr['tag'],pr.get('why','')
        items.append(dict(id=k,kind='ADR',band=a['band'],title=a['title'],state=a['status'],tag=t,why=why,proposed=not pr,demo=bool(pr and pr.get('demo')),note='',planned=None,unblocks=[],blockedBy=[],adrs=[a['id']],wps=ws))
if '--write-priorities' in sys.argv:
    new={i['id']:dict(tag=i['tag'],demo=False,why=i['why']) for i in items if i['id'] not in prio}
    prio.update(new); json.dump(dict(sorted(prio.items())),open(PRIO,'w'),indent=1,ensure_ascii=False); print('added',len(new),'to priorities.json')
# velocity: WPs finished per ISO week, last 8 weeks
done=collections.Counter()
for w in wps:
    if w['state']=='Done' and w['date']:
        d=datetime.date.fromisoformat(w['date']); y,wk,_=d.isocalendar(); done[f'{y}-W{wk:02d}']+=1
order={'P0':0,'P1':1,'P2':2,'P3':3}
bi=lambda b: ORDER.index(b) if b in ORDER else 99
items.sort(key=lambda i:(order[i['tag']],not i['demo'],bi(i['band']),-len(i['unblocks']),i['id']))
data=dict(items=items,order=ORDER,planned=list(PLANNED),demo='2026-11-24',freeze='2026-11-23',today=today.isoformat(),done=dict(sorted(done.items())[-10:]),
  counts=dict(wpOpen=sum(1 for w in wps if w['open']),wpAll=len(wps),adrOpen=sum(1 for a in amap.values() if a['cls'] in('open','partial')),adrAll=len(amap)))
json.dump(data,open('data.json','w'),ensure_ascii=False,separators=(',',':'))
print(collections.Counter(i['tag'] for i in items),data['counts'])
