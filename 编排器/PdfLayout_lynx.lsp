;;; Row-coherent placement for LYNX / LBD labels.
;;; Loaded after PdfLayout_auto.lsp. All text is ASCII.
(setq *PdfLayout_LynxMaxStep* 8)
(setq *PdfLayout_LynxRowFactor* 4.0)

(defun PdfLayout_LynxViewState (vpObj / ed c h)
  (setq ed (vl-catch-all-apply
             '(lambda ()
                (entget (vlax-vla-object->ename vpObj)))))
  (if (vl-catch-all-error-p ed)
    nil
    (progn
      (setq c (cdr (assoc 12 ed)) h (cdr (assoc 40 ed)))
      (if (and c h (numberp h) (> h 0.0))
        (list (float (car c)) (float (cadr c)) (float h))
        nil
      )
    )
  )
)

(defun PdfLayout_LynxViewMatches (vpObj center viewH / st)
  (setq st (PdfLayout_LynxViewState vpObj))
  (and st
       (< (abs (- (car st) (car center)))
          (max 1e-6 (* 1e-5 viewH)))
       (< (abs (- (cadr st) (cadr center)))
          (max 1e-6 (* 1e-5 viewH)))
       (< (abs (- (caddr st) viewH))
          (max 1e-5 (* 1e-4 viewH)))
  )
)

(defun PdfLayout_FitViewport (vpObj bbox lockVp
                              / bb pmin pmax pw ph minPt maxPt center w h
                                scale viewH inset oldCmdEcho oldExpert ok)
  ;; Verified replacement for the plugin function. It returns T only when
  ;; the viewport DXF data really matches the requested center and height.
  (setq bb (PdfLayout_GetExtentsSafeObj vpObj))
  (if (and bb bbox)
    (progn
      (setq pmin (car bb) pmax (cadr bb))
      (setq inset (if (and *PdfLayout_ViewInset*
                           (numberp *PdfLayout_ViewInset*)
                           (> *PdfLayout_ViewInset* 0.05)
                           (<= *PdfLayout_ViewInset* 1.0))
                    *PdfLayout_ViewInset* 1.0))
      (setq pw (- (car pmax) (car pmin))
            ph (- (cadr pmax) (cadr pmin)))
      (setq minPt (car bbox) maxPt (cadr bbox))
      (setq center (list (* 0.5 (+ (car minPt) (car maxPt)))
                         (* 0.5 (+ (cadr minPt) (cadr maxPt)))
                         0.0))
      (setq w (- (car maxPt) (car minPt))
            h (- (cadr maxPt) (cadr minPt)))
      (if (and (> pw 0.0) (> ph 0.0) (> w 0.0) (> h 0.0))
        (progn
          (setq scale (min (/ pw w) (/ ph h)))
          (setq viewH (/ (/ ph scale) inset))
          (setq oldCmdEcho (getvar "CMDECHO")
                oldExpert (getvar "EXPERT"))
          (setvar "CMDECHO" 0)
          (setvar "EXPERT" 5)
          (setq ok
            (not (vl-catch-all-error-p
                   (vl-catch-all-apply
                     '(lambda ()
                        (vla-put-ViewportOn vpObj :vlax-true)
                        (vla-put-ViewCenter vpObj (vlax-3d-point center))
                        (vla-put-ViewHeight vpObj viewH))
                     nil))))
          (setq ok (and ok (PdfLayout_LynxViewMatches vpObj center viewH)))
          (if (not ok)
            (progn
              (vl-catch-all-apply 'vla-put-ViewportOn (list vpObj :vlax-true))
              (command "._MSPACE")
              (command "._ZOOM" "_C" center viewH)
              (command "._PSPACE")
              (setq ok (PdfLayout_LynxViewMatches vpObj center viewH))
            )
          )
          (if lockVp
            (vl-catch-all-apply 'vla-put-DisplayLocked (list vpObj :vlax-true))
            (vl-catch-all-apply 'vla-put-DisplayLocked (list vpObj :vlax-false))
          )
          (setvar "CMDECHO" oldCmdEcho)
          (setvar "EXPERT" oldExpert)
          ok
        )
        nil
      )
    )
    nil
  )
)

(defun PdfLayout_AutoRegionFit (cfg names lockVp
                                / regs draws i nTot k nFail nm bb r box
                                  vps vpObj fitOk tPg0 msPg)
  ;; Verified region fit. Counts only viewports whose DXF view really changed.
  (setq regs (PdfLayout_AutoReadRegions (PdfLayout_ACfg cfg "regionFile" "")))
  (setq draws (PdfLayout_ScanMarkerDrawings (PdfLayout_ACfg cfg "filter" "pdf")))
  (setq nTot (min (length regs) (length draws) (length names)))
  (if (> nTot 0)
    (progn
      (setq i 0 k 0 nFail 0)
      (PdfLayout_Prog (strcat "REGION_TOTAL " (itoa nTot)))
      (while (< i nTot)
        (setq tPg0 (PdfLayout_NowMs))
        (setq nm (nth i names)
              bb (nth i draws)
              r (nth i regs))
        (setq fitOk nil)
        (if (and (not (PdfLayout_StopGate "region-fit"))
                 bb r (PdfLayout_GetLayoutObj nm))
          (progn
            (setq box (PdfLayout_AutoRegionBox bb r))
            (command ".-LAYOUT" "_S" nm "")
            (setq vps (PdfLayout_GetLayoutViewports nm))
            (if vps
              (progn
                (setq vpObj (car (car (PdfLayout_StableSort
                                        vps 'PdfLayout_CmpVpArea))))
                (vl-catch-all-apply
                  'vla-put-DisplayLocked (list vpObj :vlax-false))
                (setq fitOk
                  (vl-catch-all-apply
                    'PdfLayout_FitViewport (list vpObj box lockVp)))
                (if (vl-catch-all-error-p fitOk) (setq fitOk nil))
              )
            )
          )
        )
        (if fitOk (setq k (1+ k)) (setq nFail (1+ nFail)))
        (setq msPg (max 0 (- (PdfLayout_NowMs) (if tPg0 tPg0 0))))
        (PdfLayout_Prog
          (strcat "REGION_FIT " (itoa (1+ i)) " " (itoa nTot)
                  " " (itoa k) " ms=" (itoa msPg)
                  " failed=" (itoa nFail)))
        (setq i (1+ i))
      )
      (if (car names) (command ".-LAYOUT" "_S" (car names) ""))
      (PdfLayout_Prog
        (strcat "REGION_DONE " (itoa k) " " (itoa nTot)
                " failed=" (itoa nFail)))
      (princ (strcat "\n[REGION-FIT] ok=" (itoa k)
                     " failed=" (itoa nFail)
                     " total=" (itoa nTot) "."))
    )
    (PdfLayout_Prog "REGION_NONE")
  )
  (princ)
)

(defun PdfLayout_LynxCenterY (r)
  (* 0.5 (+ (cadr r) (nth 3 r)))
)

(defun PdfLayout_LynxRowTol (items / h)
  (setq h 0.0)
  (foreach it items
    (if (> (nth 4 it) h) (setq h (nth 4 it)))
  )
  (* *PdfLayout_LynxRowFactor* (max h 0.05))
)

(defun PdfLayout_LynxMakeRows (sorted / rows cur rowY tol h)
  (setq rows nil cur nil rowY nil tol nil)
  (foreach it sorted
    (setq h (max 0.05 (nth 4 it)))
    (setq tol (max (if tol tol 0.0) (* *PdfLayout_LynxRowFactor* h)))
    (if (or (not cur) (<= (abs (- (car it) rowY)) tol))
      (progn
        (if cur
          (setq rowY (/ (+ rowY (car it)) 2.0))
          (setq rowY (car it))
        )
        (setq cur (append cur (list it)))
      )
      (progn
        (setq rows (append rows (list cur)))
        (setq cur (list it) rowY (car it) tol (* *PdfLayout_LynxRowFactor* h))
      )
    )
  )
  (if cur (setq rows (append rows (list cur))))
  rows
)

(defun PdfLayout_LynxUpdateLab (labs en obj newr / out)
  (setq out nil)
  (foreach x labs
    (if (= (car x) en)
      (setq out (append out (list (list en obj newr))))
      (setq out (append out (list x)))
    )
  )
  out
)

(defun PdfLayout_LynxRowBox (row margin / r x1 y1 x2 y2)
  ;; Return one rectangle covering all labels in a row.  Collision tests
  ;; are then limited to nearby STR objects instead of all 7k+ texts.
  (setq x1 1.0e30 y1 1.0e30 x2 -1.0e30 y2 -1.0e30)
  (foreach it row
    (setq r (nth 3 it))
    (setq x1 (min x1 (car r)))
    (setq y1 (min y1 (cadr r)))
    (setq x2 (max x2 (nth 2 r)))
    (setq y2 (max y2 (nth 3 r)))
  )
  (list (- x1 margin) (- y1 margin) (+ x2 margin) (+ y2 margin))
)

(defun PdfLayout_LynxAssignLanes (row base step / sorted out placed it en r rect
                                  lane hit p)
  ;; Align by default. Only a label whose actual width collides with an
  ;; earlier label in the same row is moved to the second lane.
  (setq sorted
    (PdfLayout_AutoStableSort row
      '(lambda (a b) (< (car (nth 3 a)) (car (nth 3 b))))))
  (setq out nil placed nil)
  (foreach it sorted
    (setq en (cadr it) r (nth 3 it))
    (setq rect (PdfLayout_RectShiftY r (- base (PdfLayout_LynxCenterY r))))
    (setq lane 0 hit nil)
    (foreach p placed
      (if (and (= (cadr p) 0) (PdfLayout_RectOver rect (caddr p)))
        (setq hit T)
      )
    )
    (if hit (setq lane 1))
    (setq out (append out (list (cons en lane))))
    (setq placed
      (append placed
        (list (list en lane
                    (PdfLayout_RectShiftY rect (* lane step))))))
  )
  out
)

(defun PdfLayout_LynxPlace (/ doc ms strLay labs obj bb r en h rng
                             items ctr ctr0 lo hi sorted rows rowNames base step strRects
                             signs s target dy cand hc obc lbc hard score key
                             best bestKey nMoved nRows nThis ok lanes lane
                             rowBox rowStrRects otherLabs rowIdx nRowsAll)
  (vl-load-com)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq strLay (if (and *PdfLayout_AiLayer* (/= *PdfLayout_AiLayer* ""))
                 *PdfLayout_AiLayer*
                 "PDF-AUTO-NUM"))
  (if (not (numberp *PdfLayout_LynxMaxStep*))
    (setq *PdfLayout_LynxMaxStep* 8)
  )

  (setq labs nil)
  ;; *PdfLayout_LbdRange* is filled with the exact label object enames.
  ;; Using these avoids dependence on a localized layer-name literal.
  (foreach rng *PdfLayout_LbdRange*
    (setq en (car rng))
    (if en
      (progn
        (setq obj (vl-catch-all-apply 'vlax-ename->vla-object (list en)))
        (setq bb (PdfLayout_ObjBox obj))
        (if bb
          (setq labs (append labs
                       (list (list (vlax-vla-object->ename obj) obj
                                   (PdfLayout_RectMake bb)))))
        )
      )
    )
  )
  (if (not labs)
    (progn (princ "\n[LYNX-PLACE] no labels.") (princ))
    (progn
      (PdfLayout_Prog (strcat "LYNX_SCAN start labels=" (itoa (length labs))))
      (if (PdfLayout_StopGate "lynx-scan")
        (setq strRects nil)
        (setq strRects (PdfLayout_TextRects strLay))
      )
      (PdfLayout_Prog (strcat "LYNX_SCAN text=" (itoa (length strRects))))
      (setq items nil)
      (foreach lab labs
        (setq en (car lab) obj (cadr lab) r (caddr lab))
        (setq h (vl-catch-all-apply 'vla-get-Height (list obj)))
        (setq h (if (and (numberp h) (> h 0.0)) h 0.05))
        (setq rng (assoc en *PdfLayout_LbdRange*))
        (if rng
          (progn
            (setq ctr0 (* 0.5 (+ (cadr rng) (caddr rng))))
            (setq lo (+ (cadr rng) (/ h 2.0)))
            (setq hi (- (caddr rng) (/ h 2.0)))
            (if (> lo hi) (setq lo nil hi nil))
          )
          (progn
            (setq ctr0 (PdfLayout_LynxCenterY r) lo nil hi nil)
          )
        )
        (setq items (append items
                      (list (list ctr0 en obj r h lo hi))))
      )
      (setq sorted
        (PdfLayout_AutoStableSort items
          '(lambda (a b) (> (car a) (car b)))))
      (setq rows (PdfLayout_LynxMakeRows sorted))
      (setq nMoved 0 nRows 0 rowIdx 0 nRowsAll (length rows))
      (foreach row rows
        (setq nRows (1+ nRows))
        (setq rowIdx (1+ rowIdx))
        (PdfLayout_Prog (strcat "LYNX_PLACE_PROGRESS "
                                (itoa rowIdx) " " (itoa nRowsAll)))
        (setq rowNames (mapcar 'car row))
        (setq base
          (* 0.5 (+ (apply 'min (mapcar 'car row))
                    (apply 'max (mapcar 'car row)))))
        (setq step (apply 'max (mapcar '(lambda (x) (nth 4 x)) row)))
        (setq step (max (* 1.5 step) (+ step 0.10)))
        (setq signs (list 0.0))
        (setq s 1)
        (while (<= s *PdfLayout_LynxMaxStep*)
          (setq signs (append signs (list (float s) (- 0.0 (float s)))))
          (setq s (1+ s))
        )
        (setq rowBox
          (PdfLayout_LynxRowBox
            row (* step (+ *PdfLayout_LynxMaxStep* 1.0))))
        (setq rowStrRects nil)
        (foreach sr strRects
          (if (PdfLayout_RectOver rowBox (cdr sr))
            (setq rowStrRects (cons sr rowStrRects))
          )
        )
        (setq otherLabs nil)
        (foreach ol labs
          (if (not (member (car ol) rowNames))
            (setq otherLabs (cons (caddr ol) otherLabs))
          )
        )
        (setq lanes (PdfLayout_LynxAssignLanes row base step))
        (setq best nil bestKey nil)
        (foreach sv signs
          (setq ok T)
          (foreach it row
            (setq en (cadr it))
            (setq lane (cdr (assoc en lanes)))
            (setq target (+ base (* sv step) (* (if lane lane 0) step)))
            (setq lo (nth 5 it) hi (nth 6 it))
            (if (and lo hi (or (< target lo) (> target hi)))
              (setq ok nil)
            )
          )
          (if ok
            (progn
              (setq hard 0 hc 0 obc 0 lbc 0)
              (foreach it row
                (setq en (cadr it) r (nth 3 it))
                (setq lane (cdr (assoc en lanes)))
                (setq target (+ base (* sv step) (* (if lane lane 0) step)))
                (setq dy (- target (PdfLayout_LynxCenterY r)))
                (setq cand (PdfLayout_RectShiftY r dy))
                (setq hc (+ hc (PdfLayout_RectHitsEx cand rowStrRects en)))
                (setq obc (+ obc (PdfLayout_RectHits cand *PdfLayout_ObsRects*)))
                (setq lbc (+ lbc (PdfLayout_RectHits cand otherLabs)))
              )
              (setq hard (+ hc obc))
              (setq score (+ hard lbc))
              (setq key (list score hard hc obc lbc (abs (* sv step))))
              (if (or (not bestKey) (PdfLayout_KeyLt key bestKey))
                (setq best (+ base (* sv step)) bestKey key)
              )
            )
          )
        )
        (if best
          (progn
            (foreach it row
              (setq en (cadr it) obj (nth 2 it) r (nth 3 it))
              (setq lane (cdr (assoc en lanes)))
              (setq target (+ best (* (if lane lane 0) step)))
              (setq dy (- target (PdfLayout_LynxCenterY r)))
              (if (> (abs dy) 1e-9)
                (progn
                  (vl-catch-all-apply 'vla-Move
                    (list obj (vlax-3d-point 0.0 0.0 0.0)
                          (vlax-3d-point 0.0 dy 0.0)))
                  (setq labs (PdfLayout_LynxUpdateLab
                               labs en obj (PdfLayout_RectShiftY r dy)))
                  (setq nMoved (1+ nMoved))
                )
              )
            )
          )
        )
      )
      (PdfLayout_Prog (strcat "LYNX_PLACE rows=" (itoa nRows)
                               " labels=" (itoa (length labs))
                               " moved=" (itoa nMoved)))
      (princ (strcat "\n[LYNX-PLACE] rows " (itoa nRows)
                     ", labels " (itoa (length labs))
                     ", moved " (itoa nMoved) "."))
      (princ)
    )
  )
)

(defun c:LYNXPLACE () (PdfLayout_LynxPlace))
(princ)
