#!/usr/bin/env python3
"""Gera os icones de categoria do board Wingman Marketing (ClickUp).

Reproduz do zero:
    npm pack simple-icons@13 && tar -xzf simple-icons-*.tgz
    pip install -r requirements-icones.txt && python gerar_icones.py

Saida: icons_out/*.png  (256x256, glifo branco sobre quadrado arredondado na
cor de marca oficial).

Renderizacao: o fundo arredondado sai do Pillow e o glifo sai do svglib, usado
como mascara. A versao anterior montava tudo num SVG unico e rasterizava com
cairosvg, que exige a lib nativa do Cairo e por isso nao roda no Windows.
Geometria conferida contra os PNGs antigos: mesmo tamanho e mesmo centro.
"""
import io
import os
import re

from PIL import Image, ImageDraw
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

# hex oficiais do proprio pacote simple-icons (_data/simple-icons.json)
BRAND = {
    'youtube':  'FF0000',
    'patreon':  '000000',   # rebrand 2023 e preto, nao coral
    'linkedin': '0A66C2',
    'github':   '181717',
    'discord':  '5865F2',
    'gumroad':  'FF90E8',
    'resend':   '000000',
    'n8n':      'EA4B71',
}

SIZE = 256
RADIUS = round(5 / 24 * SIZE)      # rx=5 no viewBox 24
GLYPH = round(0.6 * SIZE)          # scale(0.6)
OFFSET = round(4.8 / 24 * SIZE)    # translate(4.8,4.8)


def rasterizar(svg: str, lado: int) -> Image.Image:
    """SVG -> imagem em tons de cinza.

    dpi=96 porque o reportlab assume 72 e encolheria o desenho em 72/96.
    """
    png = renderPM.drawToString(svg2rlg(io.BytesIO(svg.encode())),
                                fmt='PNG', bg=0xFFFFFF, dpi=96)
    return Image.open(io.BytesIO(png)).convert('L')


def compor(d: str, hexc: str, destino: str) -> None:
    """Glifo branco (path `d`) centralizado sobre o quadrado da cor da marca."""
    glifo = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
             f'width="{GLYPH}" height="{GLYPH}"><path fill="#000000" d="{d}"/></svg>')
    mascara = rasterizar(glifo, GLYPH).point(lambda v: 255 - v)

    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill=f'#{hexc}')
    img.paste((255, 255, 255, 255), (OFFSET, OFFSET), mascara)

    # quantiza pra reduzir o base64 do upload (~2.5k chars por icone)
    img.quantize(colors=32, method=Image.FASTOCTREE).save(destino, optimize=True)


os.makedirs('icons_out', exist_ok=True)

for slug, hexc in BRAND.items():
    src = open(f'package/icons/{slug}.svg', encoding='utf-8').read()
    d = re.search(r'<path[^>]*?d="([^"]+)"', src).group(1)
    compor(d, hexc, f'icons_out/{slug}.png')

# EMAIL nao e marca -> envelope desenhado a mao
ENV = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
       f'width="{SIZE}" height="{SIZE}">'
       '<g fill="none" stroke="#000000" stroke-width="1.6" '
       'stroke-linejoin="round" stroke-linecap="round">'
       '<rect x="5" y="7.5" width="14" height="9.5" rx="1.4"/>'
       '<path d="M5.6 8.4 L12 13 L18.4 8.4"/></g></svg>')
env_mask = rasterizar(ENV, SIZE).point(lambda v: 255 - v)
env = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(env).rounded_rectangle(
    [0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill='#2D7FF9')
env.paste((255, 255, 255, 255), (0, 0), env_mask)
env.quantize(colors=32, method=Image.FASTOCTREE).save('icons_out/email.png', optimize=True)

for f in sorted(os.listdir('icons_out')):
    print(f'{f:15s} {os.path.getsize(f"icons_out/{f}"):6d} bytes')
