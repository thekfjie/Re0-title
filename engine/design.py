"""Reproducible design variation and explicit colour diagnostics."""
import math

def mulberry(seed):
    value=seed&0xffffffff
    def random():
        nonlocal value
        value=(value+0x6D2B79F5)&0xffffffff;t=value
        t=((t^(t>>15))*(t|1))&0xffffffff
        t^=(t+((t^(t>>7))*(t|61)&0xffffffff))&0xffffffff
        return ((t^(t>>14))&0xffffffff)/4294967296
    return random

def variation_profile(seed,rules):
    cfg=rules['variation'];random=mulberry(seed^cfg['seed_salt'])
    def between(key):
        low,high=cfg[key];return low+(high-low)*random()
    return {'version':cfg['version'],'fill':between('fill_range'),'anchor_scale':between('anchor_scale_range'),'kana_scale':between('kana_scale_range'),'baseline_scale':between('baseline_scale_range'),'row_offset_scale':between('row_offset_scale_range'),'row_direction':-1 if random()<.5 else 1,'baseline_phase':int(random()*4),'accent_rotation':int(random()*2)}

def accent_limit(seed,variant,mode,rules):
    if mode in ('none','single','dual'):return {'none':0,'single':1,'dual':2}[mode]
    if mode!='auto':raise ValueError('未知着色方式')
    cfg=rules['color_policy'];value=mulberry(seed^((variant+1)*2654435761))();total=0
    for count,probability in zip(cfg['auto_color_counts'],cfg['auto_color_probabilities']):
        total+=probability
        if value<total:return count
    return cfg['auto_color_counts'][-1]

def luminance(hex_color):
    rgb=[int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    return sum(c*w for c,w in zip(linear,[.2126,.7152,.0722]))

def contrast(a,b):
    high,low=sorted([luminance(a),luminance(b)],reverse=True)
    return (high+.05)/(low+.05)

def resolve_palette(colors,palette,canvas_theme='night'):
    if canvas_theme not in ('night','day'):raise ValueError('未知画布背景')
    return dict(colors['day_palettes' if canvas_theme=='day' else 'palettes'][palette])

def check_glyph_colors(layout,rules):
    cfg=rules['color_policy'];palette=layout.metadata['resolved_palette'];decisions=[]
    for g in layout.glyphs:
        minimum=cfg['small_text_min_contrast'] if g.size<cfg['small_text_size'] else cfg['min_contrast']
        ratio=contrast(g.color,layout.background)
        if ratio<minimum:
            g.color=palette['foreground'];g.color_reason='contrast_fallback';ratio=contrast(g.color,layout.background)
        if g.color!=palette['foreground'] or g.color_reason=='contrast_fallback':
            decisions.append({'text':g.text,'token':g.token,'role':g.role,'importance':g.importance,'color':g.color,'contrast':round(ratio,4),'reason':g.color_reason})
    layout.metadata['color_decisions']=decisions

def color_metrics(layout,rules):
    cfg=rules['color_policy'];foreground=layout.metadata['resolved_palette']['foreground'];colored=[g for g in layout.glyphs if g.color!=foreground]
    area=sum(g.width*g.height for g in layout.glyphs) or 1
    ratio=sum(g.width*g.height for g in colored)/area
    minimum=min(contrast(g.color,layout.background) for g in layout.glyphs)
    low=sum(contrast(g.color,layout.background)<(cfg['small_text_min_contrast'] if g.size<cfg['small_text_size'] else cfg['min_contrast']) for g in layout.glyphs)
    count=len({g.color for g in colored});semantic=sum(g.importance*g.width*g.height for g in colored)/max(sum(g.width*g.height for g in colored),1) if colored else 1
    maximum=cfg['short_title_max_colored_area'] if len(layout.text)<=2 else cfg['max_colored_area']
    restraint=max(0,1-max(0,ratio-maximum)/max(1-maximum,.01))
    prior=cfg['reference_count_prior'][min(count,2)] if layout.metadata.get('color_mode','auto')=='auto' else 1
    mix=cfg['quality_mix'];quality=mix['contrast']*(1-low/len(layout.glyphs))+mix['semantic']*semantic+mix['restraint']*restraint+mix['reference']*prior
    return {'color_quality':quality,'low_contrast_penalty':low,'min_color_contrast':minimum,'accent_color_count':count,'colored_area_fraction':ratio}
