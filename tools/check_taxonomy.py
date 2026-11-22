#!/usr/bin/env python3
"""校验文章的分类与标签是否符合 _config.yml 的栏目树和受控词表。

用法：
    python3 tools/check_taxonomy.py            # 人类可读报告
    python3 tools/check_taxonomy.py --strict   # 有 error 时退出码 1（可用于 CI）

只做校验，不改文件。GitHub Pages 构建不会运行它。
"""
import sys, re, glob, os
from collections import Counter, defaultdict

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_cfg():
    with open(os.path.join(ROOT, '_config.yml'), encoding='utf-8') as f:
        return yaml.safe_load(f)

def split_front_matter(path):
    with open(path, encoding='utf-8') as f:
        s = f.read()
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?', s, re.S)
    if not m:
        return None, s
    return yaml.safe_load(m.group(1)) or {}, s[m.end():]

def main():
    strict = '--strict' in sys.argv
    cfg = load_cfg()
    tree = cfg.get('category_tree') or []
    vocab = set(cfg.get('tag_vocabulary') or [])

    # key -> 中文名；key/sub -> 中文名
    cat_names, sub_names = {}, {}
    for c in tree:
        cat_names[c['key']] = c['name']
        for s in c.get('subs') or []:
            sub_names[f"{c['key']}/{s['key']}"] = s['name']

    files = sorted(glob.glob(os.path.join(ROOT, '_posts', '*')))
    errors, warns, stats = [], [], defaultdict(list)
    tag_count = Counter()

    for path in files:
        name = os.path.basename(path)
        fm, _ = split_front_matter(path)
        if fm is None:
            errors.append(f"{name}: 缺 front matter")
            continue

        cats = fm.get('categories')
        if not cats:
            errors.append(f"{name}: 没有 categories")
        elif not isinstance(cats, list):
            errors.append(f"{name}: categories 必须是列表")
        else:
            if cats[0] not in cat_names:
                errors.append(f"{name}: 一级栏目 '{cats[0]}' 不在 category_tree 中")
            else:
                stats[cats[0]].append(name)
            if len(cats) > 1:
                if len(cats) > 2:
                    errors.append(f"{name}: categories 超过两级（最多 栏目/子栏目）")
                else:
                    full = f"{cats[0]}/{cats[1]}"
                    if full not in sub_names:
                        errors.append(f"{name}: 子栏目 '{full}' 不存在于 {cats[0]} 下")
                    else:
                        stats[full].append(name)
                    if cats[0] not in cat_names:
                        pass

        tags = fm.get('tags') or []
        if not isinstance(tags, list):
            errors.append(f"{name}: tags 必须是列表")
            tags = []
        for t in tags:
            tag_count[t] += 1
            if t not in vocab:
                warns.append(f"{name}: 标签 '{t}' 不在受控词表 tag_vocabulary 中")

        if not fm.get('permalink'):
            warns.append(f"{name}: 建议显式写 permalink（中文文件名会得到乱码 URL）")

    # 报告
    print(f"栏目树：{len(cat_names)} 个一级栏目 / {len(sub_names)} 个子栏目")
    print(f"文章：{len(files)} 篇\n")

    print("各栏目文章数：")
    for c in tree:
        k = c['key']
        n = len(stats[k])
        subs = c.get('subs') or []
        detail = "  ".join(f"{s['key']}={len(stats[f'{k}/{s[chr(107)+chr(101)+chr(121)]}'])}"
                           for s in subs) if subs else ""
        print(f"  {k:10s} {c['name']:6s} {n:2d} 篇   {detail}")
        empty = [s['key'] for s in subs if not stats[f"{k}/{s['key']}"]]
        if subs and len(empty) == len(subs):
            print(f"           ! 子栏目全部为空（建了页面但没文章）")

    used = set(t for t in tag_count)
    print(f"\n标签使用：{len(used)} 个")
    for t, n in tag_count.most_common():
        mark = "" if t in vocab else "  <- 不在词表"
        print(f"  {t:20s} {n}{mark}")

    unused = vocab - used
    if unused:
        print(f"\n词表中尚未使用：{', '.join(sorted(unused))}")

    if warns:
        print(f"\n警告 {len(warns)} 条：")
        for w in warns:
            print("  ! " + w)
    if errors:
        print(f"\n错误 {len(errors)} 条：")
        for e in errors:
            print("  x " + e)
        if strict:
            sys.exit(1)
    elif not warns:
        print("\n全部通过 ✓")

if __name__ == '__main__':
    main()
