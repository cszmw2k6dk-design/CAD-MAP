;;;=============================================================
;;; PdfLayout_auto.lsp  -  PDF 半自动流程编排器 自动化层
;;; 本文件纯 ASCII，由主程序 PdfLayout.lsp 加载后再调用（复用其已有函数）。
;;; 用法(通过 COM SendCommand 发送 LISP 表达式)：
;;;   (load "..../PdfLayout.lsp")
;;;   (load "..../PdfLayout_auto.lsp")
;;;   (PdfLayout_AutoRun "..../pdfauto.ini" "..../prog.txt")
;;;=============================================================
(vl-load-com)

;; LBD 标签字高：0 = 不用 LBD 区域宽算（回到老逻辑：填固定字高 / 自动按底图尺寸）
;; 想重新启用"LBD 区域宽 x 倍数"就把它改成 >0（例如 1.4）
(setq *PdfLayout_LbdRegionScale* 0.0)
;; 画完之后要不要跑「LBD 标签避让 STR 号」这步（程序里可以设成 nil 关掉）
(setq *PdfLayout_LbdAvoidOn* T)

;;; 进度写入(覆盖写，供外部轮询)
(defun PdfLayout_Prog (msg / _ar)
  (if *PdfLayout_ProgPath*
    (vl-catch-all-apply
      '(lambda (/ f)
        (setq f (open *PdfLayout_ProgPath* "a"))
        (if f (progn (princ msg f) (princ "\n" f) (close f))))
      nil))
  (if (= (strcase msg) "RUN_DONE")
    (progn
      ;; ① STR 号已经画完：让 LBD 标签反过来避让一下（用 CAD 里的真实包围盒）
      (setq _ar (vl-catch-all-apply 'PdfLayout_LbdPlace nil))
      (if (vl-catch-all-error-p _ar)
        (setq _ar (vl-catch-all-apply 'PdfLayout_LbdAvoidStr nil))
      )
      (if (vl-catch-all-error-p _ar)
        (princ (strcat "\n[LBD避让STR] 出错：" (vl-catch-all-error-message _ar)))
      )
    )
  )
)

;;;-------------------------------------------------------------
;;; LBD 标签反过来避让 STR 号（STR 号画完之后跑一趟）
;;; 用 CAD 里真实的包围盒判断（不再靠 Python 估算）：把压住 STR 号的
;;; LBD 标签上下挪 1.5 / 3 倍字高，挪到不压为止；都挪不开就保持原位。
;;; 手动执行：LBDAVOIDSTR
;;;-------------------------------------------------------------
(defun PdfLayout_ObjBox (obj / mn mx r)
  (setq mn nil mx nil)
  (setq r (vl-catch-all-apply '(lambda () (vla-GetBoundingBox obj 'mn 'mx))))
  (if (and (not (vl-catch-all-error-p r)) mn mx)
    (list (vlax-safearray->list mn) (vlax-safearray->list mx))
  )
)

(defun PdfLayout_BoxShift (bb dx dy)
  ;; 包围盒平移后的两个角点（左下、右上）
  (list (list (+ (car (car bb)) dx) (+ (cadr (car bb)) dy))
        (list (+ (car (cadr bb)) dx) (+ (cadr (cadr bb)) dy)))
)

(defun PdfLayout_HitCount (bb layer selfE / ss p1 p2 i n)
  ;; 这个框(crossing)里有几个该图层上的文字（selfE = 自己，排除掉）
  (setq p1 (car bb) p2 (cadr bb) n 0)
  (setq ss (ssget "_C" p1 p2 (list '(0 . "MTEXT,TEXT") (cons 8 layer))))
  (if ss
    (progn
      (setq i 0)
      (while (< i (sslength ss))
        (if (or (null selfE) (/= (ssname ss i) selfE))
          (setq n (1+ n))
        )
        (setq i (1+ i))
      )
    )
  )
  n
)

;;; 三元组按字典序比大小。AutoLISP 的 < 只能比数字/字符串，
;;; 直接拿两个列表去比会报「用于比较的参数类型不正确」。
(defun PdfLayout_KeyLess (a b)
  (if (= (car a) (car b))
    (if (= (cadr a) (cadr b))
      (< (caddr a) (caddr b))
      (< (cadr a) (cadr b))
    )
    (< (car a) (car b))
  )
)

;;; 旧实现（ssget 交叉选择 + 切标签页）在自动跑的时候会把 CAD 卡住，
;;; 现在直接转发到新的安全实现。
(defun PdfLayout_LbdAvoidStr () (PdfLayout_LbdPlaceRaw))

;;; =============================================================
;;; LBD label final placement   (ASCII only: this file is GBK)
;;;  - STR numbers are the fixed part: they never move here.
;;;  - a label may only move up/down, and only inside its own LBD
;;;    region (L line columns 8/9 give that region fy range).
;;;  - it must not cover STR numbers, the printed text boxes on the
;;;    underlay (O lines) or other LBD labels.
;;;  - among free spots, the one closest to the region centre wins.
;;;  - runs after the STR numbers are drawn (PdfLayout_Prog RUN_DONE).
;;; =============================================================
(setq *PdfLayout_LbdStepMax* 6)

(defun PdfLayout_RectMake (bb)
  ;; ((x1 y1)(x2 y2)) -> (x1 y1 x2 y2)
  (if bb
    (list (car (car bb)) (cadr (car bb)) (car (cadr bb)) (cadr (cadr bb)))
  )
)

(defun PdfLayout_RectBox (r)
  ;; (x1 y1 x2 y2) -> ((x1 y1)(x2 y2)) for ssget
  (list (list (car r) (cadr r)) (list (nth 2 r) (nth 3 r)))
)

(defun PdfLayout_RectOver (a b)
  ;; T if two (x1 y1 x2 y2) rects overlap
  (and a b
       (< (car a) (nth 2 b)) (> (nth 2 a) (car b))
       (< (cadr a) (nth 3 b)) (> (nth 3 a) (cadr b)))
)

(defun PdfLayout_RectShiftY (r dy)
  (list (car r) (+ (cadr r) dy) (nth 2 r) (+ (nth 3 r) dy))
)

(defun PdfLayout_RectHits (r lst / n)
  (setq n 0)
  (foreach x lst (if (PdfLayout_RectOver r x) (setq n (1+ n))))
  n
)

;;; 某图层上的文字框，一次性收下来：((ename x1 y1 x2 y2) ...)
;;; 不用 ssget —— 那玩意在脚本 / COM 上下文里会让 CAD 卡住或等输入，
;;; 而且每个候选位置都要选一次，几十个标签就是几百次选择。
(defun PdfLayout_TextRects (layer / doc ms obj lay bb out on)  
  (setq out nil)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)))
  (setq ms (vla-get-ModelSpace doc))
  (vlax-for obj ms
    (setq on (vl-catch-all-apply 'vla-get-ObjectName (list obj)))
    (if (and (not (vl-catch-all-error-p on))
             (member (strcase on) '("ACDBTEXT" "ACDBMTEXT")))
      (progn
        (setq lay (vl-catch-all-apply 'vla-get-Layer (list obj)))
        (if (and (not (vl-catch-all-error-p lay))
                 (= (strcase lay) (strcase layer)))
          (progn
            (setq bb (PdfLayout_ObjBox obj))
            (if bb
              (setq out (cons (cons (vlax-vla-object->ename obj)
                                    (PdfLayout_RectMake bb)) out))
            )
          )
        )
      )
    )
  )
  out
)

(defun PdfLayout_RectHitsEx (r lst en / n)
  ;; 和 PdfLayout_RectHits 一样，但列表是 (ename x1 y1 x2 y2)，且排除自己
  (setq n 0)
  (foreach x lst
    (if (and (/= (car x) en) (PdfLayout_RectOver r (cdr x)))
      (setq n (1+ n))))
  n
)

(defun PdfLayout_OtherRects (labs en / out)
  (setq out nil)
  (foreach x labs (if (/= (car x) en) (setq out (append out (list (caddr x))))))
  out
)

;;; lexicographic compare of two number lists (works for any length)
(defun PdfLayout_KeyLt (a b)
  (if a
    (if b
      (cond
        ((< (car a) (car b)) T)
        ((> (car a) (car b)) nil)
        (T (PdfLayout_KeyLt (cdr a) (cdr b)))
      )
      T
    )
    nil
  )
)

;;; O <page> <fx1> <fy1> <fx2> <fy2>  = printed text boxes on the underlay
(defun PdfLayout_ObsRead (path / f line parts out)
  (setq out nil)
  (setq f (if path (open path "r") nil))
  (if f
    (progn
      (while (setq line (read-line f))
        (setq parts (PdfLayout_SplitTab line))
        (if (and (> (length parts) 5) (= (car parts) "O"))
          (setq out (append out (list (list (atoi (nth 1 parts))
                                            (atof (nth 2 parts)) (atof (nth 3 parts))
                                            (atof (nth 4 parts)) (atof (nth 5 parts))))))
        )
      )
      (close f)
    )
  )
  out
)

;;; L <pg> <fx> <fy> <name> <ang> <h> <ymin> <ymax>  = label + its region range
(defun PdfLayout_RngRead (path / f line parts out)
  (setq out nil)
  (setq f (if path (open path "r") nil))
  (if f
    (progn
      (while (setq line (read-line f))
        (setq parts (PdfLayout_SplitTab line))
        (if (and (> (length parts) 8) (= (car parts) "L"))
          (setq out (append out (list (list (atoi (nth 1 parts))
                                            (atof (nth 2 parts)) (atof (nth 3 parts))
                                            (atof (nth 7 parts)) (atof (nth 8 parts))))))
        )
      )
      (close f)
    )
  )
  out
)

(defun PdfLayout_RngFind (lst pg fx fy / hit)
  (setq hit nil)
  (foreach r lst
    (if (and (not hit) (= (car r) pg)
             (< (abs (- (cadr r) fx)) 1e-9) (< (abs (- (caddr r) fy)) 1e-9))
      (setq hit r)
    )
  )
  hit
)

;;; model space rects of the printed boxes (O lines) for one page
(defun PdfLayout_ObsForPage (pg pmin bw bh / out)
  (setq out nil)
  (foreach o *PdfLayout_ObsAll*
    (if (= (car o) pg)
      (setq out (append out (list (list (+ (car pmin) (* (nth 1 o) bw))
                                        (+ (cadr pmin) (* (nth 2 o) bh))
                                        (+ (car pmin) (* (nth 3 o) bw))
                                        (+ (cadr pmin) (* (nth 4 o) bh))))))
    )
  )
  out
)

;;; place every LBD label: only up/down, inside its region, no overlap with
;;; STR numbers / printed boxes / other labels, closest to the region centre
(defun PdfLayout_LbdPlace (/ _t0 _r)
  ;; 总开关：程序里把 *PdfLayout_LbdAvoidOn* 设成 nil 就整段跳过
  (if (eq *PdfLayout_LbdAvoidOn* nil)
    (progn (princ "\n[LBD-PLACE] 已关闭，跳过。") (princ))
    (progn
      (setq _t0 (PdfLayout_NowMs))
      (setq _r (vl-catch-all-apply 'PdfLayout_LbdPlaceRaw nil))
      (if (vl-catch-all-error-p _r)
        (princ (strcat "\n[LBD-PLACE] 出错：" (vl-catch-all-error-message _r)))
        (princ (strcat "\n[LBD-PLACE] 用时 " (itoa (fix (- (PdfLayout_NowMs) _t0))) " ms"))
      )
    )
  )
  (princ)
)

(defun PdfLayout_LbdPlaceRaw (/ doc ms labLay strLay labs obj bb r en h step k s off rng lo hi
                             ctr ctr0 cand oc hc obc lbc key best bestKey nTot nMoved
                             strRects)
  (vl-load-com)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq labLay "LBD标签")
  (setq strLay (if (and *PdfLayout_AiLayer* (/= *PdfLayout_AiLayer* ""))
                 *PdfLayout_AiLayer* "PDF-AUTO-NUM"))
  (if (not (numberp *PdfLayout_LbdStepMax*)) (setq *PdfLayout_LbdStepMax* 6))
  (setq labs nil)
  (vlax-for obj ms
    (if (= (strcase (vl-catch-all-apply 'vla-get-Layer (list obj))) (strcase labLay))
      (progn
        (setq bb (PdfLayout_ObjBox obj))
        (if bb
          (setq labs (append labs (list (list (vlax-vla-object->ename obj) obj
                                              (PdfLayout_RectMake bb)))))
        )
      )
    )
  )
  (setq strRects (PdfLayout_TextRects strLay))   ;; 一次收好，后面纯数学判交
  (setq nTot (length labs) nMoved 0)
  (foreach it labs
    (setq en (car it) obj (cadr it) r (caddr it))
    (setq h (vl-catch-all-apply 'vla-get-Height (list obj)))
    (setq h (if (and (numberp h) (> h 0.0)) h 0.05))
    (setq step (* 1.5 h))
    (setq rng (assoc en *PdfLayout_LbdRange*))
    (if rng
      (progn
        (setq lo (+ (cadr rng) (/ h 2.0)))
        (setq hi (- (caddr rng) (/ h 2.0)))
        (setq ctr0 (/ (+ (cadr rng) (caddr rng)) 2.0))
      )
      (progn (setq lo nil) (setq hi nil)
             (setq ctr0 (* 0.5 (+ (cadr r) (nth 3 r)))))
    )
    ;; region shorter than the text: no room to move, keep the drawn place
    (if (and lo (> lo hi)) (progn (setq lo nil) (setq hi nil)))
    (setq ctr (* 0.5 (+ (cadr r) (nth 3 r))))
    (setq best nil bestKey nil)
    (setq k 0)
    (while (<= k (fix *PdfLayout_LbdStepMax*))
      (foreach s (if (= k 0) (list 0.0) (list (float k) (- 0.0 (float k))))
        (setq off (* s step))
        (setq cand (PdfLayout_RectShiftY r off))
        (setq oc (* 0.5 (+ (cadr cand) (nth 3 cand))))
        (if (or (null lo) (and (>= oc (- lo 1e-9)) (<= oc (+ hi 1e-9))))
          (progn
            (setq hc (PdfLayout_RectHitsEx cand strRects en))
            (setq obc (PdfLayout_RectHits cand *PdfLayout_ObsRects*))
            (setq lbc (PdfLayout_RectHits cand (PdfLayout_OtherRects labs en)))
            (setq key (list hc obc lbc (abs (- oc ctr0)) (abs off)))
            (if (or (null bestKey) (PdfLayout_KeyLt key bestKey))
              (setq best off bestKey key)
            )
          )
        )
      )
      (setq k (1+ k))
    )
    (if (and best (/= best 0.0))
      (progn
        (vl-catch-all-apply 'vla-Move
          (list obj (vlax-3d-point 0.0 0.0 0.0) (vlax-3d-point 0.0 best 0.0)))
        (setq labs
          (mapcar '(lambda (x)
                     (if (= (car x) en)
                       (list en obj (PdfLayout_RectShiftY r best))
                       x))
                  labs))
        (setq nMoved (1+ nMoved))
      )
    )
  )
  (PdfLayout_Prog (strcat "LBD_PLACE labels=" (itoa nTot) " moved=" (itoa nMoved)))
  (princ (strcat "\n[LBD-PLACE] labels " (itoa nTot) ", moved " (itoa nMoved) "."))
  (princ)
)

(defun c:LBDAVOIDSTR () (PdfLayout_LbdPlace))
(defun c:LBDAVOIDSTR_OLD () (PdfLayout_LbdAvoidStr))
;;; 计时(毫秒)：优先 MILLISECS，取不到就用 DATE 的当天比例换算（只为进度显示）
(defun PdfLayout_NowMs (/ v)
  (setq v (vl-catch-all-apply 'getvar (list "MILLISECS")))
  (if (or (vl-catch-all-error-p v) (not (numberp v)) (<= v 0))
    (progn
      (setq v (vl-catch-all-apply 'getvar (list "DATE")))
      (if (and (numberp v) (> v 0))
        (fix (* (- v (fix v)) 86400000.0))
        0))
    (fix v))
)

;;; 读取 key=value 的 ini 配置文件，返回 ((key . val) ...)
(defun PdfLayout_ReadAutoConfig (path / f line eq k v out)
  (setq out nil)
  (setq f (open path "r"))
  (if f
    (progn
      (while (setq line (read-line f))
        (setq line (vl-string-trim " " line))
        (if (and (/= line "") (/= (substr line 1 1) ";"))
          (progn
            (setq eq (vl-string-search "=" line))
            (if (and eq (> eq 0))
              (progn
                (setq k (substr line 1 eq))
                (setq v (substr line (+ eq 2)))
                (setq out (append out (list (cons k v))))
              )
            )
          )
        )
      )
      (close f)
    )
  )
  out
)

(defun PdfLayout_ACfg (cfg key dflt / e)
  (setq e (assoc key cfg))
  (if e (cdr e) dflt)
)

;;; 运行 python 提取脚本并等待完成(返回 T 成功 / nil 失败)

(defun PdfLayout_WriteRunVbs (/ f)
  (setq f (open (strcat (getvar "TEMPPREFIX") "pdflbd_run.vbs") "w"))
  (if f
    (progn
      (princ "Set sh = CreateObject(\"WScript.Shell\")\r\n" f)
      (princ (strcat "sh.Run \"" (getvar "TEMPPREFIX") "pdflbd_run.bat\", 0, False\r\n") f)
      (close f)
    )
  )
)

(defun PdfLayout_RunExtract (pdf outPath progPath logPath pgStart pgEnd / ok)
  (setq ok nil)
  (PdfLayout_WritePyScript)
  (setq script (strcat (getvar "TEMPPREFIX") "pdf_extract.py"))
  (PdfLayout_EnsurePython)
  (PdfLayout_WriteBat script pdf outPath progPath logPath pgStart pgEnd)
  (vl-catch-all-apply 'startapp (list (strcat (getvar "TEMPPREFIX") "pdflbd_run.bat")))
  (setq wait 0 batOk nil)
  (while (and (< wait 8) (not batOk))
    (if (findfile (strcat (getvar "TEMPPREFIX") "pdflbd_bat.txt"))
      (setq batOk T)
      (if (not batOk) (progn (command "._DELAY" 300) (setq wait (1+ wait))))
    )
  )
  (setq wait 0 done nil err nil)
  (while (and (< wait 1200) (not done))
    (setq txt (PdfLayout_ReadFileText progPath))
    (if (and txt (vl-string-search "DONE" (strcase txt))) (setq done T))
    (if (and txt (vl-string-search "ERR" (strcase txt))) (setq done T err T))
    (if (not done) (progn (command "._DELAY" 200) (setq wait (1+ wait))))
  )
  (if (and done (not err) (findfile outPath)) (setq ok T))
  ok
)

;; 稳定排序：不用 vl-sort —— 中望/AutoCAD 的 vl-sort 会把"相等"的元素丢掉
(defun PdfLayout_AutoIns (lst x cmp / out done y)
  (setq out nil done nil)
  (foreach y lst
    (if (and (not done) (apply cmp (list x y)))
      (progn (setq out (append out (list x y))) (setq done T))
      (setq out (append out (list y)))
    )
  )
  (if (not done) (setq out (append out (list x))))
  out
)

(defun PdfLayout_AutoStableSort (lst cmp / out x)
  (foreach x lst
    (setq out (PdfLayout_AutoIns out x cmp))
  )
  out
)

;; 一页的 LBD 标签重排：先按 fy(第3位) 从大到小分排(容差 0.02)，排内按 fx(第2位) 从左到右
;; 元素就是提取文件里的 L 行：(页号 fx fy 文本 角度 字高)
(defun PdfLayout_LbdRowSort (lst tol / byFy rows cur out e r)
  (if (not lst)
    nil
    (progn
      (setq byFy (PdfLayout_AutoStableSort lst '(lambda (a b) (> (caddr a) (caddr b)))))
      (setq rows nil cur nil)
      (foreach e byFy
        (if (or (not cur) (> (abs (- (caddr e) (caddr (car cur)))) tol))
          (progn (if cur (setq rows (append rows (list cur)))) (setq cur (list e)))
          (setq cur (append cur (list e)))
        )
      )
      (if cur (setq rows (append rows (list cur))))
      (setq out nil)
      (foreach r rows
        (setq out (append out
                     (PdfLayout_AutoStableSort r '(lambda (a b) (< (cadr a) (cadr b))))))
      )
      out
    )
  )
)

;;; LBD 自动识别并填写标签(非交互)
(defun PdfLayout_LbdAuto (pdf xlsx pgStart pgEnd txtH labelWhere bgColor bgGap txtColor / ok autoTxt maxDim uu bbu doc actLay blk vp ptUse runOk wait nSeen hgtR txtHi pgIt pit)
  (setq autoTxt (or (not txtH) (<= txtH 0.0)))
  (setq outPath (if *PdfLayout_LbdPre* *PdfLayout_LbdOut* (strcat (getvar "TEMPPREFIX") "pdflbd_extract.txt")))
  (setq progPath (strcat (getvar "TEMPPREFIX") "pdflbd_progress.txt"))
  (setq logPath (strcat (getvar "TEMPPREFIX") "pdflbd_log.txt"))
  (if (not *PdfLayout_LbdPre*)
    (foreach pf (list outPath progPath logPath)
      (if (findfile pf) (vl-file-delete pf))
    )
  )
  (PdfLayout_Prog "LBD_RUN")
  (setq runOk nil)
  (if *PdfLayout_LbdPre*
    (progn
      ;; B2: exe 已就地解析并写出提取文件，LSP 不再调用外部 python
      (setq wait 0)
      (while (and (< wait 200) (not (findfile outPath)))
        (command "._DELAY" 200)
        (setq wait (1+ wait))
      )
      (setq runOk (findfile outPath))
    )
    (setq runOk (PdfLayout_RunExtract pdf outPath progPath logPath pgStart pgEnd))
  )
  (if (not runOk)
    (progn
      (PdfLayout_Prog (strcat "ERROR:LBD extract failed - " (PdfLayout_ReadFileText logPath)))
      nil
    )
    (progn
      (setq res (PdfLayout_ReadExtractFile outPath))
      (setq pages (car res) items (cadr res))
      (setq validItems nil)
      (foreach it items
        (if (PdfLayout_LbdNumFromText (cadddr it))
          (setq validItems (append validItems (list it)))
        )
      )
      (if (and *PdfLayout_FilterCluster* (= *PdfLayout_FilterCluster* "1"))
        (progn
          (setq nB (length validItems))
          (setq validItems (PdfLayout_FilterCluster validItems))
          (PdfLayout_Prog (strcat "LBD_FILTER excluded " (itoa (- nB (length validItems)))))
        )
      )
      (setq sheetMap nil)
      (if (and xlsx (/= xlsx "")) (setq sheetMap (PdfLayout_ReadAllLbdLabels xlsx)))
      (setq *PdfLayout_ObsAll* (PdfLayout_ObsRead outPath))
      (setq *PdfLayout_RngAll* (PdfLayout_RngRead outPath))
      (setq *PdfLayout_ObsRects* nil)
      (setq *PdfLayout_LbdRange* nil)
      (PdfLayout_Prog (strcat "LBD_OBS " (itoa (length *PdfLayout_ObsAll*))))
      (setq underlays (PdfLayout_GetPdfUnderlays))
      (setq ms (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-Acad-Object))))
      (if autoTxt
        (progn
          (setq maxDim 0.0)
          (foreach uu underlays
            (setq bbu (PdfLayout_GetExtentsSafeObj uu))
            (if bbu (setq maxDim (max maxDim (+ (- (car (cadr bbu)) (car (car bbu))) (- (cadr (cadr bbu)) (cadr (car bbu)))))))
          )
          (setq txtH (if (> maxDim 0.0) (/ maxDim 150.0) 0.05))
          (PdfLayout_Prog (strcat "LBD_AUTOTXT " (rtos txtH 2 4)))
        )
      )
      ;; 删除旧 LBD 标签
      (vlax-for mo ms
        (if (and (= (vla-get-ObjectName mo) "AcDbMText")
                 (= (strcase (vla-get-Layer mo)) (strcase "LBD标签")))
          (vl-catch-all-apply 'vla-Delete (list mo))
        )
      )
      (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
      (if (= labelWhere "L")
        (progn
          (setq actLay (vla-get-ActiveLayout doc))
          (setq blk (vla-get-Block actLay))
          (setq vp (PdfLayout_LayoutBiggestVp actLay)))
        (progn (setq blk ms) (setq vp nil))
      )
      (setq i 0 nDone 0 nSeen 0 nPgDone 0 statNoSheet 0 statNoLabel 0)
      (PdfLayout_Prog (strcat "LBD_TOTAL " (itoa (length validItems))))
      (foreach u underlays
        (setq pgnum (1+ i))
        (setq nPgDone 0)
        (setq tPg0 (PdfLayout_NowMs))
        (setq bb (PdfLayout_GetExtentsSafeObj u))
        (if bb
          (progn
            (setq pmin (car bb) pmax (cadr bb))
            (setq bw (- (car pmax) (car pmin)))
            (setq bh (- (cadr pmax) (cadr pmin)))
            (setq *PdfLayout_ObsRects*
              (append *PdfLayout_ObsRects* (PdfLayout_ObsForPage pgnum pmin bw bh)))
            ;; 这一页的 LBD 标签先按「行(上→下) + 行内 x(左→右)」排好 —— 后面按这个顺序画，
            ;; 才有"隔一个往下错一行"的整齐效果（原来是按提取文件里的先后顺序画）
            (setq pgIt nil)
            (foreach pit validItems
              (if (= (car pit) pgnum)
                (setq pgIt (append pgIt (list pit)))
              )
            )
            (setq pgIt (PdfLayout_LbdRowSort pgIt (/ (* 4.0 txtH) (if (> bh 0.0) bh 1.0))))
            (setq curRowFy nil curLane 0 lastRight nil)

            (foreach it pgIt
              (if (= (car it) pgnum)
                (progn
                  (setq nSeen (1+ nSeen))
                  (if (= (rem nSeen 5) 0)
                    (PdfLayout_Prog (strcat "LBD_LABEL " (itoa nSeen)))
                  )
                  (setq fx (cadr it) fy (caddr it) stext (cadddr it))
                  ;; LBD 字高：L 行带第 7 列(LBD 区域宽/页高) 且界面填了倍数 -> 区域宽 x 底图高 x 倍数；
                  ;; 倍数填 0、或这行没有第 7 列(按 PDF 文字层识别出来的) -> 用原来的 txtH
                  ;; （以前这里还要求「标签高度」必须是 0(自动档)，结果界面上填了倍数也不生效）
                  (setq hgtR (if (nth 5 it) (nth 5 it) 0.0))
                  (setq txtHi (if (and (> hgtR 0.0) (> bh 0.0)
                                       (numberp *PdfLayout_LbdRegionScale*)
                                       (> *PdfLayout_LbdRegionScale* 0.0))
                                (* hgtR bh *PdfLayout_LbdRegionScale*)
                                txtH))
                  (setq num (PdfLayout_LbdNumFromText stext))
                  (if num
                    (progn
                      (setq mx (+ (car pmin) (* fx bw)))
                      (setq my (+ (cadr pmin) (* fy bh)))
                      (setq shN (PdfLayout_LbdSheetFromText stext))
                      (if (not shN) (setq statNoSheet (1+ statNoSheet)))
                      (setq sheetLabels (if shN (cdr (assoc shN sheetMap)) nil))
                      (setq labels (if sheetLabels (cdr (assoc num sheetLabels)) nil))
                      ;; LBD 标签只认 Excel 映射: 查不到就不画, 不用 PDF 原文兜底, 也不编造 "LBD-xx"
                      (if labels
                        (progn
                          ;; 上下两档错行：第1个落在区域中心线上，第2个往下错一行，第3个回中心线…
                          (setq natW (* txtHi (+ (* 0.8 (strlen labels)) 0.2)))
                          (setq lft (- mx (* natW 0.5)) rgt (+ mx (* natW 0.5)))
                          (if (or (not curRowFy)
                                  (> (abs (- fy curRowFy)) (/ (* 4.0 txtH) (if (> bh 0.0) bh 1.0))))
                            (progn (setq curRowFy fy curLane 0 lastRight nil))
                          )
                          (if (and lastRight (< lft lastRight))
                            (setq curLane (if (= curLane 1) 0 1))
                            (setq curLane 0)
                          )
                          ;; 错开量：1.5 倍字高(且不小于字高+0.10) —— 下错一行后与上一个标签不再重叠
                          (setq step (max (* txtHi 1.5) (+ txtHi 0.10)))
                          (setq laneOff (if (= curLane 0) 0.0 step))
                          (setq ptIns (list mx (- my laneOff) 0.0))
                          (setq ptUse (if (and (= labelWhere "L") vp) (PdfLayout_ModelToPaper vp ptIns) ptIns))
                          (setq mObj (vl-catch-all-apply
                                'vla-AddMText
                                (list blk (vlax-3d-point ptUse)
                                      natW labels)))
                          (if (and mObj (not (vl-catch-all-error-p mObj)))
                            (progn
                              (vl-catch-all-apply 'vla-put-Height (list mObj txtHi))
                              (vl-catch-all-apply 'vla-put-BackgroundFill (list mObj :vlax-true))
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillUseDrawingBackgroundColor :vlax-false)) nil)
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillColor (if bgColor bgColor 1))) nil)
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillGapFactor (if bgGap bgGap 1.0))) nil)
                               (setq *PdfLayout_LbdBgColor* (if bgColor bgColor 1))
  (setq *PdfLayout_LbdGap* (if bgGap bgGap 1.0))
                               (vl-catch-all-apply 'PdfLayout_MTextRedWhite (list mObj))
                               (vl-catch-all-apply 'vla-put-AttachmentPoint (list mObj 5))
                               (vl-catch-all-apply 'vla-put-InsertionPoint (list mObj (vlax-3d-point ptUse)))
                              (vl-catch-all-apply 'vla-put-Color (list mObj (if (and txtColor (> txtColor 0)) txtColor 7)))
                              (vl-catch-all-apply
                                '(lambda () (command "._DRAWORDER"
                                                     (vlax-vla-object->ename mObj) "" "_Front")) nil)
                              (setq lay (PdfLayout_EnsureLayer "LBD标签"))
                              (if (and lay (not (vl-catch-all-error-p lay)))
                                (vl-catch-all-apply 'vla-put-Layer (list mObj "LBD标签")))
                              (setq _rng (PdfLayout_RngFind *PdfLayout_RngAll* pgnum fx fy))
                              (if _rng
                                (setq *PdfLayout_LbdRange*
                                  (append *PdfLayout_LbdRange*
                                    (list (list (vlax-vla-object->ename mObj)
                                                (+ (cadr pmin) (* (nth 3 _rng) bh))
                                                (+ (cadr pmin) (* (nth 4 _rng) bh))))))
                              )
                              (setq nDone (1+ nDone))
                              (setq nPgDone (1+ nPgDone))
                               (setq lastRight rgt)
                            )
                          )
                        )
                      )
                    )
                  )
                )
              )
            )
          )
        )
        (setq i (1+ i))
        (PdfLayout_Prog (strcat "LBD_PAGE " (itoa pgnum) " " (itoa (length underlays))
                                " filled=" (itoa nPgDone)
                                " ms=" (itoa (max 0 (- (PdfLayout_NowMs) (if tPg0 tPg0 0))))))
      )
      (PdfLayout_Prog (strcat "LBD_DONE " (itoa nDone)))
      (PdfLayout_Prog (strcat "LBD_STAT 匹配到页=" (itoa nSeen) " 分表名没认出=" (itoa statNoSheet) " 编号表里没有=" (itoa statNoLabel) " 分表数=" (itoa (length sheetMap))))
      (princ (strcat "\n[PDFAUTO] LBD 已填写 " (itoa nDone) " 个标签。"))
      T
    )
  )
)

;;; 主入口：读配置，依次执行 布局复制 -> LBD 自动填写 -> 另存新 DWG
(defun PdfLayout_AutoTemplate (/ names best nm)
  (setq names (PdfLayout_GetLayoutNames))
  (setq best nil)
  (foreach nm names
    (if (and (/= (strcase nm) "MODEL") (PdfLayout_GetLayoutViewports nm))
      (setq best (append best (list nm)))))
  (if best (car best) "")
)

;;;-------------------------------------------------------------
;;; 布局生成后：按识别结果里 LBD 区域的上下限对准视口（缩放 + 居中）
;;; 区域范围文件由编排器写入 %TEMP%\pdflbd_regions.txt，每行:
;;;   R <序号> <fx1> <fy1> <fx2> <fy2>
;;; 归一化 0~1，x 从左往右、y 从下往上（和提取文件 L 行 fx/fy 同一套坐标）；
;;; 序号 1 = 第 1 个布局 / 第 1 张图纸，依次往下。没有区域数据的页写整页(0,0,1,1)。
;;;-------------------------------------------------------------
(defun PdfLayout_AutoTabSplit (s / out tmp i c)
  (setq out nil tmp "" i 1)
  (while (<= i (strlen s))
    (setq c (substr s i 1))
    (if (= c (chr 9))
      (progn (setq out (append out (list tmp))) (setq tmp ""))
      (setq tmp (strcat tmp c))
    )
    (setq i (1+ i))
  )
  (if (/= tmp "") (setq out (append out (list tmp))))
  out
)

(defun PdfLayout_AutoReadRegions (path / f line parts out)
  (setq out nil)
  (if (and path (/= path "") (findfile path))
    (progn
      (setq f (open path "r"))
      (while (and f (setq line (read-line f)))
        (setq parts (PdfLayout_AutoTabSplit line))
        (if (and parts (= (strcase (car parts)) "R") (>= (length parts) 6))
          (setq out (append out (list (list (atoi (nth 1 parts))
                                            (atof (nth 2 parts)) (atof (nth 3 parts))
                                            (atof (nth 4 parts)) (atof (nth 5 parts))))))
        )
      )
      (if f (close f))
    )
  )
  out
)

;; 归一化区域范围 -> 模型空间 bbox（按底图范围换算，和画 STR 号用的是同一套映射）
(defun PdfLayout_AutoRegionBox (bb r / pmin pmax dx dy fx1 fy1 fx2 fy2)
  (setq pmin (car bb) pmax (cadr bb))
  (setq dx (- (car pmax) (car pmin)) dy (- (cadr pmax) (cadr pmin)))
  (setq fx1 (nth 1 r) fy1 (nth 2 r) fx2 (nth 3 r) fy2 (nth 4 r))
  (list (list (+ (car pmin) (* fx1 dx)) (+ (cadr pmin) (* fy1 dy)) 0.0)
        (list (+ (car pmin) (* fx2 dx)) (+ (cadr pmin) (* fy2 dy)) 0.0))
)

(defun PdfLayout_AutoRegionFit (cfg names lockVp / regs draws i nTot k nm bb r box vps vpObj vp tPg0 msPg)
  (setq regs (PdfLayout_AutoReadRegions (PdfLayout_ACfg cfg "regionFile" "")))
  (if (and regs names)
    (progn
      (setq draws (PdfLayout_ScanMarkerDrawings (PdfLayout_ACfg cfg "filter" "pdf")))
      (setq i 0 k 0)
      ;; 按 LBD 区域上下限调视口大小：布局一多这一步也要几十秒，所以逐个布局写进度，
      ;; 界面才能显示"区域对准 3/12"（REGION_TOTAL / REGION_FIT / REGION_DONE）。
      (setq nTot (length names))
      (PdfLayout_Prog (strcat "REGION_TOTAL " (itoa nTot)))
      (foreach nm names
        (setq tPg0 (PdfLayout_NowMs))
        (setq bb (nth i draws) r (nth i regs))
        (if (and bb r (PdfLayout_GetLayoutObj nm))
          (progn
            (setq box (PdfLayout_AutoRegionBox bb r))
            (command ".-LAYOUT" "_S" nm "")
            (setq vps (PdfLayout_GetLayoutViewports nm))
            (if vps
              (progn
                (setq vp (car (PdfLayout_StableSort vps 'PdfLayout_CmpVpArea)))
                (setq vpObj (car vp))
                ;; 先解锁：上一轮对准时如果锁了显示，这里就改不动了
                (vl-catch-all-apply 'vla-put-DisplayLocked (list vpObj :vlax-false))
                (PdfLayout_FitViewport vpObj box lockVp)
                (setq k (1+ k))
              )
            )
          )
        )
        (setq i (1+ i))
        (setq msPg (max 0 (- (PdfLayout_NowMs) (if tPg0 tPg0 0))))
        (PdfLayout_Prog (strcat "REGION_FIT " (itoa i) " " (itoa nTot) " " (itoa k)
                                " ms=" (itoa msPg)))
      )
      (if (car names) (command ".-LAYOUT" "_S" (car names) ""))
      (PdfLayout_Prog (strcat "REGION_DONE " (itoa k) " " (itoa nTot)))
      (if (> k 0)
        (princ (strcat "\n[区域对准] 已按 LBD 区域上下限调好 " (itoa k) " 个布局的视口。"))
        (princ "\n[区域对准] 没有可用区域范围，视口保持整页对准。")
      )
    )
    (progn
      (PdfLayout_Prog "REGION_NONE")
      (princ "\n[区域对准] 没有区域范围文件，视口保持整页对准。")
    )
  )
  (princ)
)

(defun PdfLayout_AutoRun (iniPath progPath / cfg tmpl2 names2 xlsx2 pdf outdir newname base fname newpath py nUnder countVal bgc gapc)
  (setq *PdfLayout_ProgPath* progPath)
  (setq *PdfLayout_NoAlert* T)
  (vl-load-com)
  (setq cfg (PdfLayout_ReadAutoConfig iniPath))
  (setq py (PdfLayout_ACfg cfg "pythonPath" ""))
  (if (and py (/= py "")) (setq *PdfLayout_PythonPath* py))
  (setq *PdfLayout_FilterCluster* (PdfLayout_ACfg cfg "filterCluster" "1"))
  (setq *PdfLayout_LbdPre* (PdfLayout_ACfg cfg "lbdPre" "0"))
  (setq *PdfLayout_LbdOut* (PdfLayout_ACfg cfg "lbdOut" ""))
  (PdfLayout_Prog "START")
  (PdfLayout_Prog "STEP_LAYOUT")
  (setq tmpl2 (PdfLayout_ACfg cfg "templateLayout" ""))
  (if (or (not tmpl2) (= tmpl2 "")) (setq tmpl2 (PdfLayout_AutoTemplate)))
  (PdfLayout_Prog (strcat "LAYOUT: template=" tmpl2))
  ;; Layout names come only from the LBD Excel sheet names (naming rule removed).
  (setq xlsx2 (PdfLayout_ACfg cfg "xlsx" ""))
  (setq names2 (if (and xlsx2 (/= xlsx2 "")) (PdfLayout_GetXlsxSheetNames xlsx2) nil))
  (setq nUnder (PdfLayout_CountUnderlays))
  (setq countVal (atoi (PdfLayout_ACfg cfg "count" "0")))
  (if (<= countVal 0)
    (setq countVal (if (> nUnder 0) nUnder 0))
  )
  (if (and names2 (> countVal (length names2))) (setq countVal (length names2)))
  (if (and names2 (<= countVal 0)) (setq countVal (length names2)))
  (PdfLayout_Prog (strcat "LAYOUT: count=" (itoa countVal) " underlays=" (itoa nUnder)))
  (cond
    ((not names2)
      (PdfLayout_Prog "ERROR: SheetNamesMissing")
      (princ "\n[PDFAUTO] ERROR: no LBD Excel sheet names, cannot name layouts.\n")
    )
    ((not (PdfLayout_GetLayoutObj tmpl2))
      (PdfLayout_Prog (strcat "ERROR: TemplateLayoutMissing " tmpl2))
    )
    (T
      (setq *PdfLayout_Params*
        (list
          (cons "Mode" "marker")
          (cons "Filter" (PdfLayout_ACfg cfg "filter" "pdf"))
          (cons "AutoArrange" T)
          (cons "DlgSel" nil)
          (cons "PdfFile" (PdfLayout_ACfg cfg "pdf" ""))
          (cons "TemplateLayout" tmpl2)
          (cons "Count" countVal)
          (cons "Margin" (atof (PdfLayout_ACfg cfg "margin" "5")))
          (cons "Overwrite" (= (PdfLayout_ACfg cfg "overwrite" "0") "1"))
          (cons "LockViewport" nil)      ;; 界面已删掉「锁定视口显示」，固定不锁
          (cons "NamesList" names2)
        )
      )
      (vl-catch-all-apply 'PdfLayout_Execute nil)
      ;; 布局建好后按识别到的 LBD 区域上下限再对准一次视口（不是按整页）
      (if (and names2 (= (PdfLayout_ACfg cfg "regionFit" "1") "1"))
        (vl-catch-all-apply 'PdfLayout_AutoRegionFit
          (list cfg names2 nil))         ;; 对准视口时同样不锁
      )
    )
  )
  (PdfLayout_Prog "STEP_LBD")
  (setq bgc (atoi (PdfLayout_ACfg cfg "labelBgColor" "1")))
  (setq gapc (atof (PdfLayout_ACfg cfg "labelBgGap" "1.0")))
  (setq pdf (PdfLayout_ACfg cfg "pdf" ""))
  (if (and pdf (/= pdf ""))
    (PdfLayout_LbdAuto pdf (PdfLayout_ACfg cfg "xlsx" "") (PdfLayout_ACfg cfg "pageStart" "1") (if (> (atoi (PdfLayout_ACfg cfg "importPages" "0")) 0) (PdfLayout_ACfg cfg "importPages" "0") (PdfLayout_ACfg cfg "pageEnd" "0")) (atof (PdfLayout_ACfg cfg "textHeight" "0")) (PdfLayout_ACfg cfg "labelWhere" "M") (atoi (PdfLayout_ACfg cfg "labelBgColor" "1")) (atof (PdfLayout_ACfg cfg "labelBgGap" "1.0")) (atoi (PdfLayout_ACfg cfg "labelTextColor" "7")))
  )
  (setq outdir (PdfLayout_ACfg cfg "outputDir" ""))
  ;; Auto save off by default: the orchestrator saves from the UI after the run.
  (if (and outdir (/= outdir "") (= (PdfLayout_ACfg cfg "autoSave" "0") "1"))
    (progn
      (PdfLayout_Prog "STEP_SAVE")
      (setq newname (PdfLayout_ACfg cfg "newName" ""))
      (setq base (vl-filename-base (getvar "DWGNAME")))
      (setq fname (if (or (not newname) (= newname "")) "MAP文件.dwg" (if (vl-string-search "." newname) newname (strcat newname ".dwg"))))
      (setq newpath (strcat outdir "\\" fname))
      (if (findfile newpath) (vl-catch-all-apply 'vl-file-delete (list newpath)))
      (vl-catch-all-apply '(lambda () (command "._SAVEAS" "" newpath)) nil)
      (PdfLayout_Prog (strcat "SAVED " newpath))
    )
  )
  (PdfLayout_Prog "DONE")
  (princ "\n[PDFAUTO] OK.\n")
  (princ)
)


;;; 按最近邻距离排除"集中排放"的干扰标号
;;; ==== exclude concentrated interference: cluster-drop(m3) + LBD-number dedup(m1) ====
(defun PdfLayout_Median (lst / s l m)
  (setq l (length lst))
  (if (= l 0) 0.0
    (progn (setq s (vl-sort lst (quote <))) (setq m (/ l 2))
      (if (= (rem l 2) 0) (/ (+ (nth (1- m) s) (nth m s)) 2.0) (nth m s)))))
(defun PdfLayout_ClusterDist (a b / dx dy)
  (setq dx (- (cadr a) (cadr b)))
  (setq dy (- (caddr a) (caddr b)))
  (sqrt (+ (* dx dx) (* dy dy))))
(defun PdfLayout_ComponentsTouch (a b eps / hit ia ib)
  (setq hit nil)
  (foreach ia a
    (foreach ib b
      (if (<= (PdfLayout_ClusterDist ia ib) eps) (setq hit T))))
  hit)
(defun PdfLayout_ClusterComponents (items eps / comps merged c newc hit o)
  (setq comps nil)
  (foreach it items (setq comps (append comps (list (list it)))))
  (setq merged T)
  (while merged
    (setq merged nil)
    (setq newc nil)
    (while comps
      (setq c (car comps))
      (setq comps (cdr comps))
      (setq hit T)
      (while hit
        (setq hit nil)
        (foreach o comps
          (if (PdfLayout_ComponentsTouch c o eps)
            (progn
              (setq c (append c o))
              (setq comps (vl-remove o comps))
              (setq hit T)))))
      (setq newc (append newc (list c))))
    (setq comps newc))
  comps)
(defun PdfLayout_FilterClusterGroup (items / kept comps cx cy groups ent n dsq arrs out)
  (setq kept nil)
  (foreach c (PdfLayout_ClusterComponents items 0.011)
    (if (< (length c) 3) (setq kept (append kept c))))
  (if (< (length kept) 2)
    kept
    (progn
      (setq cx (PdfLayout_Median (mapcar (quote cadr) kept)))
      (setq cy (PdfLayout_Median (mapcar (quote caddr) kept)))
      (setq groups nil)
      (foreach it kept
        (setq n (PdfLayout_LbdNumFromText (cadddr it)))
        (setq dsq (+ (* (- (cadr it) cx) (- (cadr it) cx))
                     (* (- (caddr it) cy) (- (caddr it) cy))))
        (setq ent (assoc n groups))
        (if ent
          (setq groups (subst (cons n (append (cdr ent) (list (cons dsq it)))) ent groups))
          (setq groups (append groups (list (cons n (list (cons dsq it))))))))
      (setq out nil)
      (foreach g groups
        (setq arrs (cdr g))
        (setq arrs (vl-sort arrs (quote (lambda (a b) (< (car a) (car b))))))
        (setq out (append out (list (cdr (car arrs))))))
      out)))
(defun PdfLayout_FilterCluster (items / pages pg grp out)
  (setq out nil pages nil)
  (foreach it items
    (setq pg (car it))
    (setq grp (cdr (assoc pg pages)))
    (if (not grp) (setq grp nil))
    (setq pages (append (vl-remove-if (function (lambda (g) (= (car g) pg))) pages) (list (cons pg (append grp (list it)))))))
  (foreach pg pages (setq out (append out (PdfLayout_FilterClusterGroup (cdr pg)))))
  out)

(princ "\n[PDFAUTO] 自动化层加载完成。")
(princ)
