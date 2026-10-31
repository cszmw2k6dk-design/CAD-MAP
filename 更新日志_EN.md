v2.61
1 Automatic LBD text height now uses 30% of the median LBD box width on each page instead of producing oversized text.
2 LBD labels return to the geometric centre of their regions; the forced two-lane vertical stagger was removed.
3 Improved filtering of interference inside LBD boxes so a valid identifier is no longer discarded.
4 Added support for dotted LBD identifiers such as `1.1.C.1`.
5 Navigation is locked during execution; only pause and stop remain. CAD reuse now activates an already-open DWG instead of opening a second instance.
6 HTTPS update URLs on object storage, R2 or a CDN are supported. GitHub mirror prefixes are no longer incorrectly added to non-GitHub download hosts.

v2.79
1 Reduced automatic LBD text height from 40% to 30% of the median LBD box width so the automatic size is no longer too large.
2 Restored geometric centring for LBD labels by removing the forced two-lane stagger. Every label now starts at the centre of its own LBD region instead of being shifted down merely because neighbouring label bounds are close.

v2.78
1 Fixed automatic LBD text sizing. Instead of estimating from the whole page, the app now takes the median width of all LBD (Node) boxes on each page and uses 40% of that median for the page's LBD label height. This prevents unusually narrow or wide boxes from changing the text size within one page.
2 Entering 0 in Label height enables the automatic mode. A positive value still forces the exact model-unit height entered by the user.
3 Both the annotation JSON and debug recognition JSON paths now use the same per-page median box width.

v2.77
1 Fixed an LBD de-duplication collision where an identifier number such as 4 was incorrectly compared with the index of the fourth detected box. A valid full label could therefore be discarded and replaced by a positional guess.
2 Added filtering for dense label lists at the bottom or side of a drawing. Runs of at least four closely spaced full INV...-LBD labels in the same column are now removed as interference, preventing list entries from stealing the real label inside a rack box.
3 Verified with page 24 of the HIGHLAND PDF: all 16 boxes were named from the text layer, including the correct `INV11A102-LBD-04` and its label position. Spot checks on Steel River horizontal labels showed no regression.

v2.76
1 Improved LBD text selection when a box contains interference. Multiple candidates are ranked by full INV...-LBD name, then strict format such as 1.1.C.1, then standard LBD-xx; ties choose the text nearest the box centre.
2 Added the strict dotted identifier format `number.number.letter.number`. The whole text must match, so `1.1.C.1` is recognized without treating dimensions or coordinates as IDs.
3 Tested with four interfering texts in one LBD box; the correct full identifier is still selected.

v2.75
1 Rack rows are grouped by Tracker centre X: only boxes with the same or nearly the same X belong to one vertical row.
2 The normal row-to-row distance is the median adjacent X-centre gap. A candidate row that splits this gap into two smaller gaps is checked against the Y centres of the rows on its left and right; it is removed only when Y matching reaches 80%.
3 Verified with a four-box false column (removed), normal columns (kept), a sparse Y-independent column (kept), and whole-page X translation (unchanged result).

v2.60
1 Fixed the long unresponsive final stage after STR drawing. Final LYNX label placement now checks only nearby STR text instead of recalculating collisions against every STR item in the whole model.
2 Added live scan and row-by-row placement progress for the final stage, so the UI no longer remains at "Drawing STR 100 / 121".
3 If final label placement fails, the error is reported and the completion marker is still written instead of leaving the run permanently blocked.

v2.74
1 Rack rows now use Tracker centre-Y clustering with a tolerance of 2x box width, avoiding false rows caused by height variation.
2 The normal row gap comes from the median distance between large rows. For a sparse row inserted between them, its Tracker X centres are compared with the previous and next rows; it is removed only when X matching is at least 80%, so legitimate sparse rows with different X positions are kept.
3 Whole-page X translation does not change the result. The current 86-page result removes 43 false boxes across 16 pages instead of deleting by count alone.

v2.73
1 Fixed correct boxes being removed by rack-row filtering. The same-row top-edge tolerance is now 2x the Tracker short side instead of about 0.35x, so varying rack heights no longer split a valid row.
2 Row filtering uses only top-edge Y coordinates and Tracker counts, never X-coordinate distances. The current 86-page result removes only 26 sparse false boxes across 10 pages.

v2.72
1 Fixed rack-row filtering not taking effect. Rows now use the common top edge of Tracker boxes instead of their varying centres, preventing one physical row from being split into false rows.
2 A small row is removed only when it lies between two large rows, has far fewer Tracker boxes, and the two large rows are still about one normal row-gap apart. Normal equally populated rows are kept.
3 In the current 86-page result, the filter detects 348 such extra boxes across 74 pages.

v2.71
1 Removed the "switch to layout after drawing model-space labels" option; automatic layout switching is now permanently disabled.
2 Removed automatic filtering of legends and table interference outside the main LBD array. Recognition now keeps Node/Tracker boxes outside the main array, and legacy enabled values are ignored.

v2.70
1 Fixed possible LBD region-fit failures: when a sheet name is temporarily unmatched, the sheet is now mapped by drawing-page order instead of silently falling back to the whole page.
2 Region fitting is now verified: viewport DXF view-center and view-height values must match the requested target. Failed layouts are counted and reported instead of being marked as successfully fitted.
3 Only layouts, drawings and region rows that actually exist are processed, preventing mismatches and false completion counts.

v2.69
1 Added rack-row spacing filtering. The median gap between normal rows is used as the per-page reference; a spurious Tracker row squeezed between two normal rows is removed only when both gaps are unusually small and their sum is about one normal row gap. Node detections are untouched.

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

v2.60
1 Added "Re-match all" on the recognition page. It rechecks LBD numbers on every drawing page in the current result from the PDF text layer.
  Existing names are matched again; when a box has no readable new number, its previous name is kept. Boxes that were already unnamed can still use the label-sheet fallback.

v2.59
1 The recognition page can open an existing recognition JSON and restore the page table, canvas, rack buckets and project tree.
2 Moved "Check issues" into the same toolbar row as "Draw Box", "Draw rack" and "Draw LBD area".
3 Removed the recognition-page "Save" button. "Next: fill other parameters" now applies rack types, saves the JSON automatically, and stays on the recognition page with an error message if saving fails.
4 Fixed untranslated small runtime text in the English UI, including page number, percentage, elapsed/remaining time, current-page statistics and run status.
5 Aligned the recognition-page rack table headers, column widths and cell text for Strings, Length, Count and Rows in both Chinese and English.
6 Changelog now follows the UI language. English mode shows English notes, and future releases include both Chinese and English notes.
7 Fixed annotated JSON files without a source drawing not refreshing after PDF upload. The canvas now reloads the current page with its boxes and names.
8 Added a ROW filtering algorithm that removes extra recognized Tracker rows based on their positional relationships.

v2.58
1 Restored the recognition-page project tree. LBDs without a number are shown as "(unnumbered)" and remain available for locating and renaming.

v2.57
1 The recognition canvas can add Box, rack and LBD boxes, plus copy, paste, delete, undo and in-place rename.
2 Filtering, box edits, renames, additions and deletions are all saved into the recognition result.
3 Filtering pages now recalculates rack-length buckets and refreshes the canvas and statistics.
4 Added pause, resume and stop for execution, with progress reset and total/per-step timing.
5 Split the sidebar into LBD Labels and Rack Labels, and added Chinese/English switching.
6 Improved fit-to-page, recognition image resolution and box-name display; narrow windows no longer show a horizontal scrollbar.
