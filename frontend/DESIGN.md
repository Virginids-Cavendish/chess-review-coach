---
name: 国际象棋复盘教练 · 复盘界面
description: 沿用现有中文分析界面，以清晰来源、棋谱和数值支持复盘。
colors:
  background: "#0b1220"
  panel: "#111a2b"
  panel-soft: "#16223a"
  border: "#24314c"
  text: "#e6ebf5"
  muted: "#93a1bd"
  engine: "#4f9cf9"
  coach: "#d9a441"
  outcome-white: "oklch(96.8% 0.007 247.896)"
  outcome-draw: "oklch(70.4% 0.04 256.788)"
  outcome-black: "oklch(27.9% 0.041 260.031)"
typography:
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: "1.75rem"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: "1rem"
  notation:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: "1rem"
rounded:
  control: "0.25rem"
  soft-panel: "0.625rem"
  panel: "0.75rem"
  tag: "9999px"
spacing:
  tight: "0.25rem"
  control: "0.5rem"
  compact: "0.75rem"
  panel: "1rem"
  section: "1.25rem"
components:
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  panel-soft:
    backgroundColor: "{colors.panel-soft}"
    rounded: "{rounded.soft-panel}"
    padding: "{spacing.compact}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.75rem"
  button-outline-hover:
    backgroundColor: "{colors.panel-soft}"
  field:
    backgroundColor: "{colors.panel-soft}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "{spacing.control}"
  tag:
    backgroundColor: "{colors.panel-soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.tag}"
    padding: "0.1rem 0.55rem"
---

# Design System: 国际象棋复盘教练 · 复盘界面

## Overview

**Creative North Star: "证据优先的复盘工作台"**

这是对现有前端的记录，主要证据来自复盘页、引擎证据、教练解释和真人统计面板。沿用深蓝底色、紧凑中文排版及有边界的分析区域；新增内容应接入这一界面，而不另建视觉风格。

界面让用户在棋盘、着法和解释之间核对信息。颜色帮助辨认来源，正文和数值承担内容。页面的功能标题使用现有中文系统字体，不引入展示性大标题。

**Key Characteristics:**
- 深蓝背景与逐层稍亮的容器。
- 蓝色标识引擎证据，金色标识教练说明。
- 等宽棋谱、对齐数字和明确的统计标签。
- 紧凑控件与可见边框，优先阅读和操作。

## Colors

以冷深蓝中性色构成大部分面积，蓝色与金色保留各自的来源含义。

### Primary
- **引擎蓝**（`engine`）：引擎证据左边线、引擎相关强调和真人统计控件的键盘焦点。

### Secondary
- **教练金**（`coach`）：教练解释左边线和说明标签；不作为真人历史结果的胜负色。

### Neutral
- **夜蓝底色**（`background`）、**分析面板**（`panel`）、**内层面板**（`panel-soft`）：背景与内容层次。
- **边界蓝灰**（`border`）：容器边框、表格分隔和普通控件轮廓。
- **浅色正文**（`text`）与**辅助蓝灰**（`muted`）：主要内容和说明、来源、表头。
- **白方浅色**、**和棋灰色**、**黑方深色**（`outcome-white`、`outcome-draw`、`outcome-black`）：仅用于历史白胜、和棋、黑胜比例，保留 Tailwind 的原生 OKLCH 值。

**The Source Color Rule.** 引擎证据和教练说明使用各自的颜色及文字来源；真人历史结果使用独立的白、灰、深色比例条。

## Typography

**Body Font:** 优先中文系统字体，使用 frontmatter 中的完整回退顺序。
**Label/Mono Font:** 中文标签沿用正文；棋谱和引擎数值使用等宽字体。

### Hierarchy
- **Title**：页面及应用标题，使用已有的小幅字号提升。
- **Body**：内容与状态说明；面板标题使用同一字号并加至半粗体（600）。连续解释采用较松行高（1.625）。
- **Label**：筛选标签、表头、比例、来源和辅助文字。
- **Notation**：常见走法中的 SAN 使用半粗等宽字；引擎数值按所在行的正文大小显示。统计数字启用等宽数字排列。

**The Written Meaning Rule.** 颜色旁保留可读文字；结果始终写出白胜、和棋、黑胜，不依赖用户推断条段含义。

## Layout

应用内容居中，最大宽度（80rem），左右留白（1rem）。现有复盘页在宽屏（64rem 起）分为棋盘区和说明区，窄屏按源码顺序堆叠。详情证据区在（40rem 起）可分为两列。

间距沿用四分之一 rem 的基础步长及常用半步：紧邻说明较紧，控件与表格留有辨认边界，面板内边距通常为 compact 或 panel。内容换行优先于裁掉标签。真人统计的具体位置、表格和筛选布局见局部说明，不把这一页的列宽推广为所有页面的规则。

## Elevation & Depth

已采样的分析容器依靠背景明度和细边框区分层级，不使用投影。引擎和教练内容分别使用同源颜色的浅透明底色及左边线（3px）。现有全局样式明确采用无渐变、无发光、无奖励动画的分析界面。

## Shapes

主要面板使用较圆的 panel 圆角；嵌套内容使用 soft-panel 圆角；按钮、筛选框和结果条使用较小的 control 圆角。标签保留胶囊形状。常规边框为细线（1px），表格用水平分隔线维持行的对应关系。

## Components

### Buttons
- 普通操作使用透明底、细轮廓和文字；真人统计的刷新按钮采用 frontmatter 的 outline 规格，悬停填入内层面板色。
- 禁用按钮降低透明度（0.5）并显示禁用指针。统计区域的交互元素有明确蓝色焦点轮廓（2px，外偏移 3px）。
- 连接 Lichess 是文字明确的边框链接，使用引擎蓝轮廓和浅蓝文字。它是授权状态下的操作，不是常驻主按钮。

### Inputs / Fields
- 原生选择框和月份输入框共用深色内层底色、细边框及完整宽度。标签保持可见，输入框允许在网格内收缩。
- 月份输入采用浏览器深色控件；错误提示出现在结果区域，保留用户选项。

### Chips
- 小型来源或概念标签采用胶囊边框、紧凑内边距和单行文字。
- 引擎与教练变体分别使用同源浅色文字和半透明边框，文字仍说明来源。

### Cards / Containers
- 外层面板组织独立信息，内层面板承接补充内容。引擎与教练内容保留各自左边线；不把每一行数据再套成卡片。

### Navigation
- 页首沿用文字链接和辅助色；悬停变亮。复盘动作仍围绕棋盘和选中着法展开，新统计面板不增加独立顶级导航。

### Historical Outcomes
- 比例条按白胜、和棋、黑胜从左到右，条段共享外框。数值文本保证比例在无颜色时仍可理解。
- 表格的每个走法均使用同一套纵向三行标签；整体样本的标签允许横向排列并换行。
- 样本量、使用率和结果比例各有明确位置，棋谱使用等宽字。详细分母、状态和移动端规则留在局部说明。

## Do's and Don'ts

### Do:
- **Do** 沿用深蓝容器及引擎蓝、教练金的来源含义。
- **Do** 在统计中同时呈现样本量、文字结果和比例条。
- **Do** 让同类走法行保持相同的结果顺序和排版。
- **Do** 保留表单标签与真人统计区域的键盘焦点。

### Don't:
- **Don't** 把真人历史结果渲染成引擎评分或教练判断。
- **Don't** 用颜色替代白胜、和棋、黑胜文字。
- **Don't** 为这一局部功能引入渐变、发光或奖励动画。

未纳入规范：旧棋盘／线路控件中的 Unicode 播放与方向图标，以及少数旧说明文字的 11px 特例；它们属于现存局部实现，不应成为新组件的图标或字号规则。
