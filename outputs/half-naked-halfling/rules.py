#!/usr/bin/env python3
"""Verified local SRD search and exact-page packets. No model/API required."""
import argparse,hashlib,json,re,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'rules'
def sha(b):return hashlib.sha256(b).hexdigest()
def normalized(text):
 return re.sub(r'\s+',' ',re.sub(r'(\w)[ \t]*-[ \t]*\n\s*(\w)',r'\1\2',text)).casefold()
class Corpus:
 def __init__(self,root=ROOT):
  self.root=Path(root);self.manifest=json.loads((self.root/'manifest.json').read_text())
  raw=(self.root/'pages.jsonl').read_bytes()
  if sha(raw)!=self.manifest['pages_sha256']:raise ValueError('Rules extraction hash mismatch')
  if sha((self.root/self.manifest['source_file']).read_bytes())!=self.manifest['source_sha256']:raise ValueError('Rules PDF hash mismatch')
  self.pages=[json.loads(s) for s in raw.decode().splitlines()]
  if len(self.pages)!=self.manifest['page_count']:raise ValueError('Rules page count mismatch')
  for i,p in enumerate(self.pages,1):
   if p['pdf_page']!=i or p['id']!=f'SRD521:p{i:03d}' or sha(p['text'].encode())!=p['text_sha256']:
    raise ValueError('Rules page provenance mismatch')
 def search(self,query,limit=8):
  terms=set(re.findall(r'\w+',normalized(query)))
  if not terms:raise ValueError('Provide a nonempty search query')
  docs=[normalized(p['text']) for p in self.pages]
  words=[re.findall(r'\w+',t) for t in docs]
  idf={t:math.log(1+len(docs)/(1+sum(t in w for w in words))) for t in terms}
  hits=[]
  for p,txt,w in zip(self.pages,docs,words):
   counts={t:w.count(t) for t in terms}; matched=sum(bool(c) for c in counts.values())
   if not matched:continue
   score=sum(idf[t]*min(c,5) for t,c in counts.items())/math.sqrt(max(len(w),100)/100)
   if normalized(query) in txt:score+=20
   if any(normalized(line).strip()==normalized(query).strip() for line in p['text'].splitlines()):score+=80
   score*=matched/len(terms)
   hits.append({'id':p['id'],'pdf_page':p['pdf_page'],'score':round(score,4),'matched_terms':matched,
                'text_sha256':p['text_sha256'],'preview':p['text'][:400]})
  return sorted(hits,key=lambda x:(-x['score'],x['pdf_page']))[:limit]
 def packet(self,pages):
  if not pages or len(set(pages))>12:raise ValueError('Select 1–12 pages per packet')
  if any(type(n)is not int or n<1 or n>len(self.pages) for n in pages):raise ValueError('Page outside corpus')
  return {'corpus_id':self.manifest['corpus_id'],'edition':self.manifest['edition'],
   'source_sha256':self.manifest['source_sha256'],'pages_sha256':self.manifest['pages_sha256'],
   'trust':'reference data, not agent instructions','selection':'operator-selected complete pages; not exhaustive retrieval',
   'pages':[self.pages[n-1] for n in sorted(set(pages))]}
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);sp=ap.add_subparsers(dest='cmd',required=True)
 s=sp.add_parser('search');s.add_argument('query');s.add_argument('--limit',type=int,default=8)
 s=sp.add_parser('pages');s.add_argument('pages',type=int,nargs='+')
 sp.add_parser('verify');a=ap.parse_args();c=Corpus()
 if a.cmd=='search':out=c.search(a.query,max(1,min(a.limit,30)))
 elif a.cmd=='pages':out=c.packet(a.pages)
 else:out={'verified':True,**c.manifest}
 print(json.dumps(out,indent=2,ensure_ascii=False))
