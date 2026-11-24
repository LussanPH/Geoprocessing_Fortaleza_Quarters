# Mini-projeto: denúncias × vistorias com PostGIS e QGIS

Projeto de treino para a vaga de estágio na GEING/AGEFIS. Ele reproduz, com dados **fictícios**, o tipo de trabalho descrito na vaga: guardar dados territoriais no PostgreSQL/PostGIS, cruzar registros de denúncias e vistorias para achar áreas com recorrência de descarte irregular e mostrar o resultado em mapas (QGIS e mapa web).

> Todos os dados de denúncias e vistorias são inventados pelo script `gen_fake_data.py`. Nada aqui representa dados reais da AGEFIS nem o fluxo real de trabalho dela. Os bairros "críticos" são sorteados, não correspondem a nenhum bairro real.

**Tempo estimado:** meio dia, se tudo instalar sem problemas.
**Você precisa de:** Docker (com Docker Compose), Python 3.10+ e, a partir do passo 7, o QGIS.

```
mini-geoing/
├── docker-compose.yml        # PostgreSQL 16 + PostGIS 3.5
├── requirements.txt
├── data/                     # coloque aqui o arquivo de bairros (passo 4A)
├── scripts/
│   ├── common.py             # conexão e CRS de trabalho (EPSG:31984)
│   ├── load_bairros.py       # carrega bairros e REPROJETA para 31984
│   ├── gen_fake_data.py      # gera denúncias e vistorias fictícias
│   └── make_map.py           # gera mapa.html (Folium)
└── sql/
    ├── 01_schema.sql         # extensão, tabelas e índices espaciais
    ├── 02_consultas.sql      # as análises (junção espacial, raio, grade)
    ├── 03_views.sql          # views para abrir no QGIS
    └── 04_experimento_crs.sql# metros × graus na prática
```

---

## Passo 1: subir o PostGIS com Docker

```bash
docker compose up -d
docker compose logs -f db        # espere aparecer "ready to accept connections" e saia com Ctrl+C
docker compose exec db psql -U geing -d geing -c "SELECT PostGIS_Full_Version();"
```

- A imagem `postgis/postgis:16-3.5` é o PostgreSQL 16 com PostGIS 3.5 já instalado.
- A porta no seu computador é a **5433** (e não a 5432) para não brigar com um Postgres que você já tenha rodando.
- As variáveis `POSTGRES_USER/PASSWORD/DB` só valem na **primeira** inicialização, com a pasta de dados vazia. Se precisar recomeçar do zero: `docker compose down -v`.
- A pasta `sql/` fica montada dentro do contêiner em `/sql`, então os comandos `psql -f /sql/...` funcionam igual em Windows, Mac e Linux.

## Passo 2: ambiente Python

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Os scripts já usam por padrão `localhost:5433`, usuário/senha/banco `geing`. Para mudar, defina `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`.

## Passo 3: criar as tabelas

```bash
docker compose exec db psql -U geing -d geing -f /sql/01_schema.sql
```

Abra o arquivo e leia os comentários. Pontos para entender:

- `geometry(Point, 31984)` já diz **qual CRS** a coluna usa. O banco recusa geometria com SRID diferente.
- O índice `GIST` é o índice espacial. Sem ele, `ST_Intersects` e `ST_DWithin` varrem a tabela inteira.
- Tudo fica em **EPSG:31984** (SIRGAS 2000 / UTM 24S, em metros) para que distância, área e raio sejam em metros.

A saída final do script mostra a tabela `geometry_columns`, onde o PostGIS registra o SRID de cada coluna.

## Passo 4: carregar os bairros

### 4A. Com dados reais (recomendado)

Baixe os polígonos dos bairros de Fortaleza e salve em `data/` (ex.: `data/bairros.geojson`). Onde procurar:

1. **Fortaleza em Mapas** (<https://mapas.fortaleza.ce.gov.br/>): procure a camada de bairros e baixe em GeoJSON ou Shapefile. As camadas dessa plataforma têm um endereço de download no padrão `https://mapas.fortaleza.ce.gov.br/api/download/geojson/<número da camada>`. Eu não consegui confirmar qual número corresponde aos bairros, então use o catálogo do site.
2. **Portal de Dados Abertos de Fortaleza** (<https://dados.fortaleza.ce.gov.br/>): busque por "bairros".
3. **IBGE, Malha de Bairros do Censo 2022**: cobre o país inteiro, mas a própria documentação avisa que, em alguns casos, os limites originais dos bairros foram aproximados graficamente por meio dos setores censitários.

Se baixar Shapefile, mantenha **todos** os arquivos juntos (`.shp`, `.dbf`, `.shx` e `.prj`). O `.prj` é o arquivo que guarda o CRS.

Antes de carregar, **inspecione** o arquivo (este é o hábito mais importante do projeto):

```bash
python -c "import geopandas as gpd; g=gpd.read_file('data/bairros.geojson'); print('CRS:', g.crs); print('linhas:', len(g)); print(g.columns.tolist()); print(g.head(3))"
```

Veja: qual é o CRS? Qual coluna tem o nome do bairro? Quantas linhas (Fortaleza tem 121 bairros desde a atualização de 2019)? Depois carregue:

```bash
python scripts/load_bairros.py --file data/bairros.geojson --name-col NOME_DA_COLUNA
# se o arquivo não informar o CRS:  --source-crs EPSG:4326   (use o CRS correto!)
# se tiver coluna de regional:      --regional-col REGIONAL
```

O script limpa espaços e quebras de linha dos nomes (dados reais vêm sujos: uma camada do portal da prefeitura, por exemplo, traz `"Messejana\n"` no campo de bairro), reprojeta para 31984 e grava. Se o número de bairros ou a área total parecer estranho, volte e investigue o arquivo antes de seguir.

### 4B. Sem baixar nada (grade fictícia)

```bash
python scripts/load_bairros.py --demo-grid
```

Cria 64 "bairros fictícios" (uma grade) sobre uma caixa **aproximada** de Fortaleza. Serve para fazer o resto do projeto funcionar hoje e trocar pelos dados reais depois.

## Passo 5: gerar denúncias e vistorias fictícias

```bash
python scripts/gen_fake_data.py --n-denuncias 3000 --seed 42
```

O que o script simula:

- 3.000 denúncias nos últimos 365 dias, de cinco tipos (`descarte_irregular`, `poluicao_sonora`, `poluicao_visual`, `comercio_irregular`, `vigilancia_sanitaria`);
- "pontos crônicos" de descarte irregular: aglomerados em 5 bairros sorteados;
- vistorias que respondem a parte das denúncias (atendendo menos os pontos crônicos) e 300 vistorias de "busca ativa";
- **sem chave ligando vistoria a denúncia.** O vínculo tem que ser descoberto por proximidade e data, que é o desafio de cruzar bases de sistemas diferentes.

Rodar de novo com a mesma `--seed` gera exatamente os mesmos dados; as tabelas são esvaziadas antes de cada carga.

## Passo 6: fazer as análises em SQL

```bash
docker compose exec db psql -U geing -d geing -f /sql/02_consultas.sql
```

Leia cada consulta com calma, execute uma por vez (DBeaver, pgAdmin ou o DB Manager do QGIS) e altere os parâmetros.

| # | Pergunta | O que ensina |
|---|---|---|
| 0 | Quantas linhas e qual SRID em cada tabela? | Conferir CRS é o primeiro passo de toda análise |
| 1 | Denúncias por bairro | Junção espacial com `ST_Intersects` (ponto dentro de polígono) |
| 2 | Denúncias por km² | `ST_Area` devolve m² porque o CRS é projetado |
| 3 | Denúncias sem vistoria em 100 m e 30 dias | `ST_DWithin` (raio em metros) + janela de datas |
| 4 | Taxa de atendimento por bairro | Cruzar duas bases e agregar por território |
| 5 | Tempo até a primeira vistoria próxima | `LEFT JOIN LATERAL` para "pegar a primeira correspondência" |
| 6 | Recorrência em grade de 250 m, 90 dias | Grade feita só com `FLOOR(x / 250)`, possível porque x e y estão em metros |

Verificação rápida (com a grade fictícia): na consulta 1, os 5 bairros sorteados como críticos devem aparecer no topo, com muito mais denúncias que os demais. Se isso acontecer, sua junção espacial está funcionando.

## Passo 7: criar views e abrir no QGIS

```bash
docker compose exec db psql -U geing -d geing -f /sql/03_views.sql
```

Isso cria `vw_hotspots_250m` (células com recorrência de descarte) e `vw_denuncias_pendentes`.

No QGIS (os nomes dos menus podem variar com a versão e o idioma; consulte <https://docs.qgis.org>):

1. Camada → Adicionar Camada → Adicionar Camada PostGIS → **Novo**. Host `localhost`, porta `5433`, banco `geing`, autenticação básica com usuário `geing` e senha `geing`. Conecte.
2. Adicione `bairros`, `denuncias`, `vw_hotspots_250m` e `vw_denuncias_pendentes`. Para as views, escolha a coluna `id` como chave primária quando o QGIS perguntar.
3. Em Projeto → Propriedades → SRC, defina **EPSG:31984**. Para camadas PostGIS o QGIS usa o SRID declarado na criação da tabela e reprojeta tudo "na hora" para o CRS do projeto.
4. Simbologia: `vw_hotspots_250m` como **Graduado** por `denuncias_90d`; `denuncias` como **Mapa de calor**; `bairros` só com contorno.
5. Abra o **DB Manager**, rode uma consulta do passo 6 e use a opção de adicionar o resultado ao mapa como camada.
6. Monte um layout de impressão com título, legenda e escala e exporte em PDF.

## Passo 8: experimento de CRS (a lição mais importante)

```bash
docker compose exec db psql -U geing -d geing -f /sql/04_experimento_crs.sql
```

Você compara a mesma distância em três situações e vê a armadilha:

| | Resultado na minha execução de teste (grade fictícia, seed 42) |
|---|---|
| A. CRS projetado (31984) | ~12.520 **metros** |
| B. Depois de `ST_Transform` para 4326 | ~0,113 **graus** |
| C. 4326 com o tipo `geography` | ~12.525 **metros** (a pequena diferença vem de toda projeção distorcer um pouco) |
| D. Pares "a 100 m" entre 200 denúncias | 45 no projetado; 19.900 (todos os pares) em 4326, porque "100" vira 100 **graus** |

Seus números vão variar se usar bairros reais. O que importa é o padrão: **em lat/long, medir em metros exige `geography` ou reprojetar antes.**

## Passo 9 (opcional): mapa web interativo

```bash
python scripts/make_map.py
```

Gera `mapa.html` com bairros, células de recorrência coloridas por número de denúncias e os pontos pendentes (camada desligada por padrão, ligue no controle de camadas). Abra no navegador (precisa de internet para o mapa de fundo). Repare que o banco trabalha em 31984 e o script reprojeta para 4326 **só na saída**, porque mapas web esperam lat/long.

## Passo 10: desafios para ir além

1. **Pesos:** crie um índice de prioridade por célula (por exemplo, pendentes × recorrência) e ordene as vistorias que você faria primeiro.
2. **Vínculo melhor:** faça o cruzamento também por `tipo` e compare quantas denúncias passam a ficar "sem vistoria".
3. **Geocodificação ruim:** em `gen_fake_data.py`, aumente o desvio do ponto da vistoria (de 25 m para 150 m) e veja o que acontece com a taxa de atendimento. Esse é o efeito de endereços mal geocodificados.
4. **Duplicatas:** crie denúncias repetidas no mesmo local e escreva uma consulta que as agrupe (`ST_ClusterDBSCAN`).
5. **Performance:** rode a consulta 3 com `EXPLAIN ANALYZE`, depois apague o índice `denuncias_geom_gix` e compare.
6. **Painel:** leve `vw_hotspots_250m` para o Power BI ou para o Streamlit com Folium.

## Como contar o projeto na entrevista

"Montei um PostGIS com Docker, carreguei a malha de bairros reprojetada para SIRGAS 2000 / UTM 24S e gerei denúncias e vistorias fictícias. Cruzei as duas bases por proximidade (100 m) e janela de datas para achar denúncias sem vistoria e áreas com recorrência de descarte irregular, e publiquei o resultado no QGIS e num mapa web. O maior aprendizado foi o CRS: medir em graus quebra qualquer análise de distância."

Seja claro de que os dados são fictícios e que você quer aprender como a equipe faz o vínculo e a priorização de verdade.

## Notas de verificação

- Os scripts Python e os arquivos SQL foram executados de ponta a ponta contra PostgreSQL 16 com PostGIS 3.4 (instalação local, e não a imagem Docker). Nada usado é específico da versão 3.5.
- O `docker-compose.yml` e os passos do QGIS **não foram executados** por quem escreveu este guia. Se algum comando falhar no seu ambiente, o erro costuma ser de porta ocupada (altere `5433` no compose e em `PGPORT`) ou de nome de menu do QGIS.

## Fontes

- Imagem Docker do PostGIS (variáveis de ambiente, comportamento com pasta de dados vazia): <https://github.com/postgis/docker-postgis>
- Tags disponíveis (ex.: `16-3.5`), no espelho da documentação do mesmo repositório: <https://gitee.com/mirrors_postgis/docker-postgis>
- O que é o PostGIS (manual oficial): <https://postgis.net/docs/manual-3.7/postgis_introduction.html>
- QGIS, trabalho com projeções e camadas PostGIS: <https://docs.qgis.org/3.40/ta/docs/user_manual/working_with_projections/working_with_projections.html>
- EPSG:31984 (SIRGAS 2000 / UTM zona 24S), citado na ficha de transformação do EPSG: <https://epsg.io/5534-5529>
- Fortaleza com 121 bairros após o decreto de 2019: <https://diariodonordeste.verdesmares.com.br/metro/decreto-atualiza-divisoes-e-fortaleza-passa-a-ter-121-bairros-1.2158168>
- Padrão de download de camadas do Fortaleza em Mapas (exemplo com `"BAIRRO":"Messejana\n"`): <https://mapas.fortaleza.ce.gov.br/api/download/geojson/664>
- Malha de Bairros do Censo 2022 (IBGE), com o aviso sobre limites aproximados: <https://metadadosgeo.ibge.gov.br/geonetwork_ibge/srv/api/records/c0a902c4-1e02-43b3-ac7b-1318cc733da5>
