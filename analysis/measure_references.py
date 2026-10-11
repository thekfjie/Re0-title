#!/usr/bin/env python3
"""Reproducible pixel measurements after visually calibrated title-only clips.

This is not OCR, a font identifier, or glyph segmentation. Bounding boxes are
half-open [left, top, right, bottom] in original screenshot pixel coordinates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
VIDEO_CANVAS = [448, 72, 2752, 1368]
LINE_COUNTS = [2,1,2,2,1,1,2,2,1,1,1,1,2,1,1,1,2,1,1,2,2,1,1,2,
               1,1,1,1,1,1,1,1,1,1,1,3,1,1,2,1,1,1,1,2,1,2,2,4,
               1,1,2,1,1,1,1,2,1,1,1,2,1,1,1,2,1,1,2,2,2,2,1,3,
               1,1,3,1,2,2,2,2,1,2]
# Bounds separate Japanese/main Latin titles from Chinese translation tracks.
# They were calibrated against all seven contact sheets and difficult originals.
Y_CLIPS = [(170,1165),(180,1090),(180,1150),(170,1135),(180,970),(180,1040),
 (170,1140),(170,1160),(180,1060),(180,990),(180,1090),(180,1050),
 (170,1110),(180,1050),(180,1060),(180,1080),(145,1310),(180,1090),
 (180,1070),(180,1110),(170,1300),(180,1100),(180,1030),(180,1210),
 (540,880),(480,930),(470,940),(180,930),(440,885),(180,960),
 (420,980),(180,950),(180,980),(180,965),(180,990),(140,1290),
 (565,910),(180,1020),(180,1120),(180,990),(180,940),(180,980),
 (470,940),(180,1035),(180,990),(375,1110),(180,1070),(180,1215),
 (180,990),(420,910),(180,1120),(180,990),(550,905),(510,960),
 (180,985),(180,1090),(180,955),(180,1060),(180,960),(330,1030),
 (180,930),(420,1050),(360,1000),(320,1100),(460,880),(365,1000),
 (280,1100),(180,1125),(240,1120),(355,1040),(180,925),(250,1170),
 (280,930),(280,970),(190,1320),(280,1160),(335,1020),(240,1040),
 (220,1260),(185,1260),(340,1130),(340,985)]
WHITE_IDS = {25,29,31,60,65,69,70,77,82}
LATIN_IDS = {26,41}
SPECIAL = {
 17: {"exclude_rectangles": [[448,890,1030,1210]],
      "notes": ["Chinese translation sits left of the second title row; excluded by rectangle."]},
 21: {"exclude_rectangles": [[1080,90,1960,213]],
      "notes": ["Translation overlaps vertical range of first row; top-center rectangle excluded."]},
 26: {"mask_method": "bright_black", "threshold": 95, "confidence": "low",
      "flags": ["latin_title", "glow"], "eligible_primary_black": False},
 27: {"clip": [950,470,2170,940], "confidence": "low", "flags": ["decorative_snowflakes"],
      "eligible_primary_black": False, "notes": ["Central crop avoids most snowflakes; cannot prove every retained pixel is text."]},
 31: {"clip": [1050,420,2160,980], "mask_method": "dark_white", "threshold": 110,
      "confidence": "medium", "flags": ["white_background", "petals"],
      "notes": ["Dark-text threshold suppresses pale pink petals and may lose pale glyph edges."]},
 36: {"mask_method": "neutral_black", "upper_limit": 195, "confidence": "low",
      "flags": ["translation_near_descender", "dark_gradient_title"], "eligible_primary_black": False,
      "notes": ["Neutral gray title mask suppresses bright blue-edged translation; lower descender/translation boundary is uncertain."]},
 43: {"mask_method": "neutral_black", "threshold": 65, "confidence": "low",
      "flags": ["purple_gradient_background"], "eligible_primary_black": False,
      "notes": ["Neutral contrast filter estimates gray/white glyphs over colored gradient."]},
 50: {"mask_method": "bright_black", "threshold": 95, "confidence": "low",
      "flags": ["reflection"], "eligible_primary_black": False,
      "notes": ["Crop/threshold omit mirrored decoration; the mirror boundary is approximate."]},
 53: {"clip": [650,550,2520,905], "mask_method": "strong_color", "confidence": "low",
      "flags": ["yellow_gradient_background"], "eligible_primary_black": False,
      "notes": ["Strong-color/bright-neutral mask is an estimate, unsuitable for aggregate ink-area statistics."]},
 54: {"mask_method": "neutral_black", "threshold": 45, "confidence": "medium",
      "flags": ["blood_splatter_background"], "eligible_primary_black": False,
      "notes": ["Neutral gray/white extraction suppresses red splatter; red is background, not title emphasis."]},
 58: {"confidence": "low", "flags": ["dark_textured_glyphs"], "eligible_primary_black": False,
      "notes": ["Water/texture treatment makes mask area and core colors threshold dependent."]},
 62: {"mask_method": "bright_neutral", "threshold": 220, "confidence": "low",
      "flags": ["warped_multicolor_background"], "eligible_primary_black": False,
      "notes": ["Only near-white title cores measured; colored background and anti-aliased edges intentionally omitted."]},
 64: {"confidence": "low", "flags": ["glow"], "eligible_primary_black": False,
      "notes": ["Soft glow contributes to mask area; cannot infer font outlines from the mask."]},
 65: {"threshold": 10, "confidence": "medium", "flags": ["white_background", "very_pale_title"],
      "notes": ["Very pale title requires lower contrast threshold; JPEG noise can affect small components."]},
 69: {"clip": [448,340,2752,1120], "exclude_rectangles": [[1720,300,2400,375]],
      "confidence": "excluded", "flags": ["white_background", "censored_title"],
      "notes": ["Black censorship blocks cover the title. Measurements describe visible ink/blocks only; no hidden text inferred."]},
 70: {"mask_method": "dark_white", "threshold": 95, "confidence": "medium",
      "flags": ["white_background", "water_background"],
      "notes": ["Dark-text filter suppresses pale cyan water pattern."]},
 75: {"confidence": "low", "flags": ["glow", "star_decoration"], "eligible_primary_black": False,
      "notes": ["Glow and attached stars are included in visible ink; keep out of primary font-area statistics."]},
 80: {"exclude_rectangles": [[620,710,1420,1080]], "confidence": "low",
      "flags": ["translation_interleaved", "textured_glyphs"], "eligible_primary_black": False,
      "notes": ["Chinese translation lies between Japanese characters; manual rectangle may remove a small portion of lower glyph edge."]},
 81: {"confidence": "medium", "flags": ["fractured_rotated_title"], "eligible_primary_black": False,
      "notes": ["Visible fractured red title is measured as ink; rotation/fragments prevent glyph metrics inference."]},
}


def config_for(index: int) -> dict:
    white = index in WHITE_IDS
    cfg = {"clip": [448,Y_CLIPS[index-1][0],2752,Y_CLIPS[index-1][1]],
           "canvas": VIDEO_CANVAS, "background": "white" if white else "black",
           "mask_method": "white" if white else "black", "threshold": 20 if white else 35,
           "upper_limit": 256, "neutral_chroma": 25, "minimum_component_pixels": 20,
           "confidence": "high", "eligible_primary_black": not white and index not in LATIN_IDS,
           "flags": ["white_background"] if white else [], "notes": [],
           "manual_visual_line_count": LINE_COUNTS[index-1]}
    cfg.update(SPECIAL.get(index,{}))
    if index in LATIN_IDS and "latin_title" not in cfg["flags"]: cfg["flags"].append("latin_title")
    return cfg


def make_mask(rgb: np.ndarray, cfg: dict) -> tuple[np.ndarray,np.ndarray]:
    maxc = rgb.max(axis=2).astype(np.float32)
    minc = rgb.min(axis=2).astype(np.float32)
    chroma = maxc-minc
    method = cfg["mask_method"]
    contrast = 255-minc if cfg["background"] == "white" else maxc
    threshold = cfg["threshold"]
    if method in ("white","dark_white"): mask = contrast > threshold
    elif method in ("black","bright_black"): mask = contrast > threshold
    elif method == "neutral_black": mask = (maxc > threshold)&(chroma < cfg["neutral_chroma"])&(maxc < cfg["upper_limit"])
    elif method == "bright_neutral": mask = (minc > threshold)&(chroma < cfg["neutral_chroma"])
    elif method == "strong_color":
        r,g,b = rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        mask = ((minc > 170)&(chroma < 25)) | ((maxc > 190)&(chroma > 95)&(b < 100)) | ((r > 120)&(b > 135)&(g < 145)&(chroma > 40))
    else: raise ValueError(method)
    labels,_ = ndimage.label(mask,structure=np.ones((3,3)))
    counts = np.bincount(labels.ravel())
    keep = counts >= cfg["minimum_component_pixels"]
    keep[0] = False
    mask = keep[labels]
    return mask,contrast


def color_clusters(rgb: np.ndarray, mask: np.ndarray, origin: tuple[int,int]) -> list[dict]:
    # Use interiors to reduce JPEG/anti-aliasing edge colors. This deliberately
    # reports approximate pixel color clusters, not number of chosen paint colors.
    interior = ndimage.binary_erosion(mask,iterations=2)
    sample_mask = interior if interior.sum()>100 else mask
    py,px = np.nonzero(sample_mask)
    pixels = rgb[sample_mask].astype(float)
    if not len(pixels): return []
    # Deterministic RGB cube quantization, weighted merge, no foundation model.
    quant = (pixels.astype(int)//24)
    keys = quant[:,0]*121+quant[:,1]*11+quant[:,2]
    unique,inverse,counts = np.unique(keys,return_inverse=True,return_counts=True)
    sums = np.column_stack([np.bincount(inverse,weights=pixels[:,c]) for c in range(3)])
    groups = [{"rgb": sums[i]/counts[i],"n":int(counts[i])} for i in range(len(unique)) if counts[i]/len(pixels) >= .001]
    groups.sort(key=lambda c:c["n"],reverse=True)
    merged=[]
    for group in groups:
        if merged:
            distances=[np.linalg.norm(group["rgb"]-c["rgb"]) for c in merged]
            closest=int(np.argmin(distances))
            if distances[closest]<60:
                old=merged[closest]; total=old["n"]+group["n"]
                old["rgb"]=(old["rgb"]*old["n"]+group["rgb"]*group["n"])/total
                old["n"]=total
                continue
        merged.append(group)
    result=[]
    for c in sorted(merged,key=lambda c:c["n"],reverse=True):
        fraction=c["n"]/len(pixels)
        if fraction < .005: continue
        center=[round(float(v),1) for v in c["rgb"]]
        result.append({"rgb":center,"hex":"#"+"".join(f"{round(v):02x}" for v in center),
                       "core_pixel_fraction":round(fraction,5),
                       "is_chromatic":max(center)-min(center)>35,
                       "significant":fraction>=.02})
    if result:
        distances=np.column_stack([np.sum((pixels-np.asarray(c["rgb"]))**2,axis=1) for c in result])
        assignments=distances.argmin(axis=1)
        for i,c in enumerate(result):
            selected=(assignments==i)&(distances[:,i]<=60**2)
            if c["is_chromatic"]:selected &= pixels.max(axis=1)-pixels.min(axis=1)>35
            if not selected.any():continue
            xx,yy=px[selected]+origin[0],py[selected]+origin[1]
            c["core_ink_bbox"]=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
            c["core_ink_centroid"]=[round(float(xx.mean()),2),round(float(yy.mean()),2)]
            c["core_ink_bbox_robust_01_99"]=[round(float(np.percentile(xx,1)),1),round(float(np.percentile(yy,1)),1),
                                             round(float(np.percentile(xx,99)),1),round(float(np.percentile(yy,99)),1)]
    return result


def normalized_point(point: list, canvas: list) -> list:
    return [round((point[0]-canvas[0])/(canvas[2]-canvas[0]),6),round((point[1]-canvas[1])/(canvas[3]-canvas[1]),6)]


def measure(path: Path,index: int,cfg: dict) -> tuple[dict,Image.Image]:
    source=Image.open(path).convert("RGB")
    a=np.asarray(source)
    x0,y0,x1,y1=cfg["clip"]
    rgb=a[y0:y1,x0:x1]
    mask,contrast=make_mask(rgb,cfg)
    for ex0,ey0,ex1,ey1 in cfg.get("exclude_rectangles",[]):
        mask[max(0,ey0-y0):max(0,min(y1,ey1)-y0),max(0,ex0-x0):max(0,min(x1,ex1)-x0)]=False
    ys,xs=np.nonzero(mask)
    if not len(xs): raise ValueError(f"Empty mask for {index}: {path}")
    bbox=[int(xs.min()+x0),int(ys.min()+y0),int(xs.max()+1+x0),int(ys.max()+1+y0)]
    bw,bh=bbox[2]-bbox[0],bbox[3]-bbox[1]
    ink=int(mask.sum())
    centroid=[float(xs.mean()+x0),float(ys.mean()+y0)]
    weights=contrast[mask]
    visual_centroid=[float(np.average(xs,weights=weights)+x0),float(np.average(ys,weights=weights)+y0)]
    row=mask.sum(axis=1)
    smoothed=ndimage.gaussian_filter1d(row.astype(float),4)
    active=smoothed > max(5,smoothed.max()*.015)
    # Close only narrow gaps. These are ink bands, not automatically found lines.
    active=ndimage.binary_closing(active,structure=np.ones(25))
    rowlabels,nrows=ndimage.label(active)
    bands=[]
    for label in range(1,nrows+1):
        yy=np.where(rowlabels==label)[0]
        if len(yy)<8: continue
        submask=mask[yy[0]:yy[-1]+1]
        occupied=np.where(submask.any(axis=0))[0]
        if len(occupied): bands.append({"y_start":int(yy[0]+y0),"y_end":int(yy[-1]+y0+1),
            "x_start":int(occupied[0]+x0),"x_end":int(occupied[-1]+x0+1),"ink_pixels":int(submask.sum())})
    labels,n=ndimage.label(mask,structure=np.ones((3,3)))
    components=[]
    for label,sl in enumerate(ndimage.find_objects(labels),1):
        if sl is None: continue
        sy,sx=sl; local=labels[sl]==label; area=int(local.sum())
        cy,cx=ndimage.center_of_mass(local)
        components.append({"bbox":[sx.start+x0,sy.start+y0,sx.stop+x0,sy.stop+y0],"area_pixels":area,
             "centroid":[round(cx+sx.start+x0,2),round(cy+sy.start+y0,2)]})
    colors=color_clusters(rgb,mask,(x0,y0))
    canvas=cfg["canvas"]
    canvas_area=(canvas[2]-canvas[0])*(canvas[3]-canvas[1])
    record={"index":index,"file":path.name,"source_size":list(source.size),"config":cfg,
            "title_ink_bbox":bbox,"title_bbox_size":[bw,bh],"title_bbox_aspect_ratio":round(bw/bh,6),
            "bbox_width_fraction_of_canvas":round(bw/(canvas[2]-canvas[0]),6),
            "bbox_height_fraction_of_canvas":round(bh/(canvas[3]-canvas[1]),6),
            "ink_pixels":ink,"canvas_whitespace_ratio":round(1-ink/canvas_area,6),
            "bbox_whitespace_ratio":round(1-ink/(bw*bh),6),
            "bbox_area_fraction_of_canvas":round(bw*bh/canvas_area,6),
            "binary_ink_centroid":[round(v,3) for v in centroid],
            "contrast_weighted_centroid":[round(v,3) for v in visual_centroid],
            "binary_ink_centroid_normalized":normalized_point(centroid,canvas),
            "contrast_weighted_centroid_normalized":normalized_point(visual_centroid,canvas),
            "color_clusters":colors,"approx_significant_color_cluster_count":sum(c["significant"] for c in colors),
            "approx_significant_chromatic_cluster_count":sum(c["significant"] and c["is_chromatic"] for c in colors),
            "row_projection":{"y_start":y0,"ink_pixel_count":row.astype(int).tolist()},
            "ink_bands":bands,"connected_components":components,
            "automatic_text":None,"glyph_metrics":None,
            "limitations":["Connected components are ink fragments, not glyphs or tokens.",
                "Ink bands are row-projection regions, not verified text lines.",
                "Color clusters include gradient/JPEG variability and are not a paint-count ground truth."]}
    # QA thumbnail: retained foreground only, over its source background polarity.
    bg=255 if cfg["background"]=="white" else 0
    qa=np.full_like(a,bg)
    region=qa[y0:y1,x0:x1]
    region[mask]=rgb[mask]
    qa_im=Image.fromarray(qa[canvas[1]:canvas[3],canvas[0]:canvas[2]])
    qa_im.thumbnail((360,203))
    tile=Image.new("RGB",(370,225),(35,35,35));tile.paste(qa_im,((370-qa_im.width)//2,20))
    ImageDraw.Draw(tile).text((5,4),f"{index:02} {cfg['confidence']} {bw}x{bh}",fill=(255,255,255))
    return record,tile


def distribution(values: list[float]) -> dict:
    return {"min":round(float(np.min(values)),4),"p25":round(float(np.percentile(values,25)),4),
            "median":round(float(np.median(values)),4),"p75":round(float(np.percentile(values,75)),4),
            "max":round(float(np.max(values)),4)}


def summarize(records: list[dict]) -> dict:
    primary=[r for r in records if r["config"]["eligible_primary_black"]]
    metrics=["title_bbox_aspect_ratio","bbox_width_fraction_of_canvas","bbox_height_fraction_of_canvas",
             "canvas_whitespace_ratio","bbox_whitespace_ratio","bbox_area_fraction_of_canvas"]
    strata={"first_24": [r for r in primary if r["index"]<=24],
            "later": [r for r in primary if r["index"]>24],
            "single_line": [r for r in primary if r["config"]["manual_visual_line_count"]==1],
            "two_lines": [r for r in primary if r["config"]["manual_visual_line_count"]==2]}
    return {"schema_version":1,"sample_count":len(records),"canvas_bbox":VIDEO_CANVAS,
            "all_source_sizes":dict(Counter(str(r["source_size"]) for r in records)),
            "background_counts":dict(Counter(r["config"]["background"] for r in records)),
            "confidence_counts":dict(Counter(r["config"]["confidence"] for r in records)),
            "primary_black_count":len(primary),"primary_black_indices":[r["index"] for r in primary],
            "primary_black_distributions":{k:distribution([r[k] for r in primary]) for k in metrics},
            "primary_black_stratified_distributions":{name:{"count":len(group),
                "metrics":{k:distribution([r[k] for r in group]) for k in metrics}} for name,group in strata.items()},
            "primary_black_centroid_x":distribution([r["contrast_weighted_centroid_normalized"][0] for r in primary]),
            "primary_black_centroid_y":distribution([r["contrast_weighted_centroid_normalized"][1] for r in primary]),
            "primary_black_manual_line_count":dict(Counter(str(r["config"]["manual_visual_line_count"]) for r in primary)),
            "all_manual_line_count":dict(Counter(str(r["config"]["manual_visual_line_count"]) for r in records)),
            "primary_black_approx_chromatic_cluster_count":dict(Counter(str(r["approx_significant_chromatic_cluster_count"]) for r in primary)),
            "excluded_from_primary":[{"index":r["index"],"file":r["file"],"flags":r["config"]["flags"],
                                     "confidence":r["config"]["confidence"]} for r in records if r not in primary],
            "text_counts_available":False,"glyph_level_statistics_available":False,
            "notes":"Primary-black subset excludes white cards, Latin-only titles, textured/decorative/glow/overlap variants. Manual line count is visual annotation; all other statistics are threshold-based pixels."}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=ROOT/"references"/"originals")
    parser.add_argument("--output",type=Path,default=ROOT/"analysis")
    parser.add_argument("--config",type=Path,help="Override visually calibrated JSON configuration.")
    args=parser.parse_args()
    paths=sorted(args.input.glob("*.jpg"))
    if len(paths)!=82: raise ValueError(f"Expected calibrated corpus of 82 JPGs, got {len(paths)}")
    configs=json.loads(args.config.read_text()) if args.config else [config_for(i) for i in range(1,83)]
    args.output.mkdir(parents=True,exist_ok=True)
    records=[];tiles=[]
    for index,(path,cfg) in enumerate(zip(paths,configs),1):
        record,tile=measure(path,index,cfg);records.append(record);tiles.append(tile)
    (args.output/"measurements.json").write_text(json.dumps({"schema_version":1,"coordinate_convention":"half-open XYXY in original pixels",
        "method":"manual title ROI + contrast masks + non-model CV", "samples":records},ensure_ascii=False,indent=2))
    (args.output/"measurements_summary.json").write_text(json.dumps(summarize(records),ensure_ascii=False,indent=2))
    (args.output/"measurements_config.json").write_text(json.dumps(configs,ensure_ascii=False,indent=2))
    qa=args.output/"measurement-qa";qa.mkdir(exist_ok=True)
    for start in range(0,len(tiles),12):
        sheet=Image.new("RGB",(370*3,225*4),(35,35,35))
        for n,tile in enumerate(tiles[start:start+12]):sheet.paste(tile,((n%3)*370,(n//3)*225))
        sheet.save(qa/f"{start//12+1}.jpg",quality=92)
    print(json.dumps(summarize(records),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
