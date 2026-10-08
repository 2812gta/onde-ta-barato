# ADR 0007: UI do comerciante e cálculo de distância no MVP

Status: **Aceita**

- **Comerciante:** Django Admin restrito por papel no MVP (M6); portal próprio só depois, se houver demanda.
- **Distância:** linha reta/geodésica via PostGIS (`ST_DWithin`, `ST_Distance` em geography). Rota real (OSRM/Google) fica para depois, com ADR de custo e termos de uso. O custo de deslocamento usa um R$/km configurável.
