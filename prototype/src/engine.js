/* Uplink rules engine. Deterministic: eligibility, quantities, prices, contract, timeline.
   The language model never decides anything in this file. It only extracts a profile and explains the result. */
(function (root) {
  const CITIES = {
    ahmedabad:[1,'Gujarat','gu'],bengaluru:[1,'Karnataka','kn'],bangalore:[1,'Karnataka','kn'],chennai:[1,'Tamil Nadu','ta'],delhi:[1,'Delhi','hi'],hyderabad:[1,'Telangana','te'],
    kolkata:[1,'West Bengal','bn'],mumbai:[1,'Maharashtra','mr'],pune:[1,'Maharashtra','mr'],bhopal:[2,'Madhya Pradesh','hi'],coimbatore:[2,'Tamil Nadu','ta'],indore:[2,'Madhya Pradesh','hi'],
    jaipur:[2,'Rajasthan','hi'],kochi:[2,'Kerala','ml'],lucknow:[2,'Uttar Pradesh','hi'],ludhiana:[2,'Punjab','pa'],mysuru:[2,'Karnataka','kn'],mysore:[2,'Karnataka','kn'],nagpur:[2,'Maharashtra','mr'],
    nashik:[2,'Maharashtra','mr'],patna:[2,'Bihar','hi'],surat:[2,'Gujarat','gu'],vadodara:[2,'Gujarat','gu'],visakhapatnam:[2,'Andhra Pradesh','te'],vizag:[2,'Andhra Pradesh','te']
  };
  const POS = { micro: 0, prof: 0.5, multi: 0.5, mfg: 0.5 }; // micro at catalogue floor, others at mid-band (what the data shows today)
  const FIBRE = ['P01','P02','P03'], WIRED = ['P01','P02','P03','P05','P06'];
  const SEG_NAME = { micro:'Micro retail & services', prof:'Professional office', multi:'Small multi-site business', mfg:'Small manufacturer' };
  const BUNDLE_NAME = { micro:'Dukaan Starter', prof:'Office Secure', multi:'Chain One-Bill', mfg:'Factory Connect' };
  const WHY = {
    P01:'Reliable internet so UPI, POS and WhatsApp never depend on a phone hotspot.',
    P02:'Fast enough for your whole team, with room to add a fixed IP later.',
    P03:'1 Gbps with priority support, for heavy files or many users at once.',
    P04:'Plug-and-play wireless broadband, live in about 2 days, for sites fibre cannot reach.',
    P05:'Dedicated line that is not shared with anyone, with a 99.5% uptime promise.',
    P06:'100 Mbps dedicated line with a 99.9% uptime promise, for machines and ERP.',
    P07:'A business number for you, with 50 GB and unlimited calls.',
    P08:'Priority care and roaming for the people customers actually call.',
    P09:'If the main line goes down, a 4G/5G backup takes over by itself.',
    P10:'Manage every branch from one screen and keep billing apps running first.',
    P11:'A fixed address so CCTV, servers or remote access stay reachable.',
    P12:'One business number with IVR and call recording, over your internet line.',
    P13:'An 1800 number customers can call free.',
    P14:'10,000 SMS a month for alerts and offers, with DLT registration help.',
    P15:'Verified WhatsApp with a catalogue and 1,000 conversations a month.',
    P16:'Email on your own domain, documents and video meetings for each person.',
    P17:'Automatic backup of PCs and phones, so records survive a theft or a crash.',
    P18:'A simple 5-page website with domain and SSL, so customers can find you.',
    P19:'GST-ready billing and inventory with UPI and card on a tablet.',
    P20:'Ransomware and virus protection for each device.',
    P21:'A managed firewall at the site, watched by the security team.',
    P22:'Separate Wi-Fi for customers, so your billing network stays private.',
    P23:'HD camera with 30 days of cloud recording, viewable on your phone.',
    P24:'Sensors that show machine uptime and energy use.',
    P25:'Live GPS for each vehicle on one dashboard.'
  };
  const NEED_MAP = { whatsapp:'P15', cctv:'P23', pos:'P19', website:'P18', email:'P16', backup:'P17', antivirus:'P20', firewall:'P21', wifi:'P22', fleet:'P25', iot:'P24', tollfree:'P13', ivr:'P12', sms:'P14', staticip:'P11', failover:'P09', sdwan:'P10', leased:'P05', gigabit:'P03', leased100:'P06' };

  function cat(C){ const m={}; C.forEach(p=>m[p.id]=p); return m; }

  function checkProduct(p, ctx, inBundle) {
    const r = [];
    if (p.tiers.indexOf(ctx.tier) < 0) r.push({ code:'tier', text:`${p.name} is sold only in Tier ${p.tiers.join(' and ')} cities, and ${ctx.cityName||'your city'} is Tier ${ctx.tier}.` });
    if (ctx.employees < p.minEmp) r.push({ code:'size', text:`${p.name} is for businesses with ${p.minEmp}+ people; you have ${ctx.employees}.` });
    if (ctx.sites < p.minSites) r.push({ code:'sites', text:`${p.name} is for ${p.minSites}+ locations; you have ${ctx.sites}.` });
    if (p.gst && ctx.gst !== 'active') r.push({ code:'gst', text: ctx.gst==='inactive' ? `${p.name} needs an active GSTIN, and yours is ${ctx.gstStatus||'not active'}.` : `${p.name} needs an active GSTIN.` });
    if (p.oneOf.length && !p.oneOf.some(x=>inBundle.has(x))) r.push({ code:'dep', text:`${p.name} works only with ${p.oneOf.join(', ')} in the same bundle.` });
    return r;
  }

  function altFor(id, codes, ctx) {
    if (id==='P03') return 'Biz Fibre 300 is available and suits this size.';
    if (id==='P05'||id==='P06') return ctx.tier===1 && ctx.employees>=5 && ctx.gst==='active' ? 'Biz Fibre 1G gives the speed without a leased line.' : 'Biz Fibre 300 is the closest fit today.';
    if (id==='P10') return 'Backup Failover on each site gives most of the uptime benefit.';
    if (id==='P15') return codes.includes('gst') ? 'Use the free WhatsApp Business app today. We can add the verified API as soon as you have a GSTIN.' : '';
    if (id==='P11') return 'Static IP attaches to Biz Fibre. Add a Biz Fibre line or ask for a fixed address on the leased line through the sales team.';
    if (id==='P09') return 'Failover needs a wired main line. Biz 5G AirFiber already runs on mobile network, so a second mobile line is the simple backup.';
    if (id==='P12'||id==='P13') return codes.includes('gst') ? 'Your mobile line can forward calls for now. This unlocks once you have a GSTIN.' : 'A second business mobile line covers this today.';
    if (id==='P14') return 'The free WhatsApp Business app covers small broadcasts until you have a GSTIN.';
    return '';
  }

  function connectivity(pf, seg, ctx, C) {
    const wants = new Set(pf.needs||[]);
    const elig = id => !checkProduct(C[id], ctx, new Set()).length;
    if (pf.noFibre) {
      if (seg==='mfg' && ctx.employees>=10 && ctx.gst==='active') return 'P05';
      return 'P04';
    }
    if (seg==='micro') return 'P01';
    if (seg==='prof') return (wants.has('gigabit') && elig('P03')) ? 'P03' : 'P02';
    if (seg==='multi') return 'P02';
    if (wants.has('leased100') && elig('P06')) return 'P06';
    if (ctx.employees>=25 && ctx.heavy && elig('P06')) return 'P06';
    if (elig('P05')) return 'P05';
    return (wants.has('gigabit') && elig('P03')) ? 'P03' : 'P02';
  }

  function segmentOf(pf) {
    if (pf.kind==='mfg') return 'mfg';
    if ((pf.sites||1)>=2) return 'multi';
    if (pf.kind==='prof') return 'prof';
    return 'micro';
  }

  function ctxOf(pf) {
    const city=(pf.city||'').toLowerCase().trim(), c=CITIES[city];
    return { tier: c?c[0]:(pf.tier||1), cityKnown:!!c, cityName: pf.city||'', employees: Math.max(1,+pf.employees||1), sites: Math.max(1,+pf.sites||1), gst: pf.gst||'none', gstStatus: pf.gstStatus, heavy: !!pf.heavy };
  }

  function recommend(pf, CATALOG) {
    const C = cat(CATALOG), ctx = ctxOf(pf), seg = segmentOf(pf), e=ctx.employees, s=ctx.sites;
    const out = { segment:seg, segmentName:SEG_NAME[seg], name:BUNDLE_NAME[seg], tier:ctx.tier, lines:[], addons:[], blocked:[], notes:[], ctx };
    if ((pf.city||'') && !ctx.cityKnown) { out.outOfArea=true; out.notes.push(`${pf.city} is outside the current Tier 1 and Tier 2 launch cities, so we will add you to the waitlist and share an indicative plan.`); }
    const conn = connectivity(pf, seg, ctx, C);
    const base = [];
    const add = (id,q,core)=>base.push({id,q:Math.max(1,Math.round(q)),core:!!core});
    const lines = pf.lines ? +pf.lines : null;
    if (pf.mobileOnly) { add('P07', lines||1, true); }
    else if (seg==='micro') { add(conn,1,true); add('P07',lines||1,true); }
    else if (seg==='prof') {
      add(conn,1,true); add('P08',lines||Math.min(3,Math.ceil(e/4)),true);
      add('P16',e); add('P20',Math.ceil(e*.6)); add('P17',1);
    } else if (seg==='multi') {
      add(conn,s,true); add('P08',lines||s,true); add('P09',s); add('P22',s); add('P23',2*s);
    } else {
      add(conn,1,true); add('P08',lines||Math.max(3,Math.ceil(e/20)),true); add('P16',Math.min(e,12)); add('P20',Math.min(e,9)); add('P21',1);
    }
    const addonOf = { micro:[['P07',1],['P22',1],['P19',1],['P23',2],['P18',1],['P15',1]], prof:[['P12',2],['P13',1],['P09',1],['P11',1],['P21',1],['P15',1],['P14',1]], multi:[['P10',s],['P19',s],['P13',1],['P15',1],['P21',1],['P12',2]], mfg:[['P23',4],['P24',8],['P25',4],['P02',1],['P09',1]] }[seg];
    // needs the owner asked for are promoted from add-on to bundle, and fail visibly if ineligible
    const asked = [];
    (pf.needs||[]).forEach(n=>{ let id=NEED_MAP[n]; if(!id) return; if(id==='P05'&&conn==='P06')return; if(id==='P03'&&conn==='P03')return; asked.push(id); });
    const qtyFor = id => ({P16:seg==='micro'?Math.min(e,3):e,P20:Math.ceil(e*.6),P23:pf.cameras||(seg==='multi'?2*s:2),P25:pf.vehicles||2,P24:pf.machines||8,P12:2,P10:s,P19:seg==='multi'?s:1})[id]||1;
    if (conn==='P05'||conn==='P06'||conn==='P04') { /* static IP and failover depend on fibre or wired */ }
    asked.forEach(id=>{ if(!base.find(b=>b.id===id)) base.push({id,q:qtyFor(id),core:false,asked:true}); else base.find(b=>b.id===id).asked=true; });
    // connectivity swap asked explicitly but unavailable
    const set0 = new Set(base.map(b=>b.id));
    const kept=[];
    // first pass: non-dependency rules
    base.forEach(b=>{ const p=C[b.id]; const r=checkProduct(p,ctx,set0).filter(x=>x.code!=='dep'); if(r.length){ const codes=r.map(x=>x.code); out.blocked.push({id:b.id,name:p.name,reason:r.map(x=>x.text).join(' '),alt:altFor(b.id,codes,ctx),codes}); if(b.core){ const sub=fallback(b.id,ctx,C); if(sub&&!kept.find(k=>k.id===sub)) kept.push({id:sub,q:b.q,core:true}); } } else kept.push(b); });
    // second pass: dependencies against what survived
    const set1=new Set(kept.map(k=>k.id)); const final=[];
    kept.forEach(b=>{ const p=C[b.id]; const r=checkProduct(p,ctx,set1).filter(x=>x.code==='dep'); if(r.length){ out.blocked.push({id:b.id,name:p.name,reason:r.map(x=>x.text).join(' '),alt:altFor(b.id,['dep'],ctx),codes:['dep']}); } else final.push(b); });
    const pos = POS[seg];
    const set2=new Set(final.map(b=>b.id));
    out.lines = final.map(b=>line(b,C,pos,true));
    addonOf.forEach(([id,q])=>{ if(set2.has(id) && id!=='P07') return; const p=C[id]; const inb=new Set([...set2,id]); const r=checkProduct(p,ctx,inb); if(id==='P07'&&!pf.mobileOnly){ out.addons.push(line({id,q,core:false},C,pos,false)); return;} if(!r.length) out.addons.push(line({id,q,core:false},C,pos,false)); else if(!out.blocked.find(x=>x.id===id) && r.some(x=>x.code==='gst')) out.blocked.push({id,name:p.name,reason:r.map(x=>x.text).join(' '),alt:altFor(id,r.map(x=>x.code),ctx),codes:r.map(x=>x.code),quiet:true}); });
    if (ctx.gst==='none') out.notes.push('No GSTIN is needed for this bundle. You can complete KYC with PAN and a trade licence or shop registration.');
    if (ctx.gst==='inactive') out.notes.push(`Your GSTIN is ${ctx.gstStatus||'not active'}, so GST-only products are held back until it is active again.`);
    if (pf.budget) applyBudget(out,+pf.budget);
    return finish(out,C);
  }
  function fallback(id,ctx,C){ if(id==='P03'||id==='P05'||id==='P06') return 'P02'; return null; }
  function line(b,C,pos,on){ const p=C[b.id]; const price=Math.round(p.min+(p.max-p.min)*pos); return { id:b.id,name:p.name,unit:p.unit,qty:b.q,price,total:price*b.q,setup:p.setup*b.q,contract:p.contract,days:p.days,why:WHY[b.id],core:!!b.core,asked:!!b.asked,on }; }
  function applyBudget(o,budget){
    const tot=()=>o.lines.filter(l=>l.on).reduce((a,l)=>a+l.total,0);
    const order=o.lines.filter(l=>!l.core).sort((a,b)=>(a.asked?1:0)-(b.asked?1:0)||b.total-a.total);
    for(const l of order){ if(tot()<=budget) break; l.on=false; o.notes.push(`${l.name} moved to optional add-ons to stay within your ₹${budget.toLocaleString('en-IN')} budget.`); }
    o.addons.push(...o.lines.filter(l=>!l.on)); o.lines=o.lines.filter(l=>l.on);
    if(tot()>budget){ o.overBudget=true; o.notes.push(`The lowest bundle that fits your business is ₹${tot().toLocaleString('en-IN')} a month, which is above your ₹${budget.toLocaleString('en-IN')} budget. I will not show a lower price than the catalogue allows.`); }
  }
  function finish(o,C){ return reprice(o); }
  function reprice(o){
    const on=o.lines.concat(o.addons.filter(a=>a.on));
    o.monthly=on.reduce((a,l)=>a+l.total,0); o.setup=on.reduce((a,l)=>a+l.setup,0); o.contract=on.reduce((a,l)=>Math.max(a,l.contract),0);
    on.forEach(l=>l.live=liveDay(l));
    o.firstLive=on.reduce((a,l)=>Math.min(a,l.live),99); o.allLive=on.reduce((a,l)=>Math.max(a,l.live),0);
    o.simUsers=on.filter(l=>SIMS.includes(l.id)).reduce((a,l)=>a+l.qty,0);
    return o;
  }
  /* Staged activation. Telecom rules: premises are checked before business SIMs issue, and each SIM waits for its own
     user's biometric identification. Cloud and security products have no such wait, so they go live first. */
  const SIMS=['P07','P08'], FIXED=['P01','P02','P03','P04','P05','P06'], VISIT_DAY=2;
  function liveDay(l){ if(SIMS.includes(l.id)) return Math.max(l.days,VISIT_DAY+1); if(FIXED.includes(l.id)) return Math.max(l.days,VISIT_DAY); return l.days; }
  /* Toggling an add-on re-runs dependencies, so a toggle can never create an illegal bundle */
  function canToggle(o,id,CATALOG){ const C=cat(CATALOG); const set=new Set(o.lines.map(l=>l.id).concat(o.addons.filter(a=>a.on).map(a=>a.id))); set.add(id); const r=checkProduct(C[id],o.ctx,set); return r; }
  function audit(o,CATALOG){ const C=cat(CATALOG), ids=new Set(o.lines.map(l=>l.id).concat(o.addons.filter(a=>a.on).map(a=>a.id))); const v=[]; ids.forEach(id=>{ checkProduct(C[id],o.ctx,ids).forEach(r=>v.push(id+':'+r.code)); }); return v; }

  /* Offline language understanding for the guided flow. English, Hinglish and Hindi keywords. The LLM path replaces this. */
  const KIND=[[/factory|manufactur|workshop|textile|plastic|moulding|packaging|printing|auto.?parts|food processing|कारखाना|फैक्ट्री|फैक्टरी/i,'mfg'],
    [/chain|branches|outlets|stores|franchise|शाखा|ब्रांच/i,'multi'],
    [/clinic|dental|dentist|doctor|physio|diagnostic|lab\b|ca firm|chartered|accountant|lawyer|law office|advocate|legal|architect|coaching|tuition|insurance|travel agency|real estate|office|क्लिनिक|डॉक्टर|कोचिंग|ऑफिस|वकील/i,'prof'],
    [/kirana|grocery|shop|store|dukan|dukaan|salon|parlou?r|pharmacy|medical store|bakery|sweet|boutique|optician|stationery|hardware|mobile repair|restaurant|cafe|hotel|gym|किराना|दुकान|सैलून|मेडिकल/i,'micro']];
  const NEED=[[/whats\s*app|व्हाट्स/i,'whatsapp'],[/cctv|camera|कैमरा/i,'cctv'],[/\bpos\b|billing|बिलिंग|invoice/i,'pos'],[/website|site banani|वेबसाइट/i,'website'],[/e-?mail|ईमेल/i,'email'],[/cloud backup|data backup|बैकअप/i,'backup'],[/antivirus|ransomware|virus/i,'antivirus'],[/firewall|फ़ायरवॉल/i,'firewall'],[/guest wi-?fi|customer wi-?fi|\bwi-?fi\b|वाई-?फाई/i,'wifi'],[/fleet|gps|vehicle|delivery bike|गाड़ी/i,'fleet'],[/machine|iot|sensor|मशीन/i,'iot'],[/toll.?free|1800|टोल/i,'tollfree'],[/ivr|call recording|cloud telephony|sip\b/i,'ivr'],[/\bsms\b/i,'sms'],[/static ip|fixed ip/i,'staticip'],[/failover|backup internet|backup line/i,'failover'],[/sd-?wan|central(ly)? manage/i,'sdwan'],[/leased line.*100|100.*leased line|\bill 100\b/i,'leased100'],[/leased line|dedicated (line|internet)|लीज्ड/i,'leased'],[/\b1\s?g(bps)?\b|gigabit/i,'gigabit']];
  const CITY_SCRIPT={'इंदौर':'Indore','दिल्ली':'Delhi','मुंबई':'Mumbai','पुणे':'Pune','कोच्चि':'Kochi','जयपुर':'Jaipur','लखनऊ':'Lucknow','पटना':'Patna','सूरत':'Surat','लुधियाना':'Ludhiana','नागपुर':'Nagpur','नाशिक':'Nashik','भोपाल':'Bhopal','अहमदाबाद':'Ahmedabad','वडोदरा':'Vadodara','बेंगलुरु':'Bengaluru','चेन्नई':'Chennai','हैदराबाद':'Hyderabad','कोलकाता':'Kolkata',
    'சென்னை':'Chennai','கோயம்புத்தூர்':'Coimbatore','ಬೆಂಗಳೂರು':'Bengaluru','ಮೈಸೂರು':'Mysuru','హైదరాబాద్':'Hyderabad','విశాఖపట్నం':'Visakhapatnam','কলকাতা':'Kolkata','અમદાવાદ':'Ahmedabad','સુરત':'Surat','વડોદરા':'Vadodara','ਲੁਧਿਆਣਾ':'Ludhiana','കൊച്ചി':'Kochi','पुणें':'Pune','मुम्बई':'Mumbai'};
  /* Speech recognition writes numbers as words and in Indian-script digits. Turn both into plain digits
     when they come before a unit (people, sites, cameras...), so spoken and typed messages parse the same. */
  const NUMW={'एक':1,'दो':2,'तीन':3,'चार':4,'पांच':5,'पाँच':5,'छह':6,'छः':6,'सात':7,'आठ':8,'नौ':9,'दस':10,'ग्यारह':11,'बारह':12,'पंद्रह':15,'पन्द्रह':15,'बीस':20,'पच्चीस':25,'तीस':30,'चालीस':40,'पचास':50,
    one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,fifteen:15,twenty:20,thirty:30,forty:40,fifty:50};
  const UNIT='people|staff|employees?|workers?|log|लोग|कर्मचारी|team|sites?|branch(?:es)?|outlets?|locations?|stores?|shops?|शाखा|ब्रांच|दुकानें|cameras?|कैमरे|vehicles?|trucks?|bikes?|गाड़ियां|machines?|मशीनें';
  const NUMRE=new RegExp('(^|[\\s,।])('+Object.keys(NUMW).sort((a,b)=>b.length-a.length).join('|')+')(?=\\s+(?:'+UNIT+'))','gi');
  function spoken(t){
    t=t.replace(/[०-९০-৯੦-੯૦-૯௦-௯౦-౯೦-೯൦-൯]/g,c=>String((c.charCodeAt(0)&15)-6));
    return t.replace(NUMRE,(m,a,w)=>a+NUMW[w.toLowerCase()]);
  }
  function parse(text, pf) {
    pf = Object.assign({needs:[]}, pf||{}); const t=spoken(text||'');
    for(const [re,k] of KIND){ if(re.test(t)){ pf.kind=pf.kind||k; break; } }
    let m;
    if((m=t.match(/(\d+)\s*(people|staff|employees?|workers?|log|लोग|कर्मचारी|team)/i))) pf.employees=+m[1];
    if((m=t.match(/(\d+)\s*(sites?|branches|branch|outlets?|locations?|stores?|shops?|शाखा|ब्रांच|दुकानें)/i))) pf.sites=+m[1];
    if((m=t.match(/(?:₹|rs\.?|inr|budget[^0-9]{0,12})\s*([\d,]{3,7})/i))) pf.budget=+m[1].replace(/,/g,'');
    if((m=t.match(/(\d+)\s*(cameras?|कैमरे)/i))) pf.cameras=+m[1];
    if((m=t.match(/(\d+)\s*(vehicles?|trucks?|bikes?|गाड़ियां)/i))) pf.vehicles=+m[1];
    if((m=t.match(/(\d+)\s*(machines?|मशीनें)/i))) pf.machines=+m[1];
    Object.keys(CITIES).forEach(c=>{ if(new RegExp('\\b'+c+'\\b','i').test(t)) pf.city=c[0].toUpperCase()+c.slice(1); });
    Object.keys(CITY_SCRIPT).forEach(c=>{ if(t.includes(c)) pf.city=CITY_SCRIPT[c]; });
    if(/no\s*gst|without gst|gst nahi|(gst|जीएसटी)\s*नही|बिना (gst|जीएसटी)|not registered|don'?t have gst|no gstin/i.test(t)) pf.gst='none';
    const g=t.toUpperCase().match(/\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b/); if(g) pf.gstin=g[0];
    if(/no fib(re|er)|fibre (is )?not available|fiber not available|fibre nahi/i.test(t)) pf.noFibre=true;
    if(/only (a )?mobile|just (a )?(sim|mobile)|sirf sim/i.test(t)) pf.mobileOnly=true;
    NEED.forEach(([re,n])=>{ if(re.test(t) && pf.needs.indexOf(n)<0) pf.needs.push(n); });
    return pf;
  }
  /* Prompt-injection and off-topic guard for the chat box */
  function guard(text){
    if(/ignore (all|your|previous)|system prompt|you are now|act as|jailbreak/i.test(text)) return 'injection';
    if(/(free|discount|\d+\s*%\s*off|cheaper|kam kar|sasta|छूट)/i.test(text)) return 'discount';
    return null;
  }
  const api={VISIT_DAY,SIMS,liveDay,CITIES,recommend,parse,guard,reprice,canToggle,audit,checkProduct,segmentOf,ctxOf,WHY,SEG_NAME,BUNDLE_NAME};
  if(typeof module!=='undefined') module.exports=api; else root.Engine=api;
})(typeof window!=='undefined'?window:globalThis);
