"""Shared helpers for zuno-report-todo and zuno-report-history (repo + git only, no cluster)."""
import json,re,subprocess,os
OPEN_WP=('Not started','Repo work in review','Repo work merged','Operator pending')
ORDER=['v0','v0.1','v0.2','v0.3','v0.4','v0.5','v0.6','v0.7','v0.8','v0.9','v0.10','v0.11','v0.12','v0.13','v0.14','v0.15','v0.16','v0.17','OKF v0.1']
PLANNED=('v0.17',)   # bands that have not started; update when a band starts or closes
def sh(cmd,cwd=None):
    return subprocess.run(cmd,shell=True,capture_output=True,text=True,cwd=cwd or os.environ.get('REPO','.')).stdout
def load_raw(path='raw.json'):
    """Return (adrs by id, wps list) with each WP given a band (first non-retired ADR it cites) and a kind."""
    raw=json.load(open(path)); amap={a['id']:a for a in raw['adr']}
    for w in raw['wp']:
        b=next((amap[x]['band'] for x in w['adrs'] if x in amap and not amap[x]['retired']),None) or next((amap[x]['band'] for x in w['adrs'] if x in amap),None) or 'No band'
        w['band']=b; w['open']=w['state'] in OPEN_WP
        w['num']=re.sub(r'^WP-0*','',w['id'])
    return amap,raw['wp']
def wpkey(i):
    """Normalise WP-057 / WP-57 / wp-057 to WP-57."""
    m=re.match(r'(?i)wp-0*(\w+)',i); return 'WP-'+m[1].upper() if m else i
