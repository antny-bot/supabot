# -*- coding: utf-8 -*-
"""Generate Supabot App Logos for GCP OAuth registration."""

import math
from PIL import Image, ImageDraw, ImageFilter

def create_svg():
    svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4F46E5" />
      <stop offset="50%" stop-color="#7C3AED" />
      <stop offset="100%" stop-color="#9333EA" />
    </linearGradient>
    <linearGradient id="boltGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" />
      <stop offset="60%" stop-color="#EDE9FE" />
      <stop offset="100%" stop-color="#C4B5FD" />
    </linearGradient>
    <linearGradient id="accentGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38BDF8" />
      <stop offset="100%" stop-color="#818CF8" />
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.35" />
    </filter>
    <filter id="boltGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#312E81" flood-opacity="0.3" />
    </filter>
  </defs>

  <!-- Background Squircle with Shadow -->
  <rect x="24" y="24" width="464" height="464" rx="108" fill="url(#bgGrad)" filter="url(#glow)" />

  <!-- Subtle Inner Border Highlight -->
  <rect x="26" y="26" width="460" height="460" rx="106" fill="none" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="3" />

  <!-- Quant Trend Growth Path in Background -->
  <path d="M 96 360 L 192 300 L 272 336 L 416 180" fill="none" stroke="url(#accentGrad)" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" opacity="0.45" />
  <circle cx="416" cy="180" r="10" fill="#38BDF8" opacity="0.6" />

  <!-- Lightning Bolt Main Symbol -->
  <path d="M 288 88 
           L 164 272 
           L 248 272 
           L 224 424 
           L 348 240 
           L 264 240 
           Z" 
        fill="url(#boltGrad)" 
        filter="url(#boltGlow)" 
        stroke="#FFFFFF" 
        stroke-width="4"
        stroke-linejoin="round" />

  <!-- Small sparkling accent dot -->
  <circle cx="370" cy="120" r="8" fill="#FDE047" opacity="0.9" />
</svg>
'''
    with open("manager/frontend/public/logo.svg", "w", encoding="utf-8") as f:
        f.write(svg_content)
    print("Created manager/frontend/public/logo.svg")

def create_pngs():
    # 4x Supersampling for clean antialiasing
    scale = 4
    base_size = 512
    size = base_size * scale
    
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = 28 * scale
    rx = 112 * scale
    
    # Generate background gradient
    grad_img = Image.new("RGBA", (size, size))
    grad_draw = ImageDraw.Draw(grad_img)
    # Diagonal gradient from (79, 70, 229) [indigo-600] to (147, 51, 234) [purple-600]
    c1 = (79, 70, 229)
    c2 = (147, 51, 234)
    for y in range(size):
        for x in range(0, size, 4):
            t = (x + y) / (2 * size)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            grad_draw.rectangle([x, y, x + 3, y], fill=(r, g, b, 255))

    # Mask for squircle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=rx, fill=255)

    # Shadow for squircle
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_pad = 24 * scale
    shadow_draw.rounded_rectangle(
        [shadow_pad, shadow_pad + 12 * scale, size - shadow_pad, size - shadow_pad + 12 * scale],
        radius=rx,
        fill=(15, 10, 40, 90)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(16 * scale))

    # Composite background
    final_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final_canvas.paste(shadow, (0, 0), shadow)
    final_canvas.paste(grad_img, (0, 0), mask)

    draw = ImageDraw.Draw(final_canvas)

    # Inner highlight border
    draw.rounded_rectangle(
        [pad + 3 * scale, pad + 3 * scale, size - pad - 3 * scale, size - pad - 3 * scale],
        radius=rx - 3 * scale,
        outline=(255, 255, 255, 45),
        width=3 * scale
    )

    # Trend line in background
    trend_pts = [
        (96 * scale, 355 * scale),
        (192 * scale, 295 * scale),
        (268 * scale, 335 * scale),
        (416 * scale, 185 * scale)
    ]
    draw.line(trend_pts, fill=(56, 189, 248, 120), width=12 * scale, joint="round")
    draw.ellipse([
        (416 - 12) * scale, (185 - 12) * scale,
        (416 + 12) * scale, (185 + 12) * scale
    ], fill=(56, 189, 248, 180))

    # Bolt shape
    # Bolt coords relative to 512
    bolt_pts = [
        (288 * scale, 92 * scale),
        (168 * scale, 268 * scale),
        (248 * scale, 268 * scale),
        (224 * scale, 420 * scale),
        (344 * scale, 240 * scale),
        (264 * scale, 240 * scale)
    ]

    # Bolt shadow
    bolt_shadow_pts = [
        (x, y + 8 * scale) for (x, y) in bolt_pts
    ]
    draw.polygon(bolt_shadow_pts, fill=(49, 46, 129, 90))

    # Main Bolt (White / Ice blue)
    draw.polygon(bolt_pts, fill=(255, 255, 255, 255), outline=(237, 233, 254, 255))

    # Sparkle dot
    sp_x, sp_y = 370 * scale, 125 * scale
    draw.ellipse([sp_x - 8 * scale, sp_y - 8 * scale, sp_x + 8 * scale, sp_y + 8 * scale], fill=(253, 224, 71, 230))

    # Downsample
    img_512 = final_canvas.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save("manager/frontend/public/logo.png", "PNG")
    print("Created manager/frontend/public/logo.png (512x512)")

    img_120 = final_canvas.resize((120, 120), Image.Resampling.LANCZOS)
    img_120.save("manager/frontend/public/logo-120.png", "PNG")
    print("Created manager/frontend/public/logo-120.png (120x120 GCP Standard)")

    # Favicon
    img_32 = final_canvas.resize((32, 32), Image.Resampling.LANCZOS)
    img_32.save("manager/frontend/public/favicon.ico", format="ICO")
    print("Created manager/frontend/public/favicon.ico")

if __name__ == "__main__":
    create_svg()
    create_pngs()
