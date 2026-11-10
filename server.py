#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor FastAPI para el Importador y Mapeador CAD de Parcelas.
Procesa planos PDF en tiempo real y devuelve las geometrías exactas.
"""

import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from cad_engine import process_cad_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")

app = FastAPI(
    title="TuLote CAD Plan Importer",
    description="Microservicio FastAPI para importación, detección y poligonización exacta de planos de agrimensura",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html no encontrado")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se admiten archivos PDF de agrimensura")

    try:
        content = await file.read()
        result = process_cad_pdf(content)
        if not result.get("success"):
            raise HTTPException(status_code=422, detail=result.get("error", "Error procesando vectores"))
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sample/{name}")
async def get_sample(name: str):
    filename_map = {
        "los_cerritos": "los_cerritos.pdf",
        "saenz_funes": "saenz_funes.pdf"
    }
    fname = filename_map.get(name)
    if not fname:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    pdf_path = os.path.join(SAMPLES_DIR, fname)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"Archivo {fname} no existe")

    result = process_cad_pdf(pdf_path)
    return JSONResponse(content=result)

@app.post("/api/export-geojson")
async def export_geojson(data: dict):
    lots = data.get("lots", [])
    features = []
    for lot in lots:
        poly_coords = lot.get("polygon", [])
        if len(poly_coords) >= 3:
            # Asegurar cierre de anillo
            ring = list(poly_coords)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            features.append({
                "type": "Feature",
                "properties": {
                    "number": lot.get("number"),
                    "code": lot.get("code"),
                    "block": lot.get("block"),
                    "area_px": lot.get("area_px"),
                    "status": lot.get("status", "DISPONIBLE")
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring]
                }
            })
    return JSONResponse(content={
        "type": "FeatureCollection",
        "features": features
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8095))
    print("==================================================================")
    print(f"   INICIANDO TULOTE CAD PLAN IMPORTER (FastAPI) EN PUERTO {port}   ")
    print(f"   Abrí tu navegador en: http://localhost:{port}                    ")
    print("==================================================================")
    uvicorn.run(app, host="0.0.0.0", port=port)
