"""Rebuild app/catalog_data/*.json from the sources: the record of how the
catalog files were made, and the place to change the selection.

Not run by CI or in the image: the JSON files are committed and reviewed.

    curl -LO https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
    # sha256 b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0
    unzip FoodData_Central_sr_legacy_food_csv_2018-04.zip
    curl -L -o exercises.json https://raw.githubusercontent.com/yuhonas/free-exercise-db/f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5/dist/exercises.json
    python3 -I scripts/build_catalog_data.py \
        FoodData_Central_sr_legacy_food_csv_2018-04 exercises.json app/catalog_data

Foods: a Romanian name only where the USDA food is the same food. Values
per 100 g: energy in kcal (nutrient 208), protein (203), carbohydrate by
difference (205), total fat (204). Lard (USDA 171401, 902 kcal) is left
out: user foods are limited to 900 kcal per 100 g.

Exercises: names and labels only; free-exercise-db's instructions and
images are not imported (their origin is not stated), only image paths.
"""

import csv
import json
import sys
from pathlib import Path

# USDA nutrient ids in nutrient.csv (not the old SR numbers)
NUTRIENTS = {"1008": "kcal", "1003": "protein", "1005": "carbs", "1004": "fat"}


def read_usda(directory: Path) -> dict[str, dict]:
    """fdc_id -> description and the four nutrients, from the SR Legacy CSVs."""
    foods: dict[str, dict] = {}
    with open(directory / "food.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            foods[row["fdc_id"]] = {"description": row["description"]}
    with open(directory / "food_nutrient.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = NUTRIENTS.get(row["nutrient_id"])
            if key and row["fdc_id"] in foods:
                foods[row["fdc_id"]][key] = float(row["amount"])
    return foods


# fdc_id, English name, Romanian name
FOODS = [
    # Meat, fish, eggs
    ("171077", "Chicken breast, skinless, raw", "Piept de pui fără piele, crud"),
    ("171477", "Chicken breast, roasted", "Piept de pui la cuptor"),
    (
        "173627",
        "Chicken thigh, skinless, raw",
        "Pulpă superioară de pui fără piele, crudă",
    ),
    ("171060", "Chicken liver, raw", "Ficat de pui, crud"),
    ("171098", "Turkey breast, raw", "Piept de curcan, crud"),
    ("168230", "Pork loin, lean, raw", "Cotlet de porc, slab, crud"),
    ("168249", "Pork tenderloin, lean, raw", "Mușchiuleț de porc, crud"),
    ("167845", "Pork shoulder, lean, raw", "Spată de porc, slabă, crudă"),
    ("167902", "Pork, ground, raw", "Carne tocată de porc, crudă"),
    ("167812", "Pork belly, raw", "Piept de porc, crud"),
    ("167811", "Pork backfat, fresh, raw", "Slănină crudă, nesărată"),
    ("168277", "Bacon, cured, raw", "Bacon afumat, crud"),
    ("174030", "Beef, ground, 90% lean, raw", "Carne tocată de vită, 90% slabă, crudă"),
    ("174036", "Beef, ground, 80% lean, raw", "Carne tocată de vită, 80% slabă, crudă"),
    ("173125", "Beef round, lean, raw", "Pulpă de vită, slabă, crudă"),
    ("169451", "Beef liver, raw", "Ficat de vită, crud"),
    ("170599", "Beef tripe, raw", "Burtă de vită, crudă"),
    ("171952", "Carp, raw", "Crap, crud"),
    ("173717", "Rainbow trout, farmed, raw", "Păstrăv curcubeu de crescătorie, crud"),
    (
        "175167",
        "Atlantic salmon, farmed, raw",
        "Somon de Atlantic de crescătorie, crud",
    ),
    ("171986", "Tuna, light, canned in water, drained", "Ton în apă, conservă, scurs"),
    ("175119", "Atlantic mackerel, raw", "Macrou, crud"),
    ("175116", "Atlantic herring, raw", "Hering, crud"),
    ("171287", "Egg, whole, raw", "Ou întreg, crud"),
    ("172183", "Egg white, raw", "Albuș de ou, crud"),
    ("173424", "Egg, whole, hard-boiled", "Ou fiert tare"),
    # Dairy
    ("171265", "Milk, whole, 3.25% fat", "Lapte integral, 3,25% grăsime"),
    ("171267", "Milk, 2% fat", "Lapte, 2% grăsime"),
    ("170872", "Milk, 1% fat", "Lapte, 1% grăsime"),
    ("171269", "Milk, skim", "Lapte degresat"),
    ("170874", "Buttermilk, cultured, low-fat", "Lapte bătut, slab"),
    ("171284", "Yogurt, plain, whole milk", "Iaurt simplu, din lapte integral"),
    ("171304", "Greek yogurt, plain, whole milk", "Iaurt grecesc simplu, integral"),
    ("170894", "Greek yogurt, plain, nonfat", "Iaurt grecesc simplu, degresat"),
    ("171257", "Sour cream, about 19% fat", "Smântână, circa 19% grăsime"),
    ("172182", "Cottage cheese, 2% fat", "Brânză cottage, 2% grăsime"),
    ("172179", "Cottage cheese, about 4% fat", "Brânză cottage, circa 4% grăsime"),
    ("173420", "Feta cheese", "Brânză feta"),
    ("170845", "Mozzarella, whole milk", "Mozzarella, din lapte integral"),
    ("170848", "Parmesan", "Parmezan"),
    ("170851", "Ricotta, whole milk", "Ricotta, din lapte integral"),
    ("173418", "Cream cheese", "Cremă de brânză"),
    ("173430", "Butter, unsalted", "Unt nesărat"),
    # Fats
    ("171025", "Sunflower oil", "Ulei de floarea-soarelui"),
    ("171413", "Olive oil", "Ulei de măsline"),
    # Grains and starches
    ("168929", "Cornmeal, degermed, yellow", "Mălai"),
    ("169697", "Cornmeal, whole-grain, yellow", "Mălai integral"),
    ("169761", "Wheat flour, white, all-purpose", "Făină albă de grâu"),
    ("168893", "Wheat flour, whole-grain", "Făină integrală de grâu"),
    ("168933", "Semolina", "Griș"),
    ("174924", "Bread, white", "Pâine albă"),
    ("172688", "Bread, whole-wheat", "Pâine integrală"),
    ("172684", "Bread, rye", "Pâine de secară"),
    ("169756", "Rice, white, long-grain, raw", "Orez alb cu bob lung, crud"),
    ("169757", "Rice, white, long-grain, cooked", "Orez alb cu bob lung, fiert"),
    ("169703", "Rice, brown, long-grain, raw", "Orez brun, crud"),
    ("169704", "Rice, brown, long-grain, cooked", "Orez brun, fiert"),
    ("173904", "Oats, rolled, dry", "Fulgi de ovăz"),
    ("168927", "Pasta, dry", "Paste făinoase, crude"),
    ("168928", "Pasta, cooked", "Paste făinoase, fierte"),
    ("170685", "Buckwheat groats, roasted, dry", "Hrișcă, crudă"),
    ("170686", "Buckwheat groats, roasted, cooked", "Hrișcă, fiartă"),
    ("170688", "Bulgur, dry", "Bulgur, crud"),
    ("169699", "Couscous, dry", "Cuscus, crud"),
    ("168874", "Quinoa, raw", "Quinoa, crudă"),
    ("168917", "Quinoa, cooked", "Quinoa, fiartă"),
    ("170026", "Potatoes, with skin, raw", "Cartofi cu coajă, cruzi"),
    ("170440", "Potatoes, boiled, without skin", "Cartofi fierți, fără coajă"),
    ("168482", "Sweet potato, raw", "Cartof dulce, crud"),
    # Legumes
    ("175202", "White beans, dry", "Fasole albă boabe, uscată"),
    ("175203", "White beans, boiled", "Fasole albă boabe, fiartă"),
    ("173744", "Red kidney beans, dry", "Fasole roșie boabe, uscată"),
    ("175194", "Red kidney beans, boiled", "Fasole roșie boabe, fiartă"),
    ("172420", "Lentils, dry", "Linte, uscată"),
    ("172421", "Lentils, boiled", "Linte, fiartă"),
    ("173756", "Chickpeas, dry", "Năut, uscat"),
    ("173757", "Chickpeas, boiled", "Năut, fiert"),
    ("170419", "Green peas, raw", "Mazăre verde, crudă"),
    ("169961", "Green beans, raw", "Fasole verde, crudă"),
    # Vegetables
    ("169975", "Cabbage, raw", "Varză albă, crudă"),
    ("169977", "Red cabbage, raw", "Varză roșie, crudă"),
    ("169279", "Sauerkraut", "Varză murată"),
    ("170457", "Tomatoes, raw", "Roșii, crude"),
    ("168409", "Cucumber, with peel, raw", "Castravete cu coajă, crud"),
    ("168558", "Pickled cucumbers", "Castraveți murați"),
    ("170108", "Red bell pepper, raw", "Ardei gras roșu, crud"),
    ("170427", "Green bell pepper, raw", "Ardei gras verde, crud"),
    ("170000", "Onions, raw", "Ceapă, crudă"),
    ("169230", "Garlic, raw", "Usturoi, crud"),
    ("170393", "Carrots, raw", "Morcovi, cruzi"),
    ("169145", "Beets, raw", "Sfeclă roșie, crudă"),
    ("169228", "Eggplant, raw", "Vinete, crude"),
    ("169291", "Zucchini, raw", "Dovlecel, crud"),
    ("168448", "Pumpkin, raw", "Dovleac, crud"),
    ("168462", "Spinach, raw", "Spanac, crud"),
    ("169249", "Lettuce, green leaf, raw", "Salată verde, crudă"),
    ("169986", "Cauliflower, raw", "Conopidă, crudă"),
    ("170379", "Broccoli, raw", "Broccoli, crud"),
    ("169251", "White mushrooms, raw", "Ciuperci champignon, crude"),
    ("170400", "Celery root, raw", "Țelină rădăcină, crudă"),
    ("170417", "Parsnips, raw", "Păstârnac, crud"),
    ("169246", "Leeks, raw", "Praz, crud"),
    ("169276", "Radishes, raw", "Ridichi, crude"),
    ("169998", "Sweet corn, raw", "Porumb dulce, crud"),
    ("170416", "Parsley, fresh", "Pătrunjel verde"),
    ("172233", "Dill, fresh", "Mărar verde"),
    ("170459", "Tomato paste", "Pastă de tomate"),
    ("170460", "Tomato puree", "Piure de roșii"),
    ("173472", "Horseradish, prepared", "Hrean preparat"),
    # Fruit
    ("171688", "Apples, with skin", "Mere cu coajă"),
    ("169118", "Pears", "Pere"),
    ("169949", "Plums", "Prune"),
    ("168162", "Prunes, dried", "Prune uscate"),
    ("173954", "Sour cherries", "Vișine"),
    ("171719", "Sweet cherries", "Cireșe"),
    ("171697", "Apricots", "Caise"),
    ("169928", "Peaches", "Piersici"),
    ("174683", "Grapes", "Struguri"),
    ("167762", "Strawberries", "Căpșuni"),
    ("167755", "Raspberries", "Zmeură"),
    ("171711", "Blueberries", "Afine"),
    ("167765", "Watermelon", "Pepene roșu"),
    ("169092", "Cantaloupe melon", "Pepene galben cantalup"),
    ("168163", "Quinces", "Gutui"),
    ("173944", "Bananas", "Banane"),
    ("169097", "Oranges", "Portocale"),
    ("167746", "Lemons, without peel", "Lămâi, fără coajă"),
    ("168164", "Raisins, golden", "Stafide aurii"),
    # Nuts and seeds
    ("170187", "Walnuts", "Nuci"),
    ("170581", "Hazelnuts", "Alune de pădure"),
    ("170567", "Almonds", "Migdale"),
    ("170562", "Sunflower seeds, hulled", "Semințe de floarea-soarelui decojite"),
    ("170556", "Pumpkin seeds, hulled", "Semințe de dovleac decojite"),
    ("172470", "Peanut butter, smooth, unsalted", "Unt de arahide, fin, nesărat"),
    # Sweet
    ("169640", "Honey", "Miere"),
    ("169655", "Sugar", "Zahăr"),
    ("170273", "Dark chocolate, 70-85% cocoa", "Ciocolată neagră, 70-85% cacao"),
]

# free-exercise-db id, Romanian name
EXERCISES = [
    # Chest
    ("Barbell_Bench_Press_-_Medium_Grip", "Împins la piept cu bara"),
    ("Dumbbell_Bench_Press", "Împins la piept cu gantere"),
    ("Barbell_Incline_Bench_Press_-_Medium_Grip", "Împins înclinat cu bara"),
    ("Incline_Dumbbell_Press", "Împins înclinat cu gantere"),
    ("Decline_Barbell_Bench_Press", "Împins declinat cu bara"),
    ("Close-Grip_Barbell_Bench_Press", "Împins cu bara, priză îngustă"),
    ("Machine_Bench_Press", "Împins la piept la aparat"),
    ("Dumbbell_Flyes", "Fluturări cu gantere"),
    ("Cable_Crossover", "Fluturări la scripete"),
    ("Butterfly", "Fluturări la aparat"),
    ("Pushups", "Flotări"),
    ("Dips_-_Chest_Version", "Flotări la paralele, pentru piept"),
    # Legs
    ("Barbell_Squat", "Genuflexiuni cu bara"),
    ("Front_Barbell_Squat", "Genuflexiuni frontale cu bara"),
    ("Goblet_Squat", "Genuflexiuni goblet"),
    ("Hack_Squat", "Genuflexiuni la aparatul hack"),
    ("Smith_Machine_Squat", "Genuflexiuni la aparatul Smith"),
    ("Leg_Press", "Presă pentru picioare"),
    ("Leg_Extensions", "Extensii pentru cvadricepși la aparat"),
    ("Lying_Leg_Curls", "Flexii pentru femurali, culcat"),
    ("Seated_Leg_Curl", "Flexii pentru femurali, șezând"),
    ("Barbell_Lunge", "Fandări cu bara"),
    ("Dumbbell_Lunges", "Fandări cu gantere"),
    ("Bodyweight_Walking_Lunge", "Fandări din mers"),
    ("Split_Squat_with_Dumbbells", "Genuflexiuni fandate cu gantere"),
    ("Barbell_Hip_Thrust", "Hip thrust cu bara"),
    ("Barbell_Glute_Bridge", "Pod pentru fesieri cu bara"),
    ("Standing_Calf_Raises", "Ridicări pe vârfuri, din picioare"),
    ("Seated_Calf_Raise", "Ridicări pe vârfuri, șezând"),
    # Hinge
    ("Barbell_Deadlift", "Îndreptări cu bara"),
    ("Romanian_Deadlift", "Îndreptări românești"),
    ("Sumo_Deadlift", "Îndreptări sumo"),
    ("Stiff-Legged_Barbell_Deadlift", "Îndreptări cu genunchii întinși"),
    ("Trap_Bar_Deadlift", "Îndreptări cu bara hexagonală"),
    ("Good_Morning", "Good morning cu bara"),
    ("Hyperextensions_Back_Extensions", "Hiperextensii"),
    # Back
    ("Pullups", "Tracțiuni"),
    ("Chin-Up", "Tracțiuni cu priză supinată"),
    ("Wide-Grip_Lat_Pulldown", "Tras la helcometru, priză largă"),
    ("Close-Grip_Front_Lat_Pulldown", "Tras la helcometru, priză îngustă"),
    ("Bent_Over_Barbell_Row", "Ramat cu bara"),
    ("One-Arm_Dumbbell_Row", "Ramat cu o ganteră"),
    ("Seated_Cable_Rows", "Ramat la scripete, șezând"),
    ("T-Bar_Row_with_Handle", "Ramat la bara T"),
    ("Inverted_Row", "Ramat inversat"),
    ("Straight-Arm_Dumbbell_Pullover", "Pullover cu ganteră"),
    ("Barbell_Shrug", "Ridicări din umeri cu bara"),
    ("Dumbbell_Shrug", "Ridicări din umeri cu gantere"),
    # Shoulders
    ("Standing_Military_Press", "Împins deasupra capului cu bara, din picioare"),
    ("Dumbbell_Shoulder_Press", "Împins deasupra capului cu gantere"),
    ("Arnold_Dumbbell_Press", "Împins Arnold cu gantere"),
    ("Machine_Shoulder_Military_Press", "Împins pentru umeri la aparat"),
    ("Side_Lateral_Raise", "Ridicări laterale cu gantere"),
    ("Cable_Seated_Lateral_Raise", "Ridicări laterale la scripete"),
    ("Reverse_Flyes", "Fluturări inverse cu gantere"),
    ("Cable_Rear_Delt_Fly", "Fluturări inverse la scripete"),
    ("Face_Pull", "Face pull la scripete"),
    ("Standing_Dumbbell_Upright_Row", "Ramat vertical cu gantere"),
    # Arms
    ("Barbell_Curl", "Flexii pentru biceps cu bara"),
    ("Dumbbell_Bicep_Curl", "Flexii pentru biceps cu gantere"),
    ("Hammer_Curls", "Flexii ciocan cu gantere"),
    ("Preacher_Curl", "Flexii pentru biceps la banca Scott"),
    ("Incline_Dumbbell_Curl", "Flexii pentru biceps pe banca înclinată"),
    ("Concentration_Curls", "Flexii concentrate"),
    ("Triceps_Pushdown", "Extensii pentru triceps la scripete"),
    (
        "Triceps_Pushdown_-_Rope_Attachment",
        "Extensii pentru triceps la scripete, cu frânghie",
    ),
    ("EZ-Bar_Skullcrusher", "Extensii franceze cu bara EZ"),
    ("Seated_Triceps_Press", "Extensii pentru triceps deasupra capului, șezând"),
    ("Dips_-_Triceps_Version", "Flotări la paralele, pentru triceps"),
    ("Bench_Dips", "Flotări la bancă, pentru triceps"),
    # Core
    ("Plank", "Planșă"),
    ("Crunches", "Abdomene scurte"),
    ("Cable_Crunch", "Abdomene la scripete"),
    ("Sit-Up", "Ridicări de trunchi"),
    ("Hanging_Leg_Raise", "Ridicări de picioare din atârnat"),
    ("Russian_Twist", "Răsuciri rusești"),
    ("Ab_Roller", "Roata pentru abdomen"),
    ("Mountain_Climbers", "Cățărătorul"),
    # Full body and conditioning
    ("Power_Clean", "Power clean"),
    ("One-Arm_Kettlebell_Swings", "Balansări cu kettlebell, cu o mână"),
    ("Farmers_Walk", "Mersul fermierului"),
    ("Front_Box_Jump", "Sărituri pe ladă"),
    ("Running_Treadmill", "Alergare pe bandă"),
    ("Walking_Treadmill", "Mers pe bandă"),
    ("Bicycling_Stationary", "Bicicletă staționară"),
    ("Elliptical_Trainer", "Bicicletă eliptică"),
    ("Rowing_Stationary", "Canotaj la aparat"),
    ("Stairmaster", "Urcat scări la aparat"),
]

FEDB_COMMIT = "f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5"


def main() -> None:
    usda = read_usda(Path(sys.argv[1]))
    fedb = {e["id"]: e for e in json.loads(Path(sys.argv[2]).read_text())}
    out = Path(sys.argv[3])

    assert len({f[0] for f in FOODS}) == len(FOODS), "duplicate fdc id"
    foods = []
    for ref, name, name_ro in FOODS:
        item = usda[ref]
        assert len(name) <= 100 and len(name_ro) <= 100, name
        foods.append(
            {
                "ref": ref,
                "name": name,
                "name_ro": name_ro,
                "calories_per_100g": item["kcal"],
                "protein_per_100g": item["protein"],
                "carbs_per_100g": item["carbs"],
                "fat_per_100g": item["fat"],
                "source_description": item["description"],
            }
        )
    food_file = {
        "source": {
            "key": "usda-fdc-sr-legacy",
            "name": "USDA FoodData Central, SR Legacy",
            "url": "https://fdc.nal.usda.gov/",
            "license": "CC0-1.0",
            "attribution": (
                "U.S. Department of Agriculture, Agricultural Research Service. "
                "FoodData Central: SR Legacy, April 2018. fdc.nal.usda.gov."
            ),
            "attribution_required": False,
            "share_alike": False,
            "version": "2018-04",
        },
        "foods": foods,
    }

    assert len({e[0] for e in EXERCISES}) == len(EXERCISES), "duplicate id"
    exercises = []
    for ref, name_ro in EXERCISES:
        e = fedb[ref]
        assert len(name_ro) <= 100, name_ro
        exercises.append(
            {
                "ref": ref,
                "name": e["name"],
                "name_ro": name_ro,
                "category": e["category"],
                "equipment": e["equipment"],
                "level": e["level"],
                "force": e["force"],
                "mechanic": e["mechanic"],
                "primary_muscles": e["primaryMuscles"],
                "secondary_muscles": e["secondaryMuscles"],
                "image_refs": e["images"],
            }
        )
    exercise_file = {
        "source": {
            "key": "free-exercise-db",
            "name": "Free Exercise DB",
            "url": "https://github.com/yuhonas/free-exercise-db",
            "license": "Unlicense",
            "attribution": (
                "Free Exercise DB by yuhonas and contributors, released into "
                "the public domain (Unlicense). github.com/yuhonas/free-exercise-db"
            ),
            "attribution_required": False,
            "share_alike": False,
            "version": FEDB_COMMIT,
        },
        "exercises": exercises,
    }

    for name, data in (("foods.json", food_file), ("exercises.json", exercise_file)):
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        (out / name).write_text(text, encoding="utf-8")
    print(len(foods), "foods,", len(exercises), "exercises")


if __name__ == "__main__":
    main()
