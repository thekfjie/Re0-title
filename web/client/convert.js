export class KanjiConverter{
 constructor(data){this.data=data;this.stages=['compatibility','traditional','japanese'].map(k=>({map:data[k],maximum:Object.keys(data[k]).reduce((n,s)=>Math.max(n,[...s].length),1)}));}
 convert(text){let result=text;for(const {map,maximum} of this.stages){let chars=[...result],out=[];for(let i=0;i<chars.length;){let found=false;for(let size=Math.min(maximum,chars.length-i);size>0;size--){let key=chars.slice(i,i+size).join('');if(Object.hasOwn(map,key)){out.push(map[key]);i+=size;found=true;break;}}if(!found)out.push(chars[i++]);}result=out.join('');}return {source_text:text,text:result,changed:result!==text,method:'opencc-derived-kanji-v1',source_commit:this.data.source_commit};}
}
