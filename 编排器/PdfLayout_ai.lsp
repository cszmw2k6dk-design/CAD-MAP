;;; PdfLayout_ai.lsp - 读取识别标签(L 行)并在 CAD 里逐个绘制
;;; 用法:
;;;   (load "PdfLayout.lsp")
;;;   (load "PdfLayout_ai.lsp")
;;;   (setq *PdfLayout_GridAutoFile* "path/pdflbd_extract.txt") ; L 页号 fx fy 文字 [角度] [字高比例]
;;;   (setq *PdfLayout_AiPage* 1)
;;;   pdfgridai
;;; fx 自左、fy 自下(与 pdf_extract.py 一致); 用 PDFATTACH 底图 bbox 映射到模型空间。
;;; L 行第 6/7 列可选: 角度(度)、字高比例(占页高)。STR 号由 Python 端按支架框自动给出
;;;   (竖支架=90度, 字高比例=框短边/页高), CAD 端字高 = 字高比例 x 底图边长 x *PdfLayout_AiStrScale*。
;;; 没有这两列时回落到固定值: *PdfLayout_AiRot* 旋转、*PdfLayout_AiTextH* 字高(不影响 LBD 标签)。
;;; *PdfLayout_AiStrScale* STR 字高系数(默认 1.1, 比支架框略大); *PdfLayout_AiLayer* 图层
(vl-load-com)
(setq *PdfLayout_AiTextH* 0.15)
(setq *PdfLayout_AiRot* 0)
(setq *PdfLayout_AiStrScale* 1.1)
(setq *PdfLayout_AiStrMinH* 0.15)
(setq *PdfLayout_AiStrAutoH* nil)   ; T=STR 字高按支架框自动推算; nil=用固定字高(原行为)
(setq *PdfLayout_AiStrBgOn* T)      ; T = STR label background fill (nil = off)
(setq *PdfLayout_AiStrBgColor* 1)   ; STR background fill color (ACI)
(setq *PdfLayout_AiStrBgGap* 1.0)   ; STR background fill gap factor
(setq *PdfLayout_AiStrPrefix* "STR") ; rack label prefix (orchestrator sets it; CIR belongs to PDFGRID)
(setq *PdfLayout_AiSkipLbd* T)        ; T = 不画识别出的 LBD 标签(改由 Excel 导入)
(setq *PdfLayout_AiBoxW* 0.0)
(setq *PdfLayout_AiBoxH* 0.0)
(setq *PdfLayout_AiBoxMin* nil)
(setq *PdfLayout_AiLayer* "PDF-AUTO-NUM")

;; 保证标签图层可见: 打开、解冻、解锁, 并把颜色设为 7(黑白背景下都看得见)
(defun PdfLayout_AiEnsureVisibleLayer (lname / doc layers l)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layers (vla-get-Layers doc))
  (setq l (vl-catch-all-apply 'vla-Item (list layers lname)))
  (if (and l (not (vl-catch-all-error-p l)))
    (progn
      (vl-catch-all-apply 'vla-put-LayerOn (list l :vlax-true))
      (vl-catch-all-apply 'vla-put-Freeze (list l :vlax-false))
      (vl-catch-all-apply 'vla-put-Lock (list l :vlax-false))
      (vl-catch-all-apply 'vla-put-Color (list l 7))))
  (princ))

(defun PdfLayout_AiSplitTab (s / out tmp i c)
  (setq out nil tmp "" i 1)
  (while (<= i (strlen s))
    (setq c (substr s i 1))
    (if (= c (chr 9))
      (progn (setq out (append out (list tmp))) (setq tmp ""))
      (setq tmp (strcat tmp c)))
    (setq i (1+ i)))
  (if (/= tmp "") (setq out (append out (list tmp))))
  out)

(defun PdfLayout_AiUnderlayBox (/ doc blklist obj objName box pmin pmax a best bestArea)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq best nil bestArea 0.0)
  (setq blklist (list (vla-get-ModelSpace doc)))
  (if (= (getvar "TILEMODE") 0)
    (setq blklist (append blklist (list (vla-get-Block (vla-get-ActiveLayout doc))))))
  (foreach blk blklist
    (vlax-for obj blk
      (setq objName (strcase (vla-get-ObjectName obj)))
      (if (or (vl-string-search "UNDERLAY" objName)
              (vl-string-search "PDFREFERENCE" objName)
              (vl-string-search "RASTER" objName)
              (vl-string-search "IMAGE" objName))
        (progn
          (setq box (PdfLayout_GetExtentsSafeObj obj))
          (if box
            (progn
              (setq pmin (car box) pmax (cadr box))
              (setq a (abs (* (- (car pmax) (car pmin)) (- (cadr pmax) (cadr pmin)))))
              (if (> a bestArea)
                (setq bestArea a best (list pmin pmax)))))))))
  best)

;; 返回 ((文字 x y 角度 字高比例) ...) 模型空间坐标
(defun PdfLayout_AiReadLabels (path page / f line parts box pmin pmax dx dy fx fy pgs out ang hgt)
  (setq box (PdfLayout_AiUnderlayBox))
  (if (not box)
    (progn (princ "\n[AI] no underlay.") nil)
    (progn
      (setq pmin (car box) pmax (cadr box))
      (setq dx (- (car pmax) (car pmin)) dy (- (cadr pmax) (cadr pmin)))
      (setq *PdfLayout_AiBoxW* dx *PdfLayout_AiBoxH* dy)
      (setq *PdfLayout_AiBoxMin* pmin)
      (setq pgs (if (numberp page) (itoa (fix page)) "1"))
      (setq out nil)
      (setq f (open path "r"))
      (while (and f (setq line (read-line f)))
        (setq parts (PdfLayout_AiSplitTab line))
        (if (and (> (length parts) 4) (= (car parts) "L") (= (nth 1 parts) pgs))
          (progn
            (setq fx (atof (nth 2 parts)) fy (atof (nth 3 parts)))
            (setq ang (if (> (length parts) 5) (atof (nth 5 parts)) *PdfLayout_AiRot*))
            (setq hgt (if (and (> (length parts) 6) (> (atof (nth 6 parts)) 0.0))
                        (atof (nth 6 parts)) nil))
            (if (> (strlen (nth 4 parts)) 0)
              (setq out (append out (list (list (nth 4 parts)
                                  (+ (car pmin) (* fx dx))
                                  (+ (cadr pmin) (* fy dy))
                                  ang hgt))))))))
      (if f (close f))
      out)))

;; 把对象平移, 使其包围盒几何中心落在 pt(识别框中心) 上 —— 不依赖各 CAD 对 MText 对齐点的处理差异
(defun PdfLayout_AiCenterAt (obj pt / r p1 p2 c v1 v2)
  (setq p1 nil p2 nil)
  (setq r (vl-catch-all-apply 'vla-GetBoundingBox (list obj 'p1 'p2)))
  (if (not (vl-catch-all-error-p r))
    (progn
      ;; ZWCAD returns a safearray here, AutoCAD may return a variant - accept both.
      (setq v1 (vl-catch-all-apply 'vlax-variant-value (list p1)))
      (if (vl-catch-all-error-p v1) (setq v1 p1))
      (setq v2 (vl-catch-all-apply 'vlax-variant-value (list p2)))
      (if (vl-catch-all-error-p v2) (setq v2 p2))
      (setq p1 (vl-catch-all-apply 'vlax-safearray->list (list v1)))
      (setq p2 (vl-catch-all-apply 'vlax-safearray->list (list v2)))
      (if (or (vl-catch-all-error-p p1) (vl-catch-all-error-p p2)) (setq p1 nil p2 nil))
      (if (and (listp p1) (listp p2) (= (length p1) 2) (= (length p2) 2))
        (progn
          (setq c (list (* 0.5 (+ (car p1) (car p2))) (* 0.5 (+ (cadr p1) (cadr p2))) 0.0))
          (if (or (> (abs (- (car c) (car pt))) 1e-9)
                  (> (abs (- (cadr c) (cadr pt))) 1e-9))
            (vl-catch-all-apply 'vla-Move
              (list obj (vlax-3d-point c) (vlax-3d-point (list (car pt) (cadr pt) 0.0))))
          )
        )
      )
    )
  )
  (princ)
)

;; 读某一页的标签, 底图框由外面传进来(多页模式要按每张底图自己的框换算坐标)
(defun PdfLayout_AiReadLabelsIn (path page box / f line parts pmin pmax dx dy fx fy pgs out ang hgt)
  (if (not box)
    (progn (princ "\n[AI] no underlay.") nil)
    (progn
      (setq pmin (car box) pmax (cadr box))
      (setq dx (- (car pmax) (car pmin)) dy (- (cadr pmax) (cadr pmin)))
      (setq *PdfLayout_AiBoxW* dx *PdfLayout_AiBoxH* dy)
      (setq *PdfLayout_AiBoxMin* pmin)
      (setq pgs (if (numberp page) (itoa (fix page)) "1"))
      (setq out nil)
      (setq f (open path "r"))
      (while (and f (setq line (read-line f)))
        (setq parts (PdfLayout_AiSplitTab line))
        (if (and (> (length parts) 4) (= (car parts) "L") (= (nth 1 parts) pgs))
          (progn
            (setq fx (atof (nth 2 parts)) fy (atof (nth 3 parts)))
            (setq ang (if (> (length parts) 5) (atof (nth 5 parts)) *PdfLayout_AiRot*))
            (setq hgt (if (and (> (length parts) 6) (> (atof (nth 6 parts)) 0.0))
                        (atof (nth 6 parts)) nil))
            (if (> (strlen (nth 4 parts)) 0)
              (setq out (append out (list (list (nth 4 parts)
                                  (+ (car pmin) (* fx dx))
                                  (+ (cadr pmin) (* fy dy))
                                  ang hgt))))))))
      (if f (close f))
      out)))

;; 画一批标签(坐标已经是模型空间坐标), 返回实际画了几个
(defun PdfLayout_AiDrawLabels (labels / doc blk lay txtH rad m i pt name it ang hgt autoH usedH oldBg oldGap)
  (if (not labels)
    nil
    (progn
      (princ "[AI] draw...")
      (vl-catch-all-apply 'PdfLayout_Prog
        (list (strcat "AI_TOTAL " (itoa (length labels)))))
      (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
      ;; 标签坐标是模型空间坐标(由底图包围框换算), 一律写进模型空间,
      ;; 不管当前停留在模型标签页还是布局标签页, 避免落进纸空间左下角。
      (setq blk (vla-get-ModelSpace doc))
      (setq lay (PdfLayout_EnsureLayer *PdfLayout_AiLayer*))
      (PdfLayout_AiEnsureVisibleLayer *PdfLayout_AiLayer*)
      (if (not (numberp *PdfLayout_AiStrScale*))
        (setq *PdfLayout_AiStrScale* 1.1))
      (if (not (numberp *PdfLayout_AiStrMinH*))
        (setq *PdfLayout_AiStrMinH* 0.15))
      (setq i 0 autoH nil usedH nil)
      (foreach it labels
        (setq name (car it) pt (list (nth 1 it) (nth 2 it)))
        (setq ang (if (numberp (nth 3 it)) (nth 3 it) *PdfLayout_AiRot*))
        (setq hgt (nth 4 it))
        ;; 字高: 默认用固定字高 *PdfLayout_AiTextH*(原行为)。
        ;;       把 *PdfLayout_AiStrAutoH* 设为 T 时才按支架框推算(第7列 x 底图高 x 系数, 不小于下限)
        (setq txtH
              (if (and *PdfLayout_AiStrAutoH* hgt (numberp hgt) (> hgt 0.0) (> *PdfLayout_AiBoxH* 0.0))
                (progn
                  (setq autoH (* hgt *PdfLayout_AiBoxH* *PdfLayout_AiStrScale*))
                  (if (> autoH *PdfLayout_AiStrMinH*) autoH *PdfLayout_AiStrMinH*))
                (if (and (numberp *PdfLayout_AiTextH*) (> *PdfLayout_AiTextH* 0))
                  *PdfLayout_AiTextH* 0.15)))
        (if autoH (setq usedH txtH))
        (setq rad (* ang (/ pi 180.0)))
        ;; LBD 标签交给 Excel 导入(PdfLayout_auto.lsp)去画, AI 这边只画 STR 号;
        ;; 要恢复 AI 画 LBD, 把 *PdfLayout_AiSkipLbd* 设为 nil 即可。
        (setq m (if (and *PdfLayout_AiSkipLbd* (wcmatch (strcase name) "*LBD*"))
                  nil
                  (vl-catch-all-apply 'vla-AddMText
                    (list blk (vlax-3d-point pt) 0.0 name))))
        (if (and m (not (vl-catch-all-error-p m)))
          (progn
            (vl-catch-all-apply 'vla-put-Height (list m txtH))
            (vl-catch-all-apply 'vla-put-AttachmentPoint (list m 5))
            (if (/= rad 0.0) (vl-catch-all-apply 'vla-put-Rotation (list m rad)))
            (if lay (vl-catch-all-apply 'vla-put-Layer (list m *PdfLayout_AiLayer*)))
            ;; STR 背景填充: 先走 ActiveX, 再用 DXF(兼容 ZWCAD 无 BackgroundFillColor 接口)
            (if (and *PdfLayout_AiStrBgOn* (wcmatch (strcase name) (strcat (strcase (if *PdfLayout_AiStrPrefix* *PdfLayout_AiStrPrefix* "STR")) "*")))
              (progn
                (vl-catch-all-apply 'vla-put-BackgroundFill (list m :vlax-true))
                (vl-catch-all-apply '(lambda () (vlax-put-property m 'BackgroundFillUseDrawingBackgroundColor :vlax-false)) nil)
                (vl-catch-all-apply '(lambda () (vlax-put-property m 'BackgroundFillColor (if *PdfLayout_AiStrBgColor* *PdfLayout_AiStrBgColor* 1))) nil)
                (vl-catch-all-apply '(lambda () (vlax-put-property m 'BackgroundFillGapFactor (if *PdfLayout_AiStrBgGap* *PdfLayout_AiStrBgGap* 1.0))) nil)
                (setq oldBg *PdfLayout_LbdBgColor* oldGap *PdfLayout_LbdGap*)
                (setq *PdfLayout_LbdBgColor* (if *PdfLayout_AiStrBgColor* *PdfLayout_AiStrBgColor* 1))
                (setq *PdfLayout_LbdGap* (if *PdfLayout_AiStrBgGap* *PdfLayout_AiStrBgGap* 1.0))
                (vl-catch-all-apply 'PdfLayout_MTextRedWhite (list m))
                (setq *PdfLayout_LbdBgColor* oldBg *PdfLayout_LbdGap* oldGap)
              )
            )
            ;; 标签几何中心 = 识别框几何中心:
            ;; 先按「中点对齐(5) + 插入点=目标点」放 —— 和 LBD 标签同一套，ZWCAD 里稳；
            (vl-catch-all-apply 'vla-put-AttachmentPoint (list m 5))
            (vl-catch-all-apply 'vla-put-InsertionPoint (list m (vlax-3d-point pt)))
            ;; 只有不旋转的文字才再用包围盒校一次；旋转过的文字包围盒在 ZWCAD 里不准，
            ;; 二次校正会把整排号推偏（实测往右偏约一个支架宽）。
            (if (= ang 0.0)
              (vl-catch-all-apply 'PdfLayout_AiCenterAt (list m pt)))
            (setq i (1+ i))
            (if (= (rem i 5) 0)
              (vl-catch-all-apply 'PdfLayout_Prog
                (list (strcat "AI_LABEL " (itoa i)))))
          )))
      (if (and autoH usedH)
        (princ (strcat "\n[AI] 支架推算字高=" (rtos autoH 2 6)
                       "  实际字高=" (rtos usedH 2 6))))
      i)))

;; 模型空间里的底图类对象（PDF 引用 / DWG 底图 / 光栅图 / 图片），按创建顺序
(defun PdfLayout_AiUnderlays (/ doc ms out obj nm)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq out nil)
  (vlax-for obj ms
    (setq nm (strcase (vla-get-ObjectName obj)))
    (if (or (vl-string-search "UNDERLAY" nm)
            (vl-string-search "PDFREFERENCE" nm)
            (vl-string-search "RASTER" nm)
            (vl-string-search "IMAGE" nm))
      (setq out (append out (list obj)))
    )
  )
  out
)

(defun PdfLayout_AiAutoRunAll (/ underlays u i box labs total nU)
  ;; 逐页画 STR 号: 第 i 张底图 = 提取文件里的第 i 页(和布局、底图顺序一致)
  (setq underlays (PdfLayout_AiUnderlays))
  (if (not underlays)
    (progn (princ "\n[AI] no underlay.") nil)
    (progn
      (setq nU (length underlays) i 0 total 0)
      (foreach u underlays
        (setq box (PdfLayout_GetExtentsSafeObj u))
        (if box
          (progn
            (setq labs (PdfLayout_AiReadLabelsIn *PdfLayout_GridAutoFile* (1+ i) box))
            (if labs (setq total (+ total (PdfLayout_AiDrawLabels labs))))
          )
        )
        (setq i (1+ i))
      )
      (vl-catch-all-apply 'PdfLayout_Prog (list (strcat "AI_DONE " (itoa total))))
      (princ (strcat "\n[AI] 逐页画 STR 号: 底图 " (itoa nU) " 张, 共画 " (itoa total) " 个。"))
      total
    )
  )
)

(defun PdfLayout_AiAutoRun (/ labels i)
  (princ "[AI] read-labels...")
  (if (and (numberp *PdfLayout_AiPage*) (> *PdfLayout_AiPage* 0))
    ;; 单页模式(老行为): 只画 *PdfLayout_AiPage* 这一页, 底图用面积最大的那张
    (progn
      (setq labels (PdfLayout_AiReadLabels *PdfLayout_GridAutoFile* *PdfLayout_AiPage*))
      (if (not labels)
        (progn (princ "\n[AI] no labels.") nil)
        (progn
          (setq i (PdfLayout_AiDrawLabels labels))
          (princ (strcat "\n[AI] 底图框 左下="
                         (rtos (car *PdfLayout_AiBoxMin*) 2 3) ","
                         (rtos (cadr *PdfLayout_AiBoxMin*) 2 3)
                         "  W=" (rtos *PdfLayout_AiBoxW* 2 3)
                         " H=" (rtos *PdfLayout_AiBoxH* 2 3)))
          i)))
    ;; *PdfLayout_AiPage* = 0/nil: 逐页画(编排器默认走这条)
    (PdfLayout_AiAutoRunAll))
)

(defun c:pdfgridai (/ r)
  (PdfLayout_LoadSettings)
  (setq r (vl-catch-all-apply 'PdfLayout_AiAutoRun nil))
  (if (vl-catch-all-error-p r)
    (princ (strcat "\n[AI] ERR: " (vl-catch-all-error-message r)))
    (if (numberp r)
      (princ (strcat "\n[AI] 已绘制 " (itoa (fix r)) " 个标签。"))
      (princ "\n[AI] 这次没有可画的标签（STR 号）。")
    ))
  (princ)
)

;; 诊断: 打印图层状态和底图框
(defun c:pdfgridaiinfo (/ ly)
  (setq ly (tblsearch "LAYER" *PdfLayout_AiLayer*))
  (princ (strcat "\n[AI] 图层=" *PdfLayout_AiLayer*
                 " 色号=" (vl-princ-to-string (cdr (assoc 62 ly)))
                 "(负=关闭) 标志70=" (vl-princ-to-string (cdr (assoc 70 ly)))
                 "(1=冻结 4=锁定)"))
  (princ (strcat "\n[AI] 底图框=" (vl-princ-to-string (PdfLayout_AiUnderlayBox))))
  (princ))

;; 缩放到最新一个标签, 便于确认位置和大小
(defun c:pdfgridaizoom (/ s e n)
  (setq s (ssget "_X" '((8 . "PDF-AUTO-NUM"))))
  (if (not s)
    (princ "\n[AI] 没有标签(图层 PDF-AUTO-NUM 为空)。")
    (progn
      (setq n (1- (sslength s)))
      (setq e (entget (ssname s n)))
      (princ (strcat "\n[AI] 数量=" (itoa (sslength s))
                     " 最后一个: " (cdr (assoc 1 e))
                     " 字高=" (rtos (cdr (assoc 40 e)) 2 5)
                     " 位置=" (rtos (car (cdr (assoc 10 e))) 2 3) ","
                     (rtos (cadr (cdr (assoc 10 e))) 2 3)))
      (command "_.ZOOM" "_O" (ssname s n) "")))
  (princ))
