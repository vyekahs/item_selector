# Detail Page Templates (Module D)

Jinja2 templates rendered server-side, then screenshotted by Playwright into a single tall JPG (Korean e-commerce detail page format, **860px wide fixed**).

## Files

- `detail_page_v1.html` - main template (single column, 860px, inline CSS, no JS, no external assets)
- `detail_page_v1_sample_props.json` - realistic sample data for development / preview
- (future) `detail_page_v2.html`, etc.

## Props contract

The template expects this dict to be passed to `template.render(**props)`:

```python
{
    "title_ko": str,                                    # SEO 타이틀 (h1)
    "highlight": str,                                   # 한 줄 후킹 카피 (pill)
    "main_image_url": str,                              # 메인 컷, 860x860 권장
    "aida": {
        "attention": str,                               # short hook line
        "interest":  str,                               # paragraph (\n preserved)
        "desire":    str,                               # paragraph (\n preserved)
        "action":    str,                               # CTA line
    },
    "spec_table": [{"label": str, "value": str}, ...],  # 2-col grid
    "gallery":    [str, ...],                           # detail image URLs (stacked)
    "options":    [{"name": str, "image_url": str}, ...]  # 옵션 카드 (2-col grid)
}
```

All sections except hero + AIDA are conditionally rendered - empty `gallery`, `options`, or `spec_table` lists simply skip the section. Empty AIDA fields skip individual blocks.

## Layout order

1. Hero - main image (860x860) + title + highlight pill
2. AIDA - 4 stacked text blocks (attention / interest / desire / action), action block uses red accent
3. Options gallery - 2-column grid of option cards (only if `options` non-empty)
4. Spec table - 2-column CSS grid, gray label / bold value (only if `spec_table` non-empty)
5. Gallery - vertically stacked detail images at full 860px width

## Design tokens

- Width: `860px` fixed
- Text: `#111827` (heading), `#374151` (body), `#6b7280` (muted)
- Accent: `#0ea5e9` (highlight pill), `#ef4444` (CTA / action block)
- Font: `Pretendard, 'Noto Sans KR', -apple-system, ...` (no external font load - Playwright snapshot offline)
- Section padding: `40px`

## Local preview

```sh
cd backend
.venv/bin/python -c "
import json
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
props = json.load(open('templates/detail_page_v1_sample_props.json'))
open('/tmp/preview.html', 'w').write(env.get_template('detail_page_v1.html').render(**props))
print('rendered preview to /tmp/preview.html')
"
open /tmp/preview.html
```

## Notes for Module C (renderer)

- All `<img>` use `loading="eager"` so Playwright's `wait_for_load_state("networkidle")` will block on them.
- No external CSS / JS / fonts - safe for offline rendering.
- Page width is hard-coded to 860px in the template; set Playwright viewport width to match (height can be any value, screenshot uses `full_page=True`).
- `main_image_url`, `gallery[*]`, `options[*].image_url` should be local paths served by the backend (e.g. `/generated/{id}/main.jpg`) so that Playwright can fetch them without external network.
