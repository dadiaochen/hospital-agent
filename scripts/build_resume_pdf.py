from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "陈毅_大模型应用开发实习生_指标版.pdf"
PHOTO = ROOT / "output" / "resume" / "profile.png"
PAGE_SIZE = (810, 978.96)
FONT_DIR = Path("C:/Windows/Fonts")


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Deng", str(FONT_DIR / "Deng.ttf")))
    pdfmetrics.registerFont(TTFont("Deng-Bold", str(FONT_DIR / "Dengb.ttf")))
    pdfmetrics.registerFontFamily("Deng", normal="Deng", bold="Deng-Bold")


class SectionHeading(Flowable):
    def __init__(self, text: str, width: float = 746) -> None:
        super().__init__()
        self.text = text
        self.width = width
        self.height = 27

    def draw(self) -> None:
        canvas = self.canv
        canvas.setFillColor(colors.HexColor("#e7f0ff"))
        canvas.roundRect(0, 5, 18, 18, 5, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#2f6ecb"))
        canvas.setFont("Deng-Bold", 11)
        canvas.drawCentredString(9, 9, ">")
        canvas.setFillColor(colors.HexColor("#1f2937"))
        canvas.setFont("Deng-Bold", 13.5)
        canvas.drawString(26, 8, self.text)
        canvas.setStrokeColor(colors.HexColor("#8eb5ef"))
        canvas.setLineWidth(1.2)
        canvas.line(145, 14, self.width, 14)


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def header(canvas: Canvas, _: object) -> None:
    canvas.saveState()
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, PAGE_SIZE[0], PAGE_SIZE[1], fill=1, stroke=0)

    if PHOTO.exists():
        canvas.drawImage(
            ImageReader(str(PHOTO)),
            32,
            858,
            width=74,
            height=99,
            preserveAspectRatio=True,
            anchor="sw",
            mask="auto",
        )
    canvas.setStrokeColor(colors.HexColor("#d6e0ed"))
    canvas.setLineWidth(1)
    canvas.roundRect(32, 858, 74, 99, 5, fill=0, stroke=1)

    canvas.setFillColor(colors.HexColor("#111827"))
    canvas.setFont("Deng-Bold", 30)
    canvas.drawString(120, 914, "陈毅")
    canvas.setFont("Deng-Bold", 15)
    canvas.setFillColor(colors.HexColor("#26364d"))
    canvas.drawString(235, 921, "求职意向：AI Agent / 大模型应用开发实习生")

    contact_boxes = [
        (120, 850, 132, "电话  136-4223-9080"),
        (259, 850, 225, "邮箱  1002325739@qq.com"),
        (491, 850, 175, "微信  cheny020309"),
    ]
    for x, y, width, text in contact_boxes:
        canvas.setFillColor(colors.HexColor("#f7faff"))
        canvas.setStrokeColor(colors.HexColor("#d6e0ed"))
        canvas.roundRect(x, y, width, 26, 5, fill=1, stroke=1)
        canvas.setFillColor(colors.HexColor("#344256"))
        canvas.setFont("Deng", 10.5)
        canvas.drawString(x + 9, y + 8, text)

    canvas.setStrokeColor(colors.HexColor("#1f2937"))
    canvas.setLineWidth(2)
    canvas.line(32, 833, 778, 833)
    canvas.restoreState()


def build_story() -> list[Flowable]:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontName="Deng",
        fontSize=10.8,
        leading=14.4,
        textColor=colors.HexColor("#273244"),
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    body_small = ParagraphStyle(
        "body-small",
        parent=body,
        fontSize=10.2,
        leading=13.5,
    )
    body_bold = ParagraphStyle(
        "body-bold",
        parent=body,
        fontName="Deng-Bold",
    )
    intro = ParagraphStyle(
        "intro",
        parent=body,
        fontSize=10.6,
        leading=14.1,
        spaceAfter=2,
    )
    bullet = ParagraphStyle(
        "bullet",
        parent=body,
        leftIndent=11,
        firstLineIndent=-10,
        fontSize=10.05,
        leading=13.8,
        spaceAfter=2.6,
    )
    section_gap = Spacer(1, 2)
    story: list[Flowable] = []

    story.append(SectionHeading("教育经历"))
    education = Table(
        [
            [
                paragraph("<b>华南农业大学</b>　计算机技术 硕士", body),
                paragraph("绩点：3.8 / 4.0", body),
                paragraph("2025.09 - 2028.06", body_bold),
            ],
            [
                paragraph("<b>江苏科技大学苏州理工学院</b>　本科", body),
                paragraph("担任班长", body),
                paragraph("2020.09 - 2024.06", body_bold),
            ],
        ],
        colWidths=[350, 180, 216],
    )
    education.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d6e0ed")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e4eaf3")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([education, section_gap, SectionHeading("专业技能")])

    skills = Table(
        [
            [
                paragraph(
                    "• 熟悉 <b>Python、FastAPI、MySQL / PostgreSQL</b>，可完成 API 分层、业务逻辑封装、ORM / 迁移和接口联调。<br/>"
                    "• 熟悉 <b>Prompt Engineering、RAG、Function Calling / Tool Calling</b>，了解知识库构建、工具 schema、结构化输出与来源追踪。<br/>"
                    "• 了解 <b>Dify、LangGraph、Agent 工作流</b>，关注任务拆解、状态流转、上下文隔离、人工确认与失败降级。<br/>"
                    "• 了解 <b>Tool Registry、Agent Run / Tool Call Trace、deterministic evaluation</b>，能基于固定用例做回放和回归。<br/>"
                    "• 熟悉 <b>Claude Code、Codex</b> 等 AI Coding 工具，了解 PyTorch / YOLO 模型服务化流程。",
                    body_small,
                )
            ]
        ],
        colWidths=[746],
    )
    skills.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d6e0ed")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([skills, section_gap, SectionHeading("实习经历")])

    story.append(paragraph("<b>健缘医疗互联网医院｜AI 应用开发实习生</b>　2025.05 - 2025.08", body_bold))
    story.append(
        paragraph(
            "基于互联网医院现有业务流程开展 AI 化改造，负责 Dify 医疗 Agent 原型设计与对话效果优化，并完成与原有系统数据结构及接口逻辑的衔接。",
            intro,
        )
    )
    story.append(
        paragraph(
            "<b>1.</b> 围绕公司原有的问诊、复诊和购药业务，使用 Dify 搭建患者端医疗 Agent，并扩展报告解读场景，将分散的医疗服务整合为统一对话入口，完成 Agent 原型设计与流程验证。",
            bullet,
        )
    )
    story.append(
        paragraph(
            "<b>2.</b> 构建患者服务流程知识库，并根据实际对话整理意图识别、场景分流和回答完整性等 bad case，持续优化提示词与工作流节点，提升回复稳定性。",
            bullet,
        )
    )

    story.extend([section_gap, SectionHeading("项目经历")])
    story.append(paragraph("<b>家庭健康服务 Multi-Agent 系统</b>", body_bold))
    story.append(
        paragraph(
            "面向互联网医院慢病续方、家庭药箱、用药提醒与安全确认场景，使用 Python 重构可追踪的家庭健康服务 Agent；当前版本以 deterministic + mock 完成本地演示，不接入真实医院或药店。",
            intro,
        )
    )
    story.append(paragraph("<b>技术栈：Python、FastAPI、LangGraph、PostgreSQL</b>", body))
    project_bullets = [
        "<b>• Multi-Agent 编排：</b>使用 LangGraph 实现有界工作流，由 Planner 按用户意图和家庭成员生成结构化计划，路由 Profile、Refill、Pharmacy、Reminder 和 Safety 角色；通过成员级最小上下文视图防止处方、药箱和安全信息串扰。",
        "<b>• 工具与事实溯源：</b>通过 Tool Registry 统一校验输入输出 schema、角色权限、超时重试和人工确认要求，串联档案、处方、药箱、库存和安全知识查询；运行轨迹保留工具证据与 RAG 来源。",
        "<b>• 安全与确认：</b>使用 Agent 安全拦截停药、加量、减量、换药、严重症状、越权访问和跳过确认等风险；关键动作只生成本地待确认草稿，不自动开方、修改处方或提交外部系统。",
        "<b>• Agent 评测：</b>构建覆盖 16 条固定场景的确定性 Harness，基于 RunTrace 回放检查工具覆盖、来源支撑、安全标记、确认状态和成员隔离；必需工具覆盖率 98.8%，高风险规则召回率 93.8%，成员隔离通过率 93.8%，关键事实来源覆盖率 93.8%。",
        "<b>• 运行与审计：</b>实现 Agent Run / Tool Call 记录、失败原因、幂等请求、确认后的同任务续跑和前端 Trace 展示；当前指标为本地固定用例流程指标，不代表线上模型答案正确率、人工采纳率、token 成本或真实响应延迟。",
    ]
    story.extend(paragraph(item, bullet) for item in project_bullets)

    story.extend([section_gap, paragraph("<b>农作物害虫检测小程序与模型服务化</b>", body_bold)])
    story.append(
        paragraph(
            "面向黄板图像中害虫目标小、密集重叠且易受背景干扰的问题，负责检测模型优化与算法服务接入，为原有业务系统提供害虫识别能力。",
            intro,
        )
    )
    story.append(paragraph("<b>技术栈：Python、PyTorch、YOLOv26、FastAPI、OpenCV</b>", body))
    pest_bullets = [
        "<b>• 模型优化：</b>针对微小害虫漏检和定位不准的问题，改进 YOLOv26 的小目标特征提取、多尺度特征融合和定位损失，模型 mAP50、50:95 较基线分别提升 0.9%、2.7%，相关成果形成论文，EAAI 在投中。",
        "<b>• 服务化：</b>使用 FastAPI 封装 Python 推理服务，统一模型输入与输出格式，返回检测结果并可视化，完成算法服务接入、前后端联调及部署文档迭代。",
        "<b>• 性能优化：</b>将模型加载和预热移至服务启动阶段，避免每次请求重复初始化，使单张图片接口响应时间由 5.26s 降至 88ms。",
    ]
    story.extend(paragraph(item, bullet) for item in pest_bullets)
    story.append(
        paragraph(
            '项目地址：<link href="https://github.com/dadiaochen/pest-detection-mini-program/tree/master" color="#2f6ecb">github.com/dadiaochen/pest-detection-mini-program</link>',
            body_small,
        )
    )
    return story


def main() -> None:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=PAGE_SIZE,
        leftMargin=32,
        rightMargin=32,
        topMargin=145,
        bottomMargin=28,
        title="陈毅 - AI Agent / 大模型应用开发实习生简历",
        author="陈毅",
    )
    document.build(build_story(), onFirstPage=header, onLaterPages=header)
    print(OUTPUT)


if __name__ == "__main__":
    main()
