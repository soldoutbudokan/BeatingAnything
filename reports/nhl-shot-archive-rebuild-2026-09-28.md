# NHL shot archive rebuild — September 28, 2026

The uncommitted `data/raw/` directory was lost with the previous container. This rebuild re-acquires all 285 raw FanDuel/NHL price payloads from `ldinan-git/sports-betting-ops@42cf1f8`, the six SportsDataverse boxscore/roster/schedule assets, and regenerates both schedule metadata projections. **Every file hash equals the pin committed on September 26.** Two derived files, `manifest.json` and `outcomes/source_audit.json`, held retrieval metadata that was never committed, so they are replaced by deterministic files whose original hashes are recorded inside them; the downstream tools now pin the replacements.

Replacement pins: manifest `9b43fc27fe396a7b37dd07af3e7f01ab56acb209578b2c5b0defb2bdfbeeed2f`, source audit `0680f23b515a05483264df58fcf4212dbe0af80dc4f49377ad7b0abb2fd0da00`. No sporting values were read. Receipts are in the companion JSON.
