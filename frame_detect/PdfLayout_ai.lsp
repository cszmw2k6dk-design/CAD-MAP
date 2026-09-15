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

(defun PdfLayout_AiAutoRun (/ labels doc blk txtH rad m ins i lay pt name it ang hgt autoH usedH)
  (princ "[AI] read-labels...")
  (setq labels (PdfLayout_AiReadLabels *PdfLayout_GridAutoFile* *PdfLayout_AiPage*))
  (if (not labels)
    (progn (princ "\n[AI] no labels.") nil)
    (progn
      (princ "[AI] draw...")
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
        (setq m (vl-catch-all-apply 'vla-AddMText
                  (list blk (vlax-3d-point pt) 0.0 name)))
        (if (and m (not (vl-catch-all-error-p m)))
          (progn
            (vl-catch-all-apply 'vla-put-Height (list m txtH))
            (vl-catch-all-apply 'vla-put-AttachmentPoint (list m 5))
            (if (/= rad 0.0) (vl-catch-all-apply 'vla-put-Rotation (list m rad)))
            (if lay (vl-catch-all-apply 'vla-put-Layer (list m *PdfLayout_AiLayer*)))
            (setq i (1+ i)))))
      (princ (strcat "\n[AI] 底图框 左下="
                     (rtos (car *PdfLayout_AiBoxMin*) 2 3) ","
                     (rtos (cadr *PdfLayout_AiBoxMin*) 2 3)
                     "  W=" (rtos *PdfLayout_AiBoxW* 2 3)
                     " H=" (rtos *PdfLayout_AiBoxH* 2 3)))
      (if (and autoH usedH)
        (princ (strcat "\n[AI] 支架推算字高=" (rtos autoH 2 6)
                       "  实际字高=" (rtos usedH 2 6))))
      i)))

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
