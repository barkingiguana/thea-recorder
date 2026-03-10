"""Layout validation and testcard generation for recording sessions.

Validates that panels and application regions fit within the recording
canvas without overlapping, and generates SVG testcard graphics showing
the spatial arrangement.
"""

from __future__ import annotations

import html


class Region:
    """A rectangular area on the recording canvas.

    Attributes:
        name: Unique identifier for this region.
        x: Left edge in pixels.
        y: Top edge in pixels.
        width: Width in pixels.
        height: Height in pixels.
        kind: Either ``"app"`` or ``"panel"``.
    """

    __slots__ = ("name", "x", "y", "width", "height", "kind")

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        width: int,
        height: int,
        kind: str = "panel",
    ) -> None:
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.kind = kind

    def right(self) -> int:
        return self.x + self.width

    def bottom(self) -> int:
        return self.y + self.height

    def overlaps(self, other: Region) -> bool:
        """True if this region overlaps with *other*."""
        if self.width <= 0 or self.height <= 0:
            return False
        if other.width <= 0 or other.height <= 0:
            return False
        return (
            self.x < other.right()
            and other.x < self.right()
            and self.y < other.bottom()
            and other.y < self.bottom()
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "kind": self.kind,
        }

    def __repr__(self) -> str:
        return (
            f"Region({self.name!r}, x={self.x}, y={self.y}, "
            f"w={self.width}, h={self.height}, kind={self.kind!r})"
        )


def validate_regions(
    canvas_width: int,
    canvas_height: int,
    regions: list[Region],
) -> list[str]:
    """Validate a set of regions against a canvas.

    Returns a list of warning strings.  An empty list means the layout
    is valid.

    Checks performed:

    - Regions with non-positive dimensions
    - Regions starting at negative coordinates
    - Regions extending beyond the canvas
    - Overlapping regions
    """
    warnings: list[str] = []

    for r in regions:
        if r.width <= 0 or r.height <= 0:
            warnings.append(
                f"Region '{r.name}' has non-positive dimensions "
                f"({r.width}x{r.height})"
            )
        if r.x < 0 or r.y < 0:
            warnings.append(
                f"Region '{r.name}' starts at negative coordinates "
                f"({r.x}, {r.y})"
            )
        if r.x + r.width > canvas_width:
            warnings.append(
                f"Region '{r.name}' extends beyond canvas width "
                f"({r.x + r.width} > {canvas_width})"
            )
        if r.y + r.height > canvas_height:
            warnings.append(
                f"Region '{r.name}' extends beyond canvas height "
                f"({r.y + r.height} > {canvas_height})"
            )

    for i, a in enumerate(regions):
        for b in regions[i + 1 :]:
            if a.overlaps(b):
                warnings.append(
                    f"Regions '{a.name}' and '{b.name}' overlap"
                )

    return warnings


_REGION_COLORS = {
    "app": ("#1a3a5c", "#4a9eff"),
    "panel": ("#2d1a3e", "#b06ec8"),
}


def generate_testcard(
    canvas_width: int,
    canvas_height: int,
    regions: list[Region],
    warnings: list[str] | None = None,
) -> str:
    """Generate an SVG testcard image showing the layout.

    Args:
        canvas_width: Total canvas width in pixels.
        canvas_height: Total canvas height in pixels.
        regions: List of regions to display.
        warnings: Optional validation warnings to display.

    Returns:
        SVG markup as a string.
    """
    # Scale so the SVG is reasonable for viewing (max ~960px wide)
    scale = min(1.0, 960.0 / canvas_width) if canvas_width > 0 else 1.0
    margin = 30
    warn_height = len(warnings) * 22 + 20 if warnings else 0
    vb_w = canvas_width + margin * 2
    vb_h = canvas_height + margin * 2 + 50 + warn_height
    svg_w = int(vb_w * scale)
    svg_h = int(vb_h * scale)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {vb_w} {vb_h}">',
        # Background
        f'<rect width="{vb_w}" height="{vb_h}" fill="#0d0d0d"/>',
        # Title bar
        f'<text x="{vb_w // 2}" y="22" text-anchor="middle" '
        f'font-family="monospace" font-size="16" font-weight="bold" '
        f'fill="#58a6ff">THEA LAYOUT TESTCARD</text>',
    ]

    ox, oy = margin, margin + 10  # origin offset

    # Canvas outline
    lines.append(
        f'<rect x="{ox}" y="{oy}" width="{canvas_width}" '
        f'height="{canvas_height}" fill="#111" stroke="#333" '
        f'stroke-width="2" stroke-dasharray="8,4"/>'
    )

    # Grid lines
    lines.append(f'<g stroke="#1a1a1a" stroke-width="0.5">')
    for gx in range(100, canvas_width, 100):
        lines.append(
            f'<line x1="{ox + gx}" y1="{oy}" '
            f'x2="{ox + gx}" y2="{oy + canvas_height}"/>'
        )
    for gy in range(100, canvas_height, 100):
        lines.append(
            f'<line x1="{ox}" y1="{oy + gy}" '
            f'x2="{ox + canvas_width}" y2="{oy + gy}"/>'
        )
    lines.append("</g>")

    # Regions
    for r in regions:
        fill, stroke = _REGION_COLORS.get(r.kind, ("#1a1a2e", "#666"))
        name_esc = html.escape(r.name)
        rx, ry = ox + r.x, oy + r.y

        lines.append("<g>")
        # Rectangle
        lines.append(
            f'<rect x="{rx}" y="{ry}" width="{r.width}" '
            f'height="{r.height}" fill="{fill}" fill-opacity="0.7" '
            f'stroke="{stroke}" stroke-width="3" rx="4"/>'
        )
        # Center label (name)
        cx = rx + r.width // 2
        cy = ry + r.height // 2
        font_size = min(20, max(12, r.width // 10, r.height // 8))
        lines.append(
            f'<text x="{cx}" y="{cy - 8}" text-anchor="middle" '
            f'font-family="monospace" font-size="{font_size}" '
            f'font-weight="bold" fill="{stroke}">{name_esc}</text>'
        )
        # Dimensions
        dim = f"{r.width}x{r.height}"
        lines.append(
            f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" '
            f'font-family="monospace" font-size="12" fill="#888">{dim}</text>'
        )
        # Position marker
        pos = f"({r.x},{r.y})"
        lines.append(
            f'<text x="{rx + 5}" y="{ry + 14}" '
            f'font-family="monospace" font-size="10" fill="#555">{pos}</text>'
        )
        # Kind badge
        lines.append(
            f'<text x="{rx + r.width - 5}" y="{ry + 14}" '
            f'text-anchor="end" font-family="monospace" font-size="10" '
            f'fill="#555">{r.kind}</text>'
        )
        lines.append("</g>")

    # Canvas dimensions footer
    footer_y = oy + canvas_height + 20
    lines.append(
        f'<text x="{vb_w // 2}" y="{footer_y}" text-anchor="middle" '
        f'font-family="monospace" font-size="14" fill="#666">'
        f"Canvas: {canvas_width} x {canvas_height}</text>"
    )

    # Warnings
    if warnings:
        wy = footer_y + 25
        lines.append(
            f'<text x="{ox}" y="{wy}" font-family="monospace" '
            f'font-size="13" font-weight="bold" fill="#f85149">'
            f"Warnings:</text>"
        )
        for i, w in enumerate(warnings):
            lines.append(
                f'<text x="{ox + 10}" y="{wy + 18 + i * 20}" '
                f'font-family="monospace" font-size="12" '
                f'fill="#f0883e">{html.escape(w)}</text>'
            )

    lines.append("</svg>")
    return "\n".join(lines)
