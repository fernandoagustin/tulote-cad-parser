#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de Geometría y Poligonización Vectorial para Planos de Agrimensura / Mensura.
Extrae cuadriláteros AutoCAD ('qu'), loops continuos, redes de líneas y números dentro de círculos.
"""

import os
import base64
import pymupdf
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

def process_cad_pdf(pdf_bytes_or_path, target_dpi=72):
    """
    Procesa un PDF de agrimensura y devuelve el render base en base64
    junto con la lista completa de polígonos de lote detectados.
    """
    if isinstance(pdf_bytes_or_path, (bytes, bytearray)):
        doc = pymupdf.open(stream=pdf_bytes_or_path, filetype="pdf")
    else:
        if not os.path.exists(pdf_bytes_or_path):
            return {"success": False, "error": f"Archivo no encontrado: {pdf_bytes_or_path}"}
        doc = pymupdf.open(pdf_bytes_or_path)

    page = doc[0]
    raw_w = float(page.rect.width)
    raw_h = float(page.rect.height)

    # Renderizar imagen de fondo a DPI seleccionado
    pix = page.get_pixmap(dpi=target_dpi)
    img_bytes = pix.tobytes("jpeg")
    img_b64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode("ascii")

    # Factor de escala entre puntos PDF e imagen renderizada
    scale_x = float(pix.width) / raw_w
    scale_y = float(pix.height) / raw_h

    drawings = page.get_drawings()
    lines = []
    polys = []

    # 1. Extraer cuadriláteros AutoCAD ('qu') y loops cerrados
    for d in drawings:
        rect = d['rect']
        # Descartar carátula y tablas laterales extremas
        if rect.x1 > raw_w * 0.88 and rect.y1 > raw_h * 0.70:
            continue

        for it in d['items']:
            if it[0] == 'qu':
                q = it[1]
                p_quad = Polygon([
                    (q.ul.x * scale_x, q.ul.y * scale_y),
                    (q.ur.x * scale_x, q.ur.y * scale_y),
                    (q.lr.x * scale_x, q.lr.y * scale_y),
                    (q.ll.x * scale_x, q.ll.y * scale_y)
                ])
                if p_quad.is_valid and (400 * scale_x * scale_y) <= p_quad.area <= (80000 * scale_x * scale_y):
                    polys.append(p_quad)

        d_lines = [it for it in d['items'] if it[0] == 'l']
        if len(d_lines) >= 3:
            pts = [(it[1].x * scale_x, it[1].y * scale_y) for it in d_lines]
            try:
                p_loop = Polygon(pts)
                if p_loop.is_valid and (400 * scale_x * scale_y) <= p_loop.area <= (80000 * scale_x * scale_y):
                    polys.append(p_loop)
            except Exception:
                pass

        if round(d.get('width', 0) or 0, 2) in (0.72, 0.0, 0.5, 1.0):
            for it in d_lines:
                p1, p2 = it[1], it[2]
                x1, y1 = p1.x * scale_x, p1.y * scale_y
                x2, y2 = p2.x * scale_x, p2.y * scale_y
                dx, dy = x2 - x1, y2 - y1
                if (dx*dx + dy*dy)**0.5 > (2.0 * scale_x):
                    lines.append(LineString([(x1, y1), (x2, y2)]))

    # 2. Polygonizar líneas restantes
    if lines:
        merged = unary_union(lines)
        for p in polygonize(merged):
            if (400 * scale_x * scale_y) <= p.area <= (80000 * scale_x * scale_y):
                polys.append(p)

    # 3. Detectar círculos y textos (números de parcela y manzana)
    words = page.get_text('words')
    lot_numbers = {}
    block_detected = "210"

    # Revisar textos para identificar Manzana
    for w in words:
        txt = w[4].strip()
        if "MANZ" in txt.upper() or "MZA" in txt.upper():
            parts = txt.split()
            if len(parts) > 1 and parts[-1].isalnum():
                block_detected = parts[-1]

    # Detectar números dentro de círculos catastrales
    for d in drawings:
        rect = d['rect']
        w, h = rect.width, rect.height
        if 10 <= w <= 45 and 10 <= h <= 45 and abs(w - h) < 6:
            cx = (rect.x0 + rect.x1) / 2.0
            cy = (rect.y0 + rect.y1) / 2.0
            if cy > raw_h * 0.85:
                continue # Omitir croquis de detalle inferior
            for w_item in words:
                txt = w_item[4].strip()
                if txt.isdigit() and 1 <= int(txt) <= 999:
                    wx = (w_item[0] + w_item[2]) / 2.0
                    wy = (w_item[1] + w_item[3]) / 2.0
                    if abs(wx - cx) < (w/2 + 3) and abs(wy - cy) < (h/2 + 3):
                        lot_numbers[int(txt)] = Point(cx * scale_x, cy * scale_y)

    # Si no se encontraron círculos explícitos, usar números aislados dentro de polígonos
    if len(lot_numbers) < 5:
        for w in words:
            txt = w[4].strip()
            if txt.isdigit() and 1 <= int(txt) <= 999:
                wx = (w[0] + w[2]) / 2.0 * scale_x
                wy = (w[1] + w[3]) / 2.0 * scale_y
                if wx < pix.width * 0.85 and wy < pix.height * 0.85:
                    num = int(txt)
                    if num not in lot_numbers:
                        lot_numbers[num] = Point(wx, wy)

    # 4. Asignación Point-in-Polygon
    matched = {}
    used_polys = set()

    # Pase 1: Inclusión exacta
    for num, pt in lot_numbers.items():
        best_p = None
        min_area = float('inf')
        for i, poly in enumerate(polys):
            if poly.contains(pt):
                if poly.area < min_area:
                    min_area = poly.area
                    best_p = (i, poly)
        if best_p:
            matched[num] = best_p[1]
            used_polys.add(best_p[0])

    # Pase 2: Proximidad de borde (tolerancia 35 px)
    for num, pt in lot_numbers.items():
        if num not in matched:
            best_p = None
            min_dist = float('inf')
            for i, poly in enumerate(polys):
                if i in used_polys:
                    continue
                d = poly.distance(pt)
                if d <= (35.0 * scale_x) and d < min_dist:
                    min_dist = d
                    best_p = (i, poly)
            if best_p:
                matched[num] = best_p[1]
                used_polys.add(best_p[0])

    # Generar resultado formateado
    lots_output = []
    for num, poly in sorted(matched.items(), key=lambda x: x[0]):
        coords = [[round(x, 1), round(y, 1)] for x, y in poly.exterior.coords[:-1]]
        centroid = poly.centroid
        lots_output.append({
            "number": str(num),
            "code": f"M{block_detected}-L{num}",
            "block": block_detected,
            "polygon": coords,
            "centroid": [round(centroid.x, 1), round(centroid.y, 1)],
            "area_px": round(poly.area, 1),
            "status": "DISPONIBLE"
        })

    return {
        "success": True,
        "width": pix.width,
        "height": pix.height,
        "block": block_detected,
        "total_polygons": len(polys),
        "lots_matched": len(lots_output),
        "image_data": img_b64,
        "lots": lots_output
    }

