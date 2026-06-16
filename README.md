# watch-em-all

**Watch 'Em All** is a self-hosted application that automatically monitors prices and availability of products on e-commerce sites and notifies the user when it's a good time to buy.

## The problem

People who shop online with an eye on savings end up manually checking the same products on the same sites, day after day: has the price dropped? Is it back in stock? Should I buy now or wait? When the number of products to keep an eye on grows into the dozens, manual checking becomes impractical and good deals get missed.

## The solution

The user specifies **which products to watch** and on **which sites**; the system checks them automatically several times a day, records prices and availability over time, and **notifies the user** when something interesting happens: a product goes on sale, comes back in stock, or — the heart of the product — **a whole cart of products reaches the desired savings**.

The end goal is always the same: **letting the user know that their carts are on sale**, so they can buy at the moment of maximum savings.

## How it works

1. **Scrapers** — Each e-commerce site has its own specialized "watcher". Scrapers are plugins: new ones can be added without touching the rest of the system.
2. **Catalog** — The products extracted by the scrapers flow into each user's personal catalog.
3. **Carts** — The user groups together the products they want to monitor and sets a **savings threshold** and the desired **alert types** on each group.
4. **Automatic monitoring** — A scheduled worker periodically runs the scrapers, updates prices and availability, and records every change in the **price history**.
5. **Notifications** — Everything that changed is collected into a **single aggregated message**, delivered at the time and on the days chosen by the user through the configured channels (e.g. email, Discord). Every notification also remains available in the application's internal history.

## Roles

- **User** — configures what to monitor and receives the notifications.
- **Administrator** — installs the system, creates users, decides when and how much the scrapers run, and monitors the system's health.

## What it is NOT

- It is not a public price comparison tool: it has no global search or rankings.
- It does not buy anything on the user's behalf: it stops at the alert.
- It is not a multi-organization cloud service: it is a single private installation, meant for yourself and a few other users (family or friends).

## Operations manual

> ⚠️ **Under development.** This README is the complete operations manual for the product: every deploy or maintenance command lands here in the same PR that introduces it. The sections below fill up as development progresses ([development flow](docs/development-flow/README.md)).

### Requirements

A Linux host (WSL2 or a dedicated server) with **Docker Engine + the Compose plugin**. Nothing else is ever installed on the host: everything runs in containers.

### Installation (pull-based)

The deploy is **pull-based**: the CI publishes the images to GHCR on every release tag, and you never download the sources — only the **deploy kit**, two files kept in the repo: `deploy/compose.yml` (the release compose, image-based) and `.env.example` (secrets template + image version). Fetch them at the release you want (a published `x.y.z` tag):

```bash
mkdir watchemall && cd watchemall
VERSION=0.0.16        # the release you want (a published tag)
curl -LO https://raw.githubusercontent.com/caporalesimone/watch-em-all/$VERSION/deploy/compose.yml
curl -LO https://raw.githubusercontent.com/caporalesimone/watch-em-all/$VERSION/.env.example
cp .env.example .env          # then fill in the values
docker compose pull
docker compose up -d
```

Fill `.env` before starting: set `WEA_VERSION` to the same release (`$VERSION`; never `latest`), pick strong `POSTGRES_*` values, and set `ADMIN_INITIAL_PASSWORD`. The repository and the GHCR packages are **public**, so both the file download and the image pull are anonymous — no auth. Once up, the app answers on `http://<host>:8080` (in phase 0 this is a placeholder page; the real app arrives in phase 1).

### Updating

No sources, no rebuild — just change the image version and pull:

```bash
# edit .env: WEA_VERSION=<new release>
docker compose pull
docker compose up -d
```

Only the images change; the database volume (`pgdata`) and your `.env` are untouched. Updating is always your choice — nothing is deployed automatically.

### Trying a dev image

Besides releases, you can run a **dev image** to try a branch **before it is merged**: point `WEA_VERSION` at the branch's dev tag instead of a release.

```bash
# in .env
WEA_VERSION=dev-<branch>      # e.g. dev-catalog
docker compose pull
docker compose up -d
```

`dev-<branch>` is **overwritten on every push** to that branch (you always get its latest build) and exists **only while the branch's PR is open** — it is deleted when the PR closes. To pin an exact build use the digest (`watch-em-all@sha256:…`). For normal use, stay on a release `x.y.z`.

### Backup, export and restore

*Coming with phase 1.*

### Troubleshooting

*Coming with phase 1.*

## Development

Development happens entirely inside the [dev container](docs/infrastructure/dev-container.md) — the host only needs Docker.

## Releasing (maintainer)

Releases are **manual**, and the order matters: the **tag** triggers the image build, and the GitHub **release** is the announcement you make **once the images exist**. To cut a release `x.y.z`:

1. Make sure `main` is green and `CHANGELOG.md` has the entry for the version (one PR = one version).
2. Push the tag from the CLI (plain SemVer, no `v` prefix; matching the CHANGELOG):
   ```bash
   git checkout main && git pull
   git tag x.y.z
   git push origin x.y.z
   ```
3. The push triggers the publish workflow, which builds and pushes the versioned images (`watch-em-all`, `watch-em-all-ops`) to GHCR. **Wait for it to go green.**
4. Once the images are up, create the GitHub release **on the existing tag** `x.y.z` (UI: *Draft a new release* → pick the existing tag → write the notes → *Publish*). This does not re-trigger the build.

> Create the tag **before** the release, not the other way around. Publishing a release from the UI with a *new* tag would announce the version before its images are built — a brief window where `docker compose pull` fails, or a published release pointing at a build that then failed. Tag → build → release keeps the release pointing only at images that already exist.

The deploy kit (`deploy/compose.yml` + `.env.example`) is **not** attached to the release — it lives in the repo, and users fetch it at the release tag (see [Installation](#installation-pull-based)).

## Documentation

The full documentation lives in the [docs/](docs/README.md) folder, organized by layers: business, architecture, features, technical capabilities, API, and plugin development guides. It is written in Italian (source of truth); an English equivalent grows phase by phase under [docs-eng/](docs-eng/).