import io
import qrcode
from PIL import Image, ImageDraw, ImageFont


def generate_qr(data: str, box_size: int = 10, border: int = 2) -> bytes:
    img = qrcode.make(data, box_size=box_size, border=border)
    buffer = io.BytesIO()
    img.save(buffer, 'PNG')
    return buffer.getvalue()


def _get_font(size: int = 18):
    try:
        return ImageFont.truetype('arial.ttf', size)
    except OSError:
        try:
            return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
        except OSError:
            return ImageFont.load_default()


def generate_qr_with_text(data: str, text: str, width: int = 600, height: int = 300) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white')

    # Scale QR to fit nicely
    qr_size = min(height - 60, int(height * 0.55))
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

    label = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(label)

    # Center QR
    qr_x = (width - qr_size) // 2
    qr_y = 20
    label.paste(qr_img, (qr_x, qr_y))

    # Draw text below QR
    font = _get_font(20)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    text_x = (width - text_w) // 2
    text_y = qr_y + qr_size + 20
    draw.text((text_x, text_y), text, fill='black', font=font)

    buffer = io.BytesIO()
    label.save(buffer, 'PNG')
    return buffer.getvalue()


def generate_labels_pdf(items: list) -> bytes:
    images = []
    for item in items:
        png_bytes = generate_qr_with_text(item['code'], item['name'] or item['code'])
        img = Image.open(io.BytesIO(png_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        images.append(img)

    if not images:
        return b''

    buffer = io.BytesIO()
    images[0].save(
        buffer,
        'PDF',
        save_all=True,
        append_images=images[1:],
        resolution=300.0,
    )
    return buffer.getvalue()
