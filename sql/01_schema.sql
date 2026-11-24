-- 01_schema.sql
-- Cria a extensão PostGIS e as três tabelas do projeto.
-- Todas as geometrias ficam em EPSG:31984 (SIRGAS 2000 / UTM 24S), em metros.

CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS vistorias CASCADE;
DROP TABLE IF EXISTS denuncias CASCADE;
DROP TABLE IF EXISTS bairros   CASCADE;

-- Polígonos dos bairros -----------------------------------------------------
CREATE TABLE bairros (
    id       serial PRIMARY KEY,
    nome     text NOT NULL,
    regional text,
    geom     geometry(MultiPolygon, 31984) NOT NULL
);

-- Pontos: uma linha por denúncia ---------------------------------------------
CREATE TABLE denuncias (
    id            serial PRIMARY KEY,
    data_denuncia date NOT NULL,
    tipo          text NOT NULL,
    geom          geometry(Point, 31984) NOT NULL
);

-- Pontos: uma linha por vistoria (com ou sem denúncia por trás: "busca ativa") --
CREATE TABLE vistorias (
    id            serial PRIMARY KEY,
    data_vistoria date NOT NULL,
    autuado       boolean NOT NULL,
    geom          geometry(Point, 31984) NOT NULL
);

-- Índices espaciais (GiST): é o que torna ST_Intersects / ST_DWithin rápidos.
CREATE INDEX bairros_geom_gix   ON bairros   USING GIST (geom);
CREATE INDEX denuncias_geom_gix ON denuncias USING GIST (geom);
CREATE INDEX vistorias_geom_gix ON vistorias USING GIST (geom);
CREATE INDEX denuncias_data_ix  ON denuncias (data_denuncia);
CREATE INDEX vistorias_data_ix  ON vistorias (data_vistoria);

-- Conferência: a versão do PostGIS e o SRID registrado em cada coluna.
SELECT PostGIS_Version() AS postgis;
SELECT f_table_name, f_geometry_column, srid, type
FROM geometry_columns
WHERE f_table_schema = 'public'
ORDER BY f_table_name;
