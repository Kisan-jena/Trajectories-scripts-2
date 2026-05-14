Goat Coverage Documentation

URL Patterns, Query Parameters Reference

#   

# Overview

This document defines a GOAT URL-based verifier system that identifies page types (search, category, collection, brand, product) and extracts key filters and sorting parameters directly from URLs. It ensures consistent interpretation of GOAT URLs by normalizing identifiers, decoding filters, and ignoring tracking parameters across all listing pages. 

  

# 1\. PAGE TYPES

Goat contains several search and result page types.

| Page Type | URL Pattern | Example | Data Sources |
| --- | --- | --- | --- |
| Homepage | / | goat.com | Search entry |
| Search Results | /search | /search?query=jordan%201 | Listings |
| Category Page | /sneakers | /sneakers | Product browse taxonomy |
| Collection Page | /collections/ | /collections/just-dropped | Curated collections |
| Brand Page | /brand/ | /brand/nike | Brand taxonomy (brand-based listing) |
| Product Page | /sneakers/ | /sneakers/air-jordan-1-retro-high-og-dz5485-612 | Product detail |

  
  
  
  
  
  

## Page Type Detection Rules

| Rule | URL Pattern | Condition | Page Type |
| --- | --- | --- | --- |
| Path = / | Domain = goat.com | No additional params required | Homepage |
| Path starts with /search | Query contains query | Always | Search results |
| Path starts with /sneakers AND no product slug present | Generic browse page | Always | Category Page |
| Path starts with /collections/ | Collection slug present | Always | Collection Page |
| Path starts with /brand/ | Brand slug present | Always | Brand Page |
| Path starts with /sneakers/ AND contains product slug | Product detail route | Always | Product page |

  
  

NOTE FOR PAGETYPE DETECTION:

*   /search → Search Results Page
    
*   /collections/ → Collection Page
    
*   /brand/ → Brand Page
    
*   /sneakers → Category/Browse Page
    

  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  

# 2\. URL PATTERNS – SEARCH RESULTS PAGE

Search results page URL Anatomy:

  

https://www.goat.com/search?query=air%20jordan%201&pageNumber=1

                                └── query ──┘      └── page──┘ 

  

URL STRUCTURE-

/search?query=<search\_query>&<other\_filter\_params> 

| Component | Format | Example | Note |
| --- | --- | --- | --- |
| Query | Encoded string | air%20jordan%201 | Primary search keyword (REQUIRED) |
| Page Number | Integer | 1 | Pagination |

#   

# 3\. URL PATTERNS – CATEGORY PAGE

Category URL Anatomy:

  

https://www.goat.com/sneakers?priceMin=6446500&priceMax=23000000 

                    └category┘     └────page filters────┘ 

  
  

https://www.goat.com/apparel/tops/t-shirts 

                    └parent┘└subcategory┘└leaf category┘ 

  

URL Structure- 

/<category>/<sub-category (optional)>/<leaf-category (optional)>? 

| Component | Format | Example | Note |
| --- | --- | --- | --- |
| Category Path | String | sneakers | Primary category identifier |
| Subcategory (optional) | String | tops | Intermediate category grouping |
| Leaf Category (optional) | String | t-shirts | Final category refinement |

#   

# 4\. URL PATTERNS – COLLECTION PAGE

Product URL Anatomy:

  

https://www.goat.com/collections/just-dropped 

                        └── collection slug ──┘ 

URL STRUCTURE-

/collections/<collection\_slug>?<params> 

| Component | Format | Example | Note |
| --- | --- | --- | --- |
| Collection Slug | String | just-dropped | Curated collection identifier |

  
  

# 5\. URL PATTERNS – ALL BRANDS PAGE

All Brands Page URL Anatomy:

  

https://www.goat.com/brand/nike 

                       └ brand ┘ 

  

URL STRUCTURE-

/brand/<brand-name>

| Component | Format | Example | Note |
| --- | --- | --- | --- |
| Brand Name | String (slug) | nike | Brand identifier |
| Params | Query string | ?pageNumber =2 | Filters (optional) |

  

# 6\. FILTERS FOR GOAT.COM

  

Brands Filter- 

The brand filter allows users to restrict listings based on one or more selected brands across all GOAT listing pages. 

brands=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Brand | brands | Encoded comma-separated strings | brands=Nike | Single brand filter |
| Multiple Brands | brands | Comma-separated values | brands=Air+Jordan%2CNike | Multiple brands supported |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| brands=Nike | Single brand selected |
| brands=Nike%2Cadidas | Multiple brands selected |
| + | Represents spaces |
| %2C | Encoded comma separator |

  

### Examples

*   brands=Air+Jordan%2CCactus+Jack+by+Travis+Scott%2CNike
    
*   brands=A-Cold-Wall\*%2CAcne+Studios%2CAder+Error
    
*   brands=2+Moncler%2C3.PARADIS%2C5+Moncler
    
*   brands=adidas%2CAir+Jordan
    

  

Category / Type / Activity Filters - 

The category hierarchy filters allow users to refine listings using category, product type, and activity classification across all GOAT listing pages. 

categories=<value>

types=<value>

activities=<value> 

  
  

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Category | categories | String | categories=Footwear | Top-level category |
| Type | types | Encoded string | types=%2CSneakers | Product type refinement |
| Activity | activities | Encoded string | activities=%2Cactivity%3Alifestyle | Activity/use-case refinement |

  

Value Interpretation 

| Pattern | Meaning |
| --- | --- |
| categories=Footwear | Category filter applied |
| types=%2CSneakers | Type = Sneakers |
| activities=%2Cactivity%3Alifestyle | Activity = lifestyle |
| %2C | Encoded comma separator |
| %3A | Encoded colon separator |

  

Hierarchy Mapping 

| Hierarchy Level | Example |
| --- | --- |
| Category | Footwear |
| Type | Sneakers |
| Activity | lifestyle |

  

Example:  
Footwear → Sneakers → lifestyle  
Accessories → Eyewear → Sunglasses

Gender Filter-  

The gender filter allows users to restrict listings based on target gender categories across all GOAT listing pages. 

genders=<value>

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Gender | genders | Encoded comma-separated strings | genders=women | Single gender filter |
| Multiple Genders | genders | Comma-separated values | genders=men%2Cyouth | Multiple genders supported |

  

Value Interpretation 

| Pattern | Meaning |
| --- | --- |
| genders=women | Women products only |
| genders=men%2Cyouth | Men and Youth products |
| %2C | Encoded comma separator |

  

Size Filter-  

The size filter allows users to restrict listings based on product sizing across all GOAT listing pages. 

sizes=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Size | sizes | Encoded comma-separated strings | sizes=universal_tops_men_XL | Single size filter |
| Multiple Sizes | sizes | Comma-separated values | sizes=universal_tops_men_XL%2Cuniversal_tops_men_XXL | Multiple sizes supported |

  

Value Interpretation 

| Pattern | Meaning |
| --- | --- |
| universal_tops_men_XL | Men's tops size XL |
| universal_tops_men_XXL | Men's tops size XXL |
| universal_bottoms_men_S/M | Men's bottoms size S/M |
| universal_bottoms_men_M | Men's bottoms size M |
| universal_tops_men_XS | Men's tops size XS |
| %2C | Encoded comma separator |
| %2F | Encoded "/" inside size values |

  

Size Structure 

<size\_group><product\_category><gender>\_<size\_value> 

| Component | Example |
| --- | --- |
| Size Group | universal |
| Product Category | tops / bottoms |
| Gender | men |
| Size Value | XS / M / XL / XXL / S/M |

  
  

Condition Filter-  

The condition filter allows users to restrict listings based on product condition across all GOAT listing pages. 

conditions=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Condition | conditions | Encoded comma-separated strings | conditions=used | Single condition filter |
| Multiple Conditions | conditions | Comma-separated values | conditions=new_no_defects%2Cused | Multiple conditions supported |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| new_no_defects | Brand new / no defects |
| new_with_defects | New with defects |
| used | Used products |
| %2C | Encoded comma separator |

  

Color Filter- 

The color filter allows users to restrict listings based on product color across all GOAT listing pages. 

colors=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Color | colors | Encoded comma-separated strings | colors=white | Single color filter |
| Multiple Colors | colors | Comma-separated values | colors=black%2Cwhite%2Cblue | Multiple colors supported |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| colors=white | White products only |
| colors=black%2Cwhite%2Cblue | Black, White, and Blue products |
| %2C | Encoded comma separator |

  

Price Filter- 

The price filter allows users to restrict listings based on minimum and/or maximum price across all GOAT listing pages. 

priceMin=<min\_price>  
priceMax=<max\_price>

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Min Price | priceMin | Integer | priceMin=1500 | Shows items above this price |
| Max Price | priceMax | Integer | priceMax=11896500 | Shows items below this price |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| priceMin=1500 | Minimum price applied |
| priceMax=11896500 | Maximum price applied |
| priceMin + priceMax | Price range filter applied |

  
  
  
  

Instant Shipping Filter- 

The instant ship filter allows users to restrict listings to products eligible for GOAT Instant Ship across all GOAT listing pages. 

instantShip=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Instant Ship | instantShip | Boolean (true) | instantShip=true | Shows only Instant Ship eligible products |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| instantShip=true | Instant Ship products only |
| Parameter absent | All products |

  

Under Retail Filter- 

The under retail filter allows users to restrict listings to products priced below retail value across all GOAT listing pages. 

underRetail=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Under Retail | underRetail | Boolean (true) | underRetail=true | Shows only products priced below retail |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| underRetail=true | Under retail products only |
| Parameter absent | All products |

  
  

Available Now  Filter- 

The available now filter allows users to restrict listings to products currently in stock across all GOAT listing pages. 

inStock=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Available Now | inStock | Boolean (true) | inStock=true | Shows only currently available products |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| inStock=true | In-stock products only |
| Parameter absent | All products |

  

Sale Filter- 

The sale filter allows users to restrict listings to products currently on sale across all GOAT listing pages. 

sale=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Sale | sale | Boolean (true) | sale=true | Shows only sale products |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| sale=true | Sale products only |
| Parameter absent | All products |

  
  
  

Year Filter- 

The year filter allows users to restrict listings based on product release years across all GOAT listing pages. 

years=<value> 

| Component | Key Search | Format | Example | Note |
| --- | --- | --- | --- | --- |
| Year | years | Integer | years=2009 | Single release year filter |
| Multiple Years | years | Comma-separated integers | years=2020%2C2022%2C2023 | Multiple release years supported |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| years=2009 | Products released in 2009 |
| years=2020%2C2022%2C2023 | Products released in multiple years |
| %2C | Encoded comma separator |

  

Sort By Filter- 

The sort by filter controls how listings are ordered across all GOAT listing pages. 

sortType=<value> 

| Sort Type | Search Key | Example Value | Note |
| --- | --- | --- | --- |
| Popular | sortType | popular | Most popular products |
| Recently Released Sneakers | sortType | recently_released_sneakers | Latest sneaker releases |
| New In Apparel | sortType | new_in_apparel | Newly added apparel |
| Price: Low to High | sortType | price_low_high | Lowest priced products first |
| Price: High to Low | sortType | price_high_low | Highest priced products first |

## Value Interpretation

| Pattern | Meaning |
| --- | --- |
| sortType=popular | Sort by popularity |
| sortType=recently_released_sneakers | Sort by latest sneaker releases |
| sortType=new_in_apparel | Sort by newest apparel |
| sortType=price_low_high | Sort by lowest price first |
| sortType=price_high_low | Sort by highest price first |

## Related Parameters

| Parameter | Purpose |
| --- | --- |
| releaseDateStart | Start timestamp for release-based sorting |
| releaseDateEnd | End timestamp for release-based sorting |
