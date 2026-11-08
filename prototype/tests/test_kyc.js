/* Checks the browser validator gives the same decisions as analysis/kyc_pipeline.py on raw OCR */
const path=require('path'),fs=require('fs');global.window={};
eval(fs.readFileSync(path.join(__dirname,'..','src','data.js'),'utf8'));
const KYC=require(path.join(__dirname,'..','src','kyc.js')),D=global.window.DATA;
let ok=0;for(const r of D.kres){const j=KYC.run(r.id,D);const a=j.flags.map(f=>f[0]).sort().join(),b=r.flags.map(f=>f[0]).sort().join();const same=j.decision===r.decision&&a===b;ok+=same;console.log((same?'SAME ':'DIFF ')+r.id,j.decision,a,same?'':'| python: '+r.decision+' '+b)}
console.log(ok+'/12 match');process.exit(ok===12?0:1);
