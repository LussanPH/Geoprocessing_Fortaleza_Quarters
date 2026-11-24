-- 02_consultas.sql
-- Consultas de análise. Rode tudo de uma vez ou copie uma por vez no DBeaver / QGIS DB Manager.
-- Pré-requisito: tabelas criadas (01_schema.sql) e dados carregados (scripts Python).

\echo '--- 0. Conferência: SRID das geometrias e contagens'
SELECT 'bairros'   AS tabela, COUNT(*) AS linhas, MIN(ST_SRID(geom)) AS srid FROM bairros
UNION ALL
SELECT 'denuncias', COUNT(*), MIN(ST_SRID(geom)) FROM denuncias
UNION ALL
SELECT 'vistorias', COUNT(*), MIN(ST_SRID(geom)) FROM vistorias;

\echo '--- 1. Denúncias por bairro (junção espacial: ponto dentro de polígono)'
SELECT b.nome, COUNT(d.id) AS total_denuncias
FROM bairros b
LEFT JOIN denuncias d ON ST_Intersects(b.geom, d.geom)
GROUP BY b.id, b.nome
ORDER BY total_denuncias DESC
LIMIT 10;

\echo '--- 2. Densidade: denúncias por km² (ST_Area devolve m², pois o CRS é projetado)'
SELECT b.nome,
       COUNT(d.id)                                              AS total,
       ROUND((ST_Area(b.geom) / 1e6)::numeric, 2)               AS area_km2,
       ROUND((COUNT(d.id) / (ST_Area(b.geom) / 1e6))::numeric, 1) AS denuncias_por_km2
FROM bairros b
LEFT JOIN denuncias d ON ST_Intersects(b.geom, d.geom)
GROUP BY b.id, b.nome, b.geom
ORDER BY denuncias_por_km2 DESC
LIMIT 10;

\echo '--- 3. Denúncias SEM vistoria em até 100 m e até 30 dias depois (as 15 mais antigas)'
SELECT d.id, d.tipo, d.data_denuncia
FROM denuncias d
WHERE NOT EXISTS (
    SELECT 1
    FROM vistorias v
    WHERE ST_DWithin(d.geom, v.geom, 100)          -- 100 = metros, porque o CRS é projetado
      AND v.data_vistoria BETWEEN d.data_denuncia AND d.data_denuncia + 30
)
ORDER BY d.data_denuncia
LIMIT 15;

\echo '--- 4. Taxa de atendimento por bairro (as 10 piores, bairros com 20+ denúncias)'
WITH atendimento AS (
    SELECT d.id, d.geom,
           EXISTS (
               SELECT 1 FROM vistorias v
               WHERE ST_DWithin(d.geom, v.geom, 100)
                 AND v.data_vistoria BETWEEN d.data_denuncia AND d.data_denuncia + 30
           ) AS atendida
    FROM denuncias d
)
SELECT b.nome,
       COUNT(*)                                                           AS denuncias,
       COUNT(*) FILTER (WHERE a.atendida)                                 AS atendidas,
       ROUND(100.0 * COUNT(*) FILTER (WHERE a.atendida) / COUNT(*), 1)    AS pct_atendidas
FROM bairros b
JOIN atendimento a ON ST_Intersects(b.geom, a.geom)
GROUP BY b.id, b.nome
HAVING COUNT(*) >= 20
ORDER BY pct_atendidas ASC
LIMIT 10;

\echo '--- 5. Tempo até a primeira vistoria próxima (dias), por tipo de denúncia'
SELECT d.tipo,
       COUNT(*)                          AS denuncias,
       COUNT(v.id)                       AS com_vistoria,
       ROUND(AVG(v.data_vistoria - d.data_denuncia)::numeric, 1) AS media_dias
FROM denuncias d
LEFT JOIN LATERAL (
    SELECT v.id, v.data_vistoria
    FROM vistorias v
    WHERE ST_DWithin(d.geom, v.geom, 100)
      AND v.data_vistoria BETWEEN d.data_denuncia AND d.data_denuncia + 30
    ORDER BY v.data_vistoria
    LIMIT 1
) v ON true
GROUP BY d.tipo
ORDER BY denuncias DESC;

\echo '--- 6. Recorrência de descarte irregular: grade de 250 m, últimos 90 dias (top 10 células)'
-- A grade é só aritmética com as coordenadas: floor(x / 250). Isso só funciona porque x e y estão em metros.
SELECT FLOOR(ST_X(geom) / 250)::int AS i,
       FLOOR(ST_Y(geom) / 250)::int AS j,
       COUNT(*)                     AS denuncias_90d
FROM denuncias
WHERE tipo = 'descarte_irregular'
  AND data_denuncia >= CURRENT_DATE - 90
GROUP BY 1, 2
ORDER BY denuncias_90d DESC
LIMIT 10;
