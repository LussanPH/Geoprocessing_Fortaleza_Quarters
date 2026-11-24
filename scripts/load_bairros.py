#!/usr/bin/env python3
"""Carrega a malha de bairros no PostGIS, reprojetada para EPSG:31984.

Uso com dados reais (GeoJSON, Shapefile, GPKG...):
    python scripts/load_bairros.py --file data/bairros.geojson --name-col NOME

Uso sem baixar nada (grade fictícia sobre Fortaleza, só para praticar):
    python scripts/load_bairros.py --demo-grid
"""
import argparse
import sys

import geopandas as gpd
from psycopg2.extras import execute_values
from shapely import MultiPolygon, force_2d, make_valid
from shapely.geometry import box

from common import TARGET_EPSG, connect


def demo_grid(nx: int = 8, ny: int = 8) -> gpd.GeoDataFrame:
    """Grade de 'bairros fictícios' sobre uma caixa APROXIMADA de Fortaleza (lat/long)."""
    xmin, xmax, ymin, ymax = -38.64, -38.40, -3.90, -3.69
    dx, dy = (xmax - xmin) / nx, (ymax - ymin) / ny
    rows = []
    for j in range(ny):
        for i in range(nx):
            n = j * nx + i + 1
            rows.append(
                {
                    "nome": f"Bairro Ficticio {n:02d}",
                    "regional": f"Regional {(i // (nx // 2)) + 2 * (j // (ny // 2)) + 1}",
                    "geometry": box(xmin + i * dx, ymin + j * dy, xmin + (i + 1) * dx, ymin + (j + 1) * dy),
                }
            )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def to_multipolygon(geom):
    """Garante MultiPolygon 2D válido (a tabela exige esse tipo)."""
    if geom is None or geom.is_empty:
        return None
    geom = make_valid(force_2d(geom))
    if geom.geom_type == "MultiPolygon":
        return geom
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    parts = []
    for g in getattr(geom, "geoms", []):  # GeometryCollection resultante do make_valid
        if g.geom_type == "Polygon":
            parts.append(g)
        elif g.geom_type == "MultiPolygon":
            parts.extend(g.geoms)
    return MultiPolygon(parts) if parts else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="arquivo com os polígonos dos bairros")
    ap.add_argument("--name-col", help="coluna com o nome do bairro")
    ap.add_argument("--regional-col", help="(opcional) coluna com a regional")
    ap.add_argument("--source-crs", help="CRS de origem, se o arquivo não informar (ex.: EPSG:4326)")
    ap.add_argument("--demo-grid", action="store_true", help="usa uma grade fictícia em vez de um arquivo")
    args = ap.parse_args()

    if args.demo_grid:
        gdf = demo_grid()
    else:
        if not args.file:
            sys.exit("Informe --file (ou use --demo-grid).")
        gdf = gpd.read_file(args.file)
        print("Colunas do arquivo:", [c for c in gdf.columns if c != "geometry"])
        if not args.name_col or args.name_col not in gdf.columns:
            sys.exit("Informe --name-col com uma das colunas acima.")
        if gdf.crs is None:
            if not args.source_crs:
                sys.exit("O arquivo não informa o CRS. Descubra qual é e passe --source-crs (ex.: EPSG:4326).")
            gdf = gdf.set_crs(args.source_crs)
        gdf = gdf.rename(columns={args.name_col: "nome"})
        if args.regional_col:
            gdf = gdf.rename(columns={args.regional_col: "regional"})
        # Dados reais vêm "sujos": espaços e quebras de linha no fim do texto são comuns.
        gdf["nome"] = gdf["nome"].astype(str).str.strip()

    if "regional" not in gdf.columns:
        gdf["regional"] = None

    print("CRS de origem :", gdf.crs)
    gdf = gdf.to_crs(TARGET_EPSG)  # a reprojeção acontece aqui
    print("CRS de destino:", gdf.crs)

    rows = []
    for nome, regional, geom in zip(gdf["nome"], gdf["regional"], gdf.geometry):
        mp = to_multipolygon(geom)
        if mp is not None:
            rows.append((nome, None if regional is None else str(regional).strip(), mp.wkt))

    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE bairros RESTART IDENTITY")
        execute_values(
            cur,
            "INSERT INTO bairros (nome, regional, geom) VALUES %s",
            rows,
            template=f"(%s, %s, ST_Multi(ST_GeomFromText(%s, {TARGET_EPSG})))",
        )
        cur.execute("ANALYZE bairros")
        cur.execute("SELECT COUNT(*), ROUND((SUM(ST_Area(geom)) / 1e6)::numeric, 1) FROM bairros")
        n, km2 = cur.fetchone()

    print(f"OK: {n} bairros carregados, área total {km2} km² (calculada em metros, graças ao CRS projetado).")


if __name__ == "__main__":
    main()
