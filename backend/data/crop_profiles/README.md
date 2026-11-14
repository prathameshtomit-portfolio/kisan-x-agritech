# Evidence catalogue handoff — Member 2 → Member 4

These two JSON files are intentionally empty. Populate them only from the reviewed crop profiles, rotation evidence, and rulebook prepared by Member 2.

## `crop_profiles.json`

Top-level keys: `version`, `crops`, `sources`.

Each crop record accepts:

- `crop_id`, `crop_name`
- `regions`, `seasons`
- `duration_days_min`, `duration_days_max`
- `water_demand_category`, `preferred_soil`, `soil_constraints`, `required_soil_fields`
- `nutrient_notes`, `rotation_traits`, `known_risks`
- `source_ids`, `confidence`, `unknown_fields`

## `rotation_rules.json`

Top-level keys: `version`, `scoring_enabled`, `rules`, `sources`.

Each rule accepts:

- `rule_id`, `title`, `kind` (`hard_constraint` or `preference`), `description`
- optional `scope_regions`, `scope_seasons`
- `condition` (supported condition types are listed below)
- hard constraint: optional `effect` (`exclude_if_match` or `exclude_if_not_match`)
- preference: `factor`, optional `weight`, `score_when_match`, `score_when_not_match`
- `evidence_ids`, `confidence`

Supported `condition.type` values:

- `contains_crop` / `required_crop`: checks whether `condition.crop_id` is in the sequence.
- `forbidden_crop`: checks whether `condition.crop_id` is in the sequence.
- `forbidden_adjacent_pair`: checks consecutive order using `first_crop_id` and `second_crop_id`.
- `soil_field_operator`: compares a known farm soil field using `field`, `operator` (`eq`, `neq`, `lt`, `lte`, `gt`, `gte`) and `value`.
- `irrigation_in`: checks whether the farm's irrigation label is in `values`.
- `rainfall_change_pct_operator`: checks a scenario's `rainfall_change_pct` with an operator and value.

For a preference rule, provide a factor and explanation. To allow numeric ranking, the rulebook must set `scoring_enabled` to `true`, every applicable preference rule must have evidence-linked numeric scores and positive weights, and the compare request must provide positive `priority_weights` for the factors. Otherwise the API returns a side-by-side comparison without a numeric rank.

## Source records

A source record accepts `source_id`, `organization`, `title`, optional `url`, `publication_date`, `region`, and `notes`.

Do not insert invented agronomy recommendations. Keep the source register in sync with these IDs. Label an unreviewed proposition as a hypothesis and do not use it as an operational hard constraint.
