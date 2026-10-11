from dataclasses import dataclass,asdict,field
from io import BytesIO
import html,math
from PIL import Image
import numpy as np
import cairosvg

@dataclass
class PlacedGlyph:
    text:str
    token:int
    role:str
    importance:float
    face:str
    gid:int
    path:str
    bounds:tuple
    upem:int
    x:float
    y:float
    width:float
    height:float
    size:float
    scale_x:float
    scale_y:float
    color:str
    row:int
    advance:float=0
    bearing:float=0
    ascender:float=0
    descender:float=0
    rotation:float=0
    mask:object=field(default=None,repr=False)

    def record(self):
        return {k:v for k,v in self.__dict__.items() if k not in ('mask','path')}

@dataclass
class Layout:
    text:str
    family:str
    glyphs:list
    width:int
    height:int
    background:str
    seed:int
    score:float=0
    terms:dict=field(default_factory=dict)
    lines:list=field(default_factory=list)
    metadata:dict=field(default_factory=dict)

    def record(self):
        return {'text':self.text,'family':self.family,'width':self.width,'height':self.height,'background':self.background,'seed':self.seed,'score':self.score,'score_terms':self.terms,'lines':self.lines,'metadata':self.metadata,'glyphs':[g.record() for g in self.glyphs]}

class Renderer:
    def svg(self,layout,transparent=False):
        out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout.width}" height="{layout.height}" viewBox="0 0 {layout.width} {layout.height}">',f'<title>{html.escape(layout.text)}</title>']
        if not transparent:out.append(f'<rect width="100%" height="100%" fill="{layout.background}"/>')
        for g in layout.glyphs:
            if not g.path:continue
            x0,y0,x1,y1=g.bounds
            sx=g.size*g.scale_x/g.upem;sy=g.size*g.scale_y/g.upem
            tx=g.x-x0*sx;ty=g.y+y1*sy
            rotate=f'rotate({g.rotation:.5f} {g.x+g.width/2:.5f} {g.y+g.height/2:.5f}) ' if g.rotation else ''
            out.append(f'<path d="{g.path}" fill="{g.color}" transform="{rotate}matrix({sx:.7f} 0 0 {-sy:.7f} {tx:.5f} {ty:.5f})"/>')
        out.append('</svg>');return ''.join(out)

    def png(self,layout,transparent=False):return cairosvg.svg2png(bytestring=self.svg(layout,transparent).encode(),output_width=layout.width,output_height=layout.height)

def scaled_mask(g, factor=1.):
    w=max(1,round(g.width*factor));h=max(1,round(g.height*factor))
    return np.asarray(Image.fromarray(g.mask).resize((w,h),Image.Resampling.BILINEAR))>24

def optical_x(previous,current,gap,min_distance):
    """Minimum safe x from intersecting scanlines of actual ink silhouettes."""
    pm=scaled_mask(previous);cm=scaled_mask(current)
    offset=round(current.y-previous.y);required=[]
    for cy in range(cm.shape[0]):
        py=cy+offset
        if 0<=py<pm.shape[0]:
            p=np.flatnonzero(pm[py]);c=np.flatnonzero(cm[cy])
            if len(p) and len(c):required.append(previous.x+p[-1]+min_distance-c[0])
    conventional=previous.x+previous.width+gap
    if not required:return conventional
    # Cap interlocking to 22% of the smaller ink width; mask collision is hard checked.
    return max(max(required)+gap,conventional-min(previous.width,current.width)*.22)

def minimum_ink_gap(a,b,factor=.25):
    am=scaled_mask(a,factor);bm=scaled_mask(b,factor);offset=round((b.y-a.y)*factor);gaps=[]
    for by in range(bm.shape[0]):
        ay=by+offset
        if 0<=ay<am.shape[0]:
            ap=np.flatnonzero(am[ay]);bp=np.flatnonzero(bm[by])
            if len(ap) and len(bp):gaps.append((b.x-a.x)*factor+bp[0]-ap[-1]-1)
    return min(gaps)/factor if gaps else b.x-a.x-a.width

def raster_metrics(layout,resolution=240):
    factor=resolution/layout.width;h=round(layout.height*factor)
    canvas=np.zeros((h,resolution),np.uint16)
    overflow=0
    for g in layout.glyphs:
        mask=scaled_mask(g,factor);x=round(g.x*factor);y=round(g.y*factor)
        x0=max(0,x);y0=max(0,y);x1=min(resolution,x+mask.shape[1]);y1=min(h,y+mask.shape[0])
        if x1<=x0 or y1<=y0:overflow+=mask.sum();continue
        part=mask[y0-y:y1-y,x0-x:x1-x]
        canvas[y0:y1,x0:x1]+=part
        overflow+=int(mask.sum()-part.sum())
    ys,xs=np.nonzero(canvas)
    occupied=len(xs);collision=int(np.sum(canvas>1))
    if not occupied:return {'ink_fill':0.,'collision':1.,'overflow':1.,'centroid':[.5,.5],'box_fill':0.}
    return {'ink_fill':occupied/canvas.size,'collision':collision/occupied,'overflow':overflow/max(occupied,1),'centroid':[float(xs.mean()/resolution),float(ys.mean()/h)],'box_fill':((xs.max()-xs.min()+1)*(ys.max()-ys.min()+1))/canvas.size}
