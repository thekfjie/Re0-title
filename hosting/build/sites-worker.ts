import handler from 'vinext/server/fetch-handler';
import {handlePlanner,handleTranslation} from '../semantic-gateway.js';
export default {
 async fetch(request:Request,env:any,ctx:any){
  const path=new URL(request.url).pathname;
  if(path==='/api/status')return Response.json({service:'browser-harfbuzz',llm_available:!!(env.LLM_API_KEY||env.OPENAI_API_KEY)},{headers:{'Cache-Control':'no-store'}});
  if(path==='/api/plan')return handlePlanner(request,env);
  if(path==='/api/translate')return handleTranslation(request,env);
  return handler.fetch(request,env,ctx);
 }
};
