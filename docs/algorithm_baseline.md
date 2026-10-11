# A：无大模型基线

生产生成路径不调用 LLM、VLM、CLIP、OCR 或视觉 embedding。参考分析只使用人工查看、阈值图像处理及统计。

文本先经 SudachiPy B 模式做形态素分析。POS、汉字占比、长度、重复与句首/尾位置产生 importance。三个可配置启发式为 balanced、kanji_anchor、semantic_nouns，分别注重默认平衡、汉字锚点和名词语义权重。`experiments/ablations.py` 在四条标题上做探索性消融；不是审美排名。

公式的默认形式是 `POS基值 + 汉字占比×bonus + capped长度×bonus + 重复bonus + 边缘bonus`，助词与标点单独使用低基值。它无法充分识别隐喻、上下文与反讽；B 用语义计划替代这部分，后续过程完全共用。

## 搜索

每个合格家族尝试多种行数。token 边界的 beam search 保留 32 条部分路径，总代价含目标行宽差平方和、切口惩罚与超长 token 紧急拆分惩罚。助词/标点不可作为下一行独立开头，闭标点禁行首，开括号禁行末。至少生成多个家族与三种尺度，再从候选池按家族多样性和分数选出 4–8 个答案。

形态素可以包含多个脚本。字体按 kanji/kana 角色分 run，每个 run 由 HarfBuzz shaping；拉丁 ligature 与 kerning 保留 advance/offset。日文字形通过 mask 共同扫描行测安全最小距离，可以让字面方框嵌入但保持笔画间距。FreeType 提供真实 mask，fontTools 提供相同字体实例的 SVG path 与 outline bounds。最终 SVG 包含 path，不引用字体 URL。

布局变量是字形 ink x/y、size、scaleX/scaleY、color 与行 offset。默认 scaleY=1、rotation=0；没有证据支持常规标题普遍旋转。本版退火开放上下偏移、行平移、字号、横向缩放、水平位置，最多 32 步。字体名和文本不可被 mutation 改动。禁则、溢出与显著笔画碰撞是候选淘汰条件。

## Score 定义

| 项 | 计算 | 局限 |
|---|---|---|
| Balance | 实际墨迹中心离目标 (0.5,0.5) 的归一化距离 | 居中校正后区分力有限 |
| SemanticEmphasis | 字符重要度与 ink bbox 面积相关性映射到 0–1 | 字面面积不等于感知显著性 |
| SpacingQuality | 共同扫描行的最小墨迹间距/em 与目标间距的绝对偏差，经指数映射 | 1/4 栅格量化会影响极小字 |
| TemplateConsistency | 行数是否属于所选家族 | 人工家族定义，不是设计真值 |
| WhitespaceQuality | ink 总体 bbox 占画布面积与家族目标的偏差 | 与 ink 覆盖比例分开记录 |
| Rhythm | 字号离散程度，饱和到 1 | 不代表越变化越漂亮 |
| CollisionPenalty | 240px 宽 mask 栅格的重叠比例 | 约束检查为低分辨率，非逐像素无误差保证 |
| OverflowPenalty | 画布外 mask 与字形范围 | 安全边界同时用于 fit |
| KinsokuPenalty | 非法行首/行尾数 | 不涵盖出版级 JLREQ 全部规则 |
| AwkwardBreakPenalty | 束搜索断行代价/行数 | 包含行宽分布和语义代理，不是纯语义分 |

权重全部在 `layout_weights.yaml`。正项加权、罚项减权。合格候选允许极少量栅格重叠误差（0.3% 上限），Benchmark 记录实测最大值。分数用来比较实现中的候选，不能与人类审美评分互换。

## 参考统计与泛化

占用面积参数用可靠黑底样本拟合，排除 Benchmark 的参考 ID，见 `fitted_layout_statistics.json`。样本不足四个的 wide_block、稀少的 alternating_steps 保留可审查假设。其他层级/字距参数是初始实验参数，没有伪装成逐字拟合结果。

seed、字体 SHA256、token 角色、布局家族、完整配置 hash、候选池数量、score 各项与所有字形位置均记录。随机源固定到每候选，重跑同一 Python 环境得到同一 SVG；跨渲染库版本或 Python/浏览器端不保证 bitwise 一致。

探索性消融共 20 次（四文本×五设置）：没有一种 importance 启发式在全部标题上占优，固定间距也在两条标题上获得更高内部 score。因而保留可配置启发式与光学字距，不把内部打分当审美结论。

颜色质量现在加入 Score：对比度通过率、着色区域的重要度、强调面积克制程度、参考颜色数量先验。单色/双色/统一前景色为显式选择时不使用自动数量先验。小字低于 4.5:1、大字低于 3:1 的配色在输出前改为主体前景色。该工程可读性门槛不是风格相似度或审美证明。
