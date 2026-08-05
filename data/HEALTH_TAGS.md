# Health Tag Definitions

These four tags are the only values allowed in a recipe's `health_tags` and
`excluded_for` fields. `tests/test_recipes.py` enforces that.

**Why this file exists.** `Claude.md:429` warns that vague health tags are the
hardest bug in the project to find: two people tag forty recipes, one of them
thinks ผัดกะเพรา counts as "clean" and the other doesn't, and nothing ever
crashes — the recommender just quietly returns the wrong dishes for a diet.
A rule you can check by hand is worth more than a rule that sounds right.

So every definition below is written as something you can **verify from the
recipe's own ingredient list**, not as a judgement call.

---

## The two fields are opposites

| Field | Meaning |
|---|---|
| `health_tags` | diets this dish **actively suits** — the user asked for keto, this dish is offered |
| `excluded_for` | diets this dish **must never be offered to** — a hard filter |

A dish can be in neither. Most are. `health_tags: []` is a perfectly normal
answer and does not mean "unhealthy" — it means the dish makes no particular
claim.

A dish is never in both lists for the same tag.

---

## `clean` — minimally processed, not fried, no added sugar

Tag a dish `clean` only if **all four** hold:

1. **Not deep-fried.** Stir-frying, grilling, steaming, boiling, and baking are
   fine. Submerging in oil is not.
2. **No added sugar** in `seasonings`. Naturally occurring sugar in the
   ingredients themselves (pumpkin, sweet potato, tomato) does not count.
3. **No processed meat** — no sausage, bacon, ham, meatball, luncheon meat.
4. **No coconut milk.** It is the single largest source of saturated fat in Thai
   cooking, and its presence is what separates a คลีน stir-fry from a curry.

> Deliberately a *stricter* definition than everyday Thai usage, where "คลีน"
> is closer to a vibe than a rule. Strict and checkable beats generous and
> arguable — and the report can state the rule outright.

## `keto` — 10 g available carbohydrate or less per serving

Tag a dish `keto` if **both** hold:

1. **`nutrition.carb` ≤ 10** (grams per serving, as recorded).
2. **No starch staple** in `main_ingredients` — no rice, noodles of any kind,
   spaghetti, potato, or sweet potato.

The gram threshold does the real work; rule 2 is a sanity backstop, since a
dish built on rice should never be tagged keto no matter what the arithmetic
says.

> 10 g is a per-*dish* budget, chosen because a standard ketogenic day allows
> roughly 20–50 g total and a main dish should not consume all of it. The
> number is arbitrary in the sense that any threshold is — what matters is
> that it is written down and applied identically to all 40 recipes.

## `vegetarian` — no meat, fish, or seafood

Excludes: chicken, pork, beef, shrimp, dried shrimp, squid, fish, and any
seasoning derived from them — **fish sauce, oyster sauce, and shrimp paste**.

Allows: egg, milk, butter, cheese, mayonnaise, honey.

## `vegan` — no animal products at all

Everything `vegetarian` excludes, **plus** egg, milk, butter, cheese,
mayonnaise, and honey.

> ⚠️ **The trap.** `Claude.md:429` singles this out as the most commonly missed
> detail in the whole project: **fish sauce and shrimp paste are animal
> products.** A vegetable stir-fry seasoned with น้ำปลา is not vegan, and it
> looks vegan at a glance — no meat is visible in the ingredient list. Oyster
> sauce is the same trap wearing a different hat.
>
> Anything `vegan` excludes, `vegetarian` excludes too, unless the only
> offending items are egg or dairy.

---

## How this is enforced

Rather than trusting anyone to remember the lists above, `is_animal_product` is
recorded per ingredient in `data/ingredients.json`, and
`tests/test_recipes.py` derives the vegetarian and vegan rules from that flag.

The consequence worth understanding: **if you tag a new ingredient wrongly in
the dictionary, the test will happily agree with you.** The flag is the single
place the truth lives, so it is the one place worth double-checking. Everything
downstream is arithmetic.

`clean` and `keto` are checked the same way — against `seasonings`,
`main_ingredients`, and the recorded `carb` value — so all four tags are
mechanically verifiable and none of them rests on memory.
