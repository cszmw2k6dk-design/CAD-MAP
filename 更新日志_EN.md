v2.59
1 The recognition page can open an existing recognition JSON and restore the page table, canvas, rack buckets and project tree.
2 Fixed rack selection being blocked by the enclosing LBD box; racks now receive clicks before LBD areas.
3 Fixed rack string counts inferred from the bottom table not being written back to the recognition result, including source and candidate-count metadata.
4 Moved "Check issues" into the same toolbar row as "Draw Box", "Draw rack" and "Draw LBD area".
5 Removed the recognition-page "Save" button. "Next: fill other parameters" now applies rack types, saves the JSON automatically, and stays on the recognition page with an error message if saving fails.
6 Fixed untranslated small runtime text in the English UI, including page number, percentage, elapsed/remaining time, current-page statistics and run status.
7 Bottom-table OCR and OCR models are not included in this build. The source remains available for a later release after speed and stability are validated.
8 Aligned the recognition-page rack table headers, column widths and cell text for Strings, Length, Count and Rows in both Chinese and English.
9 Changelog now follows the UI language. English mode shows English notes, and future releases include both Chinese and English notes.

v2.58
1 Restored the recognition-page project tree. LBDs without a number are shown as "(unnumbered)" and remain available for locating and renaming.

v2.57
1 The recognition canvas can add Box, rack and LBD boxes, plus copy, paste, delete, undo and in-place rename.
2 Filtering, box edits, renames, additions and deletions are all saved into the recognition result.
3 Filtering pages now recalculates rack-length buckets and refreshes the canvas and statistics.
4 Added pause, resume and stop for execution, with progress reset and total/per-step timing.
5 Split the sidebar into LBD Labels and Rack Labels, and added Chinese/English switching.
6 Improved fit-to-page, recognition image resolution and box-name display; narrow windows no longer show a horizontal scrollbar.
