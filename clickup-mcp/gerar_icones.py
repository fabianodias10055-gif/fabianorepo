#!/usr/bin/env python3
"""Gera os icones de categoria do board Wingman Marketing (ClickUp).

Reproduz do zero: npm pack simple-icons@13 && pip install cairosvg && python3 gerar_icones.py
Saida: icons_out/*.png  (256x256, glifo branco sobre quadrado arredondado na cor de marca)
"""
import re, os, cairosvg
from PIL import Image

# hex oficiais do proprio pacote simple-icons (_data/simple-icons.json)
BRAND = {
    'youtube':  'FF0000',
    'patreon':  '000000',   # rebrand 2023 e preto, nao coral
    'linkedin': '0A66C2',
    'github':   '181717',
    'discord':  '5865F2',
    'gumroad':  'FF90E8',
}

TPL = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
       '<rect width="24" height="24" rx="5" fill="#{bg}"/>'
       '<g transform="translate(4.8,4.8) scale(0.6)">'
       '<path fill="#FFFFFF" d="{d}"/></g></svg>')

os.makedirs('icons_out', exist_ok=True)

for slug, hexc in BRAND.items():
    src = open(f'package/icons/{slug}.svg').read()
    d = re.search(r'<path[^>]*?d="([^"]+)"', src).group(1)
    cairosvg.svg2png(bytestring=TPL.format(bg=hexc, d=d).encode(),
                     write_to=f'icons_out/{slug}.png',
                     output_width=256, output_height=256)

# EMAIL nao e marca -> envelope desenhado a mao
ENV = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
       '<rect width="24" height="24" rx="5" fill="#2D7FF9"/>'
       '<g fill="none" stroke="#FFFFFF" stroke-width="1.6" '
       'stroke-linejoin="round" stroke-linecap="round">'
       '<rect x="5" y="7.5" width="14" height="9.5" rx="1.4"/>'
       '<path d="M5.6 8.4 L12 13 L18.4 8.4"/></g></svg>')
cairosvg.svg2png(bytestring=ENV.encode(), write_to='icons_out/email.png',
                 output_width=256, output_height=256)

# quantiza pra reduzir o base64 do upload (~2.5k chars por icone)
for f in sorted(os.listdir('icons_out')):
    p = f'icons_out/{f}'
    Image.open(p).convert('RGBA').quantize(
        colors=32, method=Image.FASTOCTREE).save(p, optimize=True)
    print(f'{f:15s} {os.path.getsize(p):6d} bytes')
