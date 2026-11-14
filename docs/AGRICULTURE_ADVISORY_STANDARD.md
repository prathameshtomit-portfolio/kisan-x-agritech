# KrishiQ agriculture advisory standard

This implementation note applies the supplied *India Agriculture Intelligence Handbook v1.0* to the current KISAN-X prototype. The handbook's research cut-off is 14 November 2026. It is a design reference, not a verified crop package, current legal register, or substitute for local expert review.

## Advice workflow

1. Establish location at the level the farmer consents to share, crop and variety, season, sowing date, growth stage, previous crop, soil and water context, and the farmer's objective and constraints.
2. For a problem, ask when it began, how it is distributed across the field, whether it is spreading, recent weather and management, and request useful photos only as supporting evidence.
3. Separate observations, lab measurements, gridded/model estimates, assumptions, and hypotheses. Missing details remain unknown; do not fill them with invented values.
4. Use current district/State Agricultural University, ICAR, KVK, IMD, lab, market, or regulator sources for local and time-sensitive decisions. Show source, date, units, scope, uncertainty, and limitations.
5. Abstain or refer to a qualified person when evidence is incomplete, the decision is high consequence, the source is out of date, or local validation is missing.

## Current app boundaries

- KrishiQ is local scripted guidance and navigation. It is not connected to Gemini, Claude, or another generative model, and it does not diagnose crop or animal disease.
- The chat now refuses guessed pesticide products, doses, and mixtures; requests diagnostic context for crop symptoms; and requests soil-test/local package information before fertilizer-dose discussions.
- For possible poisoning, breathing difficulty, unconsciousness, or severe allergic reaction, the chat directs the user to emergency/professional help rather than giving treatment advice. Animal health questions are referred to a veterinarian.
- The app's NASA POWER series is historical gridded context, not an IMD forecast. A request for tomorrow's rain or irrigation conditions now says this clearly and points to the current local advisory.
- NASA map overlays remain browse visualisations. They do not measure plot-level soil chemistry or prove a pest, disease, fire, or crop condition.

## Data and privacy requirements for future work

Use purpose-specific consent for exact location, photos, microphone, record persistence, and any secondary use. Keep personal identity separate from agronomic case data, collect only what is needed, and provide access, correction, export, deletion, retention limits, and audit controls before production use. Do not upload this handbook or other reference works to a model-training service without checking applicable rights and terms.

## Release gate

Before field-specific recommendations are enabled, review the rules with local agronomists/KVK/SAU, verify the current district package and legal labels at query time, test abstention and escalation on realistic cases, evaluate with farmers across language/literacy groups, and validate against independent farms and seasons. The handbook's examples are response-structure examples, not crop prescriptions.
