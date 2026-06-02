# Distributed Services

This folder starts the minimum external services for a server deployment of Democr.ai:

- Redis
- PostgreSQL
- Neo4j
- Milvus standalone
- MinIO for local AWS S3-compatible media storage

The bundled [config.yaml](docker/distributed/config.yaml) is meant for running the app on the host machine and talking to the containers through `localhost`.

## Start

```bash
cd docker/distributed
cp .env.example .env
docker compose up -d
```

## Stop

```bash
docker compose down
```

To also remove data volumes:

```bash
docker compose down -v
```

## App Config

Use:

- [config.yaml](docker/distributed/config.yaml)

Copy its contents into the app data config path or adapt it for your deployment.

Important adjustments before production:

- set a real `auth.jwt_secret`
- change all default passwords in `.env`
- set production-grade S3 credentials and bucket settings under `storage.media`
- if the app itself runs inside Docker, replace `localhost` with the service names:
  - `redis`
  - `postgres`
  - `neo4j`
  - `milvus`

## PostgreSQL Databases

The init script creates:

- `democrai_core`
- `democrai_data`
- `democrai_observability`
- `democrai_ui_state`

## Media S3

The compose stack starts a dedicated `minio-media` service for application media storage. It is separate from the internal MinIO used by Milvus.

Default endpoints:

- S3 API: `http://localhost:9000`
- Console: `http://localhost:9001`
- Bucket: `democrai-media`
- Access key: `democrai`
- Secret key: `democrai-minio-secret`

The `minio-media-init` job creates the bucket and enables anonymous download for local public URL testing. The app config uses:

```yaml
storage:
  media:
    type: s3
    bucket: democrai-media
    endpoint_url: http://localhost:9000
    public_base_url: http://localhost:9000/democrai-media
    use_path_style: true
```

## Notes

- Milvus standalone needs `etcd` and its own internal `minio`; they are included because Milvus does not run alone.
- Neo4j is exposed on Bolt `7687` and HTTP `7474`.
- Redis and Postgres use small Alpine-based images.
