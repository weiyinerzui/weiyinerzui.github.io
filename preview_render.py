#!/usr/bin/env python3
"""Minimal Jekyll/Liquid renderer — enough to verify templates render sane HTML."""
import os, re, json, html, shutil, sys
from datetime import datetime
import frontmatter
import yaml
try:
    import markdown as md_lib
except ImportError:
    md_lib = None

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")


class Safe(str):
    pass


def slugify(s):
    s = str(s).strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", s)
    return re.sub(r"[\s]+", "-", s)


class Site:
    def __init__(self):
        cfg = yaml.safe_load(open(os.path.join(ROOT, "_config.yml"), encoding="utf-8"))
        self.cfg = cfg
        self.posts = self._load_posts()

    def _load_posts(self):
        d = os.path.join(ROOT, "_posts")
        posts = []
        for fn in os.listdir(d):
            if not fn.endswith((".md", ".html")):
                continue
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.(md|html)$", fn)
            if not m:
                continue
            y, mo, da, slug, ext = m.groups()
            path = os.path.join(d, fn)
            raw = open(path, encoding="utf-8").read()
            post = frontmatter.loads(raw)
            meta = post.metadata
            date = datetime(int(y), int(mo), int(da))
            posts.append({
                "layout": meta.get("layout", "post"),
                "title": meta.get("title", slug),
                "date": date,
                "tags": meta.get("tags", []) or [],
                "url": meta.get("permalink") or "/%s/" % slug,
                "excerpt": meta.get("description", ""),
                "content": post.content,
                "slug": slug,
                "ext": ext,
            })
        posts.sort(key=lambda p: p["date"], reverse=True)
        return posts


def split_filters(expr):
    parts, buf, quote = [], [], None
    for ch in expr:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == "|":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return parts


CMP_RE = re.compile(r"^(.*?)\s*(==|!=|>=|<=|>|<)\s*(.*)$", re.S)


def liquid_eval(expr, ctx):
    expr = expr.strip()
    # and / or（仅支持简单的双边）
    for op in (" or ", " and "):
        if op in expr:
            left, right = expr.split(op, 1)
            a, b = liquid_eval(left, ctx), liquid_eval(right, ctx)
            return (truthy(a) or truthy(b)) if op == " or " else (truthy(a) and truthy(b))
    # 比较运算（左右各自求值，支持左侧带过滤器）
    m = CMP_RE.match(expr)
    if m and not expr.startswith(("'", '"')):
        left, op, right = m.group(1), m.group(2), m.group(3)
        a, b = liquid_eval(left, ctx), liquid_eval(right, ctx)
        try:
            if isinstance(a, (int, float)) or isinstance(b, (int, float)):
                a2, b2 = float(a or 0), float(b or 0)
            else:
                a2, b2 = str(a), str(b)
                if op in (">", "<", ">=", "<="):
                    a2, b2 = len(a2), len(b2)
            return {"==": a2 == b2, "!=": a2 != b2, ">": a2 > b2,
                    "<": a2 < b2, ">=": a2 >= b2, "<=": a2 <= b2}[op]
        except Exception:
            return False
    # 处理过滤器链
    parts = split_filters(expr)
    base = parts[0]
    val = resolve(base, ctx)
    for f in parts[1:]:
        val = apply_filter(f, val, ctx)
    return val


def resolve(path, ctx):
    path = path.strip()
    if path in ("true", "false"):
        return path == "true"
    if re.fullmatch(r"-?\d+", path):
        return int(path)
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        return path[1:-1]
    if path == "empty":
        return ""
    cur = ctx
    for seg in path.split("."):
        if seg == "":
            continue
        if seg == "size":
            try:
                cur = len(cur)
            except TypeError:
                cur = 0
            continue
        if isinstance(cur, dict):
            cur = cur.get(seg, "")
        elif isinstance(cur, list):
            if seg.isdigit():
                cur = cur[int(seg)] if int(seg) < len(cur) else ""
            else:
                return ""
        elif isinstance(cur, datetime):
            if seg in ("year", "month", "day"):
                cur = getattr(cur, seg)
            else:
                return ""
        else:
            return ""
        if cur is None:
            return ""
    return cur


def apply_filter(f, val, ctx):
    f = f.strip()
    name = f.split(":")[0].strip()
    argstr = f.split(":", 1)[1].strip() if ":" in f else ""

    def arg(default=None):
        if not argstr:
            return default
        return liquid_eval(argstr, ctx)

    def to_str(v):
        return "" if v is None else str(v)

    if name == "date":
        fmt = to_str(arg("%Y-%m-%d"))
        return val.strftime(fmt) if isinstance(val, datetime) else to_str(val)
    if name == "date_to_xmlschema":
        return val.strftime("%Y-%m-%dT%H:%M:%S+00:00") if isinstance(val, datetime) else to_str(val)
    if name == "escape":
        return html.escape(to_str(val), quote=True)
    if name == "strip_html":
        return re.sub(r"<[^>]+>", "", to_str(val))
    if name == "normalize_whitespace":
        return re.sub(r"\s+", " ", to_str(val)).strip()
    if name == "truncate":
        n = int(arg(50))
        s = to_str(val)
        return s if len(s) <= n else s[: n - 1].rstrip() + "…"
    if name == "downcase":
        return to_str(val).lower()
    if name == "upcase":
        return to_str(val).upper()
    if name == "join":
        return to_str(arg(", ")).join([to_str(v) for v in (val or [])]) if isinstance(val, list) else to_str(val)
    if name == "size":
        try:
            return len(val)
        except TypeError:
            return 0
    if name == "slugify":
        return slugify(val)
    if name == "append":
        return to_str(val) + to_str(arg(""))
    if name == "prepend":
        return to_str(arg("")) + to_str(val)
    if name == "default":
        return val if val not in ("", None, []) else arg("")
    if name == "relative_url":
        return to_str(val)
    if name == "strip":
        return to_str(val).strip()
    if name == "first":
        if isinstance(val, list):
            return val[0] if val else ""
        if isinstance(val, dict):
            return next(iter(val.values())) if val else ""
        return ""
    if name == "last":
        if isinstance(val, list):
            return val[-1] if val else ""
        return ""
    return val


TAG_RE = re.compile(r"{%-?\s*(.*?)\s*-?%}", re.S)


def render(template, ctx, site):
    out = []
    pos = 0
    # 用递归方式处理 block 标签
    return _render_block(template, ctx, site, {})


def _render_block(tpl, ctx, site, endtags):
    out = []
    i = 0
    while True:
        m = TAG_RE.search(tpl, i)
        if not m:
            out.append(tpl[i:])
            break
        out.append(tpl[i:m.start()])
        tag = m.group(1).strip()

        if tag.startswith(("if ", "unless ")):
            negate = tag.startswith("unless")
            cond = tag.split(None, 1)[1]
            body, after, _ = _extract_block(tpl, m.end(), "if")
            truth = truthy(liquid_eval(cond, ctx))
            if negate:
                truth = not truth
            if truth:
                out.append(_render_block(body, ctx, site, {}))
            i = after
            continue

        if tag.startswith("for "):
            mm = re.match(r"for\s+(\w+)\s+in\s+(\S+)", tag)
            var, coll_expr = mm.group(1), mm.group(2)
            body, after, _ = _extract_block(tpl, m.end(), "for")
            coll = liquid_eval(coll_expr, ctx)
            items = []
            if isinstance(coll, dict):
                items = [[k, v] for k, v in coll.items()]
            elif isinstance(coll, list):
                items = coll
            for idx, item in enumerate(items):
                inner = dict(ctx)
                inner[var] = item
                inner["forloop"] = {
                    "first": idx == 0, "last": idx == len(items) - 1,
                    "index": idx + 1, "index0": idx, "length": len(items),
                }
                out.append(_render_block(body, inner, site, {}))
            i = after
            continue

        if tag.startswith("assign "):
            mm = re.match(r"assign\s+(\w+)\s*=\s*(.*)", tag, re.S)
            ctx[mm.group(1)] = liquid_eval(mm.group(2), ctx)
            i = m.end()
            continue

        if tag.startswith("capture "):
            var = tag.split(None, 1)[1].strip()
            body, after, _ = _extract_block(tpl, m.end(), "capture")
            ctx[var] = _render_block(body, ctx, site, {})
            i = after
            continue

        if tag.startswith("include "):
            mm = re.match(r"include\s+(\S+)(.*)", tag, re.S)
            name = mm.group(1)
            path = os.path.join(ROOT, "_includes", name)
            if os.path.exists(path):
                src = open(path, encoding="utf-8").read()
                inner = dict(ctx)
                for k, v in re.findall(r'(\w+)=("[^"]*"|\'[^\']*\'|\S+)', mm.group(2)):
                    inner[k] = liquid_eval(v, ctx)
                out.append(_render_block(src, inner, site, {}))
            i = m.end()
            continue

        if tag.startswith(("comment", "raw")):
            body, after, _ = _extract_block(tpl, m.end(), tag.split()[0])
            i = after
            continue

        if tag.startswith("unless "):
            i = m.end()
            continue

        if tag in ("endif", "endfor", "endcapture", "endunless", "endcomment", "endraw"):
            out.append("")  # 由 _extract_block 处理
            i = m.end()
            continue

        if tag.startswith("elsif") or tag == "else":
            i = m.end()
            continue

        # 输出 {{ }}
        out.append("")
        i = m.end()

    return _render_outputs(tpl, ctx, site, out, endtags)


def _render_outputs(tpl, ctx, site, parts, endtags):
    # 重新拼接：parts 已包含非标签文本与被递归渲染的结果，
    # 还需要把 {{ }} 替换掉（在 _render_block 里未处理）
    # 简化：直接对最终拼接结果再做一次 {{ }} 替换
    joined = "".join(parts)
    return OUT_RE.sub(lambda m: to_output(liquid_eval(m.group(1), ctx)), joined)


OUT_RE = re.compile(r"{{-?\s*(.*?)\s*-?}}", re.S)


def to_output(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    return str(v)


def truthy(v):
    if isinstance(v, bool):
        return v
    if v in ("", None, [], {}):
        return False
    if isinstance(v, (int, float)):
        return v != 0
    return True


def _extract_block(tpl, start, tag_name):
    """返回 (block_body, next_index, end_tag)."""
    depth = 1
    i = start
    end_kw = "end" + tag_name
    while True:
        m = TAG_RE.search(tpl, i)
        if not m:
            return tpl[start:], len(tpl), None
        inner = m.group(1).strip()
        if inner.startswith(tag_name + " ") or inner == tag_name:
            depth += 1
        elif inner == end_kw:
            depth -= 1
            if depth == 0:
                return tpl[start:m.start()], m.end(), inner
        elif inner.startswith("if ") and tag_name != "if":
            pass
        i = m.end()


def apply_layouts(layout, ctx, site):
    """沿 layout 链向上套用，直到没有父 layout。"""
    seen = set()
    while layout and layout != "null" and layout not in seen:
        seen.add(layout)
        path = os.path.join(ROOT, "_layouts", layout + ".html")
        if not os.path.exists(path):
            break
        src = open(path, encoding="utf-8").read()
        m = re.match(r"^---\s*(.*?)\s*---\s*", src, re.S)
        parent = None
        if m:
            fm = yaml.safe_load(m.group(1)) or {}
            parent = fm.get("layout")
            src = src[m.end():]
        ctx["content"] = _render_block(src, ctx, site, {})
        layout = parent
    return ctx["content"]


def build():
    site = Site()
    cfg = site.cfg
    tags = {}
    for p in site.posts:
        for t in p["tags"]:
            tags.setdefault(t, []).append(p)

    base_ctx = {
        "site": {
            "name": cfg.get("name", ""),
            "description": cfg.get("description", ""),
            "tagline": cfg.get("tagline", ""),
            "blurb": cfg.get("blurb", ""),
            "baseurl": cfg.get("baseurl", "") or "",
            "url": cfg.get("url", ""),
            "avatar": cfg.get("avatar", ""),
            "navigation": cfg.get("navigation", []),
            "footer-links": cfg.get("footer-links", {}),
            "posts": site.posts,
            "time": datetime.now(),
            "tags": tags,
        },
        "page": {},
    }

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    pages = [
        ("index.html", "/"),
        ("archive/index.html", "/archive/"),
        ("tags/index.html", "/tags/"),
        ("about.md", "/about/"),
        ("404.md", "/404.html"),
    ]

    results = []
    for path, url in pages:
        src = os.path.join(ROOT, path)
        meta, body = frontmatter.loads(open(src, encoding="utf-8").read()), None
        meta2 = frontmatter.load(src)
        body = meta2.content
        layout = meta2.metadata.get("layout", "default")
        ctx = dict(base_ctx)
        ctx["page"] = dict(meta2.metadata)
        ctx["page"]["url"] = url
        ctx["paginator"] = {
            "posts": site.posts[: cfg.get("paginate", 6)],
            "page": 1,
            "total_pages": max(1, (len(site.posts) + cfg.get("paginate", 6) - 1) // cfg.get("paginate", 6)),
            "previous_page": None,
            "next_page": 2 if len(site.posts) > cfg.get("paginate", 6) else None,
            "previous_page_path": "",
            "next_page_path": "/page2/",
        }
        if path.endswith(".md") and md_lib:
            body = md_lib.markdown(body, extensions=["fenced_code", "tables", "sane_lists", "md_in_html"])
        rendered = _render_block(body, ctx, site, {})
        if layout and layout != "null":
            ctx["content"] = rendered
            rendered = apply_layouts(layout, ctx, site)

        outpath = os.path.join(OUT, url.strip("/") or "", "index.html") if not url.endswith(".html") else os.path.join(OUT, url.lstrip("/"))
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        open(outpath, "w", encoding="utf-8").write(rendered)
        results.append((url, outpath, len(rendered)))

    # posts
    for p in site.posts:
        ctx = dict(base_ctx)
        ctx["page"] = {
            "layout": p["layout"], "title": p["title"], "date": p["date"], "tags": p["tags"],
            "url": p["url"], "excerpt": p["excerpt"],
        }
        idx = site.posts.index(p)
        ctx["page"]["previous"] = site.posts[idx + 1] if idx + 1 < len(site.posts) else None
        ctx["page"]["next"] = site.posts[idx - 1] if idx > 0 else None
        body = p["content"]
        if md_lib and p.get("ext") == "md":
            body = md_lib.markdown(body, extensions=["fenced_code", "tables", "sane_lists"])
        body = _render_block(body, ctx, site, {})
        ctx["content"] = body
        rendered = apply_layouts("post", ctx, site)
        outpath = os.path.join(OUT, p["url"].strip("/"), "index.html")
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        open(outpath, "w", encoding="utf-8").write(rendered)
        results.append((p["url"], outpath, len(rendered)))

    # search.json
    sjson = open(os.path.join(ROOT, "search.json"), encoding="utf-8").read()
    sjson = re.sub(r"^---.*?---\s*", "", sjson, count=1, flags=re.S)
    data = [{"title": p["title"], "tags": ", ".join(p["tags"]), "url": p["url"],
             "date": p["date"].strftime("%Y-%m-%d")} for p in site.posts]
    open(os.path.join(OUT, "search.json"), "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))

    # 静态资源
    for name in ("assets", "images"):
        s = os.path.join(ROOT, name)
        if os.path.exists(s):
            shutil.copytree(s, os.path.join(OUT, name), dirs_exist_ok=True)
    shutil.copy(os.path.join(ROOT, "sbti.html"), os.path.join(OUT, "sbti.html"))

    for url, path, n in results:
        print(f"{url:20s} {n:8d}B  {os.path.relpath(path, OUT)}")


if __name__ == "__main__":
    build()
