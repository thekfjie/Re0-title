import fs from 'node:fs/promises';import path from 'node:path';import {spawnSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),hosting=path.join(root,'hosting');
function run(args,cwd=root){const r=spawnSync(process.execPath,args,{cwd,stdio:'inherit'});if(r.status!==0)throw new Error('Build failed');}
run(['scripts/build-web.mjs']);
await fs.rm(path.join(hosting,'public'),{recursive:true,force:true});await fs.cp(path.join(root,'dist'),path.join(hosting,'public'),{recursive:true});
await fs.rm(path.join(hosting,'public/api'),{recursive:true,force:true});await fs.rm(path.join(hosting,'public/index.html'),{force:true});
run(['scripts/run-framework.mjs','build'],hosting);
await fs.rm(path.join(root,'dist'),{recursive:true,force:true});await fs.cp(path.join(hosting,'dist'),path.join(root,'dist'),{recursive:true});
console.log('Built Sites Worker semantic gateway + browser assets.');
