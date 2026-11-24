#!/usr/bin/env python3
"""Gera mapa.html (mapa interativo) a partir das views do PostGIS.

    python scripts/make_map.py
Depois abra mapa.html no navegador.
"""
import folium
import geopandas as gpd
from branca.colormap import linear
from sqlalchemy import create_engine

from common import sqlalchemy_url


def main() -> None:
    eng = create_engine(sqlalchemy_url())

    bairros = gpd.read_postgis("SELECT nome, geom FROM bairros", eng, geom_col="geom")
    celulas = gpd.read_postgis(
        "SELECT id, denuncias_90d, sem_vistoria, geom FROM vw_hotspots_250m", eng, geom_col="geom"
    )
    pendentes = gpd.read_postgis(
        """SELECT id, tipo, data_denuncia::text AS data_denuncia, geom
           FROM vw_denuncias_pendentes
           WHERE tipo = 'descarte_irregular'
           ORDER BY data_denuncia DESC
           LIMIT 500""",
        eng,
        geom_col="geom",
    )

    # O banco trabalha em 31984 (metros); mapas web esperam lat/long (4326): reprojeta só na saída.
    bairros, celulas, pendentes = (g.to_crs(4326) for g in (bairros, celulas, pendentes))

    minx, miny, maxx, maxy = bairros.total_bounds
    m = folium.Map(location=[(miny + maxy) / 2, (minx + maxx) / 2], zoom_start=11, tiles="OpenStreetMap")

    folium.GeoJson(
        bairros,
        name="Bairros",
        style_function=lambda f: {"fillOpacity": 0, "color": "#666666", "weight": 1},
        tooltip=folium.GeoJsonTooltip(fields=["nome"], aliases=["Bairro"]),
    ).add_to(m)

    vmax = max(int(celulas["denuncias_90d"].max()) if len(celulas) else 1, 1)
    cmap = linear.YlOrRd_09.scale(0, vmax)
    cmap.caption = "Denúncias de descarte irregular em 90 dias (células de 250 m)"
    folium.GeoJson(
        celulas,
        name="Hotspots 250 m",
        style_function=lambda f: {
            "fillColor": cmap(f["properties"]["denuncias_90d"]),
            "color": "#444444",
            "weight": 0.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["denuncias_90d", "sem_vistoria"], aliases=["Denúncias (90 d)", "Sem vistoria"]
        ),
    ).add_to(m)
    cmap.add_to(m)

    pts = folium.FeatureGroup(name="Denúncias pendentes (descarte)", show=False)
    for _, r in pendentes.iterrows():
        folium.CircleMarker(
            [r.geom.y, r.geom.x], radius=3, color="#1f4e79", fill=True, fill_opacity=0.8,
            tooltip=f"{r.tipo} - {r.data_denuncia}",
        ).add_to(pts)
    pts.add_to(m)

    folium.LayerControl().add_to(m)
    m.save("mapa.html")
    print(f"OK: mapa.html gerado ({len(celulas)} células, {len(pendentes)} pontos pendentes).")


if __name__ == "__main__":
    main()
