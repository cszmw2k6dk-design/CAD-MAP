;;; Row-coherent placement for LYNX / LBD labels.
;;; Loaded after PdfLayout_auto.lsp. All text is ASCII.
(setq *PdfLayout_LynxMaxStep* 8)
(setq *PdfLayout_LynxRowFactor* 4.0)

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
                             best bestKey nMoved nRows nThis ok lanes lane)
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
      (setq strRects (PdfLayout_TextRects strLay))
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
      (setq nMoved 0 nRows 0)
      (foreach row rows
        (setq nRows (1+ nRows))
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
                (setq hc (+ hc (PdfLayout_RectHitsEx cand strRects en)))
                (setq obc (+ obc (PdfLayout_RectHits cand *PdfLayout_ObsRects*)))
                (foreach lab labs
                  (if (not (member (car lab) rowNames))
                    (if (PdfLayout_RectOver cand (caddr lab))
                      (setq lbc (1+ lbc))
                    )
                  )
                )
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
