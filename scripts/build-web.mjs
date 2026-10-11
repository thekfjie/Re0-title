import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),dist=path.join(root,'dist');
await fs.mkdir(dist,{recursive:true});await fs.cp(path.join(root,'web/client'),dist,{recursive:true});await fs.mkdir(path.join(dist,'vendor'),{recursive:true});
await fs.mkdir(path.join(dist,'api'),{recursive:true});await fs.writeFile(path.join(dist,'api/status'),JSON.stringify({service:'browser-harfbuzz',llm_available:false}));
for(const file of ['hb.js','hbjs.js','hb.wasm'])await fs.copyFile(path.join(root,'node_modules/harfbuzzjs',file),path.join(dist,'vendor',file));
await fs.copyFile(path.join(root,'node_modules/kuromoji/build/kuromoji.js'),path.join(dist,'vendor/kuromoji.js'));await fs.cp(path.join(root,'node_modules/kuromoji/dict'),path.join(dist,'dict'),{recursive:true});
const {spawnSync}=await import('node:child_process');const result=spawnSync(process.env.PYTHON_BUILD||path.join(root,'.venv/bin/python'),['-c',`import yaml,json;from pathlib import Path;r=Path(${JSON.stringify(root)});c={k:yaml.safe_load((r/'config'/(n+'.yaml')).read_text()) for k,n in [('rules','template_rules'),('weights','layout_weights'),('colors','color_palettes')]};(r/'dist/config.json').write_text(json.dumps(c));cases=json.loads((r/'experiments/benchmark_cases.json').read_text());plans=json.loads((r/'experiments/session_plans.json').read_text())['plans'];(r/'dist/session-plans.json').write_text(json.dumps([{'text':c['text'],'plan':plans[c['id']]} for c in cases],ensure_ascii=False))`],{stdio:'inherit'});if(result.status)throw new Error('Config build failed');
await fs.copyFile(path.join(root,'experiments/benchmark/b14/A-2.png'),path.join(dist,'demo.png'));
await fs.cp(path.join(root,'experiments/benchmark'),path.join(dist,'benchmark'),{recursive:true});
// Research docs are already present in web/client/research.html; fonts never enter this output.
for(const folder of ['harfbuzzjs','kuromoji'])await fs.copyFile(path.join(root,'node_modules',folder,folder==='kuromoji'?'LICENSE-2.0.txt':'LICENSE'),path.join(dist,'vendor',folder+'-LICENSE.txt'));
console.log('Built font-free browser application + benchmark.');
