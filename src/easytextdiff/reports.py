"""Portable HTML comparison reports containing only the user's selected data."""
from html import escape
from .branding import APP_NAME


def _cell(text, spans):
    pieces = []
    end = 0
    for span in spans:
        pieces.append(escape(text[end:span.start]))
        pieces.append('<mark>' + escape(text[span.start:span.end]) + '</mark>')
        end = span.end
    pieces.append(escape(text[end:]))
    return ''.join(pieces) or '&nbsp;'


def html_report(result, left_name='原始文本', right_name='修改文本', options=None):
    rows = []
    for row in result.rows:
        left = result.left_lines[row.left_index] if row.left_index is not None else ''
        right = result.right_lines[row.right_index] if row.right_index is not None else ''
        left_number = str(row.left_index+1) if row.left_index is not None else ''
        right_number = str(row.right_index+1) if row.right_index is not None else ''
        rows.append(f'<tr class="{row.kind}"><td class="num">{left_number}</td>'
                    f'<td class="left">{_cell(left,row.left_spans)}</td>'
                    f'<td class="num">{right_number}</td>'
                    f'<td class="right">{_cell(right,row.right_spans)}</td></tr>')
    ignored = []
    if options and options.ignore_whitespace:
        ignored.append('忽略空白')
    if options and options.ignore_case:
        ignored.append('忽略大小写')
    option_text = ' · '.join(ignored) or '精确文本比较'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>{APP_NAME} · 差异报告</title>
    <style>body{{margin:32px;background:#f4f7f5;color:#20332c;font:14px system-ui,sans-serif}}
    h1{{font-size:24px}}p{{color:#62766b}}table{{width:100%;table-layout:fixed;border-collapse:collapse;background:white;border:1px solid #dce5df}}
    th{{text-align:left;padding:14px;background:#edf3ef}}td{{padding:3px 10px;vertical-align:top;font:13px/1.65 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}
    td.num{{width:44px;color:#8b9b91;text-align:right;background:#f9fbfa;border-right:1px solid #e4ebe6}}th.num{{width:44px}}
    td.left{{border-right:1px solid #dce5df}}.delete .left,.replace .left{{background:#fff0ed}}.insert .right,.replace .right{{background:#eaf6ee}}
    .left mark{{background:#f3bdb3;color:inherit}}.right mark{{background:#afdebf;color:inherit}}</style>
    <h1>{APP_NAME} · 文本差异报告</h1><p>{len(result.changes)} 处差异 · 新增 {result.added_lines} 行 · 删除 {result.deleted_lines} 行 · 修改 {result.modified_lines} 行<br>{option_text}</p>
    <table><thead><tr><th class="num">行号</th><th>{escape(left_name)}</th><th class="num">行号</th><th>{escape(right_name)}</th></tr></thead><tbody>{''.join(rows)}</tbody></table></html>'''
