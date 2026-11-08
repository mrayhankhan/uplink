"""Concatenates src/ into single-file builds.
dist/uplink.html  page content only
dist/index.html    full document, also copied to the repository root for GitHub Pages"""
import os, shutil
here=os.path.dirname(os.path.abspath(__file__)); src=os.path.join(here,'src'); dist=os.path.join(here,'dist'); os.makedirs(dist,exist_ok=True)
r=lambda n:open(os.path.join(src,n),encoding='utf-8').read()
h=r('shell.html')
for key,f in [('/*CSS*/','style.css'),('/*DATA*/','data.js'),('/*I18N*/','i18n.js'),('/*ENGINE*/','engine.js'),('/*KYC*/','kyc.js'),('/*APP*/','app.js')]:
    h=h.replace(key,r(f).replace('</script>','<\\/script>'))
open(os.path.join(dist,'uplink.html'),'w',encoding='utf-8').write(h)
head,body=h.split('<header',1)
icon="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%23FFB21A'/%3E%3Cpath d='M16 25V12M10 18l6-6 6 6' fill='none' stroke='%232B1D00' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M11 7.6a7.6 7.6 0 0 1 10 0' fill='none' stroke='%232B1D00' stroke-width='2.8' stroke-linecap='round'/%3E%3C/svg%3E"
meta=('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
      '<meta name="description" content="Uplink lets a small business owner find a bundle, get one monthly price, clear KYC and track activation from a phone, in their own language.">'
      '<meta name="theme-color" content="#06181D"><meta property="og:title" content="Uplink: your business, connected in one sitting">'
      '<meta property="og:description" content="Working prototype for Project Udyam Digital. All data is synthetic.">'
      f'<link rel="icon" href="{icon}">')
doc=f'<!doctype html><html lang="en"><head>{meta}{head}</head><body><header{body}</body></html>'
open(os.path.join(dist,'index.html'),'w',encoding='utf-8').write(doc)
open(os.path.join(here,'..','index.html'),'w',encoding='utf-8').write(doc)  # GitHub Pages serves the repository root
print('built KB',len(doc.encode())//1024)
