import {validateColorSettings} from './accent.js';

// Recolour outlines and remove the canvas without reshaping or invoking a model.
export function paintSVG(source,text,overrides=[],transparent=false,background='#000000'){
 const settings=validateColorSettings(text,null,overrides),doc=new DOMParser().parseFromString(source,'image/svg+xml');
 if(doc.querySelector('parsererror'))throw new Error('SVG 结果无效，请重新生成');
 const root=doc.documentElement;
 // Only our full-canvas rect is a background; glyphs are always outline paths.
 for(const rect of root.querySelectorAll(':scope > rect'))rect.remove();
 if(!transparent){const rect=doc.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('width','100%');rect.setAttribute('height','100%');rect.setAttribute('fill',background);root.insertBefore(rect,root.querySelector('path'));}
 for(const path of root.querySelectorAll('path[data-start]')){
  const a=Number(path.getAttribute('data-start')),b=Number(path.getAttribute('data-end'));
  for(const item of settings.overrides)if(a<item.end&&b>item.start)path.setAttribute('fill',item.color);
 }
 return new XMLSerializer().serializeToString(root);
}

export function applyOverrides(glyphs,overrides){return glyphs.map(g=>{const copy={...g};for(const item of overrides)if(g.source_start<item.end&&g.source_end>item.start){copy.color=item.color;copy.color_reason='manual_override';copy.color_salience=1;}return copy;});}
