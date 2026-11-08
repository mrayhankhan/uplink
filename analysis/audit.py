"""Independent recheck of deck claims straight from the CSVs, not via model.py."""
import sys, pandas as pd, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
d=sys.argv[1]; L=pd.read_csv(d+'/smb_leads.csv'); G=pd.read_csv(d+'/mock_gstin_registry.csv'); P=pd.read_csv(d+'/product_catalogue.csv',keep_default_na=False)
A=L[L.outcome=='Activated']; print('leads',len(L),'act',len(A),'conv',round(len(A)/len(L)*100,2))
print('CAC',round(L.acquisition_cost_inr.sum()/len(A)),'spend',L.acquisition_cost_inr.sum(),'MRR',A.monthly_bundle_value_inr.sum(),'churn',round((A.churned_within_6_months=='Y').mean()*100,1),'days',round(A.days_lead_to_activation.mean(),1))
cp=A[A.lead_source=='Channel partner']; ms=cp[cp.segment=='Small multi-site businesses']
print('partner payout all mean',round(cp.acquisition_cost_inr.mean()),'max',cp.acquisition_cost_inr.max(),'| chain mean',round(ms.acquisition_cost_inr.mean()),'chain median',ms.acquisition_cost_inr.median(),'chain max',ms.acquisition_cost_inr.max(),'n',len(ms),'mult',round((cp.acquisition_cost_inr/cp.monthly_bundle_value_inr).mean(),2))
m=L[(L.segment=='Micro retail & services')&(L.lead_source=='Field sales')]; ma=m[m.outcome=='Activated']
print('micro field leads',len(m),'act',len(ma),'spend',m.acquisition_cost_inr.sum(),'CAC',round(m.acquisition_cost_inr.sum()/len(ma)),'ARPU',round(ma.monthly_bundle_value_inr.mean()),'months',round(m.acquisition_cost_inr.sum()/len(ma)/ma.monthly_bundle_value_inr.mean(),1))
s=L.merge(G[['gstin','status']],on='gstin',how='left'); x=s[s.has_gstin=='Y'].groupby('status').apply(lambda g:pd.Series(dict(n=len(g),a=(g.outcome=='Activated').sum())),include_groups=False); x['c']=(x.a/x.n*100).round(1); print(x)
order={'Lead':0,'Contacted':1,'Needs assessed':2,'Quote accepted':3,'KYC complete':4,'Activated':5}; L['si']=L.stage_reached.map(order)
print('no gst pass',round((L[(L.has_gstin=='N')&(L.si>=3)].si>=4).mean()*100,1),'gst pass',round((L[(L.has_gstin=='Y')&(L.si>=3)].si>=4).mean()*100,1))
k=L[L.si>=4]; print('t1',round((k[k.city_tier==1].outcome=='Activated').mean()*100,1),'t2',round((k[k.city_tier==2].outcome=='Activated').mean()*100,1))
print('chase churn',{c:round((g.churned_within_6_months=='Y').mean()*100,1) for c,g in A.groupby('customer_follow_up_calls')},'nps',{c:round(g.nps_score.mean(),1) for c,g in A.groupby('customer_follow_up_calls')},'<=2',round((A[A.customer_follow_up_calls<=2].churned_within_6_months=='Y').mean()*100,1))
print('referral',L[L.lead_source=='Referral'].pipe(lambda g:(round((g.outcome=='Activated').mean()*100,1),round(g.acquisition_cost_inr.sum()/(g.outcome=='Activated').sum()))),'field',L[L.lead_source=='Field sales'].pipe(lambda g:(round((g.outcome=='Activated').mean()*100,1),round(g.acquisition_cost_inr.sum()/(g.outcome=='Activated').sum()))))
r=L.current_provider.fillna('').str.startswith('Accel'); print('accel share',round(r.mean()*100,1),'conv',round((L[r].outcome=='Activated').mean()*100,1),'other',round((L[~r].outcome=='Activated').mean()*100,1))
print('referral churn',round((A[A.lead_source=='Referral'].churned_within_6_months=='Y').mean()*100,1),'P04 share',round(A.bundle_products.str.contains('P04').mean()*100,1),'gst free products',(P.requires_gstin=='N').sum())
print('price+competitor drops',L.drop_reason.isin(['Price too high','Competitor offered cheaper plan']).sum())
for s_,g in L.groupby('segment'):
    a=g[g.outcome=='Activated']; print(s_,round(len(g)/len(L)*100,1),round(a.monthly_bundle_value_inr.sum()/A.monthly_bundle_value_inr.sum()*100,1),round(len(a)/len(g)*100,1),round(a.monthly_bundle_value_inr.mean()),round(g.acquisition_cost_inr.sum()/len(a)),'spend',round(g.monthly_telecom_spend_inr.mean()),'gst',round((g.has_gstin=='Y').mean()*100,1))
