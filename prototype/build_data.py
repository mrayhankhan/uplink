"""Builds src/data.js from the synthetic case pack.
Usage: python -I build_data.py <data_dir> <ocr_raw.json> <results.json> <kyc_results.json> <out.js>"""
import sys, json, io, base64
import numpy as np, pandas as pd
from PIL import Image
d,ocrf,resf,kycf,out=sys.argv[1:6]
P=pd.read_csv(d+'/product_catalogue.csv',keep_default_na=False)
G=pd.read_csv(d+'/mock_gstin_registry.csv'); U=pd.read_csv(d+'/mock_udyam_registry.csv'); L=pd.read_csv(d+'/smb_leads.csv')
R=json.load(open(resf)); K=json.load(open(kycf)); O=json.load(open(ocrf,encoding='utf-8-sig'))
cat=[dict(id=r.product_id,name=r.product_name,category=r.category,unit=r.unit,min=int(r.price_min_inr_per_month),max=int(r.price_max_inr_per_month),setup=int(r.one_time_setup_inr),contract=int(r.min_contract_months),tiers=[int(x) for x in str(r.available_city_tiers).split(';')],minEmp=int(r.min_employees),minSites=int(r.min_sites),gst=r.requires_gstin=='Y',oneOf=[x for x in str(r.requires_one_of).split('|') if x],days=int(r.typical_install_days),desc=r.description) for r in P.itertuples()]
gst={r.gstin:[r.legal_name,r.trade_name,r.constitution,r.principal_place_of_business,r.state,r.registration_date,r.status] for r in G.itertuples()}
ud={r.udyam_number:[r.enterprise_name,r.enterprise_type,r.major_activity,r.state,r.city,r.date_of_registration] for r in U.itertuples()}
# applicant context the validator needs (what a CRM lead would already hold)
leads=[]
for k in K:
    if k.get('lead'):
        r=L[L.lead_id==k['lead']].iloc[0]
        leads.append(dict(kid=k['id'],lead=r.lead_id,biz=r.business_name,gstin=r.gstin if isinstance(r.gstin,str) else None,udyam=r.udyam_number if isinstance(r.udyam_number,str) else None,contact=r.contact_name))
ocr={k:dict(l=v['lines'],a=round(float(v['angle'] or 0),1)) for k,v in O.items()}
blur={}; thumbs={}
for k in O:
    im=Image.open(f'{d}/kyc_documents/{k}.png').convert('L').resize((620,877) if 'signatory' not in k else (620,877)); a=np.asarray(im).astype(float)
    lap=a[1:-1,2:]+a[1:-1,:-2]+a[2:,1:-1]+a[:-2,1:-1]-4*a[1:-1,1:-1]; blur[k]=round(float(lap.var()))
    t=Image.open(f'{d}/kyc_documents/{k}.png').convert('RGB'); t.thumbnail((360,360)); b=io.BytesIO(); t.save(b,'JPEG',quality=58); thumbs[k]='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
# back office: leads lost to process, ranked by the propensity model
m=R['propensity_model']; names=m['names'][1:]; w=np.array(m['w'])
st=G[['gstin','status']]; L2=L.merge(st,how='left',on='gstin')
def feats(df):
    X=pd.DataFrame(index=df.index)
    for n in names:
        if n.startswith('segment='): X[n]=(df.segment==n.split('=',1)[1])*1.0
        elif n.startswith('lead_source='): X[n]=(df.lead_source==n.split('=',1)[1])*1.0
    X['tier2']=(df.city_tier==2)*1.0; X['gstin']=(df.has_gstin=='Y')*1.0; X['udyam']=(df.has_udyam=='Y')*1.0
    X['regional_lang']=(~df.preferred_language.isin(['Hindi','English']))*1.0; X['accel_customer']=df.current_provider.fillna('').str.startswith('Accel')*1.0
    X['log_spend']=np.log1p(df.monthly_telecom_spend_inr); X['log_emp']=np.log1p(df.employee_count); X['log_sites']=np.log1p(df.num_sites); X['inactive_gstin']=df.status.isin(['Cancelled','Suspended'])*1.0
    return X[names]
X=feats(L2); mu=pd.Series(m['mu'])[names]; sd=pd.Series(m['sd'])[names]; Z=((X-mu)/sd).values; Z=np.c_[np.ones(len(Z)),Z]; L2['score']=1/(1+np.exp(-Z@w))
PROC=['Unreachable after 3 attempts','Owner had no time for a visit','Visit not scheduled by sales','Quote too complex to understand','Quote took too long to arrive','Missing GST or Udyam document','Found paperwork too long','Authorised signatory not available','Document details did not match','Installation delayed beyond 21 days','Site not feasible for fibre','First payment failed','Only wanted a mobile plan']
Q=L2[L2.drop_reason.isin(PROC)&L2.status.isin(['Active'])|(L2.drop_reason.isin(PROC)&L2.gstin.isna())].copy()
def route(r):
    if r.drop_reason=='Only wanted a mobile plan': return 'Digital: mobile-first offer'
    if r.segment in('Small multi-site businesses','Small manufacturers'): return 'Field closer'
    if r.drop_reason in('Installation delayed beyond 21 days','Site not feasible for fibre'): return 'Local partner: install or FWA'
    if r.has_gstin=='N': return 'CA partner: GST or PAN path'
    return 'WhatsApp nudge in '+r.preferred_language
Q['route']=Q.apply(route,axis=1)
Q=Q.sort_values('score',ascending=False).groupby('route').head(10).sort_values('score',ascending=False).head(36)
def mask(n):
    p=str(n).split(); return ' '.join(x[0]+'***' for x in p)
bo=[dict(id=r.lead_id,biz=r.business_name,seg=r.segment,city=r.city,tier=int(r.city_tier),lang=r.preferred_language,src=r.lead_source,stage=r.stage_reached,why=r.drop_reason,score=round(float(r.score),3),route=r.route,spend=int(r.monthly_telecom_spend_inr),contact=mask(r.contact_name)) for r in Q.itertuples()]
stats=dict(leads=R['base']['leads'],act=R['base']['act'],auc=round(R['propensity']['auc'],3),top20=round(R['propensity']['top20'],3),scored=int(len(L2[L2.drop_reason.isin(PROC)])))
kres=[dict(id=k['id'],decision=k['decision'],flags=k['flags'],soft=k['soft'],biz=k.get('business')) for k in K]
js='window.DATA='+json.dumps(dict(cat=cat,gst=gst,ud=ud,leads=leads,ocr=ocr,blur=blur,thumbs=thumbs,bo=bo,stats=stats,kres=kres),ensure_ascii=False,separators=(',',':'))+';'
open(out,'w',encoding='utf-8').write(js); print('data.js KB',len(js)//1024,'bo',len(bo),'leads',len(leads))
