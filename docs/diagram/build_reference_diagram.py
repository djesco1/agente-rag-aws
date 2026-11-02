"""Genera docs/architecture_aws.png con estilo de arquitectura de referencia de AWS
(íconos oficiales de servicio, grupos AWS Cloud / Región, pasos numerados y leyenda).

Requiere: pip install diagrams playwright  (usa los íconos oficiales que trae `diagrams`).
Uso (desde la raíz del repo): python docs/diagram/build_reference_diagram.py
"""
import base64
import os
from pathlib import Path

import diagrams

ROOT = Path(__file__).resolve().parents[2]
ICONS = Path(os.path.dirname(diagrams.__file__)).parent / "resources" / "aws"


def icon(rel: str) -> str:
    return "data:image/png;base64," + base64.b64encode((ICONS / rel).read_bytes()).decode()


I = {
    "user": icon("general/user.png"),
    "lambda": icon("compute/lambda.png"),
    "bedrock": icon("ml/bedrock.png"),
    "s3": icon("storage/simple-storage-service-s3.png"),
    "ddb": icon("database/dynamodb.png"),
    "cw": icon("management/cloudwatch.png"),
    "ssm": icon("management/systems-manager.png"),
    "iam": icon("security/identity-and-access-management-iam.png"),
}

W, H = 1480, 870
# Centros de los íconos (x, y). Tamaño de ícono: 64 px.
P = {
    "user": (95, 420),
    "lambda": (420, 420),
    "bedrock": (420, 175),
    "s3": (845, 170),
    "s3v": (845, 340),
    "ddbr": (845, 510),
    "ddbh": (845, 680),
    "cw": (280, 700),
    "ssm": (420, 700),
    "iam": (560, 700),
}
S = 64
h = S // 2


def node(key, title, sub="", side="below"):
    x, y = P[key]
    img = I[{"s3v": "s3", "ddbr": "ddb", "ddbh": "ddb"}.get(key, key)]
    if side == "left":
        lab = f'<div class="lab" style="left:{x - h - 214}px;top:{y - 26}px;text-align:right;width:200px"><b>{title}</b><br>{sub}</div>'
    elif side == "right":
        lab = f'<div class="lab" style="left:{x + h + 14}px;top:{y - 26}px;text-align:left;width:200px"><b>{title}</b><br>{sub}</div>'
    else:
        wd = 136 if key in ("cw", "ssm", "iam") else 200
        lab = f'<div class="lab" style="left:{x - wd // 2}px;top:{y + h + 8}px;width:{wd}px"><b>{title}</b><br>{sub}</div>'
    return f'<img src="{img}" style="position:absolute;left:{x - h}px;top:{y - h}px;width:{S}px;height:{S}px">' + lab


def badge(x, y, t, kind="q"):
    return f'<div class="badge {kind}" style="left:{x - 12}px;top:{y - 12}px">{t}</div>'


lx, ly = P["lambda"]
ORANGE, BLUE, GRAY = "#232F3E", "#1A73E8", "#7D8998"

paths = [
    # usuario -> lambda
    (f"M{P['user'][0] + h + 6},{ly} H{lx - h - 6}", ORANGE, ""),
    # lambda -> bedrock (embeddings + LLM)
    (f"M{lx},{ly - h - 6} V{P['bedrock'][1] + h + 6}", ORANGE, ""),
    # lambda -> S3 documentos (ingesta)
    (f"M{lx + h + 6},{ly - 20} H610 V{P['s3'][1]} H{P['s3'][0] - h - 6}", BLUE, "dash"),
    # lambda <-> S3 Vectors (consulta + ingesta)
    (f"M{lx + h + 6},{ly - 7} H650 V{P['s3v'][1]} H{P['s3v'][0] - h - 6}", ORANGE, ""),
    # lambda -> DynamoDB solicitudes (herramientas)
    (f"M{lx + h + 6},{ly + 7} H730 V{P['ddbr'][1]} H{P['ddbr'][0] - h - 6}", ORANGE, ""),
    # lambda -> DynamoDB historial
    (f"M{lx + h + 6},{ly + 20} H690 V{P['ddbh'][1]} H{P['ddbh'][0] - h - 6}", ORANGE, ""),
    # lambda -> SSM
    (f"M{lx},{ly + h + 52} V{P['ssm'][1] - h - 6}", GRAY, ""),
    # lambda -> CloudWatch
    (f"M{lx - 20},{ly + h + 52} V600 H{P['cw'][0]} V{P['cw'][1] - h - 6}", GRAY, ""),
    # IAM -> lambda (rol)
    (f"M{P['iam'][0]},{P['iam'][1] - h - 6} V600 H{lx + 20} V{ly + h + 54}", GRAY, "dot"),
]


def svg_paths():
    out = []
    for d, color, style in paths:
        dash = 'stroke-dasharray="7 5"' if style == "dash" else ('stroke-dasharray="2 4"' if style == "dot" else "")
        mid = {"#232F3E": "a1", "#1A73E8": "a2", "#7D8998": "a3"}[color]
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" {dash} marker-end="url(#{mid})"/>')
    return "\n".join(out)


legend_q = [
    ("1", "El usuario envía la pregunta a la <b>Function URL</b> (HTTPS) con la cabecera <code>X-API-Key</code>."),
    ("2", "La Lambda valida la API key (<b>SSM Parameter Store</b>), la entrada y el guardrail de prompt injection."),
    ("3", "<b>Titan Embeddings V2</b> vectoriza la pregunta y <b>S3 Vectors</b> devuelve los fragmentos más similares (top-k)."),
    ("4", "<b>Nova Lite</b> (Converse API) responde con citas; el agente usa herramientas que consultan <b>DynamoDB</b>."),
    ("5", "La traza (fuentes, herramientas, tokens, latencia) se guarda en <b>DynamoDB</b> y los logs JSON en <b>CloudWatch</b>."),
]
legend_i = [
    ("A", "<code>POST /documents</code>: el original se guarda en <b>Amazon S3</b>."),
    ("B", "Chunking por secciones y embeddings con <b>Titan V2</b> (1024 dimensiones)."),
    ("C", "Los vectores y su metadata se indexan en <b>S3 Vectors</b> (coseno)."),
]


def legend():
    rows = "".join(f'<div class="lrow"><span class="badge q inl">{n}</span><span>{t}</span></div>' for n, t in legend_q)
    rows_i = "".join(f'<div class="lrow"><span class="badge i inl">{n}</span><span>{t}</span></div>' for n, t in legend_i)
    return f"""<div class="legend">
<div class="lt">Consulta · <code>POST /ask</code></div>{rows}
<div class="lt" style="margin-top:18px">Ingesta · <code>POST /documents</code></div>{rows_i}
<div class="lkey"><svg width="40" height="10"><line x1="0" y1="5" x2="40" y2="5" stroke="#232F3E" stroke-width="2"/></svg> consulta
&nbsp;&nbsp;<svg width="40" height="10"><line x1="0" y1="5" x2="40" y2="5" stroke="#1A73E8" stroke-width="2" stroke-dasharray="7 5"/></svg> ingesta
&nbsp;&nbsp;<svg width="40" height="10"><line x1="0" y1="5" x2="40" y2="5" stroke="#7D8998" stroke-width="2"/></svg> operación</div>
</div>"""


html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#fff;font-family:'Amazon Ember','Helvetica Neue',Arial,sans-serif;color:#232F3E}}
#c{{position:relative;width:{W}px;height:{H}px;background:#fff}}
.grp{{position:absolute;border:1.5px solid #232F3E}}
.grp .gl{{position:absolute;top:-1px;left:-1px;background:#232F3E;color:#fff;font-size:13px;font-weight:700;padding:5px 10px}}
.reg{{position:absolute;border:1.5px dashed #00A4A6}}
.reg .gl{{position:absolute;top:6px;left:10px;color:#00A4A6;font-size:13px;font-weight:700}}
.sub{{position:absolute;border:1.5px solid #ED7100;background:#FFF8F1;border-radius:2px}}
.sub .gl{{position:absolute;top:6px;left:10px;color:#C25A00;font-size:12.5px;font-weight:700}}
.box{{position:absolute;border:1px solid #C6CDD5;background:#FAFBFC}}
.box .gl{{position:absolute;top:6px;left:10px;color:#545B64;font-size:12px;font-weight:700;letter-spacing:.3px;text-transform:uppercase}}
.lab{{position:absolute;font-size:12.5px;line-height:1.35;text-align:center;color:#232F3E}}
.lab b{{font-weight:700}}
.badge{{position:absolute;width:24px;height:24px;border-radius:50%;color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 2px #fff}}
.badge.q{{background:#232F3E}} .badge.i{{background:#1A73E8}}
.badge.inl{{position:static;flex:0 0 24px;margin-right:10px}}
.legend{{position:absolute;left:1010px;top:40px;width:430px;font-size:13px;line-height:1.45}}
.lt{{font-weight:700;font-size:14px;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #FF9900}}
.lrow{{display:flex;align-items:flex-start;margin:7px 0}}
.lkey{{margin-top:22px;font-size:12px;color:#545B64;display:flex;align-items:center;gap:6px}}
code{{font-family:Menlo,Consolas,monospace;font-size:11.5px;background:#F2F3F3;padding:1px 4px;border-radius:3px}}
.title{{position:absolute;left:1010px;top:{H - 92}px;width:430px;font-size:12px;color:#545B64;line-height:1.5}}
.edge{{position:absolute;font-size:11.5px;color:#545B64;background:#fff;padding:0 4px}}
</style></head><body><div id="c">
<div class="grp" style="left:190px;top:30px;width:790px;height:{H - 60}px"><div class="gl">AWS Cloud</div></div>
<div class="reg" style="left:212px;top:72px;width:746px;height:{H - 124}px"><div class="gl">Región us-east-1 (N. Virginia)</div></div>
<div class="sub" style="left:300px;top:330px;width:240px;height:190px"><div class="gl">AWS Lambda · ic7-rag-agent</div></div>
<div class="box" style="left:760px;top:105px;width:180px;height:{H - 175}px"><div class="gl">Datos</div></div>
<div class="box" style="left:226px;top:622px;width:410px;height:190px"><div class="gl" style="top:auto;bottom:6px">Seguridad y operación</div></div>
<svg width="{W}" height="{H}" style="position:absolute;left:0;top:0">
<defs>
<marker id="a1" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#232F3E"/></marker>
<marker id="a2" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#1A73E8"/></marker>
<marker id="a3" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#7D8998"/></marker>
</defs>
{svg_paths()}
</svg>
{node("user", "Usuario", "Swagger UI · curl")}
{node("lambda", "FastAPI + Mangum", "guardrails · RAG · agente")}
{node("bedrock", "Amazon Bedrock", "Nova Lite (LLM + tool use)<br>Titan Text Embeddings V2", side="left")}
{node("s3", "Amazon S3", "documentos originales")}
{node("s3v", "Amazon S3 Vectors", "docs-index · coseno · 1024")}
{node("ddbr", "Amazon DynamoDB", "solicitudes (herramientas)")}
{node("ddbh", "Amazon DynamoDB", "historial / trazabilidad")}
{node("cw", "CloudWatch Logs", "JSON · trace_id")}
{node("ssm", "Parameter Store", "API key cifrada")}
{node("iam", "AWS IAM", "mínimo privilegio")}
<div class="edge" style="left:150px;top:{ly - 30}px">Function URL · HTTPS</div>
{badge(250, ly, "1")}
{badge(lx - 32, 300, "B", "i")}
{badge(lx, 300, "3")}
{badge(lx + 32, 300, "4")}
{badge(P['s3'][0] - h - 34, P['s3'][1], "A", "i")}
{badge(650, P['s3v'][1] + 40, "3")}
{badge(P['s3v'][0] - h - 34, P['s3v'][1], "C", "i")}
{badge(P['ddbr'][0] - h - 34, P['ddbr'][1], "4")}
{badge(P['ddbh'][0] - h - 34, P['ddbh'][1], "5")}
{badge(lx, 582, "2")}
{badge(330, 600, "5")}
{legend()}
<div class="title"><b>Agente RAG empresarial en AWS</b><br>Serverless · pago por uso · sin servidores que administrar.<br>Todas las llamadas a servicios usan el rol IAM de la Lambda (sin llaves estáticas).</div>
</div></body></html>"""

out_html = ROOT / "build" / "architecture_reference.html"
out_html.parent.mkdir(exist_ok=True)
out_html.write_text(html, encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
    pg.goto(out_html.as_uri())
    pg.locator("#c").screenshot(path=str(ROOT / "docs" / "architecture_aws.png"))
    b.close()
print("ok")
