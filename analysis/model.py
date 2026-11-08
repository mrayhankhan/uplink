"""Project Udyam Digital - reproducible analysis behind the deck.
Usage: python -I model.py <data_dir> <out_json>
Every number in the deck comes from this script (leads) or kyc_pipeline.py (documents).
"""
import sys, json, math
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
d=sys.argv[1]; out=sys.argv[2]
L=pd.read_csv(d+'/smb_leads.csv'); P=pd.read_csv(d+'/product_catalogue.csv',keep_default_na=False).set_index('product_id')
G=pd.read_csv(d+'/mock_gstin_registry.csv')[['gstin','status']]
ST=['Lead','Contacted','Needs assessed','Quote accepted','KYC complete','Activated']
L['si']=L.stage_reached.map({s:i for i,s in enumerate(ST)}); L['act']=(L.outcome=='Activated').astype(int)
L=L.merge(G,how='left',on='gstin')
R={}
# ---------- 1. baseline
R['base']=dict(leads=len(L),act=int(L.act.sum()),conv=L.act.mean(),spend=int(L.acquisition_cost_inr.sum()),cac=L.acquisition_cost_inr.sum()/L.act.sum(),
  wasted=int(L[L.act==0].acquisition_cost_inr.sum()),mrr=float(L.monthly_bundle_value_inr.sum()),arpu=float(L.monthly_bundle_value_inr.mean()),
  churn=float((L.churned_within_6_months=='Y').sum()/L.act.sum()),nps=float(L.nps_score.mean()),days=float(L.days_lead_to_activation.mean()),calls=float(L[L.act==1].customer_follow_up_calls.mean()))
# ---------- 2. drop reasons: process vs market
PROCESS={'Unreachable after 3 attempts','Wrong or invalid number','Owner had no time for a visit','Visit not scheduled by sales',
 'Quote too complex to understand','Quote took too long to arrive','Missing GST or Udyam document','Found paperwork too long',
 'Authorised signatory not available','Document details did not match','Installation delayed beyond 21 days','Site not feasible for fibre','First payment failed'}
dr=L.drop_reason.value_counts()
R['drops']={k:int(v) for k,v in dr.items()}
proc=int(dr[dr.index.isin(PROCESS)].sum()); R['process_drops']=proc; R['all_drops']=int(dr.sum()); R['process_share']=proc/dr.sum()
# ---------- 3. time
for c in ['created_date','contacted_date','needs_assessed_date','quote_accepted_date','kyc_complete_date','activated_date']: L[c]=pd.to_datetime(L[c])
A=L[L.act==1].copy()
t=dict(contact=(A.contacted_date-A.created_date).dt.days.mean(),needs=(A.needs_assessed_date-A.contacted_date).dt.days.mean(),quote=(A.quote_accepted_date-A.needs_assessed_date).dt.days.mean(),kyc=(A.kyc_complete_date-A.quote_accepted_date).dt.days.mean(),install=(A.activated_date-A.kyc_complete_date).dt.days.mean())
R['stage_days']={k:float(v) for k,v in t.items()}; R['paper_days']=float(t['contact']+t['needs']+t['quote']+t['kyc'])
# ---------- 4. channel x segment
fm=L.groupby(['segment','lead_source']).agg(leads=('act','size'),spend=('acquisition_cost_inr','sum'),act=('act','sum'),mrr=('monthly_bundle_value_inr','sum')).reset_index()
fm['cac']=fm.spend/fm.act; fm['arpu']=fm.mrr/fm.act; fm['payback_rev_months']=fm.cac/fm.arpu
R['seg_source']=fm.round(1).to_dict('records')
seg=L.groupby('segment').agg(leads=('act','size'),spend=('acquisition_cost_inr','sum'),act=('act','sum'),mrr=('monthly_bundle_value_inr','sum'),gst=('has_gstin',lambda s:(s=='Y').mean()),spendm=('monthly_telecom_spend_inr','mean'))
seg['conv']=seg.act/seg.leads; seg['cac']=seg.spend/seg.act; seg['arpu']=seg.mrr/seg.act; seg['mrr_share']=seg.mrr/seg.mrr.sum(); seg['lead_share']=seg.leads/seg.leads.sum(); seg['mrr_per_100']=seg.mrr/seg.leads*100
seg['churn']=[ (L[(L.segment==s)&(L.churned_within_6_months=='Y')].shape[0])/seg.loc[s,'act'] for s in seg.index]
seg['nps']=[L[(L.segment==s)].nps_score.mean() for s in seg.index]; seg['pay']=seg.cac/seg.arpu
seg['quote_acc']=[ (L[(L.segment==s)&(L.si>=3)].shape[0])/L[(L.segment==s)&(L.si>=2)].shape[0] for s in seg.index]
seg['price_ratio']=seg.arpu/seg.spendm
R['segments']=seg.reset_index().round(4).to_dict('records')
src=L.groupby('lead_source').agg(leads=('act','size'),spend=('acquisition_cost_inr','sum'),act=('act','sum'),mrr=('monthly_bundle_value_inr','sum'),contacted=('si',lambda s:(s>=1).mean()))
src['conv']=src.act/src.leads; src['cac']=src.spend/src.act; src['churn']=[ (L[(L.lead_source==s)&(L.churned_within_6_months=='Y')].shape[0])/src.loc[s,'act'] for s in src.index]
R['sources']=src.reset_index().round(4).to_dict('records')
cp=A[A.lead_source=='Channel partner']; R['partner_payout_mult']=float((cp.acquisition_cost_inr/cp.monthly_bundle_value_inr).mean()); R['partner_payout_avg']=float(cp.acquisition_cost_inr.mean())
# ---------- 5. rule audit
def parse(b): return {x.split('x')[0]:int(x.split('x')[1]) for x in b.split(';')}
viol=[]; strict=[]
for _,r in A.iterrows():
    v=set(); b=parse(r.bundle_products)
    for p in b:
        c=P.loc[p]
        if str(r.city_tier) not in c.available_city_tiers.split(';'): v.add('tier')
        if r.employee_count<int(c.min_employees): v.add('size')
        if r.num_sites<int(c.min_sites): v.add('sites')
        if c.requires_gstin=='Y' and r.has_gstin!='Y': v.add('gstin_missing')
        if c.requires_one_of and not (set(c.requires_one_of.split('|'))&set(b)): v.add('dependency')
        if c.requires_gstin=='Y' and r.has_gstin=='Y' and r.status!='Active': v.add('gst_product_on_inactive')
    strict.append(bool(v))
    if r.status in('Cancelled','Suspended'): v.add('gstin_inactive')
    viol.append(sorted(v))
A['v']=viol
from collections import Counter
R['rules']=dict(strict=int(sum(strict)),strict_share=sum(strict)/len(A),by=dict(Counter(x for v in viol for x in v)),any=int(sum(1 for v in viol if v)),any_ex_inactive=int(sum(1 for v in viol if set(v)-{'gstin_inactive'})),
  mrr_any=float(A[A.v.map(len)>0].monthly_bundle_value_inr.sum()),inactive=int(A.status.isin(['Cancelled','Suspended']).sum()),inactive_mrr=float(A[A.status.isin(['Cancelled','Suspended'])].monthly_bundle_value_inr.sum()))
s=L[L.has_gstin=='Y'].groupby('status').agg(n=('act','size'),act=('act','sum'));s['conv']=s.act/s.n; R['gst_status']=s.reset_index().to_dict('records')
# ---------- 6. GSTIN path
Lg=L.copy()
def needs_gst(s):
    return any(P.loc[p].requires_gstin=='Y' for p in str(s).split(';') if p in P.index)
Lg['ask_gst']=Lg.products_of_interest.map(needs_gst)
x=Lg[Lg.has_gstin=='N']
R['nogst']=dict(leads=len(x),share=len(x)/len(L),gst_free_interest=int((~x.ask_gst).sum()),act_free=float(x[~x.ask_gst].act.mean()),gst_free_products=int((P.requires_gstin=='N').sum()),
  kyc_pass_no=float((L[(L.has_gstin=='N')&(L.si>=3)].si>=4).mean()),kyc_pass_yes=float((L[(L.has_gstin=='Y')&(L.si>=3)].si>=4).mean()),quote_no=int(((L.has_gstin=='N')&(L.si>=3)).sum()))
# ---------- 7. language
L['reg']=L.preferred_language.isin(['Hindi','English']).map({True:'HE',False:'REG'})
la=L.groupby('reg').agg(n=('act','size'),act=('act','sum')); la['conv']=la.act/la.n
p1,p2=la.conv['HE'],la.conv['REG']; n1,n2=la.n['HE'],la.n['REG']; pp=(la.act.sum())/(n1+n2)
z=(p1-p2)/math.sqrt(pp*(1-pp)*(1/n1+1/n2)); from math import erf
pv=2*(1-0.5*(1+erf(abs(z)/math.sqrt(2))))
R['language']=dict(he=float(p1),reg=float(p2),z=z,p=pv,reg_leads=int(n2),by_seg=L.pivot_table(index='reg',columns='segment',values='act',aggfunc='mean').round(4).to_dict())
# ---------- 8. tier
k=L[L.si>=4]; R['tier']=dict(t1=float(k[k.city_tier==1].act.mean()),t2=float(k[k.city_tier==2].act.mean()),t2_kyc=int((k.city_tier==2).sum()),t2_act=int(k[k.city_tier==2].act.sum()),
  parity_add=float((k[k.city_tier==1].act.mean()-k[k.city_tier==2].act.mean())*(k.city_tier==2).sum()),
  delayed=[float((k[k.city_tier==t].drop_reason=='Installation delayed beyond 21 days').mean()) for t in (1,2)],infeasible=[float((k[k.city_tier==t].drop_reason=='Site not feasible for fibre').mean()) for t in (1,2)],
  p04_share=float(A.bundle_products.str.contains('P04').mean()))
# ---------- 9. chasing
A['ch']=(A.churned_within_6_months=='Y').astype(int)
c=A.groupby('customer_follow_up_calls').agg(n=('ch','size'),churn=('ch','mean'),nps=('nps_score','mean')).reset_index(); R['chase']=c.round(4).to_dict('records')
R['chase_le2']=float(A[A.customer_follow_up_calls<=2].ch.mean()); R['chase_ge4']=float(A[A.customer_follow_up_calls>=4].ch.mean()); R['chase_share_ge4']=float((A.customer_follow_up_calls>=4).mean())
R['nps_by_days']=dict(le18=float(A[A.days_lead_to_activation<=18].nps_score.mean()),gt21=float(A[A.days_lead_to_activation>21].nps_score.mean()))
# ---------- 10. Accel base
L['rel']=L.current_provider.fillna('').str.startswith('Accel')
rr=L.groupby('rel').agg(n=('act','size'),act=('act','sum')); rr['conv']=rr.act/rr.n; R['accel_base']=dict(leads=int(rr.n[True]),conv=float(rr.conv[True]),other=float(rr.conv[False]),share=float(rr.n[True]/len(L)))
# interest vs bought
ov=[len(set(str(r.products_of_interest).split(';'))&set(parse(r.bundle_products))) for _,r in A.iterrows()]; R['zero_overlap']=sum(1 for o in ov if o==0); R['zero_overlap_share']=sum(1 for o in ov if o==0)/len(A)
# top bundles
rows=[]
for s,g in A.groupby('segment'):
    cc=Counter(p for b in g.bundle_products for p in parse(b)); rows.append(dict(segment=s,top=[(p,round(n/len(g),2)) for p,n in cc.most_common(8)],med_qty={p:float(np.median([parse(b)[p] for b in g.bundle_products if p in parse(b)])) for p,_ in cc.most_common(8)}))
R['bundle_mix']=rows
A['nprod']=A.bundle_products.map(lambda b:len(parse(b)))
R['overbundle']=dict(n=int((A.nprod>=8).sum()),churn=float(A[A.nprod>=8].ch.mean()),other=float(A[A.nprod<8].ch.mean()))
# ---------- 11. propensity (features known at lead creation only)
def feats(df):
    X=pd.DataFrame(index=df.index)
    for c,vals in dict(segment=sorted(L.segment.unique())[1:],lead_source=sorted(L.lead_source.unique())[1:]).items():
        for v in vals: X[f'{c}={v}']=(df[c]==v)*1.0
    X['tier2']=(df.city_tier==2)*1.0; X['gstin']=(df.has_gstin=='Y')*1.0; X['udyam']=(df.has_udyam=='Y')*1.0
    X['regional_lang']=(~df.preferred_language.isin(['Hindi','English']))*1.0
    X['accel_customer']=df.current_provider.fillna('').str.startswith('Accel')*1.0
    X['log_spend']=np.log1p(df.monthly_telecom_spend_inr); X['log_emp']=np.log1p(df.employee_count); X['log_sites']=np.log1p(df.num_sites)
    X['inactive_gstin']=df.status.isin(['Cancelled','Suspended'])*1.0
    return X
X=feats(L); mu=X.mean(); sd=X.std().replace(0,1); Z=((X-mu)/sd).values; y=L.act.values.astype(float)
Z=np.c_[np.ones(len(Z)),Z]; names=['intercept']+list(X.columns)
rng=np.random.default_rng(42); idx=rng.permutation(len(Z)); cut=int(.7*len(Z)); tr,te=idx[:cut],idx[cut:]
def fit(Z,y,l2=1.0,it=40):
    w=np.zeros(Z.shape[1])
    for _ in range(it):
        p=1/(1+np.exp(-Z@w)); W=p*(1-p)+1e-9; g=Z.T@(y-p)-l2*np.r_[0,w[1:]]; H=(Z.T*W)@Z+l2*np.diag(np.r_[0,np.ones(len(w)-1)]); s=np.linalg.solve(H,g); w+=s
        if np.abs(s).max()<1e-7: break
    return w
w=fit(Z[tr],y[tr]); pte=1/(1+np.exp(-Z[te]@w))
def auc(y,s):
    o=np.argsort(s); r=np.empty(len(s)); r[o]=np.arange(1,len(s)+1); n1=y.sum(); n0=len(y)-n1; return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
a=auc(y[te],pte); o=np.argsort(-pte); yy=y[te][o]
dec=lambda f:yy[:int(f*len(yy))].sum()/yy.sum()
R['propensity']=dict(auc=float(a),top10=float(dec(.1)),top20=float(dec(.2)),top30=float(dec(.3)),base=float(y[te].mean()),top20_rate=float(yy[:int(.2*len(yy))].mean()),bottom50_share=float(yy[int(.5*len(yy)):].sum()/yy.sum()),n_test=len(te))
wf=fit(Z,y); R['propensity_model']=dict(names=names,w=[float(v) for v in wf],mu={k:float(v) for k,v in mu.items()},sd={k:float(v) for k,v in sd.items()})
R['propensity_top']=sorted([(n,round(float(v),3)) for n,v in zip(names[1:],wf[1:])],key=lambda t:-abs(t[1]))[:10]
# ---------- 12. impact: recovery of each drop reason, by segment x source
RECOV={ # share of leads lost for this reason that the new journey keeps moving
 'Unreachable after 3 attempts':.25,'Wrong or invalid number':.20,'Not interested on first call':.0,
 'Owner had no time for a visit':.50,'Visit not scheduled by sales':.70,'Only wanted a mobile plan':.25,'Locked in with current provider':.0,
 'Quote too complex to understand':.60,'Quote took too long to arrive':.80,'Price too high':.15,'Competitor offered cheaper plan':.10,'Decided to wait':.05,
 'Missing GST or Udyam document':.60,'Found paperwork too long':.70,'Authorised signatory not available':.50,'Document details did not match':.40,
 'Installation delayed beyond 21 days':.50,'Site not feasible for fibre':.50,'Customer cancelled before install':.20,'First payment failed':.60}
R['recov']=RECOV
STAGE_OF={r:int(L[L.drop_reason==r].si.iloc[0]) for r in RECOV}
stcost={'Field sales':[420,840,2690,3360,4030,4030],'Channel partner':[150,300,600,750,900,0],'Inbound call':[160,320,640,800,960,960],'Referral':[180,360,720,900,1080,1080],'Website form':[120,240,480,600,720,720],'WhatsApp campaign':[60,120,240,300,360,360]}
DIG=stcost['Website form']
STACK_LEAD=30; STACK_ACT=120; PREMISES=400   # chat and messaging per lead; KYC APIs and e-sign per activation; premises visit per activation (team assumption, shared with the line survey)
SHARE_FIELD_KEEP={'Micro retail & services':0.0,'Professional offices':.25,'Small multi-site businesses':1.0,'Small manufacturers':1.0}
ARPU_F={'Micro retail & services':.76,'Professional offices':1,'Small multi-site businesses':1,'Small manufacturers':1}
BLOCK=R['rules']['inactive']
def sim(mult=1.0,detail=False):
    tot=dict(act=0.,mrr=0.,cost=0.); wf=[0.]*5; seg_act={}; stage_new=[0.]*6
    for (s,src_),g in L.groupby(['segment','lead_source']):
        n=len(g); reach=[(g.si>=i).sum() for i in range(6)]
        rate=[];
        for i in range(5):
            enter=reach[i]; passed=reach[i+1]; lost=g[g.si==i].drop_reason.value_counts()
            rec=sum(v*min(1,RECOV.get(k,0)*mult) for k,v in lost.items())
            rate.append((passed+rec,enter))
        # new funnel
        cur=float(n); flows=[cur]
        for i,(pass_new,ent) in enumerate(rate):
            r=pass_new/ent if ent else 0; cur=cur*r; flows.append(cur)
        if reach[5]==0: flows=flows
        arpu=(g.monthly_bundle_value_inr.sum()/reach[5] if reach[5] else 0)*ARPU_F[s]
        # cost: leads finishing at each stage
        ended=[flows[i]-flows[i+1] for i in range(5)]+[flows[5]]
        tbl=stcost[src_]
        if src_=='Field sales':
            k=SHARE_FIELD_KEEP[s]; tbl=[k*a+(1-k)*b for a,b in zip(stcost['Field sales'],DIG)]
        c=sum(e*t for e,t in zip(ended,tbl))
        if src_=='Channel partner':
            first=min(arpu*1.0,10000)+1500   # capped commission plus paid install/KYC assist
            c+=flows[5]*first
        c+=n*STACK_LEAD+flows[5]*(STACK_ACT+PREMISES)
        tot['act']+=flows[5]; tot['mrr']+=flows[5]*arpu; tot['cost']+=c; seg_act[s]=seg_act.get(s,0)+flows[5]
        for i in range(6): stage_new[i]+=flows[i]
    return tot,seg_act,stage_new
def stepwise(mult=1.0):
    # waterfall: switch on stages one at a time, top to bottom
    out=[]; prev=None
    base=L.act.sum(); out.append(('Today',float(base)))
    out.append(('Compliance block',-float(BLOCK)))
    cumulative=float(base-BLOCK)
    groups=[('Contact',[0]),('Needs',[1]),('Quote',[2]),('KYC',[3]),('Install',[4])]
    active=set(); last=None
    def run(active):
        t=0.
        for (s,src_),g in L.groupby(['segment','lead_source']):
            n=len(g); reach=[(g.si>=i).sum() for i in range(6)]; cur=float(n)
            for i in range(5):
                ent=reach[i]; passed=reach[i+1]; lost=g[g.si==i].drop_reason.value_counts()
                rec=sum(v*min(1,RECOV.get(k,0)*mult) for k,v in lost.items()) if i in active else 0
                cur=cur*((passed+rec)/ent if ent else 0)
            t+=cur
        return t
    last=run(set());
    for nm,st in groups:
        active|=set(st); now=run(active); out.append((nm,float(now-last))); last=now
    return out,last
res={}
SCEN=dict(low=.35,base=.6,high=1.0)   # recovered leads are colder than average, so the base case takes a 40% quality haircut
for nm,m in SCEN.items():
    tot,sa,fl=sim(m); act=tot['act']-BLOCK;
    res[nm]=dict(act=act,conv=act/len(L),cost=tot['cost'],cac=tot['cost']/act,mrr=tot['mrr']-R['rules']['inactive_mrr'],seg={k:v for k,v in sa.items()},flows=fl)
R['impact']=res
wfall,last=stepwise(SCEN['base']); R['waterfall']=wfall
b=res['base']; R['impact_delta']=dict(act_x=b['act']/R['base']['act'],cac_drop=1-b['cac']/R['base']['cac'],mrr_x=b['mrr']/R['base']['mrr'],mrr_add=b['mrr']-R['base']['mrr'],arr_add=(b['mrr']-R['base']['mrr'])*12,arr_add_annual_cohorts=(b['mrr']-R['base']['mrr'])*12*4)
json.dump(R,open(out,'w'),indent=1,default=float)
# ---------- print
pr=lambda *a:print(*a)
pr('BASE',{k:(round(v,4) if isinstance(v,float) else v) for k,v in R['base'].items()})
pr('process drops',proc,'/',dr.sum(),round(R['process_share'],3),'paper days',round(R['paper_days'],2),R['stage_days'])
pr('rules',R['rules']); pr('gst status',R['gst_status']); pr('nogst',R['nogst']); pr('lang',R['language']); pr('tier',R['tier'])
pr('chase',R['chase'],'le2',R['chase_le2'],'ge4',R['chase_ge4'],R['chase_share_ge4']); pr('nps days',R['nps_by_days']); pr('accel',R['accel_base']); pr('zero overlap',R['zero_overlap'],R['zero_overlap_share'])
pr('overbundle',R['overbundle']); pr('partner',R['partner_payout_mult'],R['partner_payout_avg'])
pr('propensity',R['propensity']); pr('top coef',R['propensity_top'])
for s in R['segments']: pr({k:s[k] for k in ['segment','lead_share','conv','cac','arpu','mrr_share','mrr_per_100','churn','nps','pay','gst','quote_acc','spendm','price_ratio']})
for s in R['bundle_mix']: pr(s)
for k,v in res.items(): pr(k,{a:(round(b,3) if isinstance(b,float) else b) for a,b in v.items() if a not in('seg','flows')},{a:round(b,1) for a,b in v['seg'].items()},[round(x) for x in v['flows']])
pr('waterfall',[(a,round(b,1)) for a,b in wfall]); pr('delta',R['impact_delta'])
