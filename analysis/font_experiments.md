# 字体方向控制实验

本实验没有识别参考标题的原始字体，也没有把找到某款字体当作项目答案。参考截图能看到粗汉字与较细、书写感假名之间的形态差异，但截图中的压缩、字号变化、颜色、字距、独立字符定位会改变字形外观，无法据此确认字体名称。

## 实验控制

所有单字体行使用相同文本、相同 72 px 字号、相同 baseline、相同颜色。轮廓与像素度量使用 144 px，字面界定为实际 ink bbox，像素 mask 阈值为 16/255。Pillow/RAQM 负责本次控制实验 shaping；fontTools 读取字体轮廓与真实 advance、bearing、ascent/descent。没有用 CSS box 代替字面。

两句固定文本：`待ちかねた再会`、`聖域の終わりと、崩壊の始まり`。统计按这两句中的唯一汉字/平假名采样，避免字符频率影响；它不是整个字体的全字库结论。M PLUS 2、Noto Sans JP 的变量字体固定为 wght=900。

## 字面和 baseline 度量

| 字体 | 汉字/假名宽度 | 汉字/假名高度 | 汉字/假名 ink 面积 | 汉字与假名中心 y 差/em | hhea ascent/descent/em |
|---|---:|---:|---:|---:|---|
| M PLUS 2 / Black (900) | 1.102 | 1.084 | 1.454 | 0.006 | 1.160/-0.288 |
| Noto Sans JP / Black (900) | 1.156 | 1.084 | 1.552 | -0.001 | 1.160/-0.288 |
| Shippori Mincho / SemiBold (600) | 1.360 | 1.132 | 1.941 | 0.001 | 1.160/-0.288 |
| Shippori Antique / Regular (400) | 1.276 | 1.088 | 1.967 | 0.014 | 1.160/-0.288 |
| Shippori Antique B1 / Regular (400) | 1.260 | 1.085 | 1.969 | 0.012 | 1.160/-0.288 |
| Dela Gothic One / Regular (400) | 1.049 | 1.009 | 1.221 | -0.000 | 1.160/-0.288 |
| Zen Kaku Gothic New / Black (900) | 1.204 | 1.066 | 1.688 | 0.000 | 1.160/-0.288 |

中心 y 使用屏幕坐标系，以 baseline 为 0；负数向上。字符字面高度、面积以及视觉中心都和字体提供的 ascent/descent 不同。等 CSS 字号或等 baseline 不能保证混排时视觉大小一致。所有原始逐字 bbox 与 advance 保存在 JSON 中。

## 字体角色混排

图中追加三个控制组：M PLUS 2 Black、Noto Sans JP Black、Zen Kaku Gothic New Black 分别担当汉字，Shippori Mincho SemiBold 担当平假名。它们保持同字号，旨在分离字体角色对比和布局因素。

| 汉字字体 + Shippori Mincho 假名 | 汉字/假名平均 ink 高度 | ink 面积比 | 等字号视觉中心补偿/em |
|---|---:|---:|---:|
| M PLUS 2 / Black (900) | 1.142 | 4.022 | 0.025 |
| Noto Sans JP / Black (900) | 1.151 | 3.513 | 0.009 |
| Zen Kaku Gothic New / Black (900) | 1.124 | 3.332 | 0.004 |

中心补偿仅描述这批字的平均几何中心，不能直接代替每字光学校正。逐 glyph 字面、视觉质量/质心、字号层级与局部 spacing 应进入布局引擎。混排控制图已经能形成较强粗细角色对比，但它仍是普通文字排列，距离参考标题还需要断行、不同字号、非均匀缩放、强调色、标点定位和 optical kerning。

## 对引擎的建议

- 以 Noto Sans JP Black 或 M PLUS 2 Black 作为稳定的粗 Gothic 实验基准，分别对照；不宣称它们是参考原字体。
- 保留 Shippori Mincho 假名角色混排选项，再比较字号缩小、相同字号等控制组。
- Shippori Antique/B1 具有不同的假名字形方向，适合作为单字体候选；其常规字重与 Heavy Gothic 的黑度不可直接等同。
- Dela Gothic One 的显示字面很强，部分假名也很粗。应针对短标题控制其字面尺寸和间距，不把它用于全部标题。
- 字面/质量度量应在用户实际上传的字体上重新计算，不把本实验测得的数值硬编码到生产字体逻辑。

## 来源与可复现性

字体全部来自 Google Fonts 官方仓库 commit `bd8f81ddb5c74d5c8897b36ad88b440266245103`。每个文件的精确来源、原始/实例化 sha256、字重和 OFL 许可证在 `font_manifest.json`。许可证文本保存在 `font-licenses/`，字体本体只在仓库外提交范围的 `.research-fonts/`，不得提供线上字体下载。

复跑：`python3 analysis/run_font_experiments.py`。变量字体实例化结果也记录 sha256；若运行库升级导致生成字体二进制变化，需要同时记录升级和新的校验值。

本轮只比较字体和字体角色，没有进行参考图逐字轮廓拟合，也没有使用视觉 embedding。因此不能对“最相似字体”或“最好排版”给出排序。方案 A/B 比较必须使用同一组实际字体。
