"""Render repository examples with the product engine and saved semantic plans.

Run from the repository root: python -m scripts.render_showcase [--check]
No model requests are made. --check regenerates assets without writing them.
"""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from engine.fonts import FontFace
from engine.layout import LayoutEngine, load_config
from engine.renderer import Renderer
from engine.text import JapaneseAnalyzer
from llm.planner import validate_plan

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets/showcase"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def png_bytes(image):
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def make_cover(images, order):
    """Place untouched full canvases in a grid; never reposition their glyphs."""
    tile_width, tile_height, gap = 760, 428, 24
    cover = Image.new(
        "RGB", (tile_width * 2 + gap * 3, tile_height * 3 + gap * 4), "#fafafa"
    )
    for index, key in enumerate(order):
        tile = Image.open(BytesIO(images[key])).convert("RGB")
        tile = tile.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        cover.paste(
            tile,
            (gap + (index % 2) * (tile_width + gap),
             gap + (index // 2) * (tile_height + gap)),
        )
    return png_bytes(cover)


def render():
    recipe_bytes = (ASSETS / "recipes.json").read_bytes()
    recipes = json.loads(recipe_bytes)
    config = load_config()
    fonts = {role: FontFace(ROOT / path) for role, path in recipes["fonts"].items()}
    analyzer = JapaneseAnalyzer(config["rules"])
    renderer = Renderer()
    outputs, images, records = {}, {}, []
    for title in recipes["titles"]:
        for mode, number in title["selected"].items():
            plan = title.get("saved_plan") if mode == "B" else None
            tokens = validate_plan(title["text"], plan) if plan else analyzer.analyze(title["text"])
            layouts = LayoutEngine(fonts, config).generate(
                title["text"], tokens,
                seed=recipes["seed"], count=recipes["count"],
                width=recipes["canvas"]["width"], height=recipes["canvas"]["height"],
                palette=title.get("palette", recipes["palette"]),
                color_mode=recipes["color_mode"], plan=plan,
            )
            layout = layouts[number - 1]
            stem = f"{title['id']}-{mode}"
            outputs[f"{stem}.png"] = renderer.png(layout)
            outputs[f"{stem}.svg"] = renderer.svg(layout).encode()
            outputs[f"{stem}-transparent.png"] = renderer.png(layout, transparent=True)
            outputs[f"{stem}-transparent.svg"] = renderer.svg(layout, transparent=True).encode()
            images[stem] = outputs[f"{stem}.png"]
            records.append({
                "id": stem, "text": title["text"], "mode": mode,
                "selected_candidate": number, "reference_id": title["reference_id"],
                "plan_source": title.get("plan_source") if mode == "B" else None,
                "plan_replayed": mode == "B", "layout": layout.record(),
                "files": {name: digest(data) for name, data in outputs.items() if name.startswith(stem + ".") or name.startswith(stem + "-")},
            })
            print(f"{stem}: candidate {number}/{recipes['count']}", flush=True)
    outputs["cover.png"] = make_cover(images, recipes["hero"])
    source_files = sorted({
        *ROOT.glob("engine/*.py"), ROOT / "llm/planner.py",
        ROOT / "scripts/render_showcase.py", ROOT / "requirements.txt",
    })
    manifest = {
        "schema_version": 1,
        "engine": "product-python", "model_calls_this_run": 0,
        "selection": "Human-selected candidates; no glyph coordinate or color overrides.",
        "recipe_sha256": digest(recipe_bytes),
        "source_sha256": {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in source_files},
        "config_sha256": digest(json.dumps(config, sort_keys=True).encode()),
        "fonts": {role: face.metadata for role, face in fonts.items()},
        "cover_sha256": digest(outputs["cover.png"]), "examples": records,
    }
    outputs["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Regenerate and compare; write nothing")
    args = parser.parse_args()
    outputs = render()
    if args.check:
        changed = [name for name, data in outputs.items() if not (ASSETS / name).is_file() or (ASSETS / name).read_bytes() != data]
        if changed:
            raise SystemExit("Showcase differs: " + ", ".join(changed))
        print(f"Verified {len(outputs)} files against the product renderer.")
    else:
        for name, data in outputs.items():
            (ASSETS / name).write_bytes(data)
        print(f"Wrote {len(outputs)} files to {ASSETS.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
