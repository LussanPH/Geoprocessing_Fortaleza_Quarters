#!/usr/bin/env python3
"""Gera denúncias e vistorias FICTÍCIAS dentro dos bairros já carregados.

O que os dados simulam (tudo inventado, nada aqui é dado real da AGEFIS):
  * denúncias de vários tipos ao longo dos últimos 365 dias;
  * "pontos crônicos" de descarte irregular: aglomerados em alguns bairros sorteados;
  * vistorias que respondem a parte das denúncias (e atendem menos os pontos crônicos);
  * vistorias de "busca ativa", sem denúncia por trás.
Não existe chave ligando vistoria a denúncia: o vínculo precisa ser feito pelo
cruzamento espacial + temporal, como acontece quando as bases vêm de sistemas diferentes.

Uso:
    python scripts/gen_fake_data.py --n-denuncias 3000 --seed 42
"""
import argparse
from datetime import date, timedelta

import numpy as np
import shapely
from psycopg2.extras import execute_values

from common import TARGET_EPSG, connect

TIPOS = [
    ("descarte_irregular", 0.55),
    ("poluicao_sonora", 0.15),
    ("poluicao_visual", 0.12),
    ("comercio_irregular", 0.10),
    ("vigilancia_sanitaria", 0.08),
]


def random_points_in(poly, n: int, rng) -> np.ndarray:
    """n pontos uniformes dentro de um polígono (amostragem por rejeição)."""
    minx, miny, maxx, maxy = poly.bounds
    out = np.empty((0, 2))
    while len(out) < n:
        xs = rng.uniform(minx, maxx, size=max(n * 3, 50))
        ys = rng.uniform(miny, maxy, size=max(n * 3, 50))
        ok = shapely.contains_xy(poly, xs, ys)
        out = np.vstack([out, np.column_stack([xs[ok], ys[ok]])])
    return out[:n]


def gaussian_points_in(poly, center, sigma_m: float, n: int, rng) -> np.ndarray:
    """n pontos em torno de 'center' (desvio-padrão em METROS), mantidos dentro do polígono."""
    out = np.empty((0, 2))
    while len(out) < n:
        pts = rng.normal(center, sigma_m, size=(max(n * 3, 50), 2))
        ok = shapely.contains_xy(poly, pts[:, 0], pts[:, 1])
        out = np.vstack([out, pts[ok]])
    return out[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-denuncias", type=int, default=3000)
    ap.add_argument("--n-busca-ativa", type=int, default=300)
    ap.add_argument("--n-hotspot-bairros", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    end = date.today()
    start = end - timedelta(days=365)

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nome, ST_AsBinary(geom) FROM bairros ORDER BY id")
        bairros = [(i, n, shapely.from_wkb(bytes(g))) for i, n, g in cur.fetchall()]
        if not bairros:
            raise SystemExit("Tabela bairros vazia. Rode load_bairros.py antes.")

        areas = np.array([g.area for _, _, g in bairros])
        p_area = areas / areas.sum()

        # Bairros "críticos" sorteados + 2 pontos crônicos em cada um (coordenadas em metros).
        n_hot = min(args.n_hotspot_bairros, len(bairros))
        hot_idx = rng.choice(len(bairros), size=n_hot, replace=False)
        centers = []  # (índice do bairro, x, y)
        for bi in hot_idx:
            for x, y in random_points_in(bairros[bi][2], 2, rng):
                centers.append((int(bi), x, y))
        print("Bairros críticos (fictícios):", ", ".join(bairros[int(i)][1] for i in hot_idx))

        # --- Denúncias ------------------------------------------------------------
        tipos = rng.choice([t for t, _ in TIPOS], size=args.n_denuncias, p=[p for _, p in TIPOS])
        dias = rng.integers(0, 366, size=args.n_denuncias)
        denuncias = []  # (data, tipo, x, y, em_ponto_cronico)
        for tipo, d in zip(tipos, dias):
            cronico = tipo == "descarte_irregular" and rng.random() < 0.6
            if cronico:
                bi, cx, cy = centers[rng.integers(len(centers))]
                x, y = gaussian_points_in(bairros[bi][2], (cx, cy), 90.0, 1, rng)[0]
            else:
                bi = rng.choice(len(bairros), p=p_area)
                x, y = random_points_in(bairros[bi][2], 1, rng)[0]
            denuncias.append((start + timedelta(days=int(d)), str(tipo), float(x), float(y), cronico))

        # --- Vistorias ------------------------------------------------------------
        vistorias = []  # (data, autuado, x, y)
        for data_d, tipo, x, y, cronico in denuncias:
            p_atend = 0.45 if cronico else (0.70 if tipo == "descarte_irregular" else 0.50)
            if rng.random() >= p_atend:
                continue
            data_v = data_d + timedelta(days=int(rng.integers(1, 31)))
            if data_v > end:  # ainda não aconteceu
                continue
            dx, dy = rng.normal(0, 25.0, size=2)  # a vistoria cai perto, não exatamente no mesmo ponto
            autuado = bool(rng.random() < (0.40 if tipo == "descarte_irregular" else 0.25))
            vistorias.append((data_v, autuado, float(x + dx), float(y + dy)))

        for _ in range(args.n_busca_ativa):
            bi, cx, cy = centers[rng.integers(len(centers))]
            if rng.random() < 0.5:
                x, y = gaussian_points_in(bairros[bi][2], (cx, cy), 150.0, 1, rng)[0]
            else:
                bj = rng.choice(len(bairros), p=p_area)
                x, y = random_points_in(bairros[bj][2], 1, rng)[0]
            data_v = start + timedelta(days=int(rng.integers(0, 366)))
            vistorias.append((data_v, bool(rng.random() < 0.5), float(x), float(y)))

        # --- Grava ------------------------------------------------------------------
        cur.execute("TRUNCATE denuncias, vistorias RESTART IDENTITY")
        execute_values(
            cur,
            "INSERT INTO denuncias (data_denuncia, tipo, geom) VALUES %s",
            [(d, t, x, y) for d, t, x, y, _ in denuncias],
            template=f"(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), {TARGET_EPSG}))",
        )
        execute_values(
            cur,
            "INSERT INTO vistorias (data_vistoria, autuado, geom) VALUES %s",
            vistorias,
            template=f"(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), {TARGET_EPSG}))",
        )
        cur.execute("ANALYZE denuncias")
        cur.execute("ANALYZE vistorias")

    print(f"OK: {len(denuncias)} denúncias e {len(vistorias)} vistorias gravadas (seed={args.seed}).")


if __name__ == "__main__":
    main()
