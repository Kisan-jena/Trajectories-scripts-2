import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger


from navi_bench.goat.goat_url_match import (
    GoatUrlMatch,
    generate_task_config,
)

# =============================================================================
# BROWSER CONFIG
# =============================================================================

@dataclass
class BrowserConfig:
    headless: bool = False

    viewport_width: int = 1366
    viewport_height: int = 768

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    locale: str = "en-US"

    launch_args: list = field(
        default_factory=lambda: [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
            "--no-sandbox",
        ]
    )


# =============================================================================
# TASK SCENARIO
# =============================================================================

@dataclass
class TaskScenario:
    task_id: str
    name: str
    task: str
    url: str
    gt_url: list[str]
    location: str
    timezone: str

    def __post_init__(self):

        assert self.task_id
        assert self.gt_url


# =============================================================================
# SAMPLE GOAT SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    # -------------------------------------------------------------------------
    # SEARCH
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/search/jordan_red",
        name="Search Jordan Red Sneakers",
        task=(
            "Search for Air Jordan sneakers "
            "with red color and men gender."
        ),
        url="https://www.goat.com",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=air+jordan"
                "&colors=red"
                "&genders=men"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/jordan_one_new_instock",
        name="Search Jordan One Shoes New In Stock",
        task=(
            "Navigate to the men sneakers section and search for "
            "Jordan One shoes. Filter results to show only pairs "
            "that are new no defects and currently available now "
            "for immediate purchase."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=jordan+one"
                "&pageNumber=1"
                "&genders=men"
                "&conditions=new_no_defects"
                "&inStock=true"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_black_hoodie_sale_m",
        name="Search Men's Black Hoodies on Sale Size M",
        task=(
            "Search for hoodies in the apparel category, select "
            "gender as men, and filter for men's tops in size M. "
            "Show only black colored hoodies that are currently on sale."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel/tops/hoodies"
                "?pageSlug=apparel"
                "&taxonomies=tops%2Choodies"
                "&pageNumber=1"
                "&genders=men"
                "&colors=black"
                "&sale=true"
                "&sizes=universal_tops_men_M"
            ),
            (
                "https://www.goat.com/search"
                "?query=hoodies"
                "&pageNumber=1"
                "&categories=Apparel"
                "&genders=men"
                "&colors=black"
                "&sale=true"
                "&sizes=universal_tops_men_M"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_casio_gshock_watches_instock",
        name="Search Men's Casio and G-SHOCK Watches In Stock",
        task=(
            "Search for men's watches and filter results to "
            "Casio and G-SHOCK by Casio models. Show only "
            "watches that are currently in stock and available now."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/jewelry"
                "?pageNumber=1"
                "&categories=Jewelry"
                "&types=%2CWatches"
                "&brands=Casio%2CG-SHOCK+by+Casio"
                "&genders=men"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?query=mens+watches"
                "&pageNumber=1"
                "&brands=Casio%2CG-SHOCK+by+Casio"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?query=watches"
                "&pageNumber=1"
                "&genders=men"
                "&brands=Casio%2CG-SHOCK+by+Casio"
                "&inStock=true"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_black_backpacks_price_low_high",
        name="Search Men's Black Backpacks Sorted by Lowest Price",
        task=(
            "Browse for back packs and look for classic black color, "
            "select gender as men under category bags of type backpacks. "
            "Sort the results from lowest to highest price "
            "so I can easily compare the best-value high-performance backpacks."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/bags"
                "?pageNumber=1"
                "&categories=Bags"
                "&types=%2CBackpacks"
                "&genders=men"
                "&colors=black"
                "&sortType=price_low_high"
            ),
            (
                "https://www.goat.com/search"
                "?query=back+packs"
                "&pageNumber=1"
                "&genders=men"
                "&types=%2CBackpacks"
                "&categories=Bags"
                "&colors=black"
                "&sortType=price_low_high"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/crossbody_bags_neutral_colors_price_high_low",
        name="Search Crossbody Bags in Neutral Colors Sorted by Highest Price",
        task=(
            "Search for crossbody bags and filter results to "
            "neutral shades including black, brown, and cream. "
            "Sort the results from highest price to lowest."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=crossbody+bags"
                "&pageNumber=1"
                "&colors=black%2Cbrown%2Ccream"
                "&sortType=price_high_low"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_air_force_1_new_instock",
        name="Search Men's Air Force 1 New and In Stock",
        task=(
            "Search for Air Force 1 using the search bar, select "
            "gender as men, and filter for brand new conditioned "
            "pairs that are currently available now."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=air+force+1"
                "&pageNumber=1"
                "&genders=men"
                "&conditions=new_no_defects"
                "&inStock=true"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/womens_puffer_jackets_newest",
        name="Search Women's Puffer Jacket"
        " in Neutral Colors",
        task=(
            "Search for puffer jacket in the apparel category and "
            "filter results to women's styles only. Select neutral "
            "colors including black, white, and cream, and sort "
            "results by the most recently added items first."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=puffer+jacket"
                "&pageNumber=1"
                "&categories=Apparel"
                "&genders=women"
                "&colors=black%2Cwhite%2Ccream"
                "&sortType=new_in_apparel"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_tshirts_used_size_l_price_low_high",
        name="Search Men's Used T-Shirts Size L Sorted by Lowest Price",
        task=(
            "Look for the T-shirts section under categories, select "
            "gender as men, and filter for men's tops in size L "
            "with used condition only. Choose colors blue, green, "
            "and yellow, and sort the results from lowest to highest price."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel/tops/t-shirts"
                "?sizes=universal_tops_men_L"
                "&pageNumber=1"
                "&conditions=used"
                "&colors=blue%2Cgreen%2Cyellow"
                "&sortType=price_low_high"
                "&pageSlug=apparel"
                "&taxonomies=tops%2Ct-shirts"
                "&genders=men"
                "&activities=T-Shirts"
            ),
            (
                "https://www.goat.com/search"
                "?query=t-shirts"
                "&pageNumber=1"
                "&sortType=price_low_high"
                "&conditions=used"
                "&colors=blue%2Cgreen%2Cyellow"
                "&sizes=universal_tops_men_L"
                "&genders=men"
                "&activities=T-Shirts"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/used_duffle_bags_instock_price_high_low",
        name="Search Used Duffle Bags In Stock Sorted by Highest Price",
        task=(
            "Browse duffle bag options within the bags section and "
            "filter results to used condition items that are currently "
            "available now. Sort the results from highest price to lowest."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/bags"
                "?sortType=price_high_low"
                "&pageNumber=1"
                "&categories=Bags"
                "&types=%2CDuffles"
                "&conditions=used"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?query=duffle+bag"
                "&pageNumber=1"
                "&conditions=used"
                "&inStock=true"
                "&sortType=price_high_low"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/mens_amiri_bape_jackets_new_size_l",
        name="Search Men's Amiri and BAPE Jackets Size L Sorted by Highest Price",
        task=(
            "Select the jacket option in the outerwear section under "
            "categories and choose Amiri and BAPE from the brand options. "
            "Filter for men's outerwear size L, brand new condition, and "
            "colors black and red. Sort the results from highest price to lowest."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel/outerwear"
                "?pageNumber=1"
                "&brands=Amiri%2CBAPE"
                "&genders=men"
                "&sizes=universal_outerwear_men_L"
                "&conditions=new_no_defects"
                "&colors=red%2Cblack"
                "&sortType=price_high_low"
                "&categories=Apparel"
                "&types=%2COuterwear"
                "&activities=%2CJackets"
            ),
            (
                "https://www.goat.com/search"
                "?query=mens+jackets"
                "&pageNumber=1"
                "&sortType=price_high_low"
                "&brands=Amiri%2CBAPE"
                "&conditions=new_no_defects"
                "&colors=red%2Cblack"
                "&categories=Apparel"
                "&types=%2COuterwear"
                "&activities=%2CJackets"
                "&sizes=universal_outerwear_men_L"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/youth_apparel_new_instock_neutral",
        name="Search Youth Apparel New and In Stock in Neutral Colors",
        task=(
            "Browse the Apparel section under categories for youth items. "
            "Filter results to brand new pieces that are currently available "
            "now, and choose colors white, brown, and cream."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel"
                "?categories=Apparel"
                "&pageNumber=1"
                "&query="
                "&conditions=new_no_defects"
                "&inStock=true"
                "&colors=white%2Cbrown%2Ccream"
                "&genders=youth"
            ),
            (
                "https://www.goat.com/search"
                "?query=youth+apparel+"
                "&pageNumber=1"
                "&colors=cream%2Cbrown%2Cwhite"
                "&inStock=true"
                "&conditions=new_no_defects"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/category/youth_swimwear/12",
        name="Browse Youth Swimwear Sorted by Highest Price",
        task=(
            "Navigate to the Apparel section under categories and select the "
            "Swimwear category. Filter for youth sizing in gender and sort "
            "the results by price from high to low to explore stylish swimwear "
            "options from premium streetwear and luxury brands for kids."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel"
                "?pageNumber=1"
                "&genders=youth"
                "&sortType=price_high_low"
                "&categories=Apparel"
                "&types=%2CSwimwear"
            ),
            (
                "https://www.goat.com/search"
                "?query=youth+swimwear"
                "&pageNumber=1"
                "&sortType=price_high_low"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/category/with_defects_collectibles/14",
        name="Browse Collectibles New With Defects Sorted by Lowest Price",
        task=(
            "I have been looking to expand my display shelf with some collectibles, "
            "but I'm more interested in the items themselves than pristine packaging. "
            "Navigate to the Collectibles section under categories and filter for items "
            "in new with defects condition. I want to see pieces that are available now "
            "so I can receive them quickly. Sort the results from lowest price to highest "
            "so I can find the best entry-level deals on plush keychains and vinyl figures first."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/collectibles"
                "?sortType=price_low_high"
                "&pageNumber=1"
                "&types="
                "&conditions=new_with_defects"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?query=collectibles"
                "&sortType=price_low_high"
                "&pageNumber=1"
                "&conditions=new_with_defects"
                "&inStock=true"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/category/in_range_collectibles/5",
        name="Browse In-Stock Collectibles Within Price Range Sorted Low to High",
        task=(
            "Navigate and look for Collectibles section under categories and filter "
            "for items that are available now. I want to stay within the price "
            "between $460 and $1,510. Sort the results from lowest price to highest."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/collectibles"
                "?sortType=price_low_high"
                "&pageNumber=1"
                "&inStock=true"
                "&priceMin=46000"
                "&priceMax=151000"
            ),
            (
                "https://www.goat.com/search"
                "?query=collectibles"
                "&pageNumber=1"
                "&sortType=price_low_high"
                "&inStock=true"
                "&priceMin=46000"
                "&priceMax=151000"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/new_balance_women_colors_price_high_low",
        name="Browse Women's New Balance Shoes in Warm Colors Sorted High to Low",
        task=(
            "I have been looking to buy new balance shoes, and want to find a pair "
            "that stands out with a softer, sophisticated aesthetic. Navigate to the "
            "New Balance brand page under Featured Brands. Filter for womens sizing "
            "and focus on a warm, versatile color palette including pink, red, and tan. "
            "Sort the results from highest price to lowest so I can explore the most "
            "exclusive models first."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/brand/new-balance"
                "?slug=new-balance"
                "&pageNumber=1"
                "&genders=women"
                "&colors=pink%2Cred%2Ctan"
                "&sortType=price_high_low"
            ),
            (
                "https://www.goat.com/search"
                "?query=new%20balance%20shoes"
                "&pageNumber=1"
                "&genders=women"
                "&colors=pink%2Cred%2Ctan"
                "&sortType=price_high_low"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&brands=New+Balance"
                "&genders=women"
                "&colors=pink%2Ctan%2Cred"
                "&sortType=price_high_low"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/category/tops_apparel/1",
        name="Browse Men's Used T-Shirts Size L in Specific Colors Sorted Low to High",
        task=(
            "Look for T-shirts section under categories. Select gender as men and "
            "filter for mens top in size L and look for items in used condition. "
            "I'm currently into a very specific palette, so only show me shirts "
            "in blue, green and yellow. Sort by price low to high so I can see "
            "the best available option"
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/apparel/tops/t-shirts"
                "?sizes=universal_tops_men_L"
                "&pageNumber=1"
                "&conditions=used"
                "&colors=blue%2Cgreen%2Cyellow"
                "&sortType=price_low_high"
                "&pageSlug=apparel"
                "&taxonomies=tops%2Ct-shirts"
                "&genders=men"
            ),
            (
                "https://www.goat.com/search"
                "?query=t-shirts"
                "&pageNumber=1"
                "&sortType=price_low_high"
                "&conditions=used"
                "&colors=blue%2Cgreen%2Cyellow"
                "&sizes=universal_tops_men_L"
                "&genders=men"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&categories=Apparel"
                "&types=%2CTops"
                "&activities=%2CT-Shirts"
                "&sortType=price_low_high"
                "&conditions=used"
                "&colors=blue%2Cgreen%2Cyellow"
                "&sizes=universal_tops_men_L"
                "&genders=men"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
    task_id="goat/brand/fear_of_god_essentials/1",
        name="Browse Fear of God Essentials Hats in Grey and Red Sorted High to Low",
        task=(
            "I have been wanting to get Fear of God Essentials hats, to complete my everyday "
            "look and want to stick with the minimalist aesthetic of one of my favorite labels. "
            "Navigate to the Fear of God Essentials brand page under Featured Brands and filter "
            "for Hats within the Accessories section. I'm looking for a mix of neutral and bold "
            "tones, so please filter for items in grey and red. I only want to see pieces that "
            "are available now. Sort by price high to low so I can see the most expensive caps "
            "and snapbacks first."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/brand/fear-of-god-essentials"
                "?slug=fear-of-god-essentials"
                "&pageNumber=1"
                "&colors=grey%2Cred"
                "&inStock=true"
                "&sortType=price_high_low"
                "&categories=Accessories"
                "&types=%2CHats"
            ),
            (
                "https://www.goat.com/search"
                "?query=Fear+of+God+Essentials+hats"
                "&pageNumber=1"
                "&colors=grey%2Cred"
                "&sortType=price_high_low"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&brands=Fear+of+God+Essentials"
                "&categories=Accessories"
                "&types=%2CHats"
                "&colors=grey%2Cred"
                "&sortType=price_high_low"
                "&inStock=true"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/brands/collectibles_pop_mart/16",
        name="Browse Pop Mart Collectibles from 2022 in Multi-Color and White Sorted High to Low",
        task=(
            "I'm looking to track down some pop mart collectibles to round out my display case. "
            "Navigate to the brand Pop Mart brand page and filter for the Collectibles section. "
            "I'm specifically interested in pieces released in 2022 that are currently available "
            "now. I want a bright and varied look, so please filter for multi-color and white "
            "items. Sort the results from highest price to lowest."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/brand/pop-mart"
                "?pageNumber=1"
                "&categories=Collectibles"
                "&colors=multi-color%2Cwhite"
                "&sortType=price_high_low"
                "&inStock=true"
                "&years=2022"
            ),
            (
                "https://www.goat.com/search"
                "?query=pop+mart+collectibles"
                "&pageNumber=1"
                "&sortType=price_high_low"
                "&colors=multi-color%2Cwhite"
                "&years=2022"
                "&inStock=true"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&brands=Pop+Mart"
                "&sortType=price_high_low"
                "&categories=Collectibles"
                "&years=2022"
                "&inStock=true"
                "&colors=multi-color%2Cwhite"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/kids_clogs/1",
        name="Browse Kids Multi-Color Clogs with Instant Ship Sorted Low to High",
        task=(
            "Search for clogs for kids. I want the items that are available now and have "
            "instant ship option enabled. Select the multi color option under colors also "
            "please sort the results starting from price low to high."
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=clogs+for+kids"
                "&pageNumber=1"
                "&colors=multi-color"
                "&sortType=price_low_high"
                "&inStock=true"
                "&instantShip=true"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&categories=Footwear"
                "&types=%2CClogs"
                "&genders=youth"
                "&inStock=true"
                "&instantShip=true"
                "&sortType=price_low_high"
                "&colors=multi-color"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/heels/1",
        name="Browse In-Stock Heels Under Retail Sorted High to Low",
        task=(
            "I am looking for heels, only the items that are available now and are listed "
            "under retail. I want my listing sorted by price high to low so I can the best "
            "items available"
        ),
        url="https://www.goat.com/",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=heels"
                "&pageNumber=1"
                "&sortType=price_high_low"
                "&inStock=true"
                "&underRetail=true"
            ),
            (
                "https://www.goat.com/search"
                "?pageNumber=1"
                "&categories=Footwear"
                "&types=%2CHeels"
                "&inStock=true"
                "&underRetail=true"
                "&sortType=price_high_low"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    )


]


# =============================================================================
# BROWSER MANAGER
# =============================================================================

class BrowserManager:

    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.browser = None
        self.context = None
        self.page = None

    async def launch(self, playwright):

        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=self.config.launch_args,
        )

        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            user_agent=self.config.user_agent,
            locale=self.config.locale,
        )

        # Anti-detection scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        self.page = await self.context.new_page()
        return self.browser, self.context, self.page

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()


# =============================================================================
# REPORTER
# =============================================================================

class ResultReporter:

    @staticmethod
    def print_header(
        scenario: TaskScenario,
    ):

        print("\n" + "=" * 70)

        print(
            f"SCENARIO: {scenario.name}"
        )

        print("=" * 70)

        print(
            f"Task ID   : {scenario.task_id}"
        )

        print(
            f"Location  : {scenario.location}"
        )

        print("\nInstructions:")

        print(f"  {scenario.task}")

        print("=" * 70 + "\n")

    @staticmethod
    def print_result(
        result,
        evaluator,
        final_url: str,
    ):

        print("\n" + "=" * 70)

        print("RESULT")

        print("=" * 70)

        status = (
            "✅ PASS"
            if result.score >= 1.0
            else "❌ FAIL"
        )

        print(f"Status : {status}")

        print(f"Score  : {result.score}")

        if result.agent_url:

            print("\nAgent URL:")

            print(f"  {result.agent_url}")

        print("\nFinal URL:")

        print(f"  {final_url}")

        print("\nExpected / Matched GT URL:")

        print(f"  {result.gt_url or evaluator._matched_gt_url}")

        if not result.match:

            print("\nGT URLs checked:")

            for gt_url in getattr(evaluator, "gt_urls", []):

                print(f"  - {gt_url}")

        if not result.match:

            print("\nMismatches:")

            mismatches = result.details.get("mismatches", [])

            if not mismatches:

                print("  (none recorded)")

            for m in mismatches:

                print(f"  - {m}")

        print("=" * 70 + "\n")


# =============================================================================
# RUNNER
# =============================================================================

async def run_scenario(
    scenario: TaskScenario,
):

    task_config = generate_task_config(
        task=scenario.task,
        gt_url=scenario.gt_url,
        location=scenario.location,
        timezone=scenario.timezone,
        url=scenario.url,
    )

    resolved_gt_url = (
        task_config.eval_config["gt_url"]
    )

    evaluator = GoatUrlMatch(
        gt_url=resolved_gt_url
    )

    reporter = ResultReporter()

    reporter.print_header(scenario)

    input(
        "Press ENTER to launch browser..."
    )

    async with async_playwright() as p:

        browser_mgr = BrowserManager()

        browser, context, page = (
            await browser_mgr.launch(p)
        )

        await evaluator.reset()

        logger.info(
            f"Opening {scenario.url}"
        )

        await page.goto(
            scenario.url,
            timeout=60000,
        )

        await evaluator.update(
            url=page.url
        )

        # -------------------------------------------------------------
        # URL TRACKER
        # -------------------------------------------------------------

        async def on_navigation():

            try:

                current_url = page.url

                await evaluator.update(
                    url=current_url
                )

                if "goat.com" in current_url:

                    print(
                        f"📍 URL: "
                        f"{current_url[:140]}"
                    )

            except Exception as e:

                logger.debug(e)

        page.on(
            "framenavigated",
            lambda _:
                asyncio.create_task(
                    on_navigation()
                )
        )

        print(
            "\n🌐 Interact manually in browser.\n"
        )

        await asyncio.to_thread(
            input,
            "Press ENTER when done... ",
        )

        final_url = page.url

        await evaluator.update(
            url=final_url
        )

        result = (
            await evaluator.compute_detailed()
        )

        await browser_mgr.close()

    reporter.print_result(
        result,
        evaluator,
        final_url,
    )


# =============================================================================
# MAIN
# =============================================================================

async def main():

    logger.remove()

    logger.add(
        sys.stderr,
        level="INFO",
    )

    print("\nAvailable Scenarios:\n")

    for i, scenario in enumerate(
        SCENARIOS,
        1,
    ):

        print(
            f"[{i}] {scenario.name}"
        )

    choice = input(
        "\nSelect scenario index: "
    )

    if (
        choice.isdigit()
        and 1 <= int(choice) <= len(SCENARIOS)
    ):

        await run_scenario(
            SCENARIOS[int(choice) - 1]
        )


if __name__ == "__main__":
    asyncio.run(main())