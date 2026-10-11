#!/usr/bin/env python3
"""Reproduce font specimens and ink metrics using pinned, OFL research fonts.

Fonts stay in .research-fonts and are never used as online downloadable assets.
System Python requires Pillow with RAQM and fontTools.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import unicodedata
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont, features
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "bd8f81ddb5c74d5c8897b36ad88b440266245103"
BASE = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl"
FONT_SPECS = [
    ("mplus2-black", "M PLUS 2 / Black (900)", "mplus2", "MPLUS2[wght].ttf", 900),
    ("noto-sans-jp-black", "Noto Sans JP / Black (900)", "notosansjp", "NotoSansJP[wght].ttf", 900),
    ("shippori-mincho-semibold", "Shippori Mincho / SemiBold (600)", "shipporimincho", "ShipporiMincho-SemiBold.ttf", None),
    ("shippori-antique", "Shippori Antique / Regular (400)", "shipporiantique", "ShipporiAntique-Regular.ttf", None),
    ("shippori-antique-b1", "Shippori Antique B1 / Regular (400)", "shipporiantiqueb1", "ShipporiAntiqueB1-Regular.ttf", None),
    ("dela-gothic-one", "Dela Gothic One / Regular (400)", "delagothicone", "DelaGothicOne-Regular.ttf", None),
    ("zen-kaku-gothic-new-black", "Zen Kaku Gothic New / Black (900)", "zenkakugothicnew", "ZenKakuGothicNew-Black.ttf", None),
]
TEXTS = ["待ちかねた再会", "聖域の終わりと、崩壊の始まり"]
PX = 144

def digest(data):
    return hashlib.sha256(data).hexdigest()

def fetch(url, path):
    if not path.exists():
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return path.read_bytes()

def prepare(spec):
    slug, label, folder, filename, weight = spec
    private = ROOT / ".research-fonts"
    private.mkdir(parents=True, exist_ok=True)
    licences = ROOT / "analysis" / "font-licenses"
    licences.mkdir(parents=True, exist_ok=True)
    source_url = f"{BASE}/{folder}/{urllib.parse.quote(filename)}"
    source = private / filename
    source_bytes = fetch(source_url, source)
    licence_url = f"{BASE}/{folder}/OFL.txt"
    licence = licences / f"{slug}-OFL.txt"
    licence_bytes = fetch(licence_url, licence)
    assert b"SIL OPEN FONT LICENSE" in licence_bytes, slug
    output = source
    if weight is not None:
        output = private / f"{slug}.ttf"
        if not output.exists():
            font = TTFont(source)
            instantiateVariableFont(font, {"wght": weight}, inplace=True).save(output)
            font.close()
    font = TTFont(output)
    metadata = {
        "id": slug, "label": label,
        "source_repository": "https://github.com/google/fonts",
        "source_commit": COMMIT, "source_url": source_url,
        "source_filename": filename, "source_sha256": digest(source_bytes),
        "research_file": str(output.relative_to(ROOT)),
        "research_sha256": digest(output.read_bytes()),
        "license": "SIL Open Font License 1.1",
        "license_url": licence_url,
        "license_file": str(licence.relative_to(ROOT)),
        "license_sha256": digest(licence_bytes),
        "instantiation": {"wght": weight} if weight else None,
        "units_per_em": font["head"].unitsPerEm,
        "weight_class": font["OS/2"].usWeightClass,
        "policy": "Offline research only; excluded from Git and Docker, never a public font URL.",
    }
    font.close()
    return metadata

def script(character):
    value = ord(character)
    if 0x4E00 <= value <= 0x9FFF or 0x3400 <= value <= 0x4DBF:
        return "kanji"
    if 0x3041 <= value <= 0x309F:
        return "hiragana"
    if 0x30A0 <= value <= 0x30FF:
        return "katakana"
    if unicodedata.category(character).startswith("P"):
        return "punctuation"
    return "other"

def raster_metric(font, character):
    canvas = Image.new("L", (PX * 3, PX * 3))
    draw = ImageDraw.Draw(canvas)
    baseline = PX * 2
    draw.text((PX, baseline), character, font=font, fill=255,
              anchor="ls", language="ja", direction="ltr")
    mask = canvas.point(lambda value: 255 if value >= 16 else 0)
    bounds = mask.getbbox()
    if not bounds:
        return None
    x0, y0, x1, y1 = bounds
    return {
        "bbox_px_baseline": [x0 - PX, y0 - baseline, x1 - PX, y1 - baseline],
        "width_em": (x1 - x0) / PX,
        "height_em": (y1 - y0) / PX,
        "top_em": (y0 - baseline) / PX,
        "bottom_em": (y1 - baseline) / PX,
        "center_y_em": ((y0 + y1) / 2 - baseline) / PX,
        "advance_em": font.getlength(character, language="ja", direction="ltr") / PX,
        "ink_area_em2": sum(value > 0 for value in mask.getdata()) / PX ** 2,
    }

def measure(meta):
    path = ROOT / meta["research_file"]
    font = TTFont(path)
    em = font["head"].unitsPerEm
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    face = ImageFont.truetype(str(path), PX, layout_engine=ImageFont.Layout.RAQM)
    chars = sorted(set("".join(TEXTS)), key=lambda c: (script(c), ord(c)))
    metrics = []
    for character in chars:
        name = cmap.get(ord(character))
        if name is None:
            metrics.append({"character": character, "script": script(character), "missing": True})
            continue
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        advance, bearing = font["hmtx"][name]
        metrics.append({
            "character": character, "script": script(character), "glyph_name": name,
            "outline_bbox_font_units": list(pen.bounds) if pen.bounds else None,
            "outline_bbox_em": [round(v / em, 6) for v in pen.bounds] if pen.bounds else None,
            "advance_em_outline": advance / em,
            "left_bearing_em_outline": bearing / em,
            "raster": raster_metric(face, character),
        })
    groups = {}
    for role in ["kanji", "hiragana", "punctuation"]:
        selected = [m for m in metrics if m["script"] == role and m.get("raster")]
        if selected:
            keys = ["width_em", "height_em", "ink_area_em2", "top_em", "bottom_em", "center_y_em", "advance_em"]
            groups[role] = {
                "sample": "".join(m["character"] for m in selected), "count": len(selected),
                **{f"mean_{key}": statistics.mean(m["raster"][key] for m in selected) for key in keys},
            }
    ratios = {
        key: groups["kanji"]["mean_" + key] / groups["hiragana"]["mean_" + key]
        for key in ["width_em", "height_em", "ink_area_em2"]
    }
    ratios["kanji_minus_hiragana_center_y_em"] = groups["kanji"]["mean_center_y_em"] - groups["hiragana"]["mean_center_y_em"]
    vertical = {
        "hhea_ascent_em": font["hhea"].ascent / em,
        "hhea_descent_em": font["hhea"].descent / em,
        "hhea_line_gap_em": font["hhea"].lineGap / em,
        "typo_ascent_em": font["OS/2"].sTypoAscender / em,
        "typo_descent_em": font["OS/2"].sTypoDescender / em,
        "win_ascent_em": font["OS/2"].usWinAscent / em,
        "win_descent_em": font["OS/2"].usWinDescent / em,
        "pillow_ascent_px": face.getmetrics()[0], "pillow_descent_px": face.getmetrics()[1],
    }
    font.close()
    return {"id": meta["id"], "label": meta["label"], "vertical_metrics": vertical,
            "glyphs": metrics, "script_summary": groups, "kanji_hiragana_ratios": ratios}

def draw_mixed(draw, text, pos, primary, kana, size):
    x, baseline = pos
    fonts = {
        "primary": ImageFont.truetype(str(primary), size, layout_engine=ImageFont.Layout.RAQM),
        "kana": ImageFont.truetype(str(kana), size, layout_engine=ImageFont.Layout.RAQM),
    }
    runs = []
    for character in text:
        role = "kana" if script(character) == "hiragana" else "primary"
        if runs and runs[-1][0] == role:
            runs[-1] = (role, runs[-1][1] + character)
        else:
            runs.append((role, character))
    for role, run in runs:
        face = fonts[role]
        draw.text((x, baseline), run, font=face, fill="#f3eee8", anchor="ls", language="ja", direction="ltr")
        x += face.getlength(run, language="ja", direction="ltr")

def specimen(manifest, results):
    width, row_height = 2460, 228
    top = 130
    rows = len(manifest) + 3
    im = Image.new("RGB", (width, top + rows * row_height + 95), "#101012")
    draw = ImageDraw.Draw(im)
    ui = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    label_font = ImageFont.truetype(ui, 25)
    small_font = ImageFont.truetype(ui, 20)
    title_font = ImageFont.truetype(ui, 32)
    draw.text((36, 22), "Japanese font control experiment / identical 72 px / same baseline", font=title_font, fill="#ffffff")
    draw.text((36, 70), "Unmodified font specimens first; these are NOT final title layouts or source-font identification.", font=label_font, fill="#afafbb")
    by_id = {m["id"]: m for m in manifest}
    for row, meta in enumerate(manifest):
        y = top + row * row_height
        if row % 2:
            draw.rectangle((0, y, width, y + row_height), fill="#19191e")
        result = results[row]
        r = result["kanji_hiragana_ratios"]
        v = result["vertical_metrics"]
        draw.text((36, y + 10), meta["label"], font=label_font, fill="#9bc9dc")
        draw.text((36, y + 48), f"Kanji / hiragana: width {r['width_em']:.3f}, height {r['height_em']:.3f}, ink area {r['ink_area_em2']:.3f}", font=small_font, fill="#a8a8b2")
        face = ImageFont.truetype(str(ROOT / meta["research_file"]), 72, layout_engine=ImageFont.Layout.RAQM)
        for text, x in zip(TEXTS, [40, 760]):
            baseline = y + 163
            draw.line((x, baseline, x + face.getlength(text, language="ja"), baseline), fill="#49414e", width=1)
            draw.text((x, baseline), text, font=face, fill="#f3eee8", anchor="ls", language="ja", direction="ltr")
        draw.text((36, y + 190), f"hhea ascent/descent: {v['hhea_ascent_em']:.3f} / {v['hhea_descent_em']:.3f} em; metrics != actual ink bounds", font=small_font, fill="#898994")
    combinations = ["mplus2-black", "noto-sans-jp-black", "zen-kaku-gothic-new-black"]
    for index, primary_id in enumerate(combinations):
        y = top + (len(manifest) + index) * row_height
        if (len(manifest) + index) % 2:
            draw.rectangle((0, y, width, y + row_height), fill="#19191e")
        primary = by_id[primary_id]
        kana = by_id["shippori-mincho-semibold"]
        draw.text((36, y + 10), primary["label"] + " + Shippori Mincho kana", font=label_font, fill="#e7b3cb")
        draw.text((36, y + 48), "Script-role mixing control: identical 72 px; no size hierarchy, optical spacing, or layout optimization.", font=small_font, fill="#a8a8b2")
        for text, x in zip(TEXTS, [40, 760]):
            draw.line((x, y + 163, x + 1350, y + 163), fill="#49414e", width=1)
            draw_mixed(draw, text, (x, y + 163), ROOT / primary["research_file"], ROOT / kana["research_file"], 72)
    draw.text((36, im.height - 59), "Offline OFL research fonts / pinned sources in font_manifest.json / fonts excluded from Git and Docker", font=label_font, fill="#9b9ba8")
    im.save(ROOT / "analysis" / "font_experiments.png")


def write_report(manifest, results, mixed):
    lines = [
        "# 字体方向控制实验", "",
        "本实验没有识别参考标题的原始字体，也没有把找到某款字体当作项目答案。参考截图能看到粗汉字与较细、书写感假名之间的形态差异，但截图中的压缩、字号变化、颜色、字距、独立字符定位会改变字形外观，无法据此确认字体名称。",
        "", "## 实验控制", "",
        "所有单字体行使用相同文本、相同 72 px 字号、相同 baseline、相同颜色。轮廓与像素度量使用 144 px，字面界定为实际 ink bbox，像素 mask 阈值为 16/255。Pillow/RAQM 负责本次控制实验 shaping；fontTools 读取字体轮廓与真实 advance、bearing、ascent/descent。没有用 CSS box 代替字面。",
        "", "两句固定文本：`待ちかねた再会`、`聖域の終わりと、崩壊の始まり`。统计按这两句中的唯一汉字/平假名采样，避免字符频率影响；它不是整个字体的全字库结论。M PLUS 2、Noto Sans JP 的变量字体固定为 wght=900。",
        "", "## 字面和 baseline 度量", "",
        "| 字体 | 汉字/假名宽度 | 汉字/假名高度 | 汉字/假名 ink 面积 | 汉字与假名中心 y 差/em | hhea ascent/descent/em |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for result in results:
        ratios = result["kanji_hiragana_ratios"]
        v = result["vertical_metrics"]
        lines.append(f"| {result['label']} | {ratios['width_em']:.3f} | {ratios['height_em']:.3f} | {ratios['ink_area_em2']:.3f} | {ratios['kanji_minus_hiragana_center_y_em']:.3f} | {v['hhea_ascent_em']:.3f}/{v['hhea_descent_em']:.3f} |")
    lines += [
        "", "中心 y 使用屏幕坐标系，以 baseline 为 0；负数向上。字符字面高度、面积以及视觉中心都和字体提供的 ascent/descent 不同。等 CSS 字号或等 baseline 不能保证混排时视觉大小一致。所有原始逐字 bbox 与 advance 保存在 JSON 中。",
        "", "## 字体角色混排", "",
        "图中追加三个控制组：M PLUS 2 Black、Noto Sans JP Black、Zen Kaku Gothic New Black 分别担当汉字，Shippori Mincho SemiBold 担当平假名。它们保持同字号，旨在分离字体角色对比和布局因素。",
        "", "| 汉字字体 + Shippori Mincho 假名 | 汉字/假名平均 ink 高度 | ink 面积比 | 等字号视觉中心补偿/em |",
        "|---|---:|---:|---:|",
    ]
    for row in mixed:
        lines.append(f"| {row['primary_label']} | {row['kanji_hiragana_height_ratio']:.3f} | {row['kanji_hiragana_ink_area_ratio']:.3f} | {row['align_kana_center_to_kanji_offset_em']:.3f} |")
    lines += [
        "", "中心补偿仅描述这批字的平均几何中心，不能直接代替每字光学校正。逐 glyph 字面、视觉质量/质心、字号层级与局部 spacing 应进入布局引擎。混排控制图已经能形成较强粗细角色对比，但它仍是普通文字排列，距离参考标题还需要断行、不同字号、非均匀缩放、强调色、标点定位和 optical kerning。",
        "", "## 对引擎的建议", "",
        "- 以 Noto Sans JP Black 或 M PLUS 2 Black 作为稳定的粗 Gothic 实验基准，分别对照；不宣称它们是参考原字体。",
        "- 保留 Shippori Mincho 假名角色混排选项，再比较字号缩小、相同字号等控制组。",
        "- Shippori Antique/B1 具有不同的假名字形方向，适合作为单字体候选；其常规字重与 Heavy Gothic 的黑度不可直接等同。",
        "- Dela Gothic One 的显示字面很强，部分假名也很粗。应针对短标题控制其字面尺寸和间距，不把它用于全部标题。",
        "- 字面/质量度量应在用户实际上传的字体上重新计算，不把本实验测得的数值硬编码到生产字体逻辑。",
        "", "## 来源与可复现性", "",
        f"字体全部来自 Google Fonts 官方仓库 commit `{COMMIT}`。每个文件的精确来源、原始/实例化 sha256、字重和 OFL 许可证在 `font_manifest.json`。许可证文本保存在 `font-licenses/`，字体本体只在仓库外提交范围的 `.research-fonts/`，不得提供线上字体下载。",
        "", "复跑：`python3 analysis/run_font_experiments.py`。变量字体实例化结果也记录 sha256；若运行库升级导致生成字体二进制变化，需要同时记录升级和新的校验值。",
        "", "本轮只比较字体和字体角色，没有进行参考图逐字轮廓拟合，也没有使用视觉 embedding。因此不能对“最相似字体”或“最好排版”给出排序。方案 A/B 比较必须使用同一组实际字体。",
    ]
    (ROOT / "analysis" / "font_experiments.md").write_text("\n".join(lines) + "\n")

def main():
    if not features.check_feature("raqm"):
        raise RuntimeError("Pillow must include RAQM for the controlled Japanese shaping experiment")
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        manifest = list(pool.map(prepare, FONT_SPECS))
    results = [measure(item) for item in manifest]
    by_id = {result["id"]: result for result in results}
    kana = by_id["shippori-mincho-semibold"]["script_summary"]["hiragana"]
    mixed = []
    for primary_id in ["mplus2-black", "noto-sans-jp-black", "zen-kaku-gothic-new-black"]:
        primary = by_id[primary_id]
        kanji = primary["script_summary"]["kanji"]
        mixed.append({
            "primary": primary_id, "primary_label": primary["label"],
            "kana": "shippori-mincho-semibold",
            "kanji_hiragana_height_ratio": kanji["mean_height_em"] / kana["mean_height_em"],
            "kanji_hiragana_ink_area_ratio": kanji["mean_ink_area_em2"] / kana["mean_ink_area_em2"],
            "align_kana_center_to_kanji_offset_em": kanji["mean_center_y_em"] - kana["mean_center_y_em"],
        })
    data = {
        "experiment": "Same texts, uniform-size typeface/script-role controls", "texts": TEXTS,
        "render_px": PX, "specimen_px": 72, "raster_alpha_threshold": 16,
        "renderer": "Pillow with RAQM (FreeType/HarfBuzz via RAQM)",
        "pillow_version": Image.__version__, "measurement_population": "Unique characters from both fixed texts",
        "fonts": results, "mixed_font_controls": mixed,
        "limitations": ["No identification of source fonts", "No source glyph contour fitting", "No title layout quality ranking", "Metrics sampled on fixed corpus, not universal font metrics"],
    }
    (ROOT / "analysis" / "font_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "analysis" / "font_experiments.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    specimen(manifest, results)
    write_report(manifest, results, mixed)
    print(json.dumps({"files": ["font_manifest.json", "font_experiments.json", "font_experiments.png", "font_experiments.md"], "fonts": len(manifest)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
