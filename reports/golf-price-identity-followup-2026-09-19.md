# Historical golf prices: identity follow-up — September 19, 2026

**All 28 previously unmatched offers are same-course.** The recovered export's 318 fixed-cohort offers now classify as **311 same-course, seven outside the declared course pair, zero unresolved and zero cross-course**. This closes the identity gap in the [original archive audit](golf-historical-price-audit-2026-09-19.md). It does not establish the absence of cross-course offers across FanDuel's complete market history.

## New evidence

Twelve ordinary, public Data Golf player-profile requests succeeded. Each retained page identifies its own Data Golf ID in `og:url` and its current player name in `og:title`. These IDs match those already carried by the price export. For example, ID [17786](https://datagolf.com/player-profiles?dg_id=17786) identifies Cam Davis, while the older export calls him Cameron Davis; [17646](https://datagolf.com/player-profiles?dg_id=17646) identifies Matt Fitzpatrick, while the export uses Matthew.

The current profile name is joined to a unique official player name within the same tournament edition. Case, accents and punctuation follow the original audit's normalization; this follow-up also explicitly transliterates Danish `ø` to `o`. No nickname was guessed, no fuzzy match was used, and headshot filename numbers were not treated as PGA IDs. An ambiguous name remains unresolved. Profile pages were retrieved retrospectively and establish identity only; their statistics and results were not used.

The [JSON report](golf-price-identity-followup-2026-09-19.json) records all twelve source URLs, receipt clocks and SHA-256 hashes, each affected offer's identity join, and the unchanged pinned price/official-tee provenance. The profiles cover Noh, Olesen, K.H. Lee, NeSmith, Fitzpatrick, Davis, Schmid, S.H. Kim, Echavarria, both Højgaard brothers and Stevens.

## Final classification of this export

| Edition | Same course | Outside declared pair | Unresolved / cross-course |
| --- | ---: | ---: | ---: |
| Farmers 2023 | 19 | 0 | 0 / 0 |
| Farmers 2024 | 37 | 0 | 0 / 0 |
| Farmers 2025 | 38 | 0 | 0 / 0 |
| Pebble 2023 | 21 | 7 | 0 / 0 |
| Pebble 2024 | 51 | 0 | 0 / 0 |
| Pebble 2025 | 54 | 0 | 0 / 0 |
| RSM 2024 | 42 | 0 | 0 / 0 |
| RSM 2025 | 49 | 0 | 0 / 0 |
| **Total** | **311** | **7** | **0 / 0** |

The source's selection filters, unzoned price clocks and missing market-specific settlement terms still apply. **Zero offers qualify for G11.** Neither a new model nor an ROI calculation was run; the sport cohort and all research gates are unchanged.

## Reproduction and next dependency

With the ignored raw captures retained locally:

```sh
state/runtime/research-venv/bin/python tools/resolve_golf_price_identities.py
state/runtime/research-venv/bin/python -m unittest discover -s tests
```

All **242 tests pass**, including wrong-profile-ID rejection, ID-backed alias resolution and ambiguous transliteration rejection. Raw profiles and the detailed price inventory remain under ignored `data/raw/golf-historical-player-identities-2026-09-19/`; raw publisher prices are not redistributed.

The historical-price objective remains incomplete. The [round-score source search](golf-round-price-source-search-2026-09-19.md) records the remaining concrete provider route: SportsDataIO historical PGA props, with access and exact FanDuel coverage still unverified. Existing archive access or a new source export is needed. No reply to the archive-access question has arrived. Scheduled jobs remain paused.
