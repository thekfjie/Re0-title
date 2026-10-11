import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),dist=path.join(root,'dist');
await fs.rm(dist,{recursive:true,force:true});
await fs.mkdir(dist,{recursive:true});await fs.cp(path.join(root,'web/client'),dist,{recursive:true});await fs.mkdir(path.join(dist,'vendor'),{recursive:true});
const fontRoot=path.join(root,'assets/open-fonts'),fontOutput=path.join(dist,'open-fonts');
await fs.rm(fontOutput,{recursive:true,force:true});await fs.mkdir(fontOutput,{recursive:true});
const fonts=JSON.parse(await fs.readFile(path.join(fontRoot,'catalog.json'),'utf8'));
const {createHash}=await import('node:crypto');
for(const font of fonts){
 if(!/^[a-z0-9-]+\.(ttf|otf)$/.test(font.file)||!/^[-a-z0-9]+\.OFL\.txt$/.test(font.license_file)||font.license!=='SIL OFL 1.1')throw new Error('Invalid bundled font allowlist');
 const bytes=await fs.readFile(path.join(fontRoot,font.file));if(createHash('sha256').update(bytes).digest('hex')!==font.sha256)throw new Error('Bundled font SHA256 mismatch');
 await fs.writeFile(path.join(fontOutput,font.file),bytes);await fs.copyFile(path.join(fontRoot,font.license_file),path.join(fontOutput,font.license_file));
}
await fs.copyFile(path.join(fontRoot,'catalog.json'),path.join(fontOutput,'catalog.json'));
const conversionRoot=path.join(root,'assets/conversion');await fs.mkdir(path.join(dist,'conversion'),{recursive:true});
for(const file of ['kanji.json','LICENSE','manifest.json'])await fs.copyFile(path.join(conversionRoot,file),path.join(dist,'conversion',file));
await fs.mkdir(path.join(dist,'api'),{recursive:true});await fs.writeFile(path.join(dist,'api/status'),JSON.stringify({service:'browser-harfbuzz',llm_available:false}));
for(const file of ['hb.js','hbjs.js','hb.wasm'])await fs.copyFile(path.join(root,'node_modules/harfbuzzjs',file),path.join(dist,'vendor',file));
await fs.copyFile(path.join(root,'node_modules/kuromoji/build/kuromoji.js'),path.join(dist,'vendor/kuromoji.js'));await fs.cp(path.join(root,'node_modules/kuromoji/dict'),path.join(dist,'dict'),{recursive:true});
const {spawnSync}=await import('node:child_process');const result=spawnSync(process.env.PYTHON_BUILD||path.join(root,'.venv/bin/python'),['-c',`import yaml,json;from pathlib import Path;r=Path(${JSON.stringify(root)});c={k:yaml.safe_load((r/'config'/(n+'.yaml')).read_text()) for k,n in [('rules','template_rules'),('weights','layout_weights'),('colors','color_palettes')]};(r/'dist/config.json').write_text(json.dumps(c));cases=json.loads((r/'experiments/benchmark_cases.json').read_text());plans=json.loads((r/'experiments/session_plans.json').read_text())['plans'];(r/'dist/session-plans.json').write_text(json.dumps([{'text':c['text'],'plan':plans[c['id']]} for c in cases],ensure_ascii=False))`],{stdio:'inherit'});if(result.status)throw new Error('Config build failed');
await fs.copyFile(path.join(root,'experiments/benchmark/b14/A-2.png'),path.join(dist,'demo.png'));
await fs.copyFile(path.join(root,'references/catalog.json'),path.join(dist,'references.json'));
await fs.cp(path.join(root,'experiments/reference-benchmark'),path.join(dist,'reference-benchmark'),{recursive:true});
const liveFolder=path.join(root,'experiments/live-benchmark');let benchmarkFolder=path.join(root,'experiments/benchmark');
try{const live=JSON.parse(await fs.readFile(path.join(liveFolder,'summary.json'),'utf8'));if(live.live_llm&&live.errors===0)benchmarkFolder=liveFolder;}catch{}
await fs.cp(benchmarkFolder,path.join(dist,'benchmark'),{recursive:true});
// Only the explicit OFL catalogue enters this output. Uploads and private fonts never do.
for(const folder of ['harfbuzzjs','kuromoji'])await fs.copyFile(path.join(root,'node_modules',folder,folder==='kuromoji'?'LICENSE-2.0.txt':'LICENSE'),path.join(dist,'vendor',folder+'-LICENSE.txt'));
console.log('Built application with allowlisted OFL fonts + benchmark.');
