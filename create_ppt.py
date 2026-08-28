"""Create a one-page PPT for Maxwell Project Management System."""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

prs = Presentation()
prs.slide_width = Inches(13.333)  # 16:9 widescreen
prs.slide_height = Inches(7.5)

slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout

# ═══ Background: gradient effect using shapes ═══
# Top dark band
top_band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(2.2))
top_band.fill.solid()
top_band.fill.fore_color.rgb = RGBColor(0x0F, 0x1B, 0x33)
top_band.line.fill.background()

# Accent line under header
accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(11.733), Inches(0.04))
accent.fill.solid()
accent.fill.fore_color.rgb = RGBColor(0x3B, 0x82, 0xF6)
accent.line.fill.background()

# ═══ Title ═══
title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.35), Inches(11.7), Inches(0.8))
tf = title_box.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "麦科斯韦项目管理系统"
p.font.size = Pt(40)
p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
p.font.bold = True
p.alignment = PP_ALIGN.LEFT

# Subtitle
sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.2), Inches(11.7), Inches(0.6))
tf = sub_box.text_frame
p = tf.paragraphs[0]
p.text = "利用AI工具 Claude 搭建 | 15大功能模块 | 全链路研发管理平台"
p.font.size = Pt(18)
p.font.color.rgb = RGBColor(0x93, 0xC5, 0xFD)
p.alignment = PP_ALIGN.LEFT

# ═══ Module cards - 5 rows x 2 columns ═══
modules = [
    ("📊 驾驶舱", "项目全局数据可视化", "dashboard"),
    ("📦 产品技术库", "储存历史产品/电机/电控数据", "product"),
    ("🔧 BOM管理", "存储历史BOM · 版本对比 · 成本估算", "bom"),
    ("📋 项目管理", "项目台账 · 阶段门径 · 团队协作", "project"),
    ("⏱ 任务与里程碑", "甘特图 · 里程碑全景 · 进度追踪", "task"),
    ("⚠ 问题风险管理", "风险登记 · 变更管理 · 问题追踪", "risk"),
    ("📄 报告中心", "周报生成 · 报表导出 · 管理层报告", "report"),
    ("🤖 AI助手", "智能问答 · 自动诊断 · 知识提取", "ai"),
    ("📚 知识库", "文档管理 · AI搜索 · 知识图谱 · 问答", "kb"),
    ("👥 客户管理", "客户档案 · 协同门户 · 访问授权", "client"),
]

card_w = Inches(5.5)
card_h = Inches(0.78)
start_x_left = Inches(0.8)
start_x_right = Inches(7.0)
start_y = Inches(2.6)
gap_y = Inches(0.12)

colors = [
    (RGBColor(0x3B, 0x82, 0xF6), RGBColor(0xEF, 0xF6, 0xFF)),  # blue
    (RGBColor(0x10, 0xB9, 0x81), RGBColor(0xEC, 0xFD, 0xF5)),  # green
    (RGBColor(0xF5, 0x9E, 0x0B), RGBColor(0xFF, 0xFB, 0xEB)),  # amber
    (RGBColor(0x8B, 0x5C, 0xF6), RGBColor(0xF5, 0xF3, 0xFF)),  # purple
    (RGBColor(0xEF, 0x44, 0x44), RGBColor(0xFE, 0xF2, 0xF2)),  # red
]

for i, (title, desc, key) in enumerate(modules):
    col = i % 2
    row = i // 2
    x = start_x_left if col == 0 else start_x_right
    y = start_y + row * (card_h + gap_y)
    color_idx = i % len(colors)
    accent_c, bg_c = colors[color_idx]

    # Card background
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h)
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
    card.line.width = Pt(0.5)
    card.shadow.inherit = False

    # Left accent bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.12), Inches(0.06), card_h - Inches(0.24))
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent_c
    bar.line.fill.background()

    # Icon circle
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.22), y + Inches(0.19), Inches(0.4), Inches(0.4))
    circle.fill.solid()
    circle.fill.fore_color.rgb = accent_c
    circle.line.fill.background()
    # Icon text
    ctf = circle.text_frame
    ctf.word_wrap = False
    cp = ctf.paragraphs[0]
    cp.text = str(i + 1)
    cp.font.size = Pt(14)
    cp.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    cp.font.bold = True
    cp.alignment = PP_ALIGN.CENTER

    # Title text
    t_box = slide.shapes.add_textbox(x + Inches(0.75), y + Inches(0.1), Inches(3.2), Inches(0.35))
    tf = t_box.text_frame
    tp = tf.paragraphs[0]
    tp.text = title
    tp.font.size = Pt(14)
    tp.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
    tp.font.bold = True

    # Description text
    d_box = slide.shapes.add_textbox(x + Inches(0.75), y + Inches(0.42), Inches(4.5), Inches(0.3))
    tf = d_box.text_frame
    dp = tf.paragraphs[0]
    dp.text = desc
    dp.font.size = Pt(10)
    dp.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

# ═══ Bottom bar ═══
btm = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(7.1), prs.slide_width, Inches(0.4))
btm.fill.solid()
btm.fill.fore_color.rgb = RGBColor(0x0F, 0x1B, 0x33)
btm.line.fill.background()

# Bottom text
btm_box = slide.shapes.add_textbox(Inches(0.8), Inches(7.12), Inches(11.7), Inches(0.35))
tf = btm_box.text_frame
p = tf.paragraphs[0]
p.text = "Maxwell Motor | 电机集成研发项目管理平台 · v2.0 EasyTrack Edition · 本地部署 + AI驱动"
p.font.size = Pt(10)
p.font.color.rgb = RGBColor(0x93, 0xC5, 0xFD)
p.alignment = PP_ALIGN.LEFT

# ═══ Right side: AI badge ═══
badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.8), Inches(1.45), Inches(2.0), Inches(0.5))
badge.fill.solid()
badge.fill.fore_color.rgb = RGBColor(0x1D, 0x4E, 0xD8)
badge.line.fill.background()
btf = badge.text_frame
bp = btf.paragraphs[0]
bp.text = "Claude AI 驱动"
bp.font.size = Pt(12)
bp.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
bp.font.bold = True
bp.alignment = PP_ALIGN.CENTER

# ═══ Save ═══
output_path = os.path.expanduser("~/Desktop/麦科斯韦项目管理系统.pptx")
prs.save(output_path)
print(f"PPT saved to: {output_path}")
