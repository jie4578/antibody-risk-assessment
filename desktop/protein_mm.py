"""C.2A application boundary, display-only graphics and explicit local reports.

No SQL shortcut, alternative fitting, parameter intervals, ML or network calls.
"""
from copy import deepcopy
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

from protein_engineering.initial_rate import digest
from protein_engineering.mm_rate_adapter import load_rate_records
from protein_engineering.mm_kinetics import ALGORITHM_VERSION, fit_michaelis_menten, input_digest
from protein_engineering.migrations import APPLICATION_ID
from protein_engineering.rate_storage import RateStorage
from desktop.protein_snapshot import isolated_source,STRATEGY


LIMITATIONS = (
    "C.1 initial_rate_validity=NOT_ESTABLISHED；人工确认不证明初始速率成立。",
    "经典单底物 Michaelis–Menten 条件性无权重拟合；收敛和高 R² 不证明机制成立。",
    "本报告不含参数置信区间、预测区间、完整实验误差传播、kcat 或 WT/变体优劣比较。",
    "技术重复逐条保留；未确认生物学独立性，不自动合并、删点或选择最佳子集。",
    "SHA256 核对内容一致性，不是实验真实性认证或审阅人电子签名。",
)


def strict_copy(value):
    return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True))


@contextmanager
def _copy_connection(database):
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=3:
            raise ValueError("只读目录仅接受本模块既有 v3 数据库")
        if any(row[0]!='ok' for row in db.execute('PRAGMA quick_check')):
            raise ValueError('COPY_INTEGRITY_CHECK_FAILED')
        yield db


@contextmanager
def _read_connection(path):
    with isolated_source(path) as snapshot:
        with _copy_connection(snapshot.copy) as db:yield db


class _SavedRateCatalog(RateStorage):
    """Reuse C.1's catalog reader with a read-only connection, never ProteinStore."""
    def __init__(self,path):self.path=path
    def _connection(self):return _read_connection(self.path)


def list_saved_rates(path):
    # Listing is unverified display only; it cannot produce a RateRecord for fitting.
    return _SavedRateCatalog(path).initial_rate_records()


def _audit_records(path,identifiers):
    with isolated_source(path) as snapshot:
        with _copy_connection(snapshot.copy):
            records=load_rate_records(snapshot.copy,tuple(identifiers))
    return records,snapshot.sha256,snapshot.identity


def _file_digest(stream):
    value=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def numerical_dependencies():
    """Explicit worker-side probe; importing the page never imports SciPy."""
    try:
        import numpy
        import scipy
        from scipy.optimize import least_squares
        if not callable(least_squares):
            raise ImportError("SciPy least_squares 不可用")
        return dict(available=True, numpy=numpy.__version__, scipy=scipy.__version__)
    except (ImportError, OSError, RuntimeError) as exc:
        return dict(available=False, message="缺少或无法加载 SciPy/NumPy 数值依赖；C.2A 不可用，数据管理/C.1 仍可使用。" + str(exc))


def sources_summary(records):
    """Minimized lineage: no variant sequence, raw file bytes or free-text extras."""
    rows = []
    for r in records:
        c1 = r.c1_result if hasattr(r, "c1_result") else r["c1_result"]
        ident = r.analysis_id if hasattr(r, "analysis_id") else r["analysis_id"]
        variant = r.variant_id if hasattr(r, "variant_id") else r["variant_id"]
        conditions = r.conditions if hasattr(r, "conditions") else r["conditions"]
        provenance = r.provenance if hasattr(r, "provenance") else r["provenance"]
        d, m = c1["derived_initial_rate"], c1["analysis_metadata"]
        rows.append(dict(analysis_id=ident, variant_id=variant, sample_id=d["sample_id"], batch_id=d["batch_id"],
            biological_replicate=d["biological_replicate"], technical_replicate=d["technical_replicate"],
            wells=sorted({o["well_id"] for o in c1["raw_observations"]}),
            substrate=d["substrate_concentration"], substrate_unit=d["substrate_concentration_unit"],
            rate=d["product_rate"], conditions=conditions, c1_input_sha256=m["input_sha256"],
            c1_fingerprint=m["analysis_fingerprint"], initial_rate_validity=m["initial_rate_validity"],
            calibration=m["calibration"], observation_ids=[o["observation_id"] for o in c1["raw_observations"]],
            source_sha256=sorted({o["source_sha256"] for o in c1["raw_observations"]+c1["blank_observations"]}),
            identity_sources=[{k:p[k] for k in ("import_id","filename","sheet","source_row","source_sha256") if k in p}
                for item in provenance.get("identity_and_observation_records",[]) for p in [item["provenance"]]],
            quality_control=c1["quality_control"]))
    return strict_copy(rows)


def verify_selection(path, identifiers):
    records,database_sha256,identity = _audit_records(path, identifiers)
    return dict(ids=[r.analysis_id for r in records], input_sha256=input_digest(records),
        database_sha256=database_sha256,database_identity=list(identity),source_strategy=STRATEGY,
        sources=sources_summary(records), dependencies=numerical_dependencies())


def _current_records(path, identifiers, expected, database_sha256,source_identity=None):
    records,current_database_sha256,identity = _audit_records(path, identifiers)
    if (current_database_sha256 != database_sha256 or input_digest(records) != expected
            or source_identity is not None and tuple(source_identity)!=identity):
        raise ValueError("来源/输入摘要已变化；旧审核失效，请重新核验。")
    return records


def checked_result(result, expected=None):
    value = strict_copy(result)
    meta = value["metadata"]
    fingerprint = meta.pop("result_sha256")
    if digest(value) != fingerprint:
        raise ValueError("C.2A 结果摘要不一致")
    meta["result_sha256"] = fingerprint
    actual = digest(sorted(value["input_records"], key=lambda r:r["analysis_id"]))
    if (meta["algorithm_version"] != ALGORITHM_VERSION or actual != meta["input_sha256"]
            or value["review"]["input_sha256"] != actual or expected is not None and actual != expected):
        raise ValueError("C.2A 输入、版本或审核摘要不一致")
    return value


def run_fit(path, identifiers, expected, review, database_sha256,source_identity=None):
    records = _current_records(path, identifiers, expected, database_sha256,source_identity)
    dependencies = numerical_dependencies()
    if not dependencies["available"]:
        raise ValueError(dependencies["message"])
    result = checked_result(fit_michaelis_menten(records, deepcopy(review)), expected)
    # Recheck the acquired bytes and links before publishing a long-running fit.
    _current_records(path, identifiers, expected, database_sha256,source_identity)
    return result


def chart_geometry(result, width=900, height=300):
    """Display only: use the kernel estimates; never refit or invent observations."""
    if not result or result["status"] != "FIT_WITH_LIMITATIONS":
        return []
    p, points = result["parameters"], result["predictions"]
    xs = [r["substrate_concentration"] for r in points]
    low, high = min(xs), max(xs)
    if high <= low:
        return []
    curve = []
    for i in range(121):
        s = low + (high-low)*(i/120)
        scale = max(s,p["Km"])
        v = p["Vmax"] * ((s/scale)/(p["Km"]/scale+s/scale))
        curve.append((s,v))
    plots = []
    for index, key in enumerate(("observed_rate","residual")):
        observed = [(r["substrate_concentration"],r[key]) for r in points]
        line = curve if index == 0 else [(low,0.),(high,0.)]
        values = [v for _,v in observed+line]
        bottom, top = min(values), max(values)
        if top == bottom:
            padding = max(abs(top)*.1,1e-12)
        else:
            padding = (top-bottom)*.08
        bottom -= padding; top += padding
        left = index*width/2+65; right = (index+1)*width/2-24
        y0,y1 = 40,height-57
        def position(pair):
            x,y = pair
            return [left+(x-low)/(high-low)*(right-left),y1-(y-bottom)/(top-bottom)*(y1-y0)]
        plot = dict(title="观察速率与 MM 模型线" if index==0 else "残差（观察 − 拟合）",
            x_label="底物 / "+p["Km_unit"], y_label=p["Vmax_unit"],
            rectangle=[left,y0,right,y1], scatter=[position(v) for v in observed], line=[position(v) for v in line],
            x_range=[low,high],y_range=[bottom,top])
        strict_copy(plot)
        plots.append(plot)
    return plots


def chart_svg(result):
    plots = chart_geometry(result)
    if not plots:
        return "<p>没有可展示的正常拟合曲线。</p>"
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 300" role="img" aria-label="拟合与残差">']
    for q in plots:
        l,t,r,b=q["rectangle"]
        out.append(f'<path d="M {l} {t} V {b} H {r}" fill="none" stroke="#555"/>')
        out.append('<polyline points="'+" ".join(f"{x:.8g},{y:.8g}" for x,y in q["line"])
            +'" fill="none" stroke="#176b9c" stroke-width="2"/>')
        out.extend(f'<circle cx="{x:.8g}" cy="{y:.8g}" r="3" fill="#b65320"/>' for x,y in q["scatter"])
        for x,y,text in [(l,22,q["title"]),(l,b+40,q["x_label"]),(l,t-6,q["y_label"]),
                (l,b+17,f'{q["x_range"][0]:.5g}'),(r-45,b+17,f'{q["x_range"][1]:.5g}'),
                (l-61,t+12,f'{q["y_range"][1]:.5g}'),(l-61,b,f'{q["y_range"][0]:.5g}')]:
            out.append(f'<text x="{x:.8g}" y="{y:.8g}" font-size="11">{escape(text)}</text>')
    return "".join(out)+"</svg>"


def report_payload(result, database_sha256,source_identity=None):
    result = checked_result(result)
    payload = dict(format="protein-c2a-report-1", generated_at_utc=datetime.now(timezone.utc).isoformat(),
        calculation={k:result[k] for k in ("status","parameters","predictions","statistics","optimizer","diagnostics","quality_control","reasons")},
        review=result["review"], metadata=result["metadata"], source_summary=sources_summary(result["input_records"]),
        source_database_sha256=database_sha256,
        source_access_strategy=STRATEGY,
        source_database_identity=source_identity,
        limitations=list(LIMITATIONS), intervals="NOT_CALCULATED",
        native_result_sha256_scope="Complete in-memory C.2A result, including input_records; not a hash of this minimized report.",
        privacy="Local minimized report: no complete sequences or acquired source file bytes included.")
    payload = strict_copy(payload)
    return dict(payload=payload, report_sha256=digest(payload))


def render_html(report, result):
    p = report["payload"]
    def pre(value):
        return "<pre>"+escape(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))+"</pre>"
    def table(headers,rows):
        return "<table><thead><tr>"+"".join("<th>"+escape(str(x))+"</th>" for x in headers)+"</tr></thead><tbody>"+"".join(
            "<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in row)+"</tr>" for row in rows)+"</tbody></table>"
    calc=p["calculation"]
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        '<title>C.2A 本地科研报告</title><style>body{font-family:sans-serif;max-width:1100px;margin:2em auto;padding:1em} '
        'table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.4em}pre{white-space:pre-wrap;overflow-wrap:anywhere}svg{width:100%}</style>'
        '<body><h1>C.2A Michaelis–Menten 条件性拟合报告</h1><p>状态：'+escape(calc["status"])
        +'</p><h2>科学限制</h2>'+"".join("<p>"+escape(x)+"</p>" for x in p["limitations"])
        +'<h2>参数与诊断（未计算置信区间）</h2>'+pre(dict(parameters=calc["parameters"],statistics=calc["statistics"],diagnostics=calc["diagnostics"]))
        +'<h2>曲线与残差</h2><p>模型线仅由原拟合参数生成作显示，不是新增观测；不外推。</p>'+chart_svg(result)
        +table(["analysis_id","S","观察速率","拟合速率","残差"],[[r[k] for k in ("analysis_id","substrate_concentration","observed_rate","fitted_rate","residual")] for r in calc["predictions"]])
        +'<h2>科研审核</h2>'+table(["审核字段","记录"],[[k,p["review"][k]] for k in ('reviewer','reviewed_at_utc','rationale','direction')])+pre(p["review"])
        + '<h2>优化器与 QC</h2>'+pre({k:calc[k] for k in ("optimizer","quality_control","reasons")})
        +'<h2>来源、单位与分析版本</h2>'+pre(p["metadata"])+pre(p["source_summary"])
        +'<h2>报告完整性摘要</h2>'+pre(dict(report_sha256=report["report_sha256"],source_database_sha256=p["source_database_sha256"],source_access_strategy=p['source_access_strategy'],source_database_identity=p['source_database_identity'],native_result_sha256_scope=p["native_result_sha256_scope"],generated_at_utc=p["generated_at_utc"]))+'</body></html>')


def export_report(path, identifiers, expected, result, destination, kind, database_sha256,source_identity=None):
    try:
        _current_records(path, identifiers, expected, database_sha256,source_identity)
        result = checked_result(result, expected)
    except Exception as exc:
        raise ValueError('SOURCE_OR_RESULT_INVALID: '+str(exc)) from exc
    report = report_payload(result, database_sha256,source_identity)
    if kind not in {"json","html"}:
        raise OSError("未知报告格式；计算结果未改变")
    target = Path(destination)
    if str(destination).startswith(("\\\\","//")) or target.suffix.lower() != "."+kind:
        raise OSError("请选择本地、扩展名正确的新报告文件")
    body = json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n" if kind=="json" else render_html(report,result)
    # Same-directory, no-replace atomic publication. Unsupported filesystems fail safely.
    fd, temporary = tempfile.mkstemp(prefix=".protein-mm-",suffix=".tmp",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as stream:
            stream.write(body);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,target)
    finally:
        os.unlink(temporary)
    return dict(path=str(target),report_sha256=report["report_sha256"])
