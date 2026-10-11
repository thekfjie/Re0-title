"""No font URL is ever returned. Source bytes live in owner-scoped private dirs."""
from pathlib import Path
from io import BytesIO
from dataclasses import dataclass
from typing import Protocol
import hashlib, os, secrets, shutil, time, threading
import numpy as np
import uharfbuzz as hb
import freetype
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

MAX_FONT_BYTES=24*1024*1024
SIGNATURES=(b'\x00\x01\x00\x00', b'OTTO', b'true')

def inspect_font(data,filename='upload.ttf'):
    if len(data)>MAX_FONT_BYTES:raise ValueError('字体上限 24 MiB')
    if len(data)<12 or data[:4] not in SIGNATURES:raise ValueError('需要有效的单字体 TTF / OTF 文件')
    if Path(filename).suffix.lower() not in ('.ttf','.otf'):raise ValueError('扩展名须为 .ttf / .otf')
    f=TTFont(BytesIO(data),lazy=False)
    if 'cmap' not in f or 'head' not in f or 'hmtx' not in f:raise ValueError('字体缺少必要表')
    if len(f.getGlyphOrder())>65535 or len(f.keys())>128:raise ValueError('字体结构超出限制')
    cmap=f.getBestCmap() or {}
    jp_ranges=[(0x3041,0x3096),(0x30a1,0x30fa),(0x4e00,0x9fff)]
    coverage={k:round(sum(cp in cmap for cp in range(a,b+1))/(b-a+1),4) for k,(a,b) in zip(('hiragana','katakana','cjk'),jp_ranges)}
    axes={a.axisTag:{'min':a.minValue,'default':a.defaultValue,'max':a.maxValue} for a in f['fvar'].axes} if 'fvar' in f else {}
    name=lambda id: next((n.toUnicode() for n in f['name'].names if n.nameID==id),'Unknown')[:160]
    return {'family':name(1),'subfamily':name(2),'weight':f['OS/2'].usWeightClass if 'OS/2' in f else None,'glyph_count':len(cmap),'japanese_coverage':coverage,'axes':axes,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}

@dataclass
class Glyph:
    gid:int
    cluster:int
    text:str
    path:str
    bounds:tuple
    advance:float
    bearing:float
    x_offset:float
    y_offset:float
    mask:np.ndarray

class FontFace:
    def __init__(self, path, weight=900):
        self.path=Path(path);data=self.path.read_bytes()
        self.metadata=inspect_font(data,self.path.name)
        self.tt=TTFont(BytesIO(data))
        if 'fvar' in self.tt:
            axes={a.axisTag:max(a.minValue,min(a.maxValue,weight)) for a in self.tt['fvar'].axes if a.axisTag=='wght'}
            if axes:
                self.tt=instantiateVariableFont(self.tt,axes,inplace=False)
                b=BytesIO();self.tt.save(b);data=b.getvalue()
                self.metadata['applied_variations']=axes
                self.metadata['weight']=axes.get('wght',self.metadata['weight'])
        self.upem=self.tt['head'].unitsPerEm;self.order=self.tt.getGlyphOrder();self.glyph_set=self.tt.getGlyphSet();self.cmap=self.tt.getBestCmap()
        self.hb=hb.Font(hb.Face(data));self.hb.scale=(self.upem,self.upem);hb.ot_font_set_funcs(self.hb)
        self.ft=freetype.Face(BytesIO(data));self.ft.set_pixel_sizes(0,100)
        self.cache={};self.mask_cache={}
        self.metrics={'upem':self.upem,'ascender':self.tt['hhea'].ascent,'descender':self.tt['hhea'].descent,'line_gap':self.tt['hhea'].lineGap}

    def missing(self,text):return sorted(set(c for c in text if not c.isspace() and ord(c) not in self.cmap))

    def glyph(self,gid):
        if gid in self.cache:return self.cache[gid]
        name=self.order[gid];g=self.glyph_set[name]
        pen=SVGPathPen(self.glyph_set);g.draw(pen)
        bounds=BoundsPen(self.glyph_set);g.draw(bounds)
        bbox=bounds.bounds or (0,0,0,0)
        self.ft.load_glyph(gid,freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bitmap=self.ft.glyph.bitmap
        if bitmap.rows and bitmap.width:
            array=np.array(bitmap.buffer,dtype=np.uint8).reshape(bitmap.rows,abs(bitmap.pitch))[:,:bitmap.width].copy()
        else:array=np.zeros((1,1),np.uint8)
        self.cache[gid]=(pen.getCommands(),bbox,array,self.tt['hmtx'][name][1])
        return self.cache[gid]

    def shape(self,text):
        b=hb.Buffer();b.add_str(text);b.guess_segment_properties();b.language='ja'
        hb.shape(self.hb,b,{'kern':True,'liga':True})
        infos=b.glyph_infos;positions=b.glyph_positions
        clusters=sorted(set(i.cluster for i in infos)|{len(text)})
        result=[]
        for info,pos in zip(infos,positions):
            end=next((c for c in clusters if c>info.cluster),len(text))
            path,bounds,mask,bearing=self.glyph(info.codepoint)
            result.append(Glyph(info.codepoint,info.cluster,text[info.cluster:end],path,bounds,pos.x_advance,bearing,pos.x_offset,pos.y_offset,mask))
        return result

class FontProvider(Protocol):
    def resolve(self,font_id:str,owner:str)->Path: ...

class BundledFontProvider:
    """Explicit OFL allowlist. Uploaded and administrator fonts never enter it."""
    def __init__(self,directory):
        self.directory=Path(directory)
        import json
        self.catalog=json.loads((self.directory/'catalog.json').read_text()) if (self.directory/'catalog.json').exists() else []
        self.index={e['id']:e for e in self.catalog}

    def list(self):return [{**e,'font_id':'builtin_'+e['id']} for e in self.catalog]

    def resolve(self,font_id,owner):
        entry=self.index.get(font_id.removeprefix('builtin_'))
        if not entry:raise ValueError('未知预置字体')
        path=self.directory/entry['file']
        if not path.is_file() or path.is_symlink():raise ValueError('预置字体不可用')
        return path

class UploadFontProvider:
    def __init__(self,root,ttl=3600):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.root,0o700)
        self.ttl=ttl;self.lock=threading.RLock()

    def _owner(self,owner):
        if not owner or len(owner)>256:raise ValueError('无效会话')
        return self.root/hashlib.sha256(owner.encode()).hexdigest()

    def register(self,data,filename,owner):
        metadata=inspect_font(data,filename)
        with self.lock:
            directory=self._owner(owner);directory.mkdir(mode=0o700,exist_ok=True)
            entries=list(directory.glob('*'))
            if len(entries)>=8 or sum(p.stat().st_size for p in entries)+len(data)>64*1024*1024:raise ValueError('每会话最多 8 个字体、64 MiB，请清理后重试')
            fid=secrets.token_urlsafe(24);p=directory/(fid+Path(filename).suffix.lower())
            with p.open('xb') as f:f.write(data)
            os.chmod(p,0o600)
        return {'font_id':fid,**metadata,'expires_in_seconds':self.ttl}

    def resolve(self,font_id,owner):
        if not font_id or not all(c.isalnum() or c in '_-' for c in font_id):raise ValueError('无效字体 ID')
        for ext in ('.ttf','.otf'):
            path=self._owner(owner)/(font_id+ext)
            if path.is_file() and not path.is_symlink() and time.time()-path.stat().st_mtime<self.ttl:return path
        raise ValueError('字体不存在或已过期')

    def cleanup(self):
        with self.lock:
            for d in self.root.iterdir():
                if not d.is_dir() or d.is_symlink():continue
                for p in d.iterdir():
                    if p.is_file() and time.time()-p.stat().st_mtime>=self.ttl:p.unlink()
                if not any(d.iterdir()):d.rmdir()

    def delete_owner(self,owner):
        with self.lock:shutil.rmtree(self._owner(owner),ignore_errors=True)

class PrivateFontProvider:
    def __init__(self,directory,enabled=False):
        self.directory=Path(directory).resolve();self.enabled=enabled
        self.index={hashlib.sha256(str(p).encode()).hexdigest()[:24]:p for p in self.directory.glob('*') if p.suffix.lower() in ('.ttf','.otf') and p.is_file() and not p.is_symlink()} if enabled else {}

    def list(self):return [{'font_id':'private_'+id,**inspect_font(p.read_bytes(),p.name)} for id,p in self.index.items()]

    def resolve(self,font_id,owner):
        if not self.enabled or font_id.removeprefix('private_') not in self.index:raise ValueError('私有字体未启用')
        return self.index[font_id.removeprefix('private_')]
