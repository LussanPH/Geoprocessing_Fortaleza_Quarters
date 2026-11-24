-- 03_views.sql
-- Views prontas para abrir no QGIS (e no mapa HTML). Cada uma tem uma coluna id inteira única.

-- Células de 250 m com recorrência de descarte irregular nos últimos 90 dias.
CREATE OR REPLACE VIEW vw_hotspots_250m AS
WITH base AS (
    SELECT d.geom,
           NOT EXISTS (
               SELECT 1 FROM vistorias v
               WHERE ST_DWithin(d.geom, v.geom, 100)
                 AND v.data_vistoria BETWEEN d.data_denuncia AND d.data_denuncia + 30
           ) AS pendente
    FROM denuncias d
    WHERE d.tipo = 'descarte_irregular'
      AND d.data_denuncia >= CURRENT_DATE - 90
),
celulas AS (
    SELECT FLOOR(ST_X(geom) / 250)::int AS i,
           FLOOR(ST_Y(geom) / 250)::int AS j,
           COUNT(*)                     AS denuncias_90d,
           COUNT(*) FILTER (WHERE pendente) AS sem_vistoria
    FROM base
    GROUP BY 1, 2
)
SELECT ROW_NUMBER() OVER (ORDER BY denuncias_90d DESC, sem_vistoria DESC)::int AS id,
       i, j, denuncias_90d, sem_vistoria,
       ST_MakeEnvelope(i * 250, j * 250, (i + 1) * 250, (j + 1) * 250, 31984)::geometry(Polygon, 31984) AS geom
FROM celulas
WHERE denuncias_90d >= 3;

-- Denúncias ainda sem vistoria próxima (100 m / 30 dias).
CREATE OR REPLACE VIEW vw_denuncias_pendentes AS
SELECT d.id, d.tipo, d.data_denuncia, d.geom::geometry(Point, 31984) AS geom
FROM denuncias d
WHERE NOT EXISTS (
    SELECT 1 FROM vistorias v
    WHERE ST_DWithin(d.geom, v.geom, 100)
      AND v.data_vistoria BETWEEN d.data_denuncia AND d.data_denuncia + 30
);

SELECT 'vw_hotspots_250m' AS view, COUNT(*) AS linhas FROM vw_hotspots_250m
UNION ALL
SELECT 'vw_denuncias_pendentes', COUNT(*) FROM vw_denuncias_pendentes;
