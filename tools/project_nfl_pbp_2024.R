# Export only the authorized prior-season join/feature projection.
# No current-season data, game scores, EPA, betting prices or result labels.
audit_library <- Sys.getenv("BEATING_R_AUDIT_LIB", "/tmp/beating-r-audit-lib")
.libPaths(c(audit_library, .libPaths()))
args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args)) args[[1]] else "."
out <- file.path(root, "data/raw/nfl-source-audit")
raw_path <- file.path(out, "play_by_play_2024.qs")
pbp <- qs::qread(raw_path)
requested <- c("game_id", "play_id", "posteam", "defteam", "passer_player_id",
               "passer_player_name", "rusher_player_id", "rusher_player_name",
               "qb_dropback", "pass_attempt", "sack", "qb_scramble",
               "no_play", "play_type", "qtr", "down", "ydstogo")
present <- requested[requested %in% names(pbp)]
missing <- setdiff(requested, present)
stopifnot(all(c("game_id", "play_id") %in% present))
ids <- pbp[c("game_id", "play_id")]
stopifnot(!anyDuplicated(ids))
write.csv(ids, file.path(out, "play_by_play_2024-ids.csv"), row.names = FALSE, na = "")
schema <- data.frame(field = names(pbp), r_class = vapply(pbp, function(column) {
  paste(class(column), collapse = "/")
}, character(1)))
write.csv(schema, file.path(out, "play_by_play_2024-schema.csv"), row.names = FALSE)
write.csv(pbp[present], file.path(out, "play_by_play_2024-feature-projection.csv"),
          row.names = FALSE, na = "")
cat("R:", as.character(getRversion()), "qs:", as.character(packageVersion("qs")),
    "stringfish:", as.character(packageVersion("stringfish")), "\n")
cat("Rows:", nrow(pbp), "source columns:", ncol(pbp), "exported columns:", length(present), "\n")
cat("Missing requested columns:", paste(missing, collapse = ", "), "\n")
