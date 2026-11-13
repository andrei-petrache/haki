"""The haki-ro-staples selection: Romanian dishes and staples that no
clearly licensed source lists, so Haki estimates their nutrients itself.

The names are decided (#143, decisions.md); the values come in a later
pull request, and nothing here is imported yet. Every value is an
estimate, and the source says so (`catalog_sources.estimated`). Values
are CC0-1.0, like their USDA SR Legacy inputs, which are credited. The
recipes are ours, in grams; no text is copied from cookbooks or sites.

Method per item:

- recipe: computed from a recipe of USDA SR Legacy ingredients, with
  cooking losses from USDA's cooked counterparts. A fried item records
  where its oil uptake figure comes from (USDA's retention factors have
  none).
- usda-dish: SR Legacy lists the prepared dish itself, which is more
  accurate than a recipe with guessed losses; the values PR records its
  fdc_id (and falls back to a recipe only if it is missing).
- analogue: the nearest USDA food, with the reason recorded (a Romanian
  cheese or sausage that USDA does not list under its own name).

Refs are permanent once imported: never rename one after that. English
names carry the Romanian one in parentheses, so a search in English tells
ours apart from USDA's generic food of the same name.
"""

METHODS = ("recipe", "usda-dish", "analogue")

# ref (the stable id at this source), Romanian name, English name, method
RO_STAPLES = [
    # Ciorbe și supe
    (
        "ciorba-de-burta",
        "Ciorbă de burtă",
        "Tripe sour soup (Ciorbă de burtă)",
        "recipe",
    ),
    (
        "ciorba-de-perisoare",
        "Ciorbă de perișoare",
        "Meatball sour soup (Ciorbă de perișoare)",
        "recipe",
    ),
    (
        "ciorba-de-vacuta",
        "Ciorbă de văcuță",
        "Beef and vegetable sour soup (Ciorbă de văcuță)",
        "recipe",
    ),
    ("ciorba-de-pui", "Ciorbă de pui", "Chicken sour soup (Ciorbă de pui)", "recipe"),
    (
        "ciorba-radauteana",
        "Ciorbă rădăuțeană",
        "Radauti chicken sour soup (Ciorbă rădăuțeană)",
        "recipe",
    ),
    (
        "ciorba-de-fasole",
        "Ciorbă de fasole",
        "Bean sour soup (Ciorbă de fasole)",
        "recipe",
    ),
    (
        "ciorba-de-fasole-cu-afumatura",
        "Ciorbă de fasole cu afumătură",
        "Bean sour soup with smoked pork (Ciorbă de fasole cu afumătură)",
        "recipe",
    ),
    (
        "ciorba-de-legume",
        "Ciorbă de legume",
        "Vegetable sour soup (Ciorbă de legume)",
        "recipe",
    ),
    (
        "ciorba-de-peste",
        "Ciorbă de pește",
        "Fish sour soup (Ciorbă de pește)",
        "recipe",
    ),
    ("ciorba-de-miel", "Ciorbă de miel", "Lamb sour soup (Ciorbă de miel)", "recipe"),
    (
        "ciorba-de-cartofi",
        "Ciorbă de cartofi",
        "Potato sour soup (Ciorbă de cartofi)",
        "recipe",
    ),
    (
        "supa-de-pui-cu-taitei",
        "Supă de pui cu tăiței",
        "Chicken noodle soup (Supă de pui cu tăiței)",
        "usda-dish",
    ),
    (
        "supa-de-pui-cu-galuste",
        "Supă de pui cu găluște",
        "Chicken soup with semolina dumplings (Supă de pui cu găluște)",
        "recipe",
    ),
    (
        "supa-crema-de-legume",
        "Supă cremă de legume",
        "Cream of vegetable soup (Supă cremă de legume)",
        "recipe",
    ),
    (
        "supa-crema-de-ciuperci",
        "Supă cremă de ciuperci",
        "Cream of mushroom soup (Supă cremă de ciuperci)",
        "recipe",
    ),
    # Feluri principale
    (
        "sarmale-varza",
        "Sarmale în foi de varză",
        "Stuffed cabbage rolls (Sarmale în foi de varză)",
        "recipe",
    ),
    (
        "sarmale-vita-de-vie",
        "Sarmale în foi de viță",
        "Stuffed vine leaves (Sarmale în foi de viță)",
        "recipe",
    ),
    ("mici", "Mici", "Grilled minced meat rolls (Mici)", "recipe"),
    (
        "chiftele-de-carne",
        "Chiftele de carne",
        "Fried meatballs (Chiftele de carne)",
        "recipe",
    ),
    (
        "parjoale",
        "Pârjoale moldovenești",
        "Moldavian meat patties (Pârjoale moldovenești)",
        "recipe",
    ),
    (
        "snitel-de-pui",
        "Șnițel de pui",
        "Breaded chicken schnitzel (Șnițel de pui)",
        "recipe",
    ),
    (
        "snitel-de-porc",
        "Șnițel de porc",
        "Breaded pork schnitzel (Șnițel de porc)",
        "recipe",
    ),
    ("tochitura", "Tochitură", "Pork stew with sausage (Tochitură)", "recipe"),
    ("tocanita-de-porc", "Tocăniță de porc", "Pork stew (Tocăniță de porc)", "recipe"),
    (
        "ostropel-de-pui",
        "Ostropel de pui",
        "Chicken in tomato and garlic sauce (Ostropel de pui)",
        "recipe",
    ),
    (
        "papricas-de-pui",
        "Papricaș de pui",
        "Chicken paprikash (Papricaș de pui)",
        "recipe",
    ),
    (
        "ciulama-de-pui",
        "Ciulama de pui",
        "Chicken in white sauce (Ciulama de pui)",
        "recipe",
    ),
    (
        "ciulama-de-ciuperci",
        "Ciulama de ciuperci",
        "Mushrooms in white sauce (Ciulama de ciuperci)",
        "recipe",
    ),
    (
        "friptura-de-porc",
        "Friptură de porc la tavă",
        "Pan-roasted pork (Friptură de porc la tavă)",
        "recipe",
    ),
    (
        "ceafa-la-gratar",
        "Ceafă de porc la grătar",
        "Grilled pork neck (Ceafă de porc la grătar)",
        "recipe",
    ),
    (
        "pulpe-de-pui-la-cuptor",
        "Pulpe de pui la cuptor",
        "Roast chicken legs (Pulpe de pui la cuptor)",
        "recipe",
    ),
    (
        "ficatei-cu-ceapa",
        "Ficăței de pui cu ceapă",
        "Chicken livers with onion (Ficăței de pui cu ceapă)",
        "recipe",
    ),
    (
        "fasole-cu-carnati",
        "Fasole cu cârnați",
        "Beans with sausages (Fasole cu cârnați)",
        "recipe",
    ),
    ("iahnie-de-fasole", "Iahnie de fasole", "Bean stew (Iahnie de fasole)", "recipe"),
    ("varza-calita", "Varză călită", "Braised cabbage (Varză călită)", "recipe"),
    (
        "varza-cu-carne",
        "Varză călită cu carne de porc",
        "Braised cabbage with pork (Varză călită cu carne de porc)",
        "recipe",
    ),
    (
        "musaca-de-cartofi",
        "Musaca de cartofi",
        "Potato moussaka (Musaca de cartofi)",
        "recipe",
    ),
    (
        "musaca-de-vinete",
        "Musaca de vinete",
        "Aubergine moussaka (Musaca de vinete)",
        "recipe",
    ),
    ("ardei-umpluti", "Ardei umpluți", "Stuffed peppers (Ardei umpluți)", "recipe"),
    (
        "mancare-de-mazare-cu-pui",
        "Mâncare de mazăre cu pui",
        "Pea stew with chicken (Mâncare de mazăre cu pui)",
        "recipe",
    ),
    (
        "tocana-de-cartofi",
        "Tocană de cartofi",
        "Potato stew (Tocană de cartofi)",
        "recipe",
    ),
    ("ghiveci", "Ghiveci de legume", "Vegetable stew (Ghiveci de legume)", "recipe"),
    ("pilaf-de-pui", "Pilaf de pui", "Chicken pilaf (Pilaf de pui)", "recipe"),
    ("drob-de-miel", "Drob de miel", "Lamb offal loaf (Drob de miel)", "recipe"),
    (
        "stufat-de-miel",
        "Stufat de miel",
        "Lamb and green onion stew (Stufat de miel)",
        "recipe",
    ),
    (
        "saramura-de-crap",
        "Saramură de crap",
        "Grilled carp in brine (Saramură de crap)",
        "recipe",
    ),
    ("crap-prajit", "Crap prăjit", "Fried carp (Crap prăjit)", "recipe"),
    (
        "shaorma-de-pui",
        "Shaorma de pui",
        "Chicken shawarma wrap (Shaorma de pui)",
        "recipe",
    ),
    # Mămăligă și garnituri
    ("mamaliga", "Mămăligă", "Cornmeal porridge (Mămăligă)", "recipe"),
    (
        "mamaliga-cu-branza-si-smantana",
        "Mămăligă cu brânză și smântână",
        "Mamaliga with cheese and sour cream (Mămăligă cu brânză și smântână)",
        "recipe",
    ),
    ("bulz", "Bulz", "Baked mamaliga with cheese (Bulz)", "recipe"),
    (
        "piure-de-cartofi",
        "Piure de cartofi",
        "Mashed potatoes (Piure de cartofi)",
        "usda-dish",
    ),
    (
        "cartofi-prajiti",
        "Cartofi prăjiți",
        "French fries (Cartofi prăjiți)",
        "usda-dish",
    ),
    (
        "cartofi-taranesti",
        "Cartofi țărănești",
        "Country-style potatoes (Cartofi țărănești)",
        "recipe",
    ),
    (
        "orez-cu-legume",
        "Orez cu legume",
        "Rice with vegetables (Orez cu legume)",
        "recipe",
    ),
    ("mujdei", "Mujdei de usturoi", "Garlic sauce (Mujdei de usturoi)", "recipe"),
    # Salate, aperitive și conserve
    (
        "salata-de-vinete",
        "Salată de vinete",
        "Aubergine spread (Salată de vinete)",
        "recipe",
    ),
    ("zacusca", "Zacuscă", "Roasted vegetable spread (Zacuscă)", "recipe"),
    (
        "salata-de-icre",
        "Salată de icre de crap",
        "Carp roe spread (Salată de icre de crap)",
        "recipe",
    ),
    ("fasole-batuta", "Fasole bătută", "Mashed bean spread (Fasole bătută)", "recipe"),
    (
        "salata-de-boeuf",
        "Salată de boeuf",
        "Beef and vegetable salad (Salată de boeuf)",
        "recipe",
    ),
    (
        "salata-orientala",
        "Salată orientală",
        "Potato, egg and onion salad (Salată orientală)",
        "recipe",
    ),
    (
        "salata-de-cartofi",
        "Salată de cartofi",
        "Potato salad (Salată de cartofi)",
        "usda-dish",
    ),
    ("salata-de-varza", "Salată de varză", "Cabbage salad (Salată de varză)", "recipe"),
    (
        "salata-de-rosii-cu-castraveti",
        "Salată de roșii cu castraveți",
        "Tomato and cucumber salad (Salată de roșii cu castraveți)",
        "recipe",
    ),
    (
        "ardei-copti",
        "Ardei copți în oțet",
        "Roasted peppers in vinegar (Ardei copți în oțet)",
        "recipe",
    ),
    ("oua-umplute", "Ouă umplute", "Stuffed eggs (Ouă umplute)", "recipe"),
    ("piftie", "Piftie", "Pork aspic (Piftie)", "recipe"),
    (
        "muraturi-asortate",
        "Murături asortate",
        "Mixed pickles (Murături asortate)",
        "analogue",
    ),
    (
        "gogonele-murate",
        "Gogonele murate",
        "Pickled green tomatoes (Gogonele murate)",
        "analogue",
    ),
    # Mezeluri și carne preparată
    (
        "carnati-afumati",
        "Cârnați afumați de porc",
        "Smoked pork sausages (Cârnați afumați de porc)",
        "analogue",
    ),
    (
        "carnati-plescoi",
        "Cârnați de Pleșcoi",
        "Plescoi sausages (Cârnați de Pleșcoi)",
        "analogue",
    ),
    (
        "salam-de-sibiu",
        "Salam de Sibiu",
        "Sibiu dry salami (Salam de Sibiu)",
        "analogue",
    ),
    ("parizer", "Parizer", "Bologna-style sausage (Parizer)", "analogue"),
    ("crenvursti", "Crenvurști", "Frankfurters (Crenvurști)", "analogue"),
    ("kaizer", "Kaizer", "Smoked cured pork belly (Kaizer)", "analogue"),
    ("sunca-presata", "Șuncă presată", "Pressed ham (Șuncă presată)", "analogue"),
    (
        "pastrama-de-oaie",
        "Pastramă de oaie",
        "Mutton pastrami (Pastramă de oaie)",
        "analogue",
    ),
    (
        "slanina-afumata",
        "Slănină afumată",
        "Smoked pork fatback (Slănină afumată)",
        "analogue",
    ),
    ("caltabos", "Caltaboș", "Liver sausage (Caltaboș)", "analogue"),
    ("toba", "Tobă", "Head cheese (Tobă)", "analogue"),
    ("pate-de-ficat", "Pate de ficat", "Liver pâté (Pate de ficat)", "analogue"),
    # Brânzeturi
    (
        "telemea-de-vaca",
        "Telemea de vacă",
        "Cow's milk telemea cheese (Telemea de vacă)",
        "analogue",
    ),
    (
        "telemea-de-oaie",
        "Telemea de oaie",
        "Sheep's milk telemea cheese (Telemea de oaie)",
        "analogue",
    ),
    ("cascaval", "Cașcaval", "Cascaval cheese (Cașcaval)", "analogue"),
    (
        "branza-de-burduf",
        "Brânză de burduf",
        "Burduf sheep cheese (Brânză de burduf)",
        "analogue",
    ),
    ("urda", "Urdă", "Whey cheese (Urdă)", "analogue"),
    ("cas", "Caș", "Fresh sheep curd cheese (Caș)", "analogue"),
    (
        "branza-de-vaci",
        "Brânză de vaci",
        "Fresh cow's cheese (Brânză de vaci)",
        "analogue",
    ),
    ("branza-topita", "Brânză topită", "Processed cheese (Brânză topită)", "analogue"),
    # Pâine și patiserie
    ("covrigi", "Covrigi", "Pretzel rings (Covrigi)", "recipe"),
    (
        "placinta-cu-branza",
        "Plăcintă cu brânză",
        "Cheese pie (Plăcintă cu brânză)",
        "recipe",
    ),
    ("placinta-cu-mere", "Plăcintă cu mere", "Apple pie (Plăcintă cu mere)", "recipe"),
    (
        "langosi",
        "Langoși cu brânză",
        "Fried dough with cheese (Langoși cu brânză)",
        "recipe",
    ),
    ("gogosi", "Gogoși", "Fried doughnuts (Gogoși)", "usda-dish"),
    # Deserturi
    (
        "cozonac-cu-nuca",
        "Cozonac cu nucă",
        "Sweet bread with walnuts (Cozonac cu nucă)",
        "recipe",
    ),
    ("pasca", "Pască", "Easter cheese cake (Pască)", "recipe"),
    (
        "papanasi",
        "Papanași cu smântână și dulceață",
        "Cheese doughnuts with sour cream and jam (Papanași cu smântână și dulceață)",
        "recipe",
    ),
    (
        "clatite-cu-dulceata",
        "Clătite cu dulceață",
        "Crêpes with jam (Clătite cu dulceață)",
        "recipe",
    ),
    (
        "clatite-cu-branza",
        "Clătite cu brânză",
        "Crêpes with sweet cheese (Clătite cu brânză)",
        "recipe",
    ),
    ("cornulete", "Cornulețe", "Filled crescent cookies (Cornulețe)", "recipe"),
    (
        "salam-de-biscuiti",
        "Salam de biscuiți",
        "Biscuit chocolate log (Salam de biscuiți)",
        "recipe",
    ),
    ("chec", "Chec", "Pound cake (Chec)", "usda-dish"),
    ("orez-cu-lapte", "Orez cu lapte", "Rice pudding (Orez cu lapte)", "usda-dish"),
    ("gris-cu-lapte", "Griș cu lapte", "Semolina pudding (Griș cu lapte)", "recipe"),
    ("coliva", "Colivă", "Boiled wheat with walnuts (Colivă)", "recipe"),
    (
        "dulceata-de-visine",
        "Dulceață de vișine",
        "Sour cherry preserve (Dulceață de vișine)",
        "recipe",
    ),
    ("magiun-de-prune", "Magiun de prune", "Plum butter (Magiun de prune)", "recipe"),
    ("halva", "Halva", "Sunflower halva (Halva)", "recipe"),
]

# What the values PR must settle for an item, beyond its method
NOTES = {
    # Fat varies a lot by producer: the name states the fat assumed, so
    # whoever has the label knows to enter their own food instead
    "branza-de-vaci": "0.1-20% fat by producer: assume about 5%, the most common",
    "telemea-de-vaca": "fat by producer: state the assumed % in the name",
    "telemea-de-oaie": "fat by producer: state the assumed % in the name",
    "cascaval": "fat by producer: state the assumed % in the name",
    # USDA's halva is tahini halva: sunflower halva differs in fat and protein
    "halva": "a recipe of sunflower seeds and sugar",
    # Fried: USDA's retention factors have no oil uptake, so cite its source
    "langosi": "fried: record where the oil uptake figure comes from",
    "snitel-de-pui": "fried: record where the oil uptake figure comes from",
    "snitel-de-porc": "fried: record where the oil uptake figure comes from",
    "crap-prajit": "fried: record where the oil uptake figure comes from",
    "papanasi": "fried: record where the oil uptake figure comes from",
}
