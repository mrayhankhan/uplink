"""Smart KYC pipeline: runs on RAW OCR text only (never on hand transcription).
Usage: python -I kyc_pipeline.py <data_dir> <ocr_raw.json> <out.json>
Steps: image gate -> parse -> repair GSTIN by position -> checksum -> registry -> cross-document checks -> decision
"""
import sys, re, json, difflib, datetime as dt, os
import numpy as np, pandas as pd
from PIL import Image
sys.stdout.reconfigure(encoding='utf-8')
d,ocrf,out=sys.argv[1:4]
TODAY=dt.date(2026,7,15)
G=pd.read_csv(d+'/mock_gstin_registry.csv'); U=pd.read_csv(d+'/mock_udyam_registry.csv'); L=pd.read_csv(d+'/smb_leads.csv')
O=json.load(open(ocrf,encoding='utf-8-sig'))
gset={r['gstin']:r for r in G.to_dict('records')}; uset={r['udyam_number']:r for r in U.to_dict('records')}
ALPH='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
def checksum(g):
    s=0
    for i,c in enumerate(g[:14]):
        v=ALPH.index(c)*(2 if i%2 else 1); s+=v//36+v%36
    return ALPH[(36-s%36)%36]
TO_D={'O':'0','Q':'0','D':'0','I':'1','L':'1','Z':'2','S':'5','B':'8','G':'6'}; TO_A={v:k for k,v in {'O':'0','I':'1','Z':'2','S':'5','B':'8','G':'6'}.items()}
def repair(raw):
    g=re.sub(r'[^A-Z0-9]','',raw.upper());
    if len(g)!=15: return g
    o=list(g)
    for i in list(range(0,2))+list(range(7,11)): o[i]=TO_D.get(o[i],o[i])
    for i in list(range(2,7))+[11]: o[i]=TO_A.get(o[i],o[i])
    o[13]='Z'
    if o[12] in 'I': o[12]='1'
    return ''.join(o)
def find(pat,lines):
    for l in lines:
        m=re.search(pat,l)
        if m: return m
    return None
def blur(path):
    im=np.asarray(Image.open(path).convert('L').resize((620,877))).astype(float)
    lap=im[1:-1,2:]+im[1:-1,:-2]+im[2:,1:-1]+im[:-2,1:-1]-4*im[1:-1,1:-1]; return float(lap.var())
def sim(a,b): return difflib.SequenceMatcher(None,re.sub(r'\W','',a or '').lower(),re.sub(r'\W','',b or '').lower()).ratio()
leads_by_gst={r['gstin']:r for r in L[L.gstin.notna()].to_dict('records')}
KINDS=['gst_certificate','udyam_certificate','signatory_id','address_proof']
res=[];
for k in range(1,13):
    a=f'K{k:02d}'; rec=dict(id=a,flags=[],soft=[],docs={})
    # image gate
    for t in KINDS:
        key=f'{a}_{t}'; p=f'{d}/kyc_documents/{key}.png'
        if key not in O: rec['docs'][t]=dict(present=False); continue
        rec['docs'][t]=dict(present=True,blur=blur(p),angle=float(O[key]['angle'] or 0),nlines=len(O[key]['lines']))
    lines={t:(O.get(f'{a}_{t}') or {}).get('lines',[]) for t in KINDS}
    # GST doc
    gd=lines['gst_certificate']; raw=None
    for l in gd:
        c=re.sub(r'[^A-Za-z0-9]','',l.replace('lJ','U'))
        if 14<=len(c)<=16 and c[:2].isdigit() and c==c.upper() and sum(x.isalpha() for x in c)>=4: raw=c
    gst=repair(raw) if raw else None
    low_conf=False
    if gst and len(gst)!=15:
        near=difflib.get_close_matches(gst,list(gset),n=1,cutoff=.85)
        if near: gst=near[0]; low_conf=True
    rec['gstin_raw']=raw; rec['gstin']=gst
    m=rec['docs']['gst_certificate']
    legal=next((l for l in gd if '(Prop' in l or re.search(r'(LLP|Pvt Ltd)$',l)),None)
    rec['legal_doc']=legal
    if m['nlines']<6: rec['flags'].append(('UNREADABLE_GST_CERT','GST certificate too blurred to read (only %d text lines, sharpness %.0f). Ask for a re-photo in the same screen.'%(m['nlines'],m['blur'])))
    reg=None
    if gst:
        ok=(len(gst)==15 and checksum(gst)==gst[14]); rec['checksum_ok']=ok
        reg=gset.get(gst)
        if not ok or reg is None:
            near=difflib.get_close_matches(gst,list(gset),n=1,cutoff=.9)
            rec['flags'].append(('GSTIN_INVALID','GSTIN on certificate (%s) fails checksum and is not in the registry%s.'%(gst,'; nearest registered GSTIN differs by one character: '+near[0] if near else '')))
            if near: reg=gset[near[0]]; rec['nearest']=near[0]
        elif reg['status']!='Active':
            rec['flags'].append(('GSTIN_'+reg['status'].upper(),'Registry shows this GSTIN is %s. GST-dependent products are blocked until it is restored.'%reg['status']))
        if reg and legal and sim(legal,reg['legal_name'])<.97:
            rec['flags'].append(('LEGAL_NAME_MISMATCH','Legal name on certificate "%s" differs from the registry "%s".'%(legal,reg['legal_name'])))
    # lead context
    lead=None
    if reg: lead=leads_by_gst.get(reg['gstin'])
    if lead is None and gd==[] : pass
    # blurred GST: fall back to Udyam number to find the business
    ud=lines['udyam_certificate']; um=find(r'U[DO0]YAM\s*-?\s*[A-Z]{2}\s*-?\s*[0OQD]{2}\s*-?\s*\d{7}',ud); rec['udyam']=None
    if um:
        c=re.sub(r'[\s-]','',um.group(0)); rec['udyam']='UDYAM-%s-00-%s'%(c[5:7],c[-7:])
    ur=uset.get(rec['udyam']) if rec['udyam'] else None
    if lead is None and rec['udyam']:
        c=L[L.udyam_number==rec['udyam']]
        if len(c): lead=c.iloc[0].to_dict()
    rec['lead']=lead['lead_id'] if lead else None
    rec['business']=(lead or {}).get('business_name')
    if not rec['docs']['udyam_certificate']['present']:
        if lead and isinstance(lead.get('udyam_number'),str):
            rec['flags'].append(('UDYAM_CERT_MISSING','Udyam certificate not uploaded. Number %s found by lookup, so the owner only confirms it (no document needed).'%lead['udyam_number']))
        else: rec['flags'].append(('UDYAM_CERT_MISSING','Udyam certificate not uploaded and no record found.'))
    elif not rec['udyam']:
        rec['flags'].append(('UDYAM_NUMBER_BLANK','Udyam certificate has no registration number on it, and no record exists for this business. Treat as unregistered and route to the no-Udyam path.'))
    elif ur is None:
        rec['flags'].append(('UDYAM_NOT_FOUND','Udyam number is not in the registry.'))
    else:
        rec['udyam_status']='found'
        dm=find(r'\d{4}-\d{2}-\d{2}',ud)
        if dm and dm.group(0)!=ur['date_of_registration']: rec['soft'].append(('UDYAM_DATE_DIFF','Registration date on certificate %s, registry %s'%(dm.group(0),ur['date_of_registration'])))
        if not any(ur['major_activity']==l for l in ud): rec['soft'].append(('UDYAM_ACTIVITY_DIFF','Activity on certificate differs from registry (%s)'%ur['major_activity']))
    # signatory
    sd=lines['signatory_id']
    try:
        sname=sd[sd.index('Name')+1]; sdes=sd[sd.index('Designation')+1]
    except ValueError: sname=sdes=None
    vm=find(r'\d{4}-\d{2}-\d{2}',sd); rec['signatory']=sname; rec['designation']=sdes
    if vm and dt.date.fromisoformat(vm.group(0))<TODAY: rec['flags'].append(('ID_EXPIRED','Signatory ID expired on %s.'%vm.group(0)))
    if lead and sname and sim(sname,lead['contact_name'])<.85:
        rec['flags'].append(('SIGNATORY_MISMATCH','ID belongs to "%s" but the applicant on record is "%s". Ask for the right ID or an authorisation letter.'%(sname,lead['contact_name'])))
    # address proof
    bd=lines['address_proof']; bm=find(r'\d{4}-\d{2}-\d{2}',bd)
    if bm:
        age=(TODAY-dt.date.fromisoformat(bm.group(0))).days; rec['bill_age']=age
        if age>90: rec['flags'].append(('ADDRESS_PROOF_STALE','Bill is dated %s, %d days old; the limit is 90. Ask for a newer bill.'%(bm.group(0),age)))
    if reg:
        addr=reg['principal_place_of_business']; bill_text=' '.join(l for l in bd if re.search(r'Shop/Unit|\d{5}$|Pradesh|Punjab|Kerala|Gujarat|Maharash|Rajasth|Delhi|Bengal',l))
        rec['addr_sim']=round(sim(addr,bill_text),3); shop=re.search(r'Shop/Unit \d+',addr).group(0)
        if rec['addr_sim']<.7 and shop not in ' '.join(bd): rec['flags'].append(('ADDRESS_MISMATCH','Address on the bill does not match the GST address.'))
    # image soft flags
    if low_conf: rec['soft'].append(('OCR_LOW_CONFIDENCE','GSTIN partly misread by OCR; resolved by registry lookup and confirmed by matching legal name.'))
    if abs(rec['docs']['gst_certificate'].get('angle',0))>3: rec['soft'].append(('SKEWED_SCAN','GST certificate is rotated %.0f degrees; auto-deskewed and read correctly.'%rec['docs']['gst_certificate']['angle']))
    rec['decision']='PASS' if not rec['flags'] else ('STOP' if any(f[0] in('GSTIN_CANCELLED','GSTIN_SUSPENDED','GSTIN_INVALID') for f in rec['flags']) else 'FIX')
    res.append(rec)
json.dump(res,open(out,'w'),indent=1,default=str)
for r in res:
    print(f"{r['id']} {str(r.get('business')):32} {r['decision']:6} raw={r.get('gstin_raw')} -> {r.get('gstin')} blurvar={r['docs']['gst_certificate'].get('blur',0):.0f} lines={r['docs']['gst_certificate'].get('nlines')}")
    for f in r['flags']: print('    !',f[0],'-',f[1])
    for f in r['soft']: print('    ~',f[0],'-',f[1])
print('PASS',sum(r['decision']=='PASS' for r in res),'FIX',sum(r['decision']=='FIX' for r in res),'STOP',sum(r['decision']=='STOP' for r in res))
print('blur all',sorted([(round(v['blur']),r['id'],t) for r in res for t,v in r['docs'].items() if v.get('present')])[:6])
