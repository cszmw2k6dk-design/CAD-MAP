v2.68
1 Added a final LYNX layout pass. Labels are grouped by their original LBD row and aligned by default; only labels whose real widths collide move to a stable second lane instead of shifting all following labels unpredictably.
2 The order is now fixed: place STR numbers using the real text-box exclusions, then place LYNX labels while avoiding printed numbers, STR numbers and previously placed LYNX labels.
3 Final LYNX placement now runs automatically; manual LBDAVOIDSTR is no longer required.

v2.67
1 LBD avoidance now uses the actual text-layer label_bbox instead of estimating from name length and STR height whenever a bbox is available. A small safety margin of about 0.15x STR height is added; label_pos/region-center fallback remains only for older data without bboxes.

v2.66
1 Fixed ESC sometimes failing to leave draw mode. One ESC now cancels an unfinished box and exits draw mode, including when focus is in the number field or toolbar.
2 Recognition canvas rendering now uses 260 DPI with a 3200 px maximum width for clearer label inspection when zoomed.
3 Removed the Lock LBD feature and ignored legacy lock flags, so LBD boxes remain selectable, movable and deletable.
4 Added a subtle translucent fill to recognized boxes for better separation from the drawing.

v2.65
1 Fixed rack strings, split rows and length hints leaking from a previous drawing into a new recognition. New recognition/JSON state is cleared, stale asynchronous fills are rejected, while regrouping within one drawing still preserves current values.
2 LBD naming now supports both INV1101-LBD-06 and INV11A101-LBD-06 prefixes. When no label sheet is selected, the dominant INV prefix is inferred from the page text so split PDF text runs no longer collapse to LBD-06.
3 Recognized LBD text is no longer truncated at 40 characters. The complete text is stored in both final_node_name and recognized_text, and CAD label rows keep the full identifier.

v2.64
1 LBD label positions now use high-contrast markers with a black outer stroke, cyan inner outline and translucent fill, with a larger minimum screen size so they remain visible when zoomed out.

v2.63
1 The recognition canvas no longer overlays LBD number text. It now uses orange rectangles to mark the actual text-layer label bounds, falling back to a small label_pos marker when no bbox exists.

v2.62
1 Fixed "Re-match all" updating only LBD names but not label positions. Re-matching now writes label_pos, label_bbox and their source back to the OCR records so STR numbering can avoid printed LBD marks.
2 The recognition canvas now shows every LBD name, preferring its original PDF text position instead of showing only the selected box.

v2.61
1 Navigation and "Back to recognition" are locked during execution so switching pages cannot reset the run; only Stop remains.
2 Removed the legacy manual rack type, split and single-string-length fields. Rack type detail is generated from recognition, lengths are read-only, and the detail refreshes automatically when recognized buckets or counts change.
3 Fixed duplicate CAD instances: reuse the running CAD application and activate an already-open DWG instead of opening it again.
4 CAD status text is now vendor-neutral; both ZWCAD and AutoCAD 2018+ remain supported.

v2.60
1 Added "Re-match all" on the recognition page. It rechecks LBD numbers on every drawing page in the current result from the PDF text layer.
  Existing names are matched again; when a box has no readable new number, its previous name is kept. Boxes that were already unnamed can still use the label-sheet fallback.

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
