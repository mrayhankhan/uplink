/* Smart KYC validator. Same steps as analysis/kyc_pipeline.py, running on raw OCR text. */
(function (root) {
  const ALPH='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', TODAY=new Date('2026-07-15'); // case-defined "today"
  const STATE={'03':'Punjab','07':'Delhi','08':'Rajasthan','09':'Uttar Pradesh','10':'Bihar','19':'West Bengal','23':'Madhya Pradesh','24':'Gujarat','27':'Maharashtra','29':'Karnataka','32':'Kerala','33':'Tamil Nadu','36':'Telangana','37':'Andhra Pradesh'};
  function checksum(g){let s=0;for(let i=0;i<14;i++){const v=ALPH.indexOf(g[i])*(i%2?2:1);s+=Math.floor(v/36)+v%36}return ALPH[(36-s%36)%36]}
  const FORMAT=/^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
  const validGstin=g=>FORMAT.test(g)&&checksum(g)===g[14];
  const TO_D={O:'0',Q:'0',D:'0',I:'1',L:'1',Z:'2',S:'5',B:'8',G:'6'},TO_A={'0':'O','1':'I','2':'Z','5':'S','8':'B','6':'G'};
  function repair(raw){const g=raw.toUpperCase().replace(/[^A-Z0-9]/g,'');if(g.length!==15)return g;const o=g.split('');[0,1,7,8,9,10].forEach(i=>o[i]=TO_D[o[i]]||o[i]);[2,3,4,5,6,11].forEach(i=>o[i]=TO_A[o[i]]||o[i]);o[13]='Z';if(o[12]==='I')o[12]='1';return o.join('')}
  function ratio(a,b){a=(a||'').replace(/\W/g,'').toLowerCase();b=(b||'').replace(/\W/g,'').toLowerCase();if(!a.length&&!b.length)return 1;const m=[];for(let i=0;i<=a.length;i++){m[i]=[i];for(let j=1;j<=b.length;j++)m[i][j]=i===0?j:Math.min(m[i-1][j]+1,m[i][j-1]+1,m[i-1][j-1]+(a[i-1]===b[j-1]?0:1))}return 1-m[a.length][b.length]/Math.max(a.length,b.length,1)}
  function nearest(g,keys,cut){let best=null,bs=cut;for(const k of keys){if(k.slice(0,2)!==g.slice(0,2))continue;const r=ratio(g,k);if(r>=bs){bs=r;best=k}}return best}
  const mask=g=>g?g.slice(0,2)+'•••••'+g.slice(7,11)+'•'+g.slice(12):'';
  function run(id,D,log){
    log=log||(()=>{});
    const O=t=>D.ocr[id+'_'+t], rec={id,flags:[],soft:[],steps:[]};
    const gd=(O('gst_certificate')||{l:[]}).l, ud=O('udyam_certificate'), sd=(O('signatory_id')||{l:[]}).l, bd=(O('address_proof')||{l:[]}).l;
    const sharp=D.blur[id+'_gst_certificate'];
    log(`image check: GST certificate sharpness ${sharp}, ${gd.length} text lines`);
    if(gd.length<6) rec.flags.push(['UNREADABLE_GST_CERT','GST certificate is too blurred to read. Ask for a new photo on this same screen.']);
    let raw=null;gd.forEach(l=>{const c=l.replace(/lJ/g,'U').replace(/[^A-Za-z0-9]/g,'');if(c.length>=14&&c.length<=16&&/^\d\d/.test(c)&&c===c.toUpperCase()&&(c.match(/[A-Z]/g)||[]).length>=4)raw=c});
    let g=raw?repair(raw):null,lowConf=false;
    if(g&&g.length!==15){const n=nearest(g,Object.keys(D.gst),.85);if(n){g=n;lowConf=true}}
    let reg=null,legal=gd.find(l=>l.includes('(Prop')||/(LLP|Pvt Ltd)$/.test(l));
    if(g){
      const ok=g.length===15&&validGstin(g);reg=D.gst[g]||null;log(`GSTIN ${mask(g)}: checksum ${ok?'valid':'FAILED'}, registry ${reg?reg[6]:'no match'}`);
      if(!ok||!reg){const n=nearest(g,Object.keys(D.gst),.9);rec.flags.push(['GSTIN_INVALID',`GSTIN on the certificate fails the checksum and is not in the registry.${n?' The nearest registered GSTIN differs by one character.':''}`]);if(n)reg=D.gst[n]}
      else if(reg[6]!=='Active')rec.flags.push(['GSTIN_'+reg[6].toUpperCase(),`Registry shows this GSTIN is ${reg[6]}. GST-only products stay blocked until it is active.`]);
      if(reg&&legal&&ratio(legal,reg[0])<.97)rec.flags.push(['LEGAL_NAME_MISMATCH',`Legal name on the certificate does not match the registry ("${legal}" against "${reg[0]}").`]);
    }
    const lead=D.leads.find(x=>x.kid===id)||null; rec.business=lead?lead.biz:(reg?reg[1]:null);
    let um=null;if(ud)for(const l of ud.l){const m=l.match(/U[DO0]YAM\s*-?\s*[A-Z]{2}\s*-?\s*[0OQD]{2}\s*-?\s*\d{7}/);if(m){const c=m[0].replace(/[\s-]/g,'');um=`UDYAM-${c.slice(5,7)}-00-${c.slice(-7)}`;break}}
    if(!ud){rec.flags.push(['UDYAM_CERT_MISSING',lead&&lead.udyam?'Udyam certificate was not uploaded. The number was found by lookup, so the owner only confirms it.':'Udyam certificate was not uploaded and no record was found.']);log('Udyam certificate absent, trying lookup')}
    else if(!um){rec.flags.push(['UDYAM_NUMBER_BLANK','Udyam certificate has no registration number. Treat as unregistered and use the no-Udyam path.'])}
    else if(!D.ud[um])rec.flags.push(['UDYAM_NOT_FOUND','Udyam number is not in the registry.']);
    else log(`Udyam ${um.slice(0,8)}•••: found in registry`);
    let sname=null;const si=sd.indexOf('Name');if(si>=0)sname=sd[si+1];
    const vm=sd.join(' ').match(/\d{4}-\d{2}-\d{2}/);
    if(vm&&new Date(vm[0])<TODAY)rec.flags.push(['ID_EXPIRED',`Signatory ID expired on ${vm[0]}.`]);
    if(lead&&sname&&ratio(sname,lead.contact)<.85)rec.flags.push(['SIGNATORY_MISMATCH',`The ID is for ${sname}, but the applicant on record is ${lead.contact}. Ask for the right ID or an authorisation letter.`]);
    const bm=bd.join(' ').match(/\d{4}-\d{2}-\d{2}/);
    if(bm){const age=Math.round((TODAY-new Date(bm[0]))/864e5);rec.billAge=age;log(`address proof dated ${bm[0]}: ${age} days old, limit 90`);if(age>90)rec.flags.push(['ADDRESS_PROOF_STALE',`Bill is ${age} days old and the limit is 90. Ask for a newer bill.`])}
    if(lowConf)rec.soft.push(['OCR_LOW_CONFIDENCE','OCR misread part of the GSTIN. Registry lookup and the legal name resolved it.']);
    if(O('gst_certificate')&&Math.abs(O('gst_certificate').a)>3)rec.soft.push(['SKEWED_SCAN',`Scan is rotated ${Math.round(O('gst_certificate').a)} degrees and was still read correctly.`]);
    rec.gstin=g;rec.reg=reg;rec.sig=sname;rec.contact=lead?lead.contact:null;rec.udyamNo=um;rec.billDate=bm?bm[0]:null;rec.lines=gd.length;
    rec.decision=!rec.flags.length?'PASS':rec.flags.some(f=>/GSTIN_(CANCELLED|SUSPENDED|INVALID)/.test(f[0]))?'STOP':'FIX';
    return rec;
  }
  function lookupGstin(g,D){g=(g||'').toUpperCase().replace(/\s/g,'');if(!FORMAT.test(g))return{ok:false,why:'That does not look like a 15-character GSTIN.'};if(checksum(g)!==g[14])return{ok:false,why:'The last character does not match the GSTIN checksum. Please check for a typing error.'};const r=D.gst[g];if(!r)return{ok:false,why:'This GSTIN is valid in format but is not in the registry.'};return{ok:true,gstin:g,legal:r[0],trade:r[1],constitution:r[2],address:r[3],state:r[4],since:r[5],status:r[6],stateFromCode:STATE[g.slice(0,2)]}}
  function lookupUdyam(u,D){u=(u||'').toUpperCase().trim();const r=D.ud[u];return r?{ok:true,name:r[0],type:r[1],activity:r[2],state:r[3],city:r[4],since:r[5]}:{ok:false,why:'No Udyam record for this number.'}}
  const api={run,checksum,validGstin,repair,lookupGstin,lookupUdyam,mask};
  if(typeof module!=='undefined')module.exports=api;else root.KYC=api;
})(typeof window!=='undefined'?window:globalThis);
