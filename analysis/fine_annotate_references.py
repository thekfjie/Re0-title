#!/usr/bin/env python3
"""Six visually checked ink-unit annotations. Never estimates font point size."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
MEASUREMENTS=json.loads((ROOT/'analysis/measurements.json').read_text())['samples']


def u(text,script,components,color,role,bbox=None,error=3,line=1):
    return {'text':text,'script':script,'component_ids':components,'color_label':color,
            'visual_role':role,'bbox_override':bbox,'bbox_error_per_edge_px':error,'line':line}


ANNOTATIONS={
2: {'text':'再会の魔女','units':[
 u('再','kanji',[1],'white','secondary_anchor',[591,603,967,960],12),
 u('会','kanji',[1],'white','secondary_anchor',[926,640,1318,1037],12),
 u('の','hiragana',[3],'white','connector'),
 u('魔','kanji',[0],'warm_yellow','dominant_accent_anchor'),
 u('女','kanji',[2],'white','secondary_anchor')],
 'notes':['再/会 share a connected ink component; manual overlapping boxes preserve their staggered heights.']},
6: {'text':'鎖の音','units':[
 u('鎖','kanji',[0],'pink','primary_accent_anchor'),
 u('の','hiragana',[1],'white','connector',[1525,655,1768,872],12),
 u('音','kanji',[1,2],'white','secondary_anchor',[1758,570,2117,950],12)],
 'notes':['の touches the upper portion of 音. Its border and the left edge of 音 require visual correction.']},
14: {'text':'絶望という病','units':[
 u('絶','kanji',[1],'white','primary_anchor'),
 u('望','kanji',[3],'white','secondary_anchor'),
 u('と','hiragana',[4],'white','connector'),
 u('い','hiragana',[6,7],'white','connector'),
 u('う','hiragana',[2,5],'white','connector_with_tall_ink_extent'),
 u('病','kanji',[0],'light_blue','primary_accent_anchor')],
 'notes':['い and う each have disconnected stroke components; each annotation unions its own strokes. A tall う ink box does not prove larger font size.']},
30: {'text':'待ちかねた再会','units':[
 u('待','kanji',[0,1],'dark_blue','left_accent_anchor'),
 u('ちかねた','hiragana',[4,5,6,7,8,10],'white','connector_group',error=5),
 u('再','kanji',[2],'pink','right_accent_anchor'),
 u('会','kanji',[3,9],'white','secondary_anchor')],
 'notes':['ち and か share a connected component. The complete continuous small-kana span ちかねた is retained as one group; no invented individual glyph boxes.']},
35: {'text':'命の価値','units':[
 u('命','kanji',[0],'light_gray','primary_anchor'),
 u('の','hiragana',[2],'red','accent_connector'),
 u('価','kanji',[1],'white','secondary_anchor',[1600,572,1890,853],12),
 u('値','kanji',[1,3],'white','secondary_anchor',[1870,619,2137,900],12)],
 'notes':['価/値 touch and share a connected component. Their visual boxes are manually corrected and have larger uncertainty.']},
48: {'text':'聖域の始まりと、崩壊の始まり','units':[
 u('聖','kanji',[0,2,5],'pink','first_phrase_accent_anchor',line=1),
 u('域','kanji',[1,4],'white','first_phrase_anchor',line=1),
 u('の','hiragana',[3],'white','connector',line=1),
 u('始','kanji',[6],'white','concept_anchor',line=2),
 u('ま','hiragana',[8],'white','connector',line=2),
 u('り','hiragana',[7],'pink','kana_accent',line=2),
 u('と','hiragana',[9],'white','connector',line=2),
 u('、','punctuation',[10],'white','offset_punctuation',line=2),
 u('崩','kanji',[11,13],'white','second_phrase_anchor',line=3),
 u('壊','kanji',[12],'pink','second_phrase_accent_anchor',[1477,731,1702,959],6,line=3),
 u('の','hiragana',[12],'white','connector',[1691,823,1840,940],6,line=3),
 u('始','kanji',[14],'white','concept_anchor',line=4),
 u('ま','hiragana',[15],'pink','kana_accent',line=4),
 u('り','hiragana',[16],'white','connector',line=4)],
 'notes':['壊/の share a component but have different colors; visual/color separation corrects their boxes. The first り and second ま are pink, showing kana can carry emphasis. Punctuation is independently offset.']}
}


def observed_rgb(image,bbox,label):
    x0,y0,x1,y1=bbox
    rgb=image[y0:y1,x0:x1].astype(int)
    r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    if label=='warm_yellow':mask=(r>160)&(g>120)&(r-b>50)
    elif label=='pink':mask=(r>140)&(r-g>30)&(b>100)
    elif label in ('dark_blue','light_blue'):mask=(b-r>35)&(b-g>20)&(b>110)
    elif label=='red':mask=(r>100)&(g<75)&(b<75)
    else:mask=(rgb.min(2)>110)&(rgb.max(2)-rgb.min(2)<25)
    interior=ndimage.binary_erosion(mask,iterations=2)
    pixels=rgb[interior if interior.sum()>50 else mask]
    if not len(pixels):return None
    return [round(float(v),1) for v in np.median(pixels,axis=0)]


def ratio_record(numerator,denominator):
    n=float(np.median([u['ink_bbox_height_px'] for u in numerator]))
    d=float(np.median([u['ink_bbox_height_px'] for u in denominator]))
    nlow=float(np.median([u['height_uncertainty_px'][0] for u in numerator]))
    nhigh=float(np.median([u['height_uncertainty_px'][1] for u in numerator]))
    dlow=float(np.median([u['height_uncertainty_px'][0] for u in denominator]))
    dhigh=float(np.median([u['height_uncertainty_px'][1] for u in denominator]))
    return {'value':round(n/d,4),'approx_bbox_error_range':[round(nlow/dhigh,4),round(nhigh/dlow,4)],
            'numerator_median_ink_height_px':n,'denominator_median_ink_height_px':d}


def max_min_range(units):
    return [round(max(u['height_uncertainty_px'][0] for u in units)/min(u['height_uncertainty_px'][1] for u in units),4),
            round(max(u['height_uncertainty_px'][1] for u in units)/min(u['height_uncertainty_px'][0] for u in units),4)]


def main():
    output=[]
    qa=ROOT/'analysis/fine-annotation-qa';qa.mkdir(exist_ok=True)
    for index,annotation in ANNOTATIONS.items():
        source=MEASUREMENTS[index-1]
        image=Image.open(ROOT/'references/originals'/source['file']).convert('RGB');a=np.asarray(image)
        units=[];cursor=0
        for unit in annotation['units']:
            item=dict(unit);override=item.pop('bbox_override')
            if override is None:
                boxes=[source['connected_components'][c]['bbox'] for c in item['component_ids']]
                bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
            else:bbox=override
            item['bbox']=bbox
            item['bbox_basis']='manual_visual_boundary' if override else 'visually_assigned_component_union'
            item['confidence']='medium' if override else 'high'
            item['unit_kind']='hiragana_group' if len(item['text'])>1 else 'character'
            item['char_span']=[cursor,cursor+len(item['text'])];cursor+=len(item['text'])
            height=bbox[3]-bbox[1];error=2*item['bbox_error_per_edge_px']
            item['ink_bbox_height_px']=height;item['height_uncertainty_px']=[max(1,height-error),height+error]
            item['observed_rgb_median']=observed_rgb(a,bbox,item['color_label'])
            item['visual_role_basis']='manual visual hierarchy, not an LLM semantic prediction'
            item['font_size']=None;item['font_family']=None
            units.append(item)
        assert ''.join(u['text'] for u in units)==annotation['text']
        kanji=[u for u in units if u['script']=='kanji'];kana=[u for u in units if u['script']=='hiragana']
        median=float(np.median([u['ink_bbox_height_px'] for u in kanji]))
        for item in units:item['ink_height_relative_to_median_kanji']=round(item['ink_bbox_height_px']/median,4)
        heights=[u['ink_bbox_height_px'] for u in units]
        content=[u['ink_bbox_height_px'] for u in units if u['script']!='punctuation']
        result={'sample_id':f's{index:03d}','index':index,'file':source['file'],'source_size':[3200,1440],
                'transcribed_text':annotation['text'],'text_source':'manual transcription after viewing original image',
                'units':units,'median_kanji_ink_bbox_height_px':median,
                'max_min_ink_height_ratio_including_punctuation':round(max(heights)/min(heights),4),
                'max_min_ink_height_ratio_excluding_punctuation':round(max(content)/min(content),4),
                'max_min_ink_height_ratio_including_punctuation_bbox_error_range':max_min_range(units),
                'max_min_ink_height_ratio_excluding_punctuation_bbox_error_range':max_min_range([u for u in units if u['script']!='punctuation']),
                'kanji_kana_median_ink_height_ratio':ratio_record(kanji,kana),
                'kana_ratio_unit_basis':'kana group bbox' if any(u['unit_kind']=='hiragana_group' for u in kana) else 'individual kana bboxes',
                'confidence':'medium' if any(u['confidence']=='medium' for u in units) else 'high',
                'notes':annotation['notes'],'not_font_size':True}
        output.append(result)
        draw=ImageDraw.Draw(image)
        for n,item in enumerate(units,1):
            b=item['bbox'];draw.rectangle(b,outline=(0,255,128) if item['confidence']=='high' else (255,160,0),width=3)
            draw.text((b[0]+4,b[1]+4),str(n),fill=(0,255,255),stroke_width=1,stroke_fill=(0,0,0))
        b=source['title_ink_bbox']; image=image.crop((b[0]-25,b[1]-25,b[2]+25,b[3]+8))
        image.save(qa/f's{index:03d}.png')
    result={'schema_version':1,'coordinate_convention':'half-open XYXY original screenshot pixels',
            'method':'Original-image visual inspection + existing CV components + manual boundary corrections',
            'metric_warning':'All relative sizes and ratios are visible ink bounding-box heights. They are NOT font sizes, CSS sizes, or glyph advances.',
            'uncertainty_warning':'Per-edge errors are conservative manual estimates, not statistical confidence intervals. Color is median visible core RGB, not original authored paint.',
            'group_warning':'s030 has a four-kana group; its group-height ratio is not directly comparable with a per-character kana median.',
            'samples':output}
    (ROOT/'analysis/fine_annotations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps([{k:s[k] for k in ['sample_id','median_kanji_ink_bbox_height_px','max_min_ink_height_ratio_including_punctuation','max_min_ink_height_ratio_excluding_punctuation','kanji_kana_median_ink_height_ratio']} for s in output],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
