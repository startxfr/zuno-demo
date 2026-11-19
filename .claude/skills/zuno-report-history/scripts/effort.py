"""Builds data.json for the history report: observed AI-assisted hours (git sessions) vs modelled human-only hours (rates.json), past and forecast.
Needs raw.json (shared parser) in the work dir. Repo + git only."""
import json,re,sys,os,datetime,collections,statistics
sys.path.insert(0,os.path.join(os.environ['SKILL_DIR'],'..','_zuno-report-common'))
from common import *
R=json.load(open(os.path.join(os.environ['SKILL_DIR'],'rates.json')))
amap,wps=load_raw(); wmap={wpkey(w['id']):w for w in wps}
DOCS=os.environ.get('REPO','.')+'/docs/'
# ---- commits
raw=sh("git log --no-merges --format='%x1e%H%x1f%at%x1f%an%x1f%s%x1f%b%x1f' --numstat")
commits=[]
for rec in raw.split('\x1e')[1:]:
    h,at,an,subj,body,stat=rec.split('\x1f',5)
    if 'dependabot' in an.lower(): continue
    files=[];la=0
    for l in stat.strip().splitlines():
        p=l.split('\t')
        if len(p)==3:
            a,d,f=p; files.append(f); la+=(int(a) if a.isdigit() else 0)+(int(d) if d.isdigit() else 0)
    txt=subj+'\n'+body
    refs=set()
    for m in re.finditer(r'(?i)\b(wp|adr)-0*(\d+[a-z]?)',txt):
        refs.add(wpkey('WP-'+m[2]) if m[1].lower()=='wp' else 'ADR-'+m[2].zfill(4))
    for f in files:
        m=re.match(r'docs/roadmap/work-packages/wp-0*(\d+[a-z]?)-',f)
        if m: refs.add(wpkey('WP-'+m[1]))
        m=re.match(r'docs/adr/(\d{4})-',f)
        if m: refs.add('ADR-'+m[1])
    refs={r for r in refs if (r in wmap or (r.startswith('ADR-') and r[4:] in amap))}
    commits.append(dict(t=int(at),ai=bool(re.search(r'(?i)co-authored-by:\s*claude',body)),refs=sorted(refs),lines=la,files=len(files),who=an))
commits.sort(key=lambda c:c['t'])
# ---- sessions (gap rule), hours split over commits, then over each commit's refs
gap=R['session_gap_min']*60; lead=R['session_lead_h']
sess=[];cur=[]
for c in commits:
    if cur and c['t']-cur[-1]['t']>gap: sess.append(cur);cur=[]
    cur.append(c)
if cur: sess.append(cur)
task=collections.defaultdict(lambda:dict(ai=0.0,human_obs=0.0,commits=0,lines=0,files=0,first=None,last=None))
week=collections.defaultdict(lambda:dict(h=0.0,c=0,ai_c=0,unattr=0.0))
unattr=0.0;tot=0.0;obs_human=0.0
for s in sess:
    hrs=(s[-1]['t']-s[0]['t'])/3600+lead; per=hrs/len(s); tot+=hrs
    for c in s:
        d=datetime.date.fromtimestamp(c['t']); y,w,_=d.isocalendar(); wk=week[f'{y}-W{w:02d}']; wk['h']+=per; wk['c']+=1; wk['ai_c']+=c['ai']; wk['start']=wk.get('start') or d.isoformat()
        if not c['ai']: obs_human+=per
        if not c['refs']: unattr+=per; wk['unattr']+=per; continue
        for r in c['refs']:
            t=task[r]; sh_=per/len(c['refs'])
            t['ai' if c['ai'] else 'human_obs']+=sh_; t['commits']+=1; t['lines']+=c['lines']/len(c['refs']); t['files']+=c['files']/len(c['refs'])
            iso=datetime.date.fromtimestamp(c['t']).isoformat(); t['first']=min(t['first'] or iso,iso); t['last']=max(t['last'] or iso,iso)
# ---- human-only model
def ttype(title,kind):
    if kind=='ADR': return 'adr'
    low=(title or '').lower()+' '
    for ty in('security','cluster','doc'):
        if any(k in low for k in R['keywords'][ty]): return ty
    return 'code'
def human(ty,files,lines,kchars):
    r=R['types'][ty]; h=r['base']+r['per_file']*files+r['per_kline']*lines/1000+r['per_kchar']*kchars
    return round(max(R['min_h'],min(R['max_h'],h)),1)
def adr_kchars(a):
    try: return len(open(DOCS+'adr/'+a['file']).read())/1000
    except Exception: return 5.0
rows=[]
for w in wps:
    k=wpkey(w['id']); t=task.get(k); ty=ttype(w['title'],'WP')
    files=(t['files'] if t and t['commits'] else None) or w['est'] or 6
    lines=t['lines'] if t and t['commits'] else None
    rows.append(dict(id=k,kind='WP',band=w['band'],title=w['title'],type=ty,state=w['state'],open=w['open'],done=w['date'] if w['state']=='Done' else None,
        commits=t['commits'] if t else 0,aiH=round(t['ai']+t['human_obs'],1) if t else 0,hum=None,files=round(files),lines=round(lines) if lines else None,kch=round(w['size']/1000,1)))
for a in amap.values():
    k='ADR-'+a['id']; t=task.get(k)
    rows.append(dict(id=k,kind='ADR',band=a['band'],title=a['title'],type='adr',state=a['status'],open=a['cls'] in('open','partial'),done=a['date'] if a['cls']=='implemented' else None,
        created=a['date'],commits=t['commits'] if t else 0,aiH=round(t['ai']+t['human_obs'],1) if t else 0,hum=None,files=1,lines=None,kch=round(adr_kchars(a),1)))
# median observed lines per type for items without commits yet
med={}
for ty in R['types']:
    ls=[r['lines'] for r in rows if r['type']==ty and r['lines']]
    med[ty]=statistics.median(ls) if ls else 300
for r in rows:
    r['hum']=human(r['type'],r['files'],r['lines'] if r['lines'] is not None else (med[r['type']] if r['type']!='adr' else 0),r['kch'])
# speed-up per type from tasks that have both an observed AI time and a model estimate (closed only)
ratio={}
for ty in R['types']:
    cl=[r for r in rows if r['type']==ty and not r['open'] and r['aiH']>0]
    ratio[ty]=round(sum(r['hum'] for r in cl)/sum(r['aiH'] for r in cl),2) if cl else None
allcl=[r for r in rows if not r['open'] and r['aiH']>0]
overall=round(sum(r['hum'] for r in allcl)/sum(r['aiH'] for r in allcl),2) if allcl else 1
for r in rows:
    if r['open']:
        rr=ratio.get(r['type']) or overall; r['fAI']=round(r['hum']/rr,1)
# ---- bands
bands=[]
for b in ORDER+['No band']:
    br=[r for r in rows if r['band']==b]
    if not br: continue
    cl=[r for r in br if not r['open']]; op=[r for r in br if r['open']]
    ob=[r for r in cl if r['aiH']>0]
    bands.append(dict(b=b,planned=b in PLANNED,closed=len(cl),open=len(op),humClosed=round(sum(r['hum'] for r in cl)),aiClosed=round(sum(r['aiH'] for r in cl)),
        humCovered=round(sum(r['hum'] for r in ob)),aiCovered=round(sum(r['aiH'] for r in ob)),commits=sum(r['commits'] for r in br),
        humOpen=round(sum(r['hum'] for r in op)),aiOpen=round(sum(r['fAI'] for r in op))))
# ---- weekly curve (done tasks by done date for the human model) and velocity
wk=[]
doneh=collections.Counter(); donen=collections.Counter()
for r in rows:
    if r['done']:
        d=datetime.date.fromisoformat(r['done']); y,w,_=d.isocalendar(); doneh[f'{y}-W{w:02d}']+=r['hum']; donen[f'{y}-W{w:02d}']+=(r['kind']=='WP')
weeks=sorted(set(week)|set(doneh))
for k in weeks:
    v=week.get(k,dict(h=0,c=0,ai_c=0,unattr=0)); wk.append(dict(w=k,ai=round(v['h'],1),unattr=round(v['unattr'],1),commits=v['c'],aiShare=round(v['ai_c']/v['c'],2) if v['c'] else None,human=round(doneh[k],1),wpDone=donen[k]))
cur_w='%d-W%02d'%datetime.date.today().isocalendar()[:2]
full=[x for x in wk if x['w']<cur_w][-4:]
pace=round(sum(x['ai'] for x in full)/len(full),1) if full else 0
wpp=round(sum(x['wpDone'] for x in full)/len(full),1) if full else 0
fAI=sum(r['fAI'] for r in rows if r['open']); fH=sum(r['hum'] for r in rows if r['open'])
owner=sum(1 for r in rows if r['open'] and r['kind']=='WP' and re.search(r"owner'?s? (decision|go)",wmap[r['id']]['note'] or ''))
eta=lambda per: (datetime.date.today()+datetime.timedelta(weeks=(fAI/per if per else 0))).isoformat() if per else None
data=dict(rows=rows,bands=bands,weeks=wk,ratio=ratio,overall=overall,rates=R,today=datetime.date.today().isoformat(),
  totals=dict(ownerWait=owner,openWp=sum(1 for r in rows if r['open'] and r['kind']=='WP'),sessionH=round(tot),unattrH=round(unattr),humanObsH=round(obs_human),commits=len(commits),aiCommits=sum(c['ai'] for c in commits),sessions=len(sess),
   humClosed=round(sum(r['hum'] for r in rows if not r['open'])),humOpen=round(fH),aiOpen=round(fAI),pace=pace,wpPace=wpp,eta=eta(pace),
   etaWp=(datetime.date.today()+datetime.timedelta(weeks=sum(1 for r in rows if r['open'] and r['kind']=='WP')/wpp)).isoformat() if wpp else None))
json.dump(data,open('data.json','w'),ensure_ascii=False,separators=(',',':'))
print(data['totals']);print('ratio',ratio,overall)
for b in bands: print(b)
print(wk[-4:])
