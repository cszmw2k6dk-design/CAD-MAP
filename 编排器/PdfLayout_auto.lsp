;;;=============================================================
;;; PdfLayout_auto.lsp  -  PDF 半自动流程编排器 自动化层
;;; 本文件纯 ASCII，由主程序 PdfLayout.lsp 加载后再调用（复用其已有函数）。
;;; 用法(通过 COM SendCommand 发送 LISP 表达式)：
;;;   (load "..../PdfLayout.lsp")
;;;   (load "..../PdfLayout_auto.lsp")
;;;   (PdfLayout_AutoRun "..../pdfauto.ini" "..../prog.txt")
;;;=============================================================
(vl-load-com)

;;; 进度写入(覆盖写，供外部轮询)
(defun PdfLayout_Prog (msg)
  (if *PdfLayout_ProgPath*
    (vl-catch-all-apply
      '(lambda (/ f)
        (setq f (open *PdfLayout_ProgPath* "a"))
        (if f (progn (princ msg f) (princ "\n" f) (close f))))
      nil))
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

;;; LBD 自动识别并填写标签(非交互)
(defun PdfLayout_LbdAuto (pdf xlsx pgStart pgEnd txtH labelWhere bgColor bgGap / ok autoTxt maxDim uu bbu doc actLay blk vp ptUse runOk wait nSeen)
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
      (setq i 0 nDone 0 nSeen 0)
      (PdfLayout_Prog (strcat "LBD_TOTAL " (itoa (length validItems))))
      (foreach u underlays
        (setq pgnum (1+ i))
        (setq bb (PdfLayout_GetExtentsSafeObj u))
        (if bb
          (progn
            (setq pmin (car bb) pmax (cadr bb))
            (setq bw (- (car pmax) (car pmin)))
            (setq bh (- (cadr pmax) (cadr pmin)))
            (setq pgXs nil)
            (foreach it validItems
              (if (= (car it) pgnum)
                (setq pgXs (append pgXs (list (list (cadr it) (caddr it)))))
              )
            )
            (setq minGap 1e9)
            (foreach a pgXs
              (foreach b pgXs
                (if (and (not (equal a b)) (< (abs (- (cadr a) (cadr b))) 0.02))
                  (setq minGap (min minGap (abs (- (car a) (car b)))))
                )
              )
            )
            (setq curRowFy nil curLane 0 lastRight nil)

            (foreach it validItems
              (if (= (car it) pgnum)
                (progn
                  (setq nSeen (1+ nSeen))
                  (if (= (rem nSeen 5) 0)
                    (PdfLayout_Prog (strcat "LBD_LABEL " (itoa nSeen)))
                  )
                  (setq fx (cadr it) fy (caddr it) stext (cadddr it))
                  (setq num (PdfLayout_LbdNumFromText stext))
                  (if num
                    (progn
                      (setq mx (+ (car pmin) (* fx bw)))
                      (setq my (+ (cadr pmin) (* fy bh)))
                      (setq shN (PdfLayout_LbdSheetFromText stext))
                      (setq sheetLabels (if shN (cdr (assoc shN sheetMap)) nil))
                      (setq labels (if sheetLabels (cdr (assoc num sheetLabels)) nil))
                      ;; LBD 标签只认 Excel 映射: 查不到就不画, 不用 PDF 原文兜底, 也不编造 "LBD-xx"
                      (if labels
                        (progn
                          (setq natW (* txtH (+ (* 0.8 (strlen labels)) 0.2)))
                                                    (setq lft (- mx (* natW 0.5)) rgt (+ mx (* natW 0.5)))
                                                    (if (or (not curRowFy) (> (abs (- fy curRowFy)) 0.02))
                                                      (progn (setq curRowFy fy curLane 0 lastRight nil))
                                                    )
                                                    (if (and lastRight (< lft lastRight))
                                                      (setq curLane (1+ curLane))
                                                      (setq curLane 0)
                                                    )
                                                    (setq step (* txtH 1.5))
                          (setq laneOff (if (= curLane 0) 0.0 
                            (if (= (rem curLane 2) 1)
                              (* step (/ (1+ curLane) 2))
                              (- (* step (/ curLane 2))))))
                          (setq ptIns (list mx (- my laneOff) 0.0))
                          (setq ptUse (if (and (= labelWhere "L") vp) (PdfLayout_ModelToPaper vp ptIns) ptIns))
                          (setq mObj (vl-catch-all-apply
                                'vla-AddMText
                                (list blk (vlax-3d-point ptUse)
                                      natW labels)))
                          (if (and mObj (not (vl-catch-all-error-p mObj)))
                            (progn
                              (vl-catch-all-apply 'vla-put-Height (list mObj txtH))
                              (vl-catch-all-apply 'vla-put-BackgroundFill (list mObj :vlax-true))
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillUseDrawingBackgroundColor :vlax-false)) nil)
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillColor (if bgColor bgColor 1))) nil)
                              (vl-catch-all-apply '(lambda () (vlax-put-property mObj 'BackgroundFillGapFactor (if bgGap bgGap 1.0))) nil)
                               (setq *PdfLayout_LbdBgColor* (if bgColor bgColor 1))
  (setq *PdfLayout_LbdGap* (if bgGap bgGap 1.0))
                               (vl-catch-all-apply 'PdfLayout_MTextRedWhite (list mObj))
                               (vl-catch-all-apply 'vla-put-AttachmentPoint (list mObj 5))
                               (vl-catch-all-apply 'vla-put-InsertionPoint (list mObj (vlax-3d-point ptUse)))
                              (vl-catch-all-apply 'vla-put-Color (list mObj 7))
                              (vl-catch-all-apply
                                '(lambda () (command "._DRAWORDER"
                                                     (vlax-vla-object->ename mObj) "" "_Front")) nil)
                              (setq lay (PdfLayout_EnsureLayer "LBD标签"))
                              (if (and lay (not (vl-catch-all-error-p lay)))
                                (vl-catch-all-apply 'vla-put-Layer (list mObj "LBD标签")))
                              (setq nDone (1+ nDone))
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
        (PdfLayout_Prog (strcat "LBD_PAGE " (itoa pgnum)))
      )
      (PdfLayout_Prog (strcat "LBD_DONE " (itoa nDone)))
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
          (cons "LockViewport" (= (PdfLayout_ACfg cfg "lockViewport" "0") "1"))
          (cons "NamesList" names2)
        )
      )
      (vl-catch-all-apply 'PdfLayout_Execute nil)
    )
  )
  (PdfLayout_Prog "STEP_LBD")
  (setq bgc (atoi (PdfLayout_ACfg cfg "labelBgColor" "1")))
  (setq gapc (atof (PdfLayout_ACfg cfg "labelBgGap" "1.0")))
  (setq pdf (PdfLayout_ACfg cfg "pdf" ""))
  (if (and pdf (/= pdf ""))
    (PdfLayout_LbdAuto pdf (PdfLayout_ACfg cfg "xlsx" "") (PdfLayout_ACfg cfg "pageStart" "1") (if (> (atoi (PdfLayout_ACfg cfg "importPages" "0")) 0) (PdfLayout_ACfg cfg "importPages" "0") (PdfLayout_ACfg cfg "pageEnd" "0")) (atof (PdfLayout_ACfg cfg "textHeight" "0")) (PdfLayout_ACfg cfg "labelWhere" "M") (atoi (PdfLayout_ACfg cfg "labelBgColor" "1")) (atof (PdfLayout_ACfg cfg "labelBgGap" "1.0")))
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
