importScripts('/vendor/hb.js','/vendor/hbjs.js','/vendor/kuromoji.js');
let core,config,fonts,tokenizer,plans;
const ready=(async()=>{
 core=await import('/core.js');config=await fetch('/config.json').then(r=>r.json());plans=await fetch('/session-plans.json').then(r=>r.json());
 let module=await createHarfBuzz({locateFile:path=>'/vendor/'+path});fonts=new core.BrowserFontProvider(hbjs(module));
 tokenizer=await new Promise((resolve,reject)=>kuromoji.builder({dicPath:'/dict/'}).build((err,t)=>err?reject(err):resolve(t)));
 postMessage({type:'ready'});
})();
self.onmessage=async event=>{
 const {id,type,...args}=event.data;
 try{
  await ready;
  if(type==='font')postMessage({id,type:'font',metadata:await fonts.register(args.role,args.data,args.name)});
  else if(type==='analyze')postMessage({id,type:'tokens',tokens:core.analyze(args.text,tokenizer,config.rules)});
  else if(type==='clear'){fonts.clear();postMessage({id,type:'cleared'});}
  else if(type==='render'){
   const start=performance.now(),text=args.options.text;
   let plan=args.options.mode==='llm'?(args.plan||plans.find(p=>p.text===text)?.plan):null;
   if(args.options.mode==='llm'&&!plan)throw new Error('在线版 B 尚未配置 API；离线计划只支持 Benchmark 固定文本');
   const tokens=plan?core.planTokens(text,plan):core.analyze(text,tokenizer,config.rules);
   const results=core.generate(text,tokens,fonts,config,args.options,plan);
   postMessage({id,type:'results',results,latency:performance.now()-start,plan});
  }
 }catch(error){postMessage({id,type:'error',message:error.message});}
};
ready.catch(error=>postMessage({type:'startup-error',message:error.message}));
