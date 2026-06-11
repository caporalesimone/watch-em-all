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

## Documentation

The full documentation lives in the [docs/](docs/README.md) folder, organized by layers: business, architecture, features, technical capabilities, API, and plugin development guides.