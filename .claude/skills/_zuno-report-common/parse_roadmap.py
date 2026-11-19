import re,json,glob,collections,os
import os
R=os.environ.get('REPO','.').rstrip('/')+'/docs/'
adr={};band=None;retired=False
for l in open(R+'adr/README.md'):
    m=re.match(r'## (v[\d.]+|OKF v0\.1|Retired)',l)
    if m: band=m.group(1);retired=band=='Retired';continue
    if retired:
        m=re.match(r'\| \[ADR-(\d+)\]\(([^)]*)\) \| ([^|]*)\| ([^|]*)\| ([^|]*)\|',l)
        if m: adr[m[1]]=dict(id=m[1],file=m[2],band=m[3].strip(),status=m[4].strip(),title=m[5].strip(),retired=True)
    else:
        m=re.match(r'\| \[ADR-(\d+)\]\(([^)]*)\) \| ([^|]*)\| ([^|]*)\|',l)
        if m and band and band!='Retired': adr[m[1]]=dict(id=m[1],file=m[2],band=band,status=m[3].strip(),title=m[4].strip(),retired=False)
for a in adr.values():
    try:
        t=open(R+'adr/'+a['file']).read(3000)
        d=re.search(r'\*\*Date:\*\*\s*(\d{4}-\d\d-\d\d)',t); a['date']=d[1] if d else None
    except Exception as e: a['date']=None
    s=a['status']
    a['cls']=('implemented' if s=='Implemented' else 'partial' if s.startswith('Partially') else 'open' if s in('Proposed','Accepted','Deferred') else 'retired')
wp=[];phase=None
for l in open(R+'roadmap/implementation-roadmap.md'):
    m=re.match(r'### (.*)',l)
    if m: phase=re.sub(r'\s*\(added.*','',m[1].strip());continue
    if l.startswith('| WP-'):
        c=[x.strip() for x in l.strip().strip('|').split('|')]
        if len(c)<5: continue
        t=re.search(r'\[([^\]]*)\]\(work-packages/([^)]*)\)',c[1]); fn=t[2] if t else ''
        title='';date=None;size=0;est=None
        if fn and os.path.exists(R+'roadmap/work-packages/'+fn):
            full=open(R+'roadmap/work-packages/'+fn).read(); size=len(full); txt=full[:2500]
            e=re.search(r'\*\*Estimated files touched:\*\*\s*~?(\d+)',txt); est=int(e[1]) if e else None
            title=re.sub(r'^#\s*WP-[\w.]+\s*[:—–-]*\s*','',txt.split('\n')[0]).strip()
            d=re.search(r'\*\*State:\*\*[^\n]*?\((\d{4}-\d\d-\d\d)',txt); date=d[1] if d else None
        st=c[4].split(' (')[0].split(' —')[0].strip()
        if not date:
            d=re.search(r'(\d{4}-\d\d-\d\d)',c[4]); date=d[1] if d else None
        wp.append(dict(id=c[0],phase=phase,title=title,adrs=re.findall(r'\d{3,4}',c[2]),state=st,date=date,deps=re.findall(r'WP-[\w.]+',c[3]),note=c[5] if len(c)>5 else '',file=fn,size=size,est=est))
print(len(adr),len(wp))
print(collections.Counter(a['cls'] for a in adr.values()))
print(collections.Counter(w['state'] for w in wp))
print(sum(1 for a in adr.values() if a['date']),sum(1 for w in wp if w['date']))
json.dump(dict(adr=list(adr.values()),wp=wp),open('raw.json','w'),ensure_ascii=False)
