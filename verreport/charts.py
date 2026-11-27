"""정적 SVG 차트.

Jenkins HTML Publisher의 기본 CSP는 스크립트와 인라인 style을 막는다. 그래서 차트는
SVG 마크업으로 만들고, 색은 외부 CSS의 class로만 칠한다 (style 속성을 쓰지 않는다).
마우스를 올리면 보이는 설명은 SVG <title>로 넣는다. 모든 값은 옆의 표에도 있다.

마크 규격 (dataviz): 막대 두께 <= 24px, 데이터 끝 4px 둥근 모서리, 표면색 2px 간격,
격자·축은 1px 실선.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from markupsafe import Markup, escape

GAP = 2


@dataclass
class Part:
    """분할 막대 한 칸 / 가로 막대 한 개."""

    label: str
    value: float
    css: str
    title: str | None = None


def _title(text: str) -> str:
    return f"<title>{escape(text)}</title>"


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def segmented_bar(parts: list[Part], label: str, width: int = 240, height: int = 8) -> Markup:
    """얇은 분할 막대: 하나의 전체를 나눈 비율. 글자 없음 (옆 표가 숫자를 가진다)."""
    total = sum(p.value for p in parts)
    out = [f'<svg class="segbar" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'role="img" aria-label="{escape(label)}">']
    if total <= 0:
        out.append(f'<rect class="track" x="0" y="0" width="{width}" height="{height}" '
                   f'rx="{height / 2}"/>')
    else:
        visible = [p for p in parts if p.value > 0]
        usable = width - GAP * (len(visible) - 1)
        x = 0.0
        key = repr((label, width, [(p.label, p.value) for p in parts])).encode()
        clip = "seg-" + hashlib.sha1(key).hexdigest()[:10]   # 같은 입력이면 같은 HTML
        out.append(f'<clipPath id="{clip}"><rect x="0" y="0" width="{width}" height="{height}" '
                   f'rx="{height / 2}"/></clipPath><g clip-path="url(#{clip})">')
        for p in visible:
            w = usable * p.value / total
            out.append(f'<rect class="{p.css}" x="{_num(x)}" y="0" width="{_num(w)}" '
                       f'height="{height}">{_title(p.title or f"{p.label} {_num(p.value)}")}</rect>')
            x += w + GAP
        out.append("</g>")
    out.append("</svg>")
    return Markup("".join(out))


def meter(percent: float | None, label: str, target: float | None = None,
          width: int = 120, height: int = 8, css: str = "fill-accent") -> Markup:
    """미터: 0~100% 비율. target이 있으면 기준 위치에 눈금을 긋는다."""
    out = [f'<svg class="meter" viewBox="0 0 {width} {height + 4}" width="{width}" '
           f'height="{height + 4}" role="img" aria-label="{escape(label)}">',
           _title(label),
           f'<rect class="track" x="0" y="2" width="{width}" height="{height}" rx="{height / 2}"/>']
    if percent is not None and percent > 0:
        w = max(width * min(percent, 100.0) / 100.0, height)
        out.append(f'<rect class="{css}" x="0" y="2" width="{_num(w)}" height="{height}" '
                   f'rx="{height / 2}"/>')
    if target is not None:
        tx = min(width * target / 100.0, width - 1)
        out.append(f'<rect class="tick" x="{_num(tx - 1)}" y="0" width="2" height="{height + 4}"/>')
    out.append("</svg>")
    return Markup("".join(out))


def hbar_chart(rows: list[Part], label: str, threshold: float | None = None,
               threshold_label: str | None = None, width: int = 460,
               label_width: int = 150, bar: int = 14, row: int = 26) -> Markup:
    """가로 막대 차트: 이름 | 막대 | 값. threshold가 있으면 세로 기준선을 긋는다."""
    top = 18 if threshold is not None else 4
    height = top + row * max(len(rows), 1) + 4
    value_w = 40
    plot_w = width - label_width - value_w
    vmax = max([r.value for r in rows] + [threshold or 0, 1])
    scale = plot_w / vmax

    out = [f'<svg class="hbar" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'preserveAspectRatio="xMinYMin meet" role="img" aria-label="{escape(label)}">']
    # 기준축
    out.append(f'<rect class="axis" x="{label_width}" y="{top - 2}" width="1" '
               f'height="{row * max(len(rows), 1) + 2}"/>')
    for i, r in enumerate(rows):
        y = top + i * row
        cy = y + row / 2
        limit = max(8, (label_width - 12) // 7)
        name = r.label if len(r.label) <= limit else r.label[:limit - 1] + "…"
        out.append(f'<g>{_title(r.title or f"{r.label}: {_num(r.value)}")}'
                   f'<text class="lbl" x="{label_width - 8}" y="{_num(cy)}" text-anchor="end" '
                   f'dominant-baseline="central">{escape(name)}</text>')
        w = r.value * scale
        if w > 0:
            out.append(_bar_path(label_width + 1, cy - bar / 2, w, bar, r.css))
        out.append(f'<text class="val" x="{_num(label_width + 1 + w + 6)}" y="{_num(cy)}" '
                   f'dominant-baseline="central">{_num(r.value)}</text></g>')
    if threshold is not None:
        tx = label_width + 1 + threshold * scale
        out.append(f'<rect class="threshold" x="{_num(tx - 0.5)}" y="{top - 4}" width="1" '
                   f'height="{row * max(len(rows), 1) + 4}"/>')
        if threshold_label:
            out.append(f'<text class="lbl" x="{_num(tx)}" y="10" text-anchor="middle">'
                       f'{escape(threshold_label)}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def _bar_path(x: float, y: float, w: float, h: float, css: str, r: float = 4) -> str:
    """기준선 쪽은 직각, 데이터 끝은 4px 둥근 모서리인 가로 막대."""
    r = min(r, w, h / 2)
    d = (f"M{_num(x)},{_num(y)} H{_num(x + w - r)} "
         f"Q{_num(x + w)},{_num(y)} {_num(x + w)},{_num(y + r)} "
         f"V{_num(y + h - r)} Q{_num(x + w)},{_num(y + h)} {_num(x + w - r)},{_num(y + h)} "
         f"H{_num(x)} Z")
    return f'<path class="{css}" d="{d}"/>'
