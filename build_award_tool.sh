#!/usr/bin/env bash
# award-tool.src.html に SheetJS を埋め込み、単一ファイル award-tool.html を生成する。
set -e
cd "$(dirname "$0")"
python3 - <<'PY'
lib=open('vendor/xlsx.full.min.js',encoding='utf-8',errors='replace').read()
src=open('award-tool.src.html',encoding='utf-8').read()
inline='<script>\n/* SheetJS (xlsx.js) v0.18.5  https://sheetjs.com  Apache-2.0 */\n'+lib+'\n</script>'
out=src.replace('<!--XLSX_LIB_PLACEHOLDER-->',inline)
assert '<!--XLSX_LIB_PLACEHOLDER-->' not in out
open('award-tool.html','w',encoding='utf-8').write(out)
print('built award-tool.html')
PY
