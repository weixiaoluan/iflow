"""生成 iFlow 中转工具图标 (.ico)"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 圆角矩形背景 - 深蓝渐变色
        margin = max(1, size // 16)
        radius = max(2, size // 6)
        # 主背景色: 深蓝色
        bg_color = (30, 85, 130, 255)
        draw.rounded_rectangle(
            [margin, margin, size - margin - 1, size - margin - 1],
            radius=radius, fill=bg_color
        )

        # 内层光泽 - 稍亮的蓝色条纹
        inner_margin = max(2, size // 8)
        accent_color = (45, 120, 180, 80)
        draw.rounded_rectangle(
            [inner_margin, inner_margin, size - inner_margin - 1, size // 2],
            radius=max(1, radius // 2), fill=accent_color
        )

        # 绘制 "iF" 文字
        font_size = max(8, int(size * 0.5))
        try:
            font = ImageFont.truetype("consola.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

        text = "iF"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) // 2
        ty = (size - th) // 2 - bbox[1]

        # 文字阴影
        shadow_offset = max(1, size // 64)
        draw.text((tx + shadow_offset, ty + shadow_offset), text, fill=(0, 0, 0, 100), font=font)
        # 白色文字
        draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

        # 底部小箭头装饰 (代表"中转/流转")
        arrow_y = size - inner_margin - max(2, size // 10)
        arrow_size = max(2, size // 12)
        arrow_color = (78, 203, 113, 220)
        cx = size // 2
        draw.polygon([
            (cx - arrow_size * 2, arrow_y),
            (cx, arrow_y + arrow_size),
            (cx + arrow_size * 2, arrow_y),
        ], fill=arrow_color)

        images.append(img)

    # 保存为 .ico
    ico_path = os.path.join(os.path.dirname(__file__), "iflow.ico")
    images[0].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    print(f"Icon saved: {ico_path}")

if __name__ == "__main__":
    create_icon()
