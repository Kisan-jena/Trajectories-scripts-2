# Swappa Coverage Documentation
## URL Patterns, Query Parameters & Verifier Reference
**swappa.com**
**Browser-Verified: May 2026**

---

## Overview

This document provides the authoritative reference for Swappa's URL structures, query parameter
encoding, and verifier matching logic. All patterns were validated through dedicated browser
deep-dive sessions against the live production site (May 2026).

> **Important:** Swappa is a **product-catalog marketplace** for used tech (phones, tablets,
> laptops, watches, gaming). Unlike search-based sites (Mercari), navigation is organized
> around specific product pages rather than free-text keyword search. No authentication is
> required to browse or filter listings.

> [!WARNING]
> **Swappa uses TWO page types for the same product!** `/buy/{slug}` shows a product overview
> with carrier/storage grid, while `/listings/{slug}` shows filterable individual listings.
> Clicking a carrier+storage on the `/buy/` page redirects to `/listings/` with query params.

> [!CAUTION]
> **These URL patterns are NOT officially documented by Swappa.** They are reverse-engineered
> from browser observation. Swappa may change parameter names, values, or behavior without
> notice. All patterns documented here were browser-verified in May 2026.

---

## 1. Page Types

| Page Type | URL Pattern | Example |
| :--- | :--- | :--- |
| **Homepage** | `/` | `swappa.com/` |
| **Product Overview** | `/buy/{product-slug}` | `/buy/apple-iphone-15` |
| **Listings (Filterable)** | `/listings/{product-slug}` | `/listings/apple-iphone-15` |
| **Category Browse** | `/buy/{category}` | `/buy/phones` |
| **Individual Listing** | `/listing/view/{listing-id}` | `/listing/view/LAEU99283` |

### Detection Rules

| Rule | Pattern Match | Page Type |
| :--- | :--- | :--- |
| `/buy/{slug}` in path | Product overview (carrier grid) | Buy |
| `/listings/{slug}` in path | Filterable listings with sidebar | Listings |
| `/listing/view/` in path | Single item detail page | Item |
| `/` root only | Homepage | Landing |

> [!IMPORTANT]
> The verifier only processes **buy** and **listings** URLs. Individual listing pages
> (`/listing/view/{id}`) are explicitly ignored and will not produce a match.
> `/buy/` and `/listings/` are treated as **equivalent** for product slug comparison.

---

## 1b. Homepage & Navigation Layout (Browser-Verified May 2026)

```
+------------------------------------------------------------------+
|  [reload] SWAPPA                              [search] Find a good deal      |
+------------------------------------------------------------------+
|  [Applev] [iPhonesv] [Phonesv] [Laptopsv] [Watchesv]            |
|  [Tabletsv] [Gamingv] [Morev] [Sellv]                            |
+------------------------------------------------------------------+
|  [truck] Free Shipping  [no] No Junk, No Jerks                          |
|  [user] Human Support   [shield] PayPal Protection                         |
+------------------------------------------------------------------+
|  Breadcrumb: Swappa / {Category} / {Product}                     |
|                                                                    |
|  {Product Name}        ***** {N reviews}    Starting at ${price} |
|                                                                    |
|  [Product Image]    +---------+---------+----------+----------+  |
|                     |Unlocked |  AT&T   | T-Mobile | Verizon  |  |
|                     |  $319   |  $299   |  $319    |  $349    |  |
|                     +---------+---------+----------+----------+  |
|                     | 128 GB ->| 128 GB ->| 128 GB -> | 128 GB -> |  |
|                     | 256 GB ->| 256 GB ->| 256 GB -> | 256 GB -> |  |
|                     | 512 GB ->|         |          |          |  |
|                     +---------+---------+----------+----------+  |
|                                                                    |
|  [Shop Unlocked [lock]]  [Shop All Listings ->]                       |
|                                                                    |
|  More Carriers:                                                    |
|  AT&T $299 | T-Mobile $319 | Unlocked $319 | Verizon $349       |
|  Mint Mobile | C-Spire | Unlocked Non-US | US Cellular $428     |
|  Boost $329 | Consumer Cellular | Metro by T-Mobile              |
|  Red Pocket | Spectrum $412 | Straight Talk $509                 |
|  TracFone $350 | Xfinity $334                                    |
+------------------------------------------------------------------+
```

Key observations:
- Top navigation bar lists product categories as dropdown menus
- Product overview shows carrier/storage grid with starting prices
- Clicking carrier+storage navigates to `/listings/{slug}?carrier=...&storage=...`
- "More Carriers" section shows ALL available carriers with prices
- No login required — all pages are fully browsable
- No location-based filtering (unlike Facebook Marketplace)

---

## 2. URL Transition Flow

```
swappa.com/                          <- Homepage
    v click category or search
swappa.com/buy/{product-slug}        <- Product overview (carrier grid)
    v click carrier card + storage
swappa.com/listings/{product-slug}?carrier=unlocked&storage=128gb
    v apply sidebar filters          <- Filterable listings
swappa.com/listings/{product-slug}?carrier=unlocked&storage=128gb&condition=mint&sort=price_low
```

### URL Anatomy

**Product overview (no filters):**
```
https://swappa.com/buy/apple-iphone-15
```

**Listings with all filters:**
```
https://swappa.com/listings/apple-iphone-15
  ?carrier=unlocked
  &condition=mint
  &storage=128gb
  &color=black
  &sort=price_low
```


---

## 3. Query Parameters

| Filter | Parameter | Values / Format | Verifier Handling |
| :--- | :--- | :--- | :--- |
| **Carrier** | `carrier` | Slug string (see S4) | Alias-normalized exact match |
| **Condition** | `condition` | `new`, `mint`, `good`, `fair` | Alias-normalized exact match |
| **Storage** | `storage` | `128gb`, `256gb`, `512gb`, `1tb` | Alias-normalized exact match |
| **Color** | `color` | Lowercase slug (see S7) | Case-insensitive exact match |
| **Sort Order** | `sort` | `price_low`, `price_high`, `newest`, `oldest` | Alias-normalized exact match |
| **Model** | `model` | Device model number slug | Exact match |

> [!NOTE]
> Swappa does NOT have a keyword search in URLs. Unlike Mercari (`keyword=`), Swappa uses
> product-specific pages. The search bar shows an autocomplete dropdown that navigates
> directly to a product page — no search results URL is generated.

---

## 4. Carrier Filter (Browser-Verified)

### All Carriers (from iPhone 15 "More Carriers" section)

| UI Label | `carrier` Value | Notes |
| :--- | :--- | :--- |
| Unlocked | `unlocked` | Factory unlocked for all carriers |
| AT&T | `att` | |
| T-Mobile | `tmobile` | |
| Verizon | `verizon` | |
| Sprint | `sprint` | Merged with T-Mobile |
| Boost | `boost` | Boost Mobile |
| Cricket | `cricket` | |
| Mint Mobile | `mint-mobile` | |
| US Cellular | `us-cellular` | |
| C-Spire | `c-spire` | Regional carrier |
| Unlocked Non-US | `unlocked-non-us` | International models |
| Xfinity | `xfinity` | Xfinity Mobile |
| Spectrum | `spectrum` | |
| Straight Talk | `straight-talk` | |
| Metro by T-Mobile | `metro` | |
| Google Fi | `google-fi` | |
| Visible | `visible` | |
| Consumer Cellular | `consumer-cellular` | |
| Red Pocket | `red-pocket` | |
| TracFone | `tracfone` | |
| Total Wireless | `total-wireless` | |

### Carrier Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `t-mobile`, `tmobile` | `tmobile` |
| `us-cellular`, `us_cellular`, `uscellular` | `us-cellular` |
| `mint-mobile`, `mint_mobile`, `mintmobile` | `mint-mobile` |
| `google-fi`, `google_fi`, `googlefi` | `google-fi` |
| `c-spire`, `c_spire`, `cspire` | `c-spire` |
| `at-t` | `att` |
| `metro-by-t-mobile` | `metro` |
| `straight_talk` | `straight-talk` |
| `consumer_cellular`, `consumercellular` | `consumer-cellular` |

### Carrier in Path (Alternative Encoding)

Carriers can also appear as **path segments**:
```
/buy/apple-iphone-15/unlocked   <- carrier in path
/buy/unlocked/iphones           <- carrier as category prefix
```

The verifier checks **both** query params and path segments. Query params take priority.

---

## 5. Condition Filter (Browser-Verified)

| UI Label | `condition` Value |
| :--- | :--- |
| New | `new` |
| Mint | `mint` |
| Good | `good` |
| Fair | `fair` |

**Condition hierarchy:** New > Mint > Good > Fair

### Sidebar Dropdown (Browser-Verified)

```
+----------------------+
| All Conditions    v  | <- Default (no filter)
+----------------------+
| * All Conditions     | <- Highlighted blue
|   New                |
|   Mint               |
|   Good               |
|   Fair               |
+----------------------+
```

### Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `like_new`, `like new`, `excellent` | `mint` |
| `used` | `good` |
| `acceptable` | `fair` |

---

## 6. Sort Options (Browser-Verified)

| UI Label | `sort` Value |
| :--- | :--- |
| Price (Low) | `price_low` |
| Price (High) | `price_high` |
| Listing Created (Newest) | `newest` |
| Listing Created (Oldest) | `oldest` |

### Sidebar Dropdown (Browser-Verified)

```
+------------------------------+
| Sort By                   v  | <- Default
+------------------------------+
| * Sort By                    | <- Highlighted blue
|   Price (Low)                |
|   Price (High)               |
|   Listing Created (Newest)   |
|   Listing Created (Oldest)   |
+------------------------------+
```

### Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `cheapest`, `cheapest first`, `price (low)`, `price_asc`, `price_min` | `price_low` |
| `most expensive`, `price (high)`, `price_desc`, `price_max` | `price_high` |
| `newest first`, `most recent`, `listing created (newest)` | `newest` |
| `oldest first`, `least_recent`, `listing created (oldest)` | `oldest` |

---

## 7. Color Filter (Browser-Verified)

Colors are **device-specific** — not all colors appear for all products.

### iPhone 15 Colors (Browser-Verified)

| UI Label | `color` Value |
| :--- | :--- |
| Black | `black` |
| Blue | `blue` |
| Green | `green` |
| Pink | `pink` |
| Yellow | `yellow` |

### Sidebar Dropdown (Browser-Verified)

```
+----------------------+
| All Colors        v  |
+----------------------+
| * All Colors         | <- Highlighted blue
|   Black              |
|   Blue               |
|   Green              |
|   Pink               |
|   Yellow             |
+----------------------+
```

> [!NOTE]
> Color options vary by device. Samsung Galaxy S24 Ultra may show different colors
> (Titanium Black, Titanium Gray, etc.). The verifier normalizes colors to lowercase
> with spaces replaced by hyphens: `space black` -> `space-black`.

---

## 8. Storage Filter (Browser-Verified)

### iPhone 15 Storage Options

| UI Label | `storage` Value |
| :--- | :--- |
| 128 GB | `128gb` |
| 256 GB | `256gb` |
| 512 GB | `512gb` |

### Alias Resolution

| Alias | Normalized To |
| :--- | :--- |
| `128`, `128 gb`, `128GB` | `128gb` |
| `256`, `256 gb`, `256GB` | `256gb` |
| `512`, `512 gb`, `512GB` | `512gb` |
| `1 tb`, `1TB`, `1024gb` | `1tb` |

> [!NOTE]
> Storage options are device-specific. iPhones typically show 128/256/512/1TB.
> Samsung devices may show different storage tiers.

---

## 9. Model Filter (Browser-Verified)

The "All Models" dropdown shows **hardware model numbers** specific to each device.

### iPhone 15 Models (Browser-Verified)

```
+----------------------+
| All Models        v  |
+----------------------+
| * All Models         |
|   A2846              |
|   A3089              |
|   A3090              |
|   A3092              |
+----------------------+
```

These are Apple model numbers for different regional/carrier variants.

---

## 10. Checkbox Filters (Browser-Verified — NOT in URL)

Below the dropdown filters, the sidebar shows checkbox options:

```
[ ] One-Year Warranty
[ ] Accepts Credit Cards
[ ] Exclude Businesses
[ ] PhoneCheck Certified
[ ] International Shipping
```

> [!WARNING]
> These checkboxes were observed in the sidebar but their URL encoding has
> **NOT been confirmed**. They are NOT included in the verifier until URL
> encoding is verified.

---

## 11. Category Pages

### Top Navigation Categories

| Category | URL |
| :--- | :--- |
| iPhones | `/buy/iphones` |
| Phones (all) | `/buy/phones` |
| Laptops | `/buy/laptops` |
| Tablets | `/buy/tablets` |
| Watches | `/buy/watches` |
| Gaming | `/buy/gaming` |
| Apple (all) | `/buy/apple` |

### Category + Carrier

```
https://swappa.com/buy/unlocked/iphones
```

---

## 12. Domain Variations

| Domain | Accepted | Description |
| :--- | :---: | :--- |
| `swappa.com` | YES | Primary (no www) |
| `www.swappa.com` | YES | Standard desktop |
| `m.swappa.com` | YES | Any subdomain |
| `*.swappa.com` | YES | Any subdomain |
| `fakeswappa.com` | NO | Not a subdomain |
| `mercari.com` | NO | Different site |

---

## 13. Ignored Parameters

These parameters do not affect search semantics and are excluded from comparison:

### Tracking & Attribution (Ignored)
`utm_source`, `utm_medium`, `utm_campaign`, `srsltid`, `gclid`, `fbclid`, `ref`

### Session State (Ignored)
Any parameter not in the verified filter set is silently ignored during
URL comparison. Extra parameters in the agent URL do not cause a mismatch.

---

## 14. Verifier Matching Rules

### Core Comparison Logic

| # | Field | Normalization | Comparison | Fail if GT has & Agent missing? |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Product slug | Lowercase, hyphen-collapse, strip `/buy/` or `/listings/` prefix | Case-insensitive string match | YES Yes |
| 2 | Carrier | Alias resolution (see S4) | Exact string match | YES Yes |
| 3 | Condition | Alias resolution (see S5) | Exact string match | YES Yes |
| 4 | Storage | Alias resolution (see S8) | Exact string match | YES Yes |
| 5 | Color | Lowercase, space->hyphen | Exact string match | YES Yes |
| 6 | Sort order | Alias resolution (see S6) | Exact string match | YES Yes |
| 7 | Model | Lowercase, strip | Exact string match | YES Yes |

### Precedence Rules (Hardened — No Auto-Pass Loopholes)

1. If ground truth specifies a field and agent **omits** it -> **FAIL** (no auto-pass)
2. If ground truth **omits** a field -> agent value is **ignored** (pass)
3. **No auto-pass loopholes**: every GT-specified field must be present and correct
4. `/buy/` and `/listings/` paths are **equivalent** for product slug matching
5. Carrier can match via **query param** OR **path segment** — either is valid
6. First successful match across multi-GT URLs -> **score = 1.0** (OR semantics)
7. All mismatches are logged with detailed diagnostic messages
8. Extra agent parameters not in GT are **ignored**
9. Tracking/session parameters (S13) are always ignored
10. Individual listing pages (`/listing/view/`) are ignored — never match

### Matching Flow

```
Agent URL -> Parse -> Normalize
  v
GT URL -> Parse -> Normalize
  v
Compare (sequential — first failure stops):
  1. product_slug
  2. carrier
  3. condition
  4. storage
  5. color
  6. sort
  7. model
  v
All match? -> score = 1.0
Any mismatch? -> score = 0.0 (with mismatch field + details logged)
```

---

## 15. Listing Card Anatomy (Browser-Verified)

### Standard Listing Card

```
+-----------------------------------------------------------------+
| [Rank *]  LAEE39064                                   [tag] $300   |
| [[camera] 8]                                                          |
| [Photo]   Good condition  [battery] 79%  128GB  * Pink                 |
|           [lock] Unlocked    A2846                                   |
|                                                                   |
|           Brian O.                                                |
|           ***** ² Rockville Centre, NY                          |
|           Pink iPhone 15                                          |
+-----------------------------------------------------------------+
```

### Listing Card Fields

| Field | Location | Description |
| :--- | :--- | :--- |
| Rank | Top left (green badge) | 1*, 2*, 3*, etc. — listing quality rank |
| Listing ID | Top left | Alphanumeric code (e.g., LAEE39064) |
| Price | Top right | Dollar amount with [tag] tag icon |
| Photo count | Below rank | [camera] N — number of listing photos |
| Condition | Info grid | New / Mint / Good / Fair |
| Battery | Info grid | [battery] percentage (phone-specific) |
| Storage | Info grid | 128GB / 256GB / etc. |
| Color | Info grid | * Color name with dot indicator |
| Carrier | Info grid | [lock] Unlocked / AT&T / T-Mobile / etc. |
| Model number | Info grid | Hardware model (A2846, etc.) |
| Seller name | Below grid | Username |
| Rating | Below seller | ***** with review count |
| Location | Below seller | City, State |
| Badges | Below seller | Trusted / PhoneCheck / Stackry / QuickBox / Power / Enterprise |
| Description | Bottom | Seller's listing description text |

### Key Observations

- Listings are **paginated** — "Showing 1-50 of 209" with page navigation
- Listings are **ranked** with star badges (1* = best deal)
- Battery health percentage shown for phones
- **PhoneCheck** badge indicates third-party verification
- **Enterprise** badge indicates business sellers
- Prices are displayed in **dollars** (unlike Mercari which uses cents in URLs)
- No "SOLD" overlay — Swappa only shows active listings

---

## 16. Sidebar Filter Layout (Browser-Verified Desktop)

```
[search] Filters [N]                  <- N = active filter count
-----------------------------
All Conditions ............. v   <- Dropdown: New, Mint, Good, Fair
All Carriers ............... v   <- Dropdown: Unlocked, AT&T, T-Mobile, ...
All Colors ................. v   <- Dropdown: device-specific colors
All Storages ............... v   <- Dropdown: device-specific sizes
All Models ................. v   <- Dropdown: hardware model numbers
Sort By .................... v   <- Dropdown: Price Low/High, Newest/Oldest
-----------------------------
[ ] One-Year Warranty
[ ] Accepts Credit Cards
[ ] Exclude Businesses
[ ] PhoneCheck Certified
[ ] International Shipping
-----------------------------
Clear Filters                    <- Resets all filters, returns to base URL
```

### Filter Behavior

- Selecting a filter **immediately** updates the URL and reloads listings
- Active filters show their value in the dropdown label (e.g., "Mint" instead of "All Conditions")
- Filter count badge updates: `Filters [2]` when 2 filters are active
- "Clear Filters" removes all query params and returns to base `/listings/` URL
- Dropdowns are **single-select** — only one value per filter at a time
- **No price range filter** — unlike Mercari, Swappa has no min/max price in URLs

---

## 17. Search Behavior (Browser-Verified)

Swappa's search bar uses **autocomplete** rather than a search results page:

```
+------------------------------------------+
| [search] iPhone 14 Pro                    x    |
+------------------------------------------+
| Apple iPhone 14 Pro                      |
|   In Products starting at $298           |
|   74 reviews · 4.8 stars *****          |
|                                          |
| Apple iPhone 14 Pro Max                  |
|   In Products starting at $393           |
|   81 reviews · 4.8 stars *****          |
|                                          |
| Apple iPhone 14 Pro - Unlocked           |
|   In Products starting at $299           |
|                                          |
| Apple iPhone 14 Pro Max - Unlocked       |
|   In Products starting at $393           |
+------------------------------------------+
```

> [!IMPORTANT]
> Swappa does NOT have a `/search/?keyword=` URL pattern. The search bar shows
> an autocomplete dropdown, and clicking a result navigates directly to the
> product's `/buy/{slug}` page. This is fundamentally different from Mercari.

---

## 18. Listings Page Full Anatomy (Browser-Verified)

```
+------------------------------------------------------------------+
|  [reload] SWAPPA                              [search] Find a good deal      |
+------------------------------------------------------------------+
|  [Applev] [iPhonesv] [Phonesv] [Laptopsv] [Watchesv] ...        |
+------------------------------------------------------------------+
|  [truck] Free Shipping  [no] No Junk  [user] Human Support  [shield] PayPal       |
+------------------------------------------------------------------+
|  Swappa / iPhones / iPhone 15 / Page 1                           |
|                                                                    |
|  Apple iPhone 15        ***** 17 reviews      Starting at $299  |
+------------+-----------------------------------------------------+
|            |  ☰ Showing 1-50 of 209            Clear Filters     |
| [Product]  +-----------------------------------------------------+
| [Image]    |  1* LAEE39064                              [tag] $300  |
|            |  Good condition [battery]79% 128GB * Pink                   |
| Filters[0] |  AT&T  A2846                                        |
| ---------- |  Brian O. *****² Rockville Centre, NY              |
| All Cond v +-----------------------------------------------------+
| All Carr v |  2* LAET12929                              [tag] $328  |
| All Colr v |  Fair condition [battery]83% 128GB * Black                 |
| All Stor v |  T-Mobile  A2846                                    |
| All Modl v |  Gilly's Smart Phones *****¹²⁵⁴                   |
| Sort By  v +-----------------------------------------------------+
| ---------- |  3* LAET34558                              [tag] $330  |
| [ ] Warranty |  Fair condition [battery]86% 128GB * Black                 |
| [ ] Credit   |  T-Mobile  A2846                                    |
| [ ] Exclude  |  ...                                                |
| [ ] PhoneCk  +-----------------------------------------------------+
| [ ] Intl     |  (more listings below with pagination)              |
| Clear Fltr |                                                     |
+------------+-----------------------------------------------------+
|  Footer                                                          |
+------------------------------------------------------------------+
```

---

## 19. Test & Benchmark Coverage

### Unit Tests

**95 tests** across 16+ test classes, covering:

| Category | Tests | Focus |
| :--- | :---: | :--- |
| URL Parsing | 8 | Full parse pipeline, all filter types |
| Slug Normalization | 5 | Case, hyphens, slashes |
| Carrier Normalization | 11 | All carriers, aliases, case sensitivity |
| Condition Normalization | 4 | All 4 conditions, aliases |
| Sort Normalization | 4 | All 4 sorts, aliases |
| Storage Normalization | 5 | All sizes, number-only aliases |
| Color Normalization | 4 | Case, space-to-hyphen |
| Path Extraction | 6 | Product slug from /buy/ and /listings/ |
| Carrier Path Extraction | 5 | Carrier from path segments |
| Domain Validation | 6 | Valid domains, rejections |
| Product Slug Matching | 5 | /buy/ vs /listings/ equivalence |
| Carrier Matching | 4 | Match, mismatch, missing, alias |
| Condition Matching | 4 | Match, mismatch, missing, alias |
| Storage Matching | 4 | Match, mismatch, missing, alias |
| Sort Matching | 3 | Match, mismatch, missing |
| Color Matching | 2 | Match, mismatch |
| Combination Matching | 3 | Multi-filter, missing one, extra params |
| Async Lifecycle | 5 | reset -> update -> compute, sticky match |
| Multi-GT URLs | 3 | OR semantics |
| Edge Cases | 5 | Non-Swappa URLs, listing pages, empty, www |

### Benchmark Dataset

**70 tasks** in `swappa_benchmark_tasks.csv` — **all hard difficulty**:

| Category | Count | Difficulty Strategy |
| :--- | :---: | :--- |
| Product Navigation | 10 | Navigate to correct product page |
| Carrier Selection | 10 | Product + specific carrier filter |
| Condition Filter | 10 | Product + carrier + condition |
| Storage Combos | 10 | Product + carrier + storage size |
| Red Herring | 10 | Narrative distractors with irrelevant details |
| Multi-Filter | 10 | 3-5 simultaneous filters combined |
| Ultra-Hard | 10 | Budget arithmetic + narrative + multi-filter |

---

## Appendix A: Live URL Examples

### Product Overview (no filters)
```
https://swappa.com/buy/apple-iphone-15
```

### Listings with Carrier
```
https://swappa.com/listings/apple-iphone-15?carrier=unlocked
```

### Listings with Condition + Sort
```
https://swappa.com/listings/apple-iphone-14-pro?condition=mint&sort=price_low
```
^ Mint condition only, sorted by lowest price first

### Full Filter Combination
```
https://swappa.com/listings/apple-iphone-15
  ?carrier=unlocked
  &condition=mint
  &storage=128gb
  &color=black
  &sort=price_low
```
^ Unlocked, mint, 128GB, black, cheapest first

### Samsung Product
```
https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=unlocked&storage=256gb
```

### Individual Listing (Ignored by verifier)
```
https://swappa.com/listing/view/LAEU99283
```

---

## Appendix B: Comparison with Other Domains

| Feature | Swappa | Mercari | Facebook Marketplace |
| :--- | :--- | :--- | :--- |
| **Type** | E-commerce (used tech) | E-commerce (secondhand) | E-commerce (local) |
| **URL model** | Path-based product catalog | Query-param search | Query-param search |
| **Primary nav** | Browse by product | Keyword search | Keyword search |
| **Search path** | `/buy/{slug}` or `/listings/{slug}` | `/search/?keyword=` | `/marketplace/search/?query=` |
| **Filter encoding** | Query params on `/listings/` | Query params on `/search/` | Query params |
| **Price encoding** | **Not in URL** | **Cents** ($25 = 2500) | Dollars |
| **Price filter** | Not available | `minPrice`/`maxPrice` | `minPrice`/`maxPrice` |
| **Conditions** | String slugs (`mint`, `good`) | Numeric IDs (`1`-`5`) | String keys |
| **Multi-condition** | Not supported (single-select) | Hyphen separator (`1-2`) | Not supported |
| **Sort values** | String slugs (`price_low`) | Numeric IDs (`1`-`4`) | String keys |
| **Carriers** | In URL (`carrier=unlocked`) | N/A | N/A |
| **Storage** | In URL (`storage=128gb`) | N/A | N/A |
| **Location** | Not in URL | Not in URL | City slug in path |
| **Categories** | Product slug in path | Numeric IDs | String slugs |
| **Brands** | Implied by product slug | Numeric IDs | Numeric make IDs |
| **Login required** | No | No | Partial |
| **Pagination** | Yes (page-based) | No (infinite scroll) | No (infinite scroll) |
| **Search behavior** | Autocomplete dropdown | Results page | Results page |

---
