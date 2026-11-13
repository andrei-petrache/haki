"""The values of the haki-ro-staples list (scripts/ro_staples.py), and how
each is reached. Every value is an estimate, and the source says so
(catalog_sources.estimated); nothing here is measured by us.

- recipe: our own recipe, in grams of USDA SR Legacy foods (April 2018,
  CC0), written for this file (no text copied from a cookbook or site).
  Values per 100 g = the ingredients' nutrients / the cooked weight, where
  cooked weight = raw weight x yield_factor (water lost or, for grains,
  water taken up is counted as an ingredient). Meats that are roasted,
  grilled or fried in the dish use USDA's cooked cut where it exists, so
  their losses come from USDA. Fried dishes carry the oil they absorb as
  an ingredient; USDA's retention factors give no oil uptake, so that
  figure is our assumption, stated in each recipe's note.
- usda-dish: SR Legacy lists the prepared dish itself; its values as they
  are.
- analogue: the nearest SR Legacy food, with the reason.

    python3 -I scripts/ro_staples_values.py FoodData_Central_sr_legacy_food_csv_2018-04

writes scripts/ro_staples_usda.json (the SR Legacy rows used, so tests and
reviewers can recompute without the 200 MB dataset) and
app/catalog_data/ro_staples.json (what the import reads).
"""

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.ro_staples import RO_STAPLES
except ModuleNotFoundError:  # run as a script from backend/
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.ro_staples import RO_STAPLES

BACKEND = Path(__file__).resolve().parent.parent
SNAPSHOT = BACKEND / "scripts" / "ro_staples_usda.json"
CATALOG_FILE = BACKEND / "app" / "catalog_data" / "ro_staples.json"
# USDA nutrient ids (nutrient.csv): energy kcal, protein, carbohydrate, fat
NUTRIENTS = {"1008": "kcal", "1003": "protein", "1005": "carbs", "1004": "fat"}

SOURCE = {
    "key": "haki-ro-staples",
    "name": "Haki estimates: Romanian dishes and staples",
    "url": "https://github.com/andrei-petrache/haki/blob/main/backend/scripts/ro_staples_values.py",
    "license": "CC0-1.0",
    "attribution": (
        "Haki's own estimates, computed from recipes of USDA FoodData Central "
        "SR Legacy (April 2018) foods, or the nearest SR Legacy food."
    ),
    "attribution_required": False,
    "share_alike": False,
    "version": "2026-11-14",
    "estimated": True,
}

# SR Legacy foods used, by a short name. fdc_id from food.csv (2018-04)
USDA = {
    "apples": "171688",
    "bacon": "168277",
    "beans_white_cooked": "175203",
    "beans_white_dry": "175202",
    "beef_chuck_lean": "174018",
    "beef_ground": "174036",
    "bread_white": "174924",
    "breadcrumbs": "174928",
    "butter": "173410",
    "butter_cookies": "174950",
    "cabbage": "169975",
    "carp": "171952",
    "carp_cooked": "174185",
    "carrot": "170393",
    "cauliflower": "169986",
    "celery": "169988",
    "chicken_breast": "171077",
    "chicken_leg": "172378",
    "chicken_leg_roasted": "173617",
    "chicken_liver": "171060",
    "chicken_thigh": "173627",
    "chicken_whole": "171447",
    "cocoa": "169593",
    "cornmeal": "168867",
    "cottage_cheese": "172179",
    "cucumber": "168409",
    "dill": "172233",
    "egg": "171287",
    "egg_boiled": "173424",
    "eggplant": "169228",
    "feta": "173420",
    "flour": "168894",
    "french_fries": "170698",
    "garlic": "169230",
    "green_beans": "169961",
    "ham": "168295",
    "jam": "169641",
    "lamb": "174315",
    "lamb_liver": "172531",
    "lard": "171401",
    "lemon_juice": "167747",
    "mayonnaise": "171009",
    "milk": "171265",
    "mushrooms": "169251",
    "mustard": "172234",
    "oil": "171025",
    "onion": "170000",
    "paprika": "171329",
    "parsley": "170416",
    "parsnip": "170417",
    "peas": "170016",
    "pepper_green": "170427",
    "pepper_red": "170108",
    "phyllo": "172791",
    "pickles": "168558",
    "pita": "174915",
    "plums": "169949",
    "pork_ears": "167857",
    "pork_feet": "167859",
    "pork_ground": "167902",
    "pork_loin": "168238",
    "pork_neck_broiled": "167851",
    "pork_shoulder": "167843",
    "pork_shoulder_roasted": "167844",
    "potato": "170026",
    "potato_boiled": "170440",
    "raisins": "168165",
    "rice": "168877",
    "roe": "175132",
    "sauerkraut": "169279",
    "scallion": "170005",
    "semolina": "169715",
    "smoked_sausage": "174584",
    "sour_cherries": "173954",
    "sour_cream": "171257",
    "sugar": "169655",
    "sunflower_seeds": "170562",
    "tomato": "170457",
    "tomato_paste": "170459",
    "vinegar": "172237",
    "vine_leaves": "168575",
    "walnuts": "170187",
    "water": "173647",
    "wheat": "169720",
    "yeast": "175043",
    "zucchini": "169291",
    # usda-dish and analogues
    "braunschweiger": "171621",
    "bologna": "172013",
    "chicken_noodle_soup": "172909",
    "cottage_creamed": "172179",
    "doughnuts_yeast": "172758",
    "frankfurter": "172968",
    "gouda": "171241",
    "headcheese": "171630",
    "ham_sliced": "173864",
    "mashed_potatoes": "168555",
    "pastrami": "170204",
    "pate": "172930",
    "polish_sausage": "172954",
    "potato_salad": "169269",
    "pound_cake": "172704",
    "process_cheese": "170853",
    "queso_fresco": "172223",
    "rice_pudding": "168782",
    "ricotta": "171248",
    "romano": "171249",
    "salami": "172938",
    "salt_pork": "168287",
    "tomatoes_green": "170456",
}

OIL_UPTAKE = (
    "Fried: the oil it absorbs is our assumption, about 10% of the coated "
    "raw weight (USDA's retention factors give no oil uptake)."
)


@dataclass(frozen=True)
class Recipe:
    ingredients: tuple[tuple[str, float], ...]
    # Cooked weight / raw weight (water lost; water taken up is an ingredient)
    yield_factor: float
    note: str = ""


def r(yield_factor: float, *ingredients: tuple[str, float], note: str = "") -> Recipe:
    return Recipe(tuple(ingredients), yield_factor, note)


SOUP = 0.92  # a pot simmered about an hour loses some 8% of its water
STEW = 0.80
BAKED = 0.85

RECIPES: dict[str, Recipe] = {
    # Ciorbe și supe
    "ciorba-de-burta": r(
        SOUP,
        ("tripe_beef", 500),
        ("water", 2000),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 80),
        ("onion", 100),
        ("sour_cream", 200),
        ("egg", 60),
        ("garlic", 20),
        ("vinegar", 30),
    ),
    "ciorba-de-perisoare": r(
        SOUP,
        ("pork_ground", 300),
        ("rice", 40),
        ("egg", 50),
        ("onion", 150),
        ("carrot", 150),
        ("parsnip", 80),
        ("pepper_red", 100),
        ("tomato_paste", 40),
        ("water", 2200),
        ("lemon_juice", 40),
        ("parsley", 15),
        ("oil", 15),
    ),
    "ciorba-de-vacuta": r(
        SOUP,
        ("beef_chuck_lean", 400),
        ("water", 2200),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 80),
        ("onion", 150),
        ("potato", 300),
        ("pepper_red", 100),
        ("green_beans", 100),
        ("tomato_paste", 40),
        ("lemon_juice", 40),
        ("oil", 15),
        ("parsley", 15),
    ),
    "ciorba-de-pui": r(
        SOUP,
        ("chicken_whole", 500),
        ("water", 2200),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 80),
        ("onion", 150),
        ("potato", 250),
        ("pepper_red", 100),
        ("tomato_paste", 30),
        ("lemon_juice", 40),
        ("parsley", 15),
    ),
    "ciorba-radauteana": r(
        SOUP,
        ("chicken_whole", 600),
        ("water", 2200),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 60),
        ("onion", 120),
        ("sour_cream", 250),
        ("egg", 60),
        ("garlic", 25),
        ("vinegar", 30),
    ),
    "ciorba-de-fasole": r(
        SOUP,
        ("beans_white_dry", 300),
        ("water", 2300),
        ("onion", 150),
        ("carrot", 120),
        ("parsnip", 60),
        ("pepper_red", 80),
        ("tomato_paste", 40),
        ("oil", 30),
        ("vinegar", 20),
        ("dill", 10),
    ),
    "ciorba-de-fasole-cu-afumatura": r(
        SOUP,
        ("beans_white_dry", 300),
        ("water", 2300),
        ("ham", 150),
        ("bacon", 100),
        ("onion", 150),
        ("carrot", 120),
        ("parsnip", 60),
        ("pepper_red", 80),
        ("tomato_paste", 40),
        ("oil", 20),
        ("vinegar", 20),
        ("dill", 10),
    ),
    "ciorba-de-legume": r(
        SOUP,
        ("water", 2000),
        ("potato", 300),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 80),
        ("onion", 150),
        ("pepper_red", 100),
        ("green_beans", 150),
        ("peas", 100),
        ("cauliflower", 150),
        ("tomato", 150),
        ("tomato_paste", 30),
        ("oil", 25),
        ("lemon_juice", 40),
        ("parsley", 15),
    ),
    "ciorba-de-peste": r(
        SOUP,
        ("carp", 600),
        ("water", 2000),
        ("onion", 150),
        ("carrot", 120),
        ("parsnip", 80),
        ("pepper_red", 100),
        ("tomato", 200),
        ("potato", 200),
        ("lemon_juice", 40),
        ("parsley", 15),
    ),
    "ciorba-de-miel": r(
        SOUP,
        ("lamb", 500),
        ("water", 2200),
        ("scallion", 150),
        ("onion", 80),
        ("carrot", 120),
        ("parsnip", 60),
        ("pepper_red", 80),
        ("rice", 40),
        ("sour_cream", 200),
        ("egg", 60),
        ("lemon_juice", 40),
        ("dill", 20),
    ),
    "ciorba-de-cartofi": r(
        SOUP,
        ("potato", 600),
        ("water", 2000),
        ("onion", 150),
        ("carrot", 120),
        ("pepper_red", 80),
        ("tomato_paste", 30),
        ("oil", 30),
        ("sour_cream", 150),
        ("lemon_juice", 30),
        ("parsley", 15),
    ),
    "supa-de-pui-cu-galuste": r(
        SOUP,
        ("chicken_whole", 500),
        ("water", 2300),
        ("carrot", 150),
        ("parsnip", 100),
        ("celery", 80),
        ("onion", 100),
        ("semolina", 120),
        ("egg", 100),
        ("oil", 20),
    ),
    "supa-crema-de-legume": r(
        0.90,
        ("potato", 300),
        ("carrot", 300),
        ("zucchini", 300),
        ("onion", 150),
        ("celery", 100),
        ("butter", 30),
        ("sour_cream", 100),
        ("water", 1200),
    ),
    "supa-crema-de-ciuperci": r(
        0.90,
        ("mushrooms", 600),
        ("onion", 150),
        ("potato", 200),
        ("butter", 40),
        ("sour_cream", 200),
        ("flour", 20),
        ("water", 1000),
        ("garlic", 10),
    ),
    # Feluri principale
    "sarmale-varza": r(
        0.75,
        ("pork_ground", 500),
        ("rice", 100),
        ("onion", 150),
        ("sauerkraut", 400),
        ("tomato_paste", 50),
        ("bacon", 100),
        ("oil", 20),
        ("water", 600),
        ("paprika", 3),
        ("dill", 10),
    ),
    "sarmale-vita-de-vie": r(
        0.75,
        ("pork_ground", 300),
        ("beef_ground", 200),
        ("rice", 100),
        ("onion", 150),
        ("vine_leaves", 200),
        ("tomato_paste", 40),
        ("oil", 20),
        ("water", 600),
        ("dill", 15),
    ),
    "mici": r(
        0.75,
        ("beef_ground", 600),
        ("pork_ground", 200),
        ("garlic", 30),
        ("water", 120),
        ("paprika", 5),
        note="Grilled: a quarter of the raw weight lost, water and dripping fat.",
    ),
    "chiftele-de-carne": r(
        0.80,
        ("pork_ground", 500),
        ("potato", 200),
        ("onion", 100),
        ("egg", 100),
        ("bread_white", 80),
        ("flour", 50),
        ("parsley", 15),
        ("dill", 10),
        ("oil", 100),
        note=OIL_UPTAKE,
    ),
    "parjoale": r(
        0.80,
        ("pork_ground", 300),
        ("beef_ground", 200),
        ("potato", 150),
        ("onion", 100),
        ("egg", 100),
        ("bread_white", 80),
        ("breadcrumbs", 80),
        ("garlic", 10),
        ("parsley", 15),
        ("oil", 100),
        note=OIL_UPTAKE,
    ),
    "snitel-de-pui": r(
        0.85,
        ("chicken_breast", 600),
        ("egg", 100),
        ("flour", 60),
        ("breadcrumbs", 120),
        ("oil", 90),
        note=OIL_UPTAKE,
    ),
    "snitel-de-porc": r(
        0.85,
        ("pork_loin", 600),
        ("egg", 100),
        ("flour", 60),
        ("breadcrumbs", 120),
        ("oil", 90),
        note=OIL_UPTAKE,
    ),
    "tochitura": r(
        STEW,
        ("pork_shoulder", 600),
        ("smoked_sausage", 250),
        ("onion", 100),
        ("garlic", 20),
        ("tomato_paste", 30),
        ("lard", 30),
        ("water", 200),
    ),
    "tocanita-de-porc": r(
        STEW,
        ("pork_shoulder", 700),
        ("onion", 400),
        ("pepper_red", 150),
        ("tomato_paste", 60),
        ("oil", 40),
        ("garlic", 15),
        ("water", 400),
        ("paprika", 5),
    ),
    "ostropel-de-pui": r(
        STEW,
        ("chicken_leg", 1000),
        ("tomato_paste", 80),
        ("garlic", 40),
        ("flour", 30),
        ("oil", 40),
        ("water", 400),
    ),
    "papricas-de-pui": r(
        STEW,
        ("chicken_leg", 1000),
        ("onion", 300),
        ("pepper_red", 200),
        ("sour_cream", 200),
        ("flour", 20),
        ("paprika", 15),
        ("oil", 40),
        ("water", 300),
    ),
    "ciulama-de-pui": r(
        BAKED,
        ("chicken_breast", 500),
        ("chicken_thigh", 300),
        ("butter", 50),
        ("flour", 60),
        ("milk", 500),
        ("sour_cream", 150),
        ("onion", 100),
        ("water", 200),
        ("dill", 10),
    ),
    "ciulama-de-ciuperci": r(
        STEW,
        ("mushrooms", 800),
        ("butter", 50),
        ("flour", 50),
        ("milk", 400),
        ("sour_cream", 150),
        ("onion", 100),
        ("garlic", 10),
        ("dill", 10),
    ),
    "friptura-de-porc": r(
        1.0,
        ("pork_shoulder_roasted", 1000),
        ("oil", 10),
        ("garlic", 20),
        note="USDA's roasted shoulder: its cooking loss is USDA's.",
    ),
    "ceafa-la-gratar": r(
        1.0,
        ("pork_neck_broiled", 1000),
        ("oil", 10),
        ("garlic", 10),
        note="USDA's broiled shoulder blade steaks, the cut ceafă is.",
    ),
    "pulpe-de-pui-la-cuptor": r(
        1.0,
        ("chicken_leg_roasted", 1000),
        ("oil", 15),
        ("garlic", 10),
        ("paprika", 5),
        note="USDA's roasted chicken leg, meat and skin.",
    ),
    "ficatei-cu-ceapa": r(
        0.75,
        ("chicken_liver", 600),
        ("onion", 400),
        ("oil", 40),
        ("tomato_paste", 20),
    ),
    "fasole-cu-carnati": r(
        STEW,
        ("beans_white_dry", 400),
        ("water", 1300),
        ("smoked_sausage", 400),
        ("onion", 250),
        ("tomato_paste", 60),
        ("oil", 40),
        ("garlic", 15),
        ("paprika", 5),
    ),
    "iahnie-de-fasole": r(
        STEW,
        ("beans_white_dry", 400),
        ("water", 1200),
        ("onion", 300),
        ("carrot", 100),
        ("tomato_paste", 60),
        ("oil", 60),
        ("garlic", 20),
        ("paprika", 5),
    ),
    "varza-calita": r(
        0.75,
        ("cabbage", 1200),
        ("onion", 200),
        ("tomato_paste", 60),
        ("oil", 60),
        ("paprika", 5),
        ("dill", 10),
    ),
    "varza-cu-carne": r(
        0.75,
        ("cabbage", 1000),
        ("pork_shoulder", 500),
        ("onion", 200),
        ("tomato_paste", 60),
        ("oil", 40),
        ("water", 200),
    ),
    "musaca-de-cartofi": r(
        STEW,
        ("potato", 1000),
        ("pork_ground", 300),
        ("beef_ground", 200),
        ("onion", 200),
        ("egg", 150),
        ("milk", 300),
        ("flour", 30),
        ("oil", 50),
        ("tomato_paste", 40),
    ),
    "musaca-de-vinete": r(
        0.75,
        ("eggplant", 1000),
        ("pork_ground", 300),
        ("beef_ground", 200),
        ("onion", 200),
        ("tomato", 300),
        ("egg", 100),
        ("milk", 200),
        ("flour", 30),
        ("oil", 100),
    ),
    "ardei-umpluti": r(
        STEW,
        ("pepper_green", 800),
        ("pork_ground", 400),
        ("rice", 100),
        ("onion", 150),
        ("tomato", 300),
        ("tomato_paste", 60),
        ("oil", 20),
        ("water", 400),
        ("dill", 10),
    ),
    "mancare-de-mazare-cu-pui": r(
        BAKED,
        ("peas", 800),
        ("chicken_leg", 600),
        ("onion", 200),
        ("carrot", 100),
        ("tomato_paste", 50),
        ("oil", 40),
        ("dill", 15),
        ("water", 300),
    ),
    "tocana-de-cartofi": r(
        BAKED,
        ("potato", 1200),
        ("onion", 250),
        ("pepper_red", 150),
        ("tomato_paste", 60),
        ("oil", 60),
        ("paprika", 5),
        ("water", 400),
        ("parsley", 15),
    ),
    "ghiveci": r(
        STEW,
        ("eggplant", 300),
        ("zucchini", 300),
        ("pepper_red", 300),
        ("potato", 300),
        ("carrot", 200),
        ("onion", 250),
        ("green_beans", 200),
        ("tomato", 400),
        ("cauliflower", 200),
        ("oil", 100),
        ("tomato_paste", 40),
    ),
    "pilaf-de-pui": r(
        0.90,
        ("chicken_thigh", 500),
        ("rice", 300),
        ("water", 750),
        ("onion", 150),
        ("carrot", 100),
        ("pepper_red", 80),
        ("oil", 40),
    ),
    "drob-de-miel": r(
        BAKED,
        ("lamb_liver", 400),
        ("lamb", 200),
        ("scallion", 300),
        ("dill", 50),
        ("parsley", 30),
        ("egg", 250),
        ("bread_white", 100),
        ("milk", 100),
        ("oil", 20),
        note="Lamb liver and meat stand in for the mixed offal.",
    ),
    "stufat-de-miel": r(
        STEW,
        ("lamb", 800),
        ("scallion", 400),
        ("garlic", 60),
        ("tomato_paste", 50),
        ("oil", 40),
        ("water", 300),
        ("dill", 20),
    ),
    "saramura-de-crap": r(
        1.0,
        ("carp_cooked", 800),
        ("water", 300),
        ("garlic", 40),
        ("tomato", 200),
        ("pepper_red", 100),
        ("oil", 20),
        ("vinegar", 20),
        note="USDA's carp cooked by dry heat, with the brine it is served in.",
    ),
    "crap-prajit": r(
        0.80,
        ("carp", 800),
        ("flour", 80),
        ("oil", 90),
        note=OIL_UPTAKE,
    ),
    "shaorma-de-pui": r(
        0.90,
        ("chicken_thigh", 300),
        ("pita", 200),
        ("cabbage", 100),
        ("tomato", 80),
        ("pickles", 60),
        ("french_fries", 100),
        ("mayonnaise", 40),
        ("garlic", 10),
        ("oil", 15),
        note="USDA's fast-food french fries, as they come in the wrap.",
    ),
    # Mămăligă și garnituri
    "mamaliga": r(0.92, ("cornmeal", 250), ("water", 1000)),
    "mamaliga-cu-branza-si-smantana": r(
        0.94,
        ("cornmeal", 250),
        ("water", 1000),
        ("feta", 200),
        ("sour_cream", 200),
        ("butter", 30),
        note="Feta stands in for telemea (see the telemea analogue).",
    ),
    "bulz": r(
        BAKED,
        ("cornmeal", 200),
        ("water", 800),
        ("feta", 200),
        ("butter", 30),
        ("egg", 50),
    ),
    "cartofi-taranesti": r(
        0.75,
        ("potato", 1000),
        ("onion", 150),
        ("bacon", 100),
        ("oil", 60),
        ("paprika", 3),
    ),
    "orez-cu-legume": r(
        0.95,
        ("rice", 300),
        ("water", 700),
        ("carrot", 100),
        ("peas", 150),
        ("pepper_red", 100),
        ("onion", 100),
        ("oil", 40),
    ),
    "mujdei": r(1.0, ("garlic", 100), ("water", 100), ("oil", 30)),
    # Salate, aperitive și conserve
    "salata-de-vinete": r(
        0.625,
        ("eggplant", 1000),
        ("oil", 120),
        ("onion", 80),
        note="Baked and drained, the aubergine loses about 45% of its weight.",
    ),
    "zacusca": r(
        0.60,
        ("eggplant", 1000),
        ("pepper_red", 1000),
        ("onion", 300),
        ("tomato_paste", 150),
        ("oil", 250),
    ),
    "salata-de-icre": r(
        1.0,
        ("roe", 150),
        ("oil", 350),
        ("onion", 50),
        ("lemon_juice", 20),
        ("bread_white", 30),
    ),
    "fasole-batuta": r(
        0.95,
        ("beans_white_cooked", 750),
        ("garlic", 20),
        ("oil", 90),
        ("onion", 150),
        ("paprika", 3),
        note="USDA's boiled white beans.",
    ),
    "salata-de-boeuf": r(
        0.93,
        ("chicken_breast", 300),
        ("potato", 400),
        ("carrot", 200),
        ("parsnip", 100),
        ("peas", 100),
        ("pickles", 150),
        ("pepper_red", 100),
        ("mayonnaise", 250),
        ("mustard", 15),
        ("egg", 100),
    ),
    "salata-orientala": r(
        1.0,
        ("potato_boiled", 800),
        ("egg_boiled", 200),
        ("onion", 150),
        ("oil", 50),
        ("vinegar", 10),
        ("parsley", 15),
        note="USDA's boiled potatoes and hard-boiled eggs.",
    ),
    "salata-de-varza": r(
        1.0,
        ("cabbage", 500),
        ("oil", 30),
        ("vinegar", 20),
        ("dill", 10),
    ),
    "salata-de-rosii-cu-castraveti": r(
        1.0,
        ("tomato", 400),
        ("cucumber", 300),
        ("onion", 50),
        ("oil", 25),
        ("vinegar", 10),
    ),
    "ardei-copti": r(
        0.75,
        ("pepper_red", 1000),
        ("oil", 50),
        ("vinegar", 50),
        ("garlic", 20),
        ("water", 100),
        note="Roasted and peeled, the peppers lose about 30% of their weight.",
    ),
    "oua-umplute": r(
        1.0,
        ("egg_boiled", 600),
        ("mayonnaise", 80),
        ("mustard", 10),
        ("butter", 20),
        ("parsley", 5),
    ),
    "piftie": r(
        0.60,
        ("pork_feet", 1000),
        ("pork_ears", 300),
        ("water", 2500),
        ("garlic", 60),
        ("carrot", 100),
        ("onion", 100),
        note="Boiled down to the set aspic; the vegetables stay in the count.",
    ),
    # Pâine și patiserie
    "covrigi": r(
        BAKED,
        ("flour", 1000),
        ("water", 550),
        ("yeast", 15),
        ("oil", 40),
        ("sugar", 20),
    ),
    "placinta-cu-branza": r(
        0.90,
        ("phyllo", 400),
        ("cottage_cheese", 600),
        ("egg", 150),
        ("sugar", 120),
        ("butter", 100),
        ("raisins", 50),
        ("sour_cream", 100),
    ),
    "placinta-cu-mere": r(
        0.80,
        ("flour", 400),
        ("butter", 200),
        ("sugar", 150),
        ("egg", 50),
        ("apples", 1000),
    ),
    "langosi": r(
        0.90,
        ("flour", 500),
        ("milk", 250),
        ("yeast", 10),
        ("sugar", 10),
        ("feta", 200),
        ("oil", 100),
        note=OIL_UPTAKE,
    ),
    # Deserturi
    "cozonac-cu-nuca": r(
        0.88,
        ("flour", 1000),
        ("milk", 400),
        ("sugar", 450),
        ("butter", 200),
        ("egg", 300),
        ("yeast", 30),
        ("walnuts", 400),
        ("cocoa", 30),
        ("raisins", 100),
    ),
    "pasca": r(
        0.88,
        ("flour", 500),
        ("milk", 200),
        ("sugar", 300),
        ("butter", 80),
        ("egg", 300),
        ("yeast", 15),
        ("cottage_cheese", 1000),
        ("raisins", 100),
        ("sour_cream", 150),
    ),
    "papanasi": r(
        0.92,
        ("cottage_cheese", 500),
        ("egg", 100),
        ("flour", 200),
        ("sugar", 50),
        ("semolina", 50),
        ("oil", 85),
        ("sour_cream", 300),
        ("jam", 200),
        note=OIL_UPTAKE + " Served with sour cream and jam, counted in.",
    ),
    "clatite-cu-dulceata": r(
        0.90,
        ("flour", 250),
        ("milk", 500),
        ("egg", 150),
        ("oil", 30),
        ("sugar", 20),
        ("jam", 300),
    ),
    "clatite-cu-branza": r(
        0.90,
        ("flour", 250),
        ("milk", 500),
        ("egg", 200),
        ("oil", 30),
        ("sugar", 100),
        ("cottage_cheese", 500),
        ("raisins", 50),
    ),
    "cornulete": r(
        0.88,
        ("flour", 500),
        ("butter", 200),
        ("sour_cream", 150),
        ("sugar", 150),
        ("egg", 50),
        ("jam", 200),
    ),
    "salam-de-biscuiti": r(
        1.0,
        ("butter_cookies", 500),
        ("butter", 150),
        ("sugar", 150),
        ("cocoa", 40),
        ("walnuts", 100),
        ("milk", 100),
    ),
    "gris-cu-lapte": r(
        0.92,
        ("semolina", 100),
        ("milk", 1000),
        ("sugar", 80),
        ("butter", 20),
    ),
    "coliva": r(
        1.0,
        ("wheat", 500),
        ("water", 750),
        ("walnuts", 250),
        ("sugar", 250),
        ("raisins", 100),
        note="The water the boiled wheat takes up is counted in.",
    ),
    "dulceata-de-visine": r(
        0.70,
        ("sour_cherries", 1000),
        ("sugar", 1000),
        ("lemon_juice", 30),
    ),
    "magiun-de-prune": r(
        0.30,
        ("plums", 3000),
        note="Plums cooked down to a third of their weight, no sugar added.",
    ),
    "halva": r(
        0.85,
        ("sunflower_seeds", 500),
        ("sugar", 400),
        ("water", 150),
        note="Sunflower halva; USDA's halva is tahini (sesame).",
    ),
}

USDA["tripe_beef"] = "170599"

USDA_DISH: dict[str, str] = {
    "supa-de-pui-cu-taitei": "chicken_noodle_soup",
    "piure-de-cartofi": "mashed_potatoes",
    "cartofi-prajiti": "french_fries",
    "salata-de-cartofi": "potato_salad",
    "gogosi": "doughnuts_yeast",
    "chec": "pound_cake",
    "orez-cu-lapte": "rice_pudding",
}

ANALOGUES: dict[str, tuple[str, str]] = {
    "muraturi-asortate": (
        "pickles",
        "Mostly cucumbers in brine and vinegar, as dill pickles are.",
    ),
    "gogonele-murate": (
        "tomatoes_green",
        "Green tomatoes; brining changes little but the salt.",
    ),
    "carnati-afumati": ("smoked_sausage", "A smoked pork sausage."),
    "carnati-plescoi": (
        "polish_sausage",
        "A smoked, spiced sausage; Pleșcoi's mutton and beef are not in USDA.",
    ),
    "salam-de-sibiu": ("salami", "A dry-cured pork salami."),
    "parizer": ("bologna", "A fine emulsified cooked sausage, as bologna is."),
    "crenvursti": ("frankfurter", "Frankfurters."),
    "kaizer": ("bacon", "Smoked cured pork belly, as bacon is."),
    "sunca-presata": ("ham_sliced", "Pressed sliced ham, about 11% fat."),
    "pastrama-de-oaie": (
        "pastrami",
        "Cured, spiced, smoked meat; USDA has no mutton pastrami, which is fattier.",
    ),
    "slanina-afumata": ("salt_pork", "Cured pork fatback."),
    "caltabos": ("braunschweiger", "A pork liver sausage."),
    "toba": ("headcheese", "Pork head cheese."),
    "pate-de-ficat": ("pate", "A liver pâté."),
    "telemea-de-vaca": (
        "feta",
        "A brined white cheese like feta, 21% fat; makers range widely.",
    ),
    "telemea-de-oaie": (
        "feta",
        "A brined white sheep's cheese like feta, 21% fat; makers range widely.",
    ),
    "cascaval": ("gouda", "A semi-hard yellow cheese like gouda, 27% fat."),
    "branza-de-burduf": (
        "romano",
        "A strong aged sheep's cheese; romano is the nearest USDA has.",
    ),
    "urda": ("ricotta", "A whey cheese, as ricotta is."),
    "cas": ("queso_fresco", "A fresh unripened curd cheese."),
    "branza-de-vaci": (
        "cottage_creamed",
        "A fresh cow's curd cheese, about 4% fat like creamed cottage cheese.",
    ),
    "branza-topita": ("process_cheese", "A processed cheese."),
}

PER_100G = ("calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g")
KEYS = ("kcal", "protein", "carbs", "fat")


def from_recipe(recipe: Recipe, usda: dict[str, dict]) -> tuple[dict, str]:
    raw = sum(grams for _, grams in recipe.ingredients)
    cooked = raw * recipe.yield_factor
    totals = dict.fromkeys(KEYS, 0.0)
    for name, grams in recipe.ingredients:
        row = usda[USDA[name]]
        for key in KEYS:
            totals[key] += row[key] * grams / 100
    values = {
        field: totals[key] / cooked * 100
        for field, key in zip(PER_100G, KEYS, strict=True)
    }
    parts = ", ".join(
        f"{grams:g} g {usda[USDA[name]]['description']} [{USDA[name]}]"
        for name, grams in recipe.ingredients
    )
    description = (
        f"Recipe: {parts}. Cooked weight {recipe.yield_factor:g} x raw "
        f"({cooked:.0f} g of {raw:.0f} g)."
    )
    if recipe.note:
        description += f" {recipe.note}"
    if OIL_UPTAKE in recipe.note:
        description += f" {oil_effect(recipe, usda, cooked)}"
    return values, description


def oil_effect(recipe: Recipe, usda: dict[str, dict], cooked: float) -> str:
    """What our oil uptake assumption weighs: 5 points of the coated raw
    weight more or less oil, in kcal per 100 g of the dish (review)."""
    coated = sum(grams for name, grams in recipe.ingredients if name != "oil")
    kcal = usda[USDA["oil"]]["kcal"] * 0.05 * coated / 100 / cooked * 100
    return (
        "Each 5 points of oil uptake more or less move it by about "
        f"{kcal:.0f} kcal/100 g."
    )


def from_food(name: str, usda: dict[str, dict], prefix: str) -> tuple[dict, str]:
    row = usda[USDA[name]]
    values = {field: row[key] for field, key in zip(PER_100G, KEYS, strict=True)}
    return values, f"{prefix}: {row['description']} [{USDA[name]}]."


def compute(usda: dict[str, dict]) -> list[dict]:
    """The catalog items, in the list's order, from the SR Legacy rows."""
    items = []
    for ref, name_ro, name, method in RO_STAPLES:
        if method == "recipe":
            values, description = from_recipe(RECIPES[ref], usda)
        elif method == "usda-dish":
            values, description = from_food(USDA_DISH[ref], usda, "USDA dish")
        else:
            food, reason = ANALOGUES[ref]
            values, description = from_food(food, usda, "Analogue")
            description += f" {reason}"
        items.append(
            {
                "ref": ref,
                "name": name,
                "name_ro": name_ro,
                **{field: round(value, 1) for field, value in values.items()},
                "source_description": description,
            }
        )
    return items


def catalog_file(usda: dict[str, dict]) -> dict:
    return {"source": SOURCE, "foods": compute(usda)}


def read_snapshot(path: Path = SNAPSHOT) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_from_csv(directory: Path) -> dict[str, dict]:
    """The SR Legacy rows this file uses: description and four nutrients."""
    wanted = set(USDA.values())
    rows: dict[str, dict] = {}
    with open(directory / "food.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["fdc_id"] in wanted:
                rows[row["fdc_id"]] = {"description": row["description"]}
                rows[row["fdc_id"]].update(dict.fromkeys(KEYS, 0.0))
    with open(directory / "food_nutrient.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = NUTRIENTS.get(row["nutrient_id"])
            if key and row["fdc_id"] in rows:
                rows[row["fdc_id"]][key] = float(row["amount"])
    missing = wanted - set(rows)
    if missing:
        raise SystemExit(f"not in SR Legacy: {sorted(missing)}")
    return dict(sorted(rows.items()))


def write_json(path: Path, value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> None:
    usda = snapshot_from_csv(Path(argv[0]))
    write_json(SNAPSHOT, usda)
    write_json(CATALOG_FILE, catalog_file(usda))
    print(f"{len(usda)} SR Legacy rows, {len(RO_STAPLES)} items written")


if __name__ == "__main__":
    main(sys.argv[1:])
