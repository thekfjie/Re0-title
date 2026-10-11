from pathlib import Path
from dataclasses import replace
from copy import deepcopy
import random, math, re, hashlib, json
import numpy as np
import yaml
from engine.text import script, break_penalty, NO_START, NO_END, Token
from engine.fonts import FontFace
from engine.renderer import Layout,PlacedGlyph,optical_x,raster_metrics,minimum_ink_gap

ROOT=Path(__file__).resolve().parents[1]

def load_config():
    return {k:yaml.safe_load((ROOT/'config'/f'{name}.yaml').read_text()) for k,name in [('rules','template_rules'),('weights','layout_weights'),('colors','color_palettes')]}

class LayoutEngine:
    def __init__(self,fonts,config=None):
        self.config=config or load_config();self.rules=self.config['rules'];self.fonts=fonts
        self.mask_profiles={}

    def chunks(self,tokens):
        # Exceptional long dictionary token: preserve reading order, split safely.
        out=[]
        for t in tokens:
            if len(t.text)<=12:out.append(t);continue
            start=0
            while start<len(t.text):
                end=min(start+8,len(t.text))
                while end<len(t.text) and (t.text[end] in NO_START or t.text[end-1] in NO_END):end+=1
                out.append(replace(t,text=t.text[start:end],start=t.start+start,pos=t.pos+' / emergency_split'))
                start=end
        return out

    def token_width(self,t):
        st=self.rules['style']
        return sum(st['particle_size'] if t.role in ('particle','connector') else st['punctuation_size'] if script(c)=='punctuation' else st['kana_size'] if script(c)=='hiragana' else st['primary_size'] if t.importance>.62 else st['secondary_size'] for c in t.text)

    def line_search(self,tokens,n,beam_width):
        total=sum(self.token_width(t) for t in tokens);target=total/n
        widths=[self.token_width(t) for t in tokens];prefix=np.cumsum([0]+widths)
        states=[(0.,[0])]
        for line in range(n):
            next_states=[]
            for cost,breaks in states:
                start=breaks[-1]
                ends=[len(tokens)] if line==n-1 else range(start+1,len(tokens)-(n-line-1)+1)
                for end in ends:
                    if end<=start:continue
                    penalty=break_penalty(tokens,end)
                    if not math.isfinite(penalty):continue
                    if all(t.role=='punctuation' for t in tokens[start:end]):continue
                    width=prefix[end]-prefix[start]
                    c=cost+((width-target)/max(target,1))**2+penalty*.4
                    if any('emergency_split' in t.pos for t in tokens[start:end]):c+=.4
                    next_states.append((c,breaks+[end]))
            states=sorted(next_states,key=lambda x:(x[0],x[1]))[:beam_width]
        return [(cost,[tokens[a:b] for a,b in zip(breaks,breaks[1:])]) for cost,breaks in states[:self.rules['search']['per_family']]]

    def eligible_families(self,text,tokens):
        families=[]
        for name,cfg in self.rules['families'].items():
            if len(text)<=cfg['max_chars'] and (name!='alternating_steps' or len(tokens)>=4):families.append(name)
        return families or ['offset_stack']

    def make_layout(self,text,tokens,lines,family,seed,variant,width,height,palette):
        rng=random.Random(seed);style=self.rules['style'];base=style['font_size_base'];fcfg=self.rules['families'][family]
        max_imp=max(t.importance for t in tokens)
        anchors=sorted(range(len(tokens)),key=lambda i:(-tokens[i].importance,i))[:style['accent_budget']]
        color_anchor={i:palette['accents'][j%len(palette['accents'])] for j,i in enumerate(anchors) if tokens[i].importance>.42}
        token_indices={id(t):i for i,t in enumerate(tokens)}
        # When the semantic plan names single-character anchors, honor them.
        explicit=self.active_plan.get('emphasis_relation',[]) if hasattr(self,'active_plan') else []
        explicit=[next((c for c in word if script(c) in ('kanji','katakana','latin')),word[0]) for word in explicit]
        glyphs=[];line_texts=[];y=0.
        for row,line in enumerate(lines):
            rowglyphs=[];x=0.;previous=None
            for t in line:
                idx=token_indices[id(t)];groups=[]
                for c in t.text:
                    face_key='kana' if script(c)=='hiragana' else 'kanji'
                    if groups and groups[-1][0]==face_key:groups[-1]=(face_key,groups[-1][1]+c)
                    else:groups.append((face_key,c))
                anchor_char=next((c for c in t.text if script(c) in ('kanji','katakana','latin')),t.text[0])
                for face_key,run in groups:
                    face=self.fonts.get(face_key,self.fonts['kanji'])
                    if face.missing(run):raise ValueError(f'{face_key} 字体缺字：'+''.join(face.missing(run)))
                    for shaped in face.shape(run):
                        kind=script(shaped.text[0])
                        factor=style['particle_size'] if t.role in ('particle','connector') else style['punctuation_size'] if kind=='punctuation' else style['kana_size'] if kind=='hiragana' else style['secondary_size']
                        is_anchor=shaped.text[0]==anchor_char and t.importance>=.62
                        if is_anchor:factor=style['primary_size']*(.90+t.importance*.17)
                        if shaped.text in explicit:factor=max(factor,style['primary_size']*1.08)
                        if family=='wide_block' and kind not in ('punctuation','hiragana'):factor=.98+.23*t.importance
                        if is_anchor:factor*=1+(variant-1)*.06
                        size=base*factor
                        sx=rng.uniform(.94,1.02) if family!='wide_block' else 1.
                        sy=1.
                        x0,y0,x1,y1=shaped.bounds;gw=(x1-x0)*size/face.upem*sx;gh=(y1-y0)*size/face.upem*sy
                        if gw<=0 or gh<=0:
                            x+=shaped.advance*size/face.upem;continue
                        # Small glyphs float within the row; punctuation sits near baseline.
                        gy=y+(base*1.4-gh)*(.68 if kind=='punctuation' else .50+fcfg['baseline_shift']*(rng.random()-.5))
                        gy-=shaped.y_offset*size/face.upem
                        color=palette['foreground']
                        if idx in color_anchor and shaped.text[0]==anchor_char:color=color_anchor[idx]
                        if shaped.text in explicit:color=palette['accents'][explicit.index(shaped.text)%len(palette['accents'])]
                        g=PlacedGlyph(shaped.text,idx,t.role,t.importance,face_key,shaped.gid,shaped.path,shaped.bounds,face.upem,x,gy,gw,gh,size,sx,sy,color,row,shaped.advance,shaped.bearing,face.metrics['ascender'],face.metrics['descender'],mask=shaped.mask)
                        # Latin within a shaped run keeps HarfBuzz advances and offsets.
                        if previous is not None:
                            if kind=='latin' and previous.text[-1:].isascii() and previous.face==g.face:
                                g.x=previous.x+previous.advance*previous.size/previous.upem+(x0-previous.bounds[0]+shaped.x_offset)*size/face.upem
                            else:g.x=optical_x(previous,g,base*style['optical_gap'],base*style['optical_min_distance']) if style.get('optical_kerning',True) else previous.x+previous.width+base*style['optical_gap']
                        else:g.x=shaped.x_offset*size/face.upem
                        rowglyphs.append(g);previous=g;x=g.x+gw
            if not rowglyphs:continue
            minx=min(g.x for g in rowglyphs);maxx=max(g.x+g.width for g in rowglyphs)
            if family in ('offset_stack','alternating_steps'):
                offset=(row%2-.5)*base*fcfg['offset']*4
                if family=='offset_stack':offset=(row-(len(lines)-1)/2)*base*fcfg['offset']*2.5
            else:offset=0
            for g in rowglyphs:g.x+=offset-(maxx+minx)/2
            glyphs.extend(rowglyphs);line_texts.append(''.join(t.text for t in line))
            rowbottom=max(g.y+g.height for g in rowglyphs)
            y=rowbottom+base*style['row_gap']
        if not glyphs:raise ValueError('没有可渲染字形')
        layout=Layout(text,family,glyphs,width,height,palette['background'],seed,lines=line_texts)
        layout.metadata['fill_multiplier']=self.rules['scale_regimes'][variant]
        return self.fit(layout)

    def fit(self,layout):
        gs=layout.glyphs;minx=min(g.x for g in gs);maxx=max(g.x+g.width for g in gs);miny=min(g.y for g in gs);maxy=max(g.y+g.height for g in gs)
        w=max(maxx-minx,1);h=max(maxy-miny,1);margin=self.rules['canvas']['margin'];target=self.rules['families'][layout.family]['fill']*layout.metadata.get('fill_multiplier',1)
        scale=min(layout.width*(1-2*margin)/w,layout.height*(1-2*margin)/h,math.sqrt(layout.width*layout.height*target/(w*h)))
        for g in gs:
            g.x=(g.x-minx-w/2)*scale+layout.width/2;g.y=(g.y-miny-h/2)*scale+layout.height/2
            g.width*=scale;g.height*=scale;g.size*=scale
        # Translate using actual bitmap mass, then clamp to safe margins.
        mass=[max(1,float(g.mask.sum())/255)*(g.size/100)**2*g.scale_x*g.scale_y for g in gs]
        cx=sum((g.x+g.width/2)*m for g,m in zip(gs,mass))/sum(mass);cy=sum((g.y+g.height/2)*m for g,m in zip(gs,mass))/sum(mass)
        dx=layout.width/2-cx;dy=layout.height/2-cy
        dx=max(layout.width*margin-min(g.x for g in gs),min(dx,layout.width*(1-margin)-max(g.x+g.width for g in gs)))
        dy=max(layout.height*margin-min(g.y for g in gs),min(dy,layout.height*(1-margin)-max(g.y+g.height for g in gs)))
        for g in gs:g.x+=dx;g.y+=dy
        return layout

    def score(self,layout,awkward=None):
        if awkward is None:awkward=layout.metadata.get('break_cost',0)
        metrics=raster_metrics(layout);gs=layout.glyphs
        center=metrics['centroid'];balance=max(0,1-math.hypot(center[0]-.5,center[1]-.5)*3)
        imp=np.array([g.importance for g in gs]);areas=np.array([g.width*g.height for g in gs])
        correlation=float(np.corrcoef(imp,areas)[0,1]) if np.std(imp)>1e-8 and np.std(areas)>1e-8 else 0
        semantic=max(0,(correlation+1)/2)
        gaps=[]
        for a,b in zip(gs,gs[1:]):
            if a.row==b.row:gaps.append(minimum_ink_gap(a,b)/max(a.size,b.size))
        target_gap=self.rules['style'].get('optical_target_gap',.06)
        spacing=float(np.mean([math.exp(-abs(gap-target_gap)/.12) for gap in gaps])) if gaps else 1
        template=self.rules['families'][layout.family];consistency=1 if len(layout.lines) in template['lines'] else .3
        target_fill=template['fill']*layout.metadata.get('fill_multiplier',1)
        whitespace=max(0,1-abs(metrics['box_fill']-target_fill)/target_fill)
        rhythm=min(1,float(np.std([g.size for g in gs])/max(np.mean([g.size for g in gs]),1))/.25)
        kinsoku=sum(bool(s and (s[0] in NO_START or s[-1] in NO_END)) for s in layout.lines)
        overflow_area=sum(max(0,-g.x)+max(0,-g.y)+max(0,g.x+g.width-layout.width)+max(0,g.y+g.height-layout.height) for g in gs)
        terms={'balance':balance,'semantic_emphasis':semantic,'spacing_quality':spacing,'template_consistency':consistency,'whitespace_quality':whitespace,'rhythm':rhythm,'collision_penalty':metrics['collision'],'overflow_penalty':metrics['overflow']+overflow_area/100,'kinsoku_penalty':kinsoku,'awkward_break_penalty':awkward/max(len(layout.lines),1)}
        weights=self.config['weights'];layout.terms={**terms,**metrics}
        layout.score=sum((-1 if k.endswith('penalty') else 1)*weights[k]*v for k,v in terms.items())
        return layout.score

    def anneal(self,layout,rng):
        current=deepcopy(layout);best=deepcopy(current);self.score(current);best.score=current.score
        temp=self.rules['search']['temperature']
        for _ in range(self.rules['search']['anneal_steps']):
            c=deepcopy(current);g=rng.choice(c.glyphs);mutation=rng.randrange(5)
            if mutation==0:g.y+=rng.uniform(-.04,.04)*g.size
            elif mutation==1:
                row=g.row;dx=rng.uniform(-.03,.03)*g.size
                for other in c.glyphs:
                    if other.row==row:other.x+=dx
            elif mutation==2:
                factor=rng.uniform(.96,1.04);g.size*=factor;g.width*=factor;g.height*=factor
            elif mutation==3:
                factor=rng.uniform(.97,1.03);new=g.scale_x*factor
                if self.rules['style']['min_scale_x']<=new<=self.rules['style']['max_scale_x']:g.scale_x=new;g.width*=factor
            else:g.color=rng.choice(self.palette['accents']) if g.color!=self.palette['foreground'] else g.color
            self.fit(c);self.score(c)
            if c.terms['collision']>.002 or c.terms['overflow_penalty'] or c.terms['kinsoku_penalty']:temp*=self.rules['search']['cooling'];continue
            diff=c.score-current.score
            if diff>0 or rng.random()<math.exp(max(-100,diff/max(temp,.001))):current=c
            if c.score>best.score:best=deepcopy(c)
            temp*=self.rules['search']['cooling']
        return best

    def generate(self,text,tokens,seed=42,count=6,width=1200,height=675,palette='night',plan=None,anneal=True):
        if not (256<=width<=2400 and 256<=height<=2400 and width*height<=4000000):raise ValueError('画布须为 256–2400 像素，总像素不超过 400 万')
        if not 4<=count<=8:raise ValueError('候选数须为 4–8')
        if ''.join(t.text for t in tokens)!=text:raise ValueError('计划未保留原文')
        self.active_plan=plan or {};self.palette=self.config['colors']['palettes'][palette];tokens=self.chunks(tokens)
        candidates=[];families=self.eligible_families(text,tokens)
        suggested=self.active_plan.get('suggested_layout_family')
        if suggested in families:families=[suggested]+[f for f in families if f!=suggested]
        for f_idx,family in enumerate(families):
            for n in self.rules['families'][family]['lines']:
                if n>len(tokens):continue
                searched=self.line_search(tokens,n,self.rules['search']['beam_width'])
                for j,(cost,lines) in enumerate(searched):
                    for variant in range(3):
                        local_seed=seed+f_idx*1000+n*100+j*10+variant
                        layout=self.make_layout(text,tokens,lines,family,local_seed,variant,width,height,self.palette)
                        layout.metadata['break_cost']=cost
                        self.score(layout,cost)
                        if layout.terms['collision']<=.002 and layout.terms['kinsoku_penalty']==0 and layout.terms['overflow_penalty']==0:candidates.append(layout)
        if not candidates:raise ValueError('当前文本和字体没有满足禁则/碰撞约束的候选，请缩短文本或换字体')
        candidates.sort(key=lambda l:(-l.score,l.seed));selected=[];seen=set()
        # Family diversity first, then score; never duplicate an identical preview.
        for l in candidates:
            if l.family not in seen:selected.append(l);seen.add(l.family)
            if len(selected)==count:break
        for l in candidates:
            if len(selected)>=count:break
            if all(l is not other for other in selected):selected.append(l)
        if anneal:selected=[self.anneal(l,random.Random(seed+i+90000)) for i,l in enumerate(selected)]
        for l in selected:
            l.metadata.update({'algorithm':('llm_semantic+beam' if plan else 'classic+beam')+('+anneal' if anneal else ''),'input_seed':seed,'fonts':{k:{'family':f.metadata['family'],'sha256':f.metadata['sha256'],'weight':f.metadata['weight']} for k,f in self.fonts.items()},'config_sha256':hashlib.sha256(json.dumps(self.config,sort_keys=True).encode()).hexdigest(),'tokens':[t.dict() for t in tokens],'candidate_pool':len(candidates),'planner':self.active_plan.get('provenance','none')})
        return selected
