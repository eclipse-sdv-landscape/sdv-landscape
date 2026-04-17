# Eclipse SDV Projects - Landscape2

Creates a static site via the [Landscape2] project for the Eclipse SDV Projects.

## Build

Prerequisites: ensure you've got Docker Compose installed

```shell
docker compose --env-file .env.stable run --rm l2-build
```

## Serve

Prerequisites: ensure you've got Docker Compose installed

```shell
docker compose --env-file .env.stable run --rm --service-ports l2-serve
```

Open: `http://127.0.0.1:8000/sdv-landscape/`

If you still see missing logos/guide from older volume contents, recreate the volume and rebuild:
```shell
docker compose --env-file .env.stable down -v
docker compose --env-file .env.stable run --rm l2-build
```

## Extracting built site


```shell
mkdir -p build
docker compose --env-file .env.stable run --rm l2-export | tar -C build -xf -
```

or using:
```shell
mkdir -p build
docker run --rm -v sdv-landscape_l2_site:/site:ro -v "$PWD/build:/output" busybox:1.36 sh -c "cp -a /site/. /output/"
```

Then serve from `build/` and open the `base_path` URL:
```shell
cd build
python3 -m http.server 8000
```

Open: `http://127.0.0.1:8000/sdv-landscape/`

If you want to serve at `/` instead, set `base_path: /` in `settings.yml` and rebuild.

Note: with the current compose setup, the extracted site is expected at `build/sdv-landscape/`.

## Note on stable and latest

Any command above can also be run using `--env-file .env.latest`
to use the latest available distributed [Landscape2] Docker image.

For example:
```shell
docker compose --env-file .env.latest run --rm l2-build
```

[Landscape2]: https://github.com/cncf/landscape2

# Collect new data from Eclipse Projects API (with static categories)
Hint: execute in the root folder
Modifiy the static_categories.yml to map all the projects static. 
```shell
python ./tools/generate_data_static.py --categories static_categories.yml --output data.yml 
```
