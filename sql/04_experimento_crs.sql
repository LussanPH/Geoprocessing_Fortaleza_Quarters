-- 04_experimento_crs.sql
-- Objetivo: ver na prática por que o CRS importa.

\echo '--- A. Distância entre duas denúncias no CRS projetado (31984): resultado em METROS'
SELECT ST_Distance(a.geom, b.geom) AS metros
FROM denuncias a, denuncias b
WHERE a.id = 1 AND b.id = 2;

\echo '--- B. A mesma distância depois de transformar para lat/long (4326): resultado em GRAUS'
SELECT ST_Distance(ST_Transform(a.geom, 4326), ST_Transform(b.geom, 4326)) AS graus
FROM denuncias a, denuncias b
WHERE a.id = 1 AND b.id = 2;

\echo '--- C. De novo em 4326, mas com o tipo geography: o PostGIS calcula em METROS sobre o elipsoide'
SELECT ST_Distance(ST_Transform(a.geom, 4326)::geography, ST_Transform(b.geom, 4326)::geography) AS metros_geography
FROM denuncias a, denuncias b
WHERE a.id = 1 AND b.id = 2;

\echo '--- D. A armadilha: pares de denúncias "a 100 m" entre as 200 primeiras'
SELECT
  (SELECT COUNT(*) FROM denuncias a JOIN denuncias b ON a.id < b.id AND a.id <= 200 AND b.id <= 200
     AND ST_DWithin(a.geom, b.geom, 100))                                        AS pares_projetado_100m,
  (SELECT COUNT(*) FROM denuncias a JOIN denuncias b ON a.id < b.id AND a.id <= 200 AND b.id <= 200
     AND ST_DWithin(ST_Transform(a.geom, 4326), ST_Transform(b.geom, 4326), 100)) AS pares_4326_100_graus;
-- No 4326 o "100" significa 100 GRAUS, então praticamente todos os 19.900 pares passam no teste.
