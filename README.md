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

## Data Generation

The `tools/generate_data_static.py` script fetches project data from the
Eclipse SDV API (or a local JSON file) and generates `data.yml` in the
Landscape2 format.

> **Hint:** Run all commands from the repository root folder.

### Basic usage

Fetch live from the API and write `data.yml`:

```shell
python ./tools/generate_data_static.py --output data.yml
```

Use a previously downloaded JSON file instead:

```shell
python ./tools/generate_data_static.py --input projects.json --output data.yml
```

### Static category mapping

Edit [`static_categories.yml`](static_categories.yml) to control how projects
are grouped into categories and subcategories. The file lists project names
under each subcategory; projects not found in the mapping are placed into an
**Unmapped / Misc** category automatically.

```shell
python ./tools/generate_data_static.py --categories static_categories.yml --output data.yml
```

To generate **only** the category-mapping skeleton (no logos, repos, or
release metadata are fetched):

```shell
python ./tools/generate_data_static.py --output static_categories.generated.yml --mapping-only
```

### Logos

Downloaded logos are stored in the `logos/` directory and referenced by file
name in `data.yml`. Projects that use the generic incubation badge receive an
auto-generated SVG text logo (black project name on white background) instead.

### Verbose output

Pass `-v` / `--verbose` to follow progress in the terminal:

```shell
python ./tools/generate_data_static.py --output data.yml -v
```

The `-v` flag prints labelled messages for every significant action:

| Prefix | Description |
|--------|-------------|
| `[API]` | Fetching projects from the Eclipse SDV API |
| `[FILE]` | Loading projects from a local JSON file |
| `[CATEGORIES]` | Loading the static categories file |
| `[MODE]` | Which grouping mode is active (static / dynamic) |
| `[ITEM]` | Each project item being built |
| `[UNMAPPED]` | Projects not found in the static category mapping |
| `[GITHUB]` | GitHub organisation repository discovery |
| `[RELEASE]` | Fetching latest release / tag metadata per repository |
| `[LOGO]` | Logo download, text-SVG generation, or fallback |
| `[OUTPUT]` | Writing the final YAML file |

### GitHub API rate limits

For unauthenticated requests the GitHub API rate limit is reached quickly.
Pass a personal access token via `--github-token` or set the `GITHUB_TOKEN`
environment variable to raise the limit:

```shell
export GITHUB_TOKEN=ghp_...
python ./tools/generate_data_static.py --output data.yml
```

### All options

```
usage: generate_data_static.py [-h] [--input INPUT] [--output OUTPUT]
                                [--categories CATEGORIES]
                                [--github-token GITHUB_TOKEN] [-v]

options:
  --input INPUT         Local JSON file with project data (skips API call)
  --output OUTPUT       Output YAML file (default: data.yml)
  --categories FILE     Static categories YAML (default: static_categories.yml)
  --github-token TOKEN  GitHub personal access token
  -v, --verbose         Enable verbose progress output
```
