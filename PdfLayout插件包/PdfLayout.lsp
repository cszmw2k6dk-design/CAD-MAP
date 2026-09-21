;;;=============================================================
;;; MAP文件工具箱 PdfLayout.lsp  v2.16
;;;-------------------------------------------------------------
;;; 功能：识别模型空间已有图纸(PDFATTACH参考底图导入并摆放) →
;;;       复制模板布局(含图框) → 按可配置规则自动命名 →
;;;       每个布局视口自动对准模型空间对应图纸并锁定
;;; 命令：PDFLAYOUT    - 对话框版（需 PdfLayout.dcl）
;;; 适用：AutoCAD 2018+
;;;=============================================================
(vl-load-com)

;;;---- PDFAUTO 自动模式: 可切换告警(自动写进度/普通弹窗) ----
(setq *PdfLayout_NoAlert* nil)
(setq *PdfLayout_AutoErr* nil)
(defun PdfLayout_Alert (msg)
  (if *PdfLayout_NoAlert*
    (progn (setq *PdfLayout_AutoErr* msg)
           (vl-catch-all-apply (quote PdfLayout_Prog) (list (strcat "ERROR: " msg))))
    (PdfLayout_Alert msg))
)

;;;-------------------------------------------------------------
;;; 记录LSP文件所在路径（用于定位DCL）
;;;-------------------------------------------------------------
(defun PdfLayout_GetLspDir (/ lspDir)
  ;; 中望CAD的 *load-truename* 为 nil，无法获取 LSP 自身目录；
  ;; 不要退回 DWGPREFIX（会跟随当前图纸目录变化），取不到就返回 nil，
  ;; 由 SettingsPathLsp 改用固定的临时目录，保证记忆设置不随图纸丢失
  (setq lspDir nil)
  (if (and *load-truename* (/= *load-truename* ""))
    (setq lspDir (vl-filename-directory *load-truename*))
  )
  lspDir
)

(setq *PdfLayout_LspDir* (PdfLayout_GetLspDir))
(if *PdfLayout_LspDir*
  (princ (strcat "\n[调试] LSP目录: " *PdfLayout_LspDir*))
  (princ "\n[调试] LSP目录: (空)")
)
(princ (strcat "\n[调试] 临时目录: " (getvar "TEMPPREFIX")))

;;;-------------------------------------------------------------
;;; 全局状态与错误处理
;;;-------------------------------------------------------------
(setq *PdfLayout_ViewInset* 1.0)    ; 对准视口时图纸占视口的比例：1.0=铺满、0.9=占 90%（编排器每次都会用界面「区域对准留白」填的数覆盖它）
(setq *PdfLayout_LspVersion* "2026-09-17")   ; 插件版本（编排器只看能力标记，这行给人看）
;; 能力标记：编排器发命令前读一眼 —— 老插件没有这行，「区域对准留白」改了也不生效。
(setq *PdfLayout_LspFeatures* "viewinset")
(setq *PdfLayout_Running* nil)
(setq *PdfLayout_UndoOn* nil)
(setq *PdfLayout_CreatedLayouts* nil)
(setq *PdfLayout_OldError* *error*)
(setq *PdfLayout_Debug* nil)
(setq *PdfLayout_DclWritten* nil)
(setq *PdfLayout_PreviewPairs* nil)
(setq *PdfLayout_PreviewNames* nil)
(setq *PdfLayout_PreviewLbds* nil)
(setq *PdfLayout_LbdRows* nil)
(setq *PdfLayout_PreviewPrefix* "STR")
(setq *PdfLayout_PreviewStart* 1)
(setq *PdfLayout_PreviewDigits* 2)
(setq *PdfLayout_PreviewOrder* "1")
(setq *PdfLayout_UnderlayOrder* "2")
(setq *PdfLayout_PreviewSrc* "1")
(setq *PdfLayout_PreviewFilePath* "")
(setq *PdfLayout_PreviewResult* 0)
(setq *PdfLayout_PreviewBgMode* "0")
(setq *PdfLayout_PreviewBgColor* 7)
(setq *PdfLayout_PreviewBgScale* 1.5)
(setq *PdfLayout_RowTol* 10)
(setq *PdfLayout_Profiles* nil)
(setq *PdfLayout_CurrentProfile* "")
(setq *PdfLayout_IniPairs* nil)
(setq *PdfLayout_PythonPath* "")
(setq *PdfLayout_LbdTextHeight* 0.15)
(setq *PdfLayout_LbdBgColor* 1)
(setq *PdfLayout_LbdGap* 1.0)
(setq *PdfLayout_LbdBgList* (list (cons "红" 1) (cons "黄" 2) (cons "绿" 3) (cons "青" 4) (cons "蓝" 5) (cons "洋红" 6) (cons "白" 7) (cons "灰" 8)))
(setq *PdfLayout_ExcludeRect* nil)
(setq *PdfLayout_OrderPreviewEnts* nil)
(setq *PdfLayout_GridRows* 4)
(setq *PdfLayout_GridCols* 5)
(setq *PdfLayout_GridRowSp* 10.0)
(setq *PdfLayout_GridColSp* 20.0)
(setq *PdfLayout_GridStart* nil)
(setq *PdfLayout_GridP1* nil)
(setq *PdfLayout_GridP2* nil)
(setq *PdfLayout_GridExtX* 0.0)
(setq *PdfLayout_GridExtY* 0.0)
(setq *PdfLayout_GridH* 1.7)
(setq *PdfLayout_GridHRatio* 0.3)
(setq *PdfLayout_GridGeom* "1")
(setq *PdfLayout_GridRot* 0)
(setq *PdfLayout_GridBg* "fill")
(setq *PdfLayout_GridBgColor* 1)
(setq *PdfLayout_GridBgRGB* 255)
(setq *PdfLayout_GridTxtColor* 7)
(setq *PdfLayout_GridTxtRGB* 16777215)
(setq *PdfLayout_GridTxtTrue* T)
(setq *PdfLayout_GridBgScale* 1.0)
(setq *PdfLayout_GridSrc* "auto")
(setq *PdfLayout_GridPrefix* "CIR")
(setq *PdfLayout_GridStartN* 1)
(setq *PdfLayout_GridDigits* 2)
(setq *PdfLayout_GridFile* "")
(setq *PdfLayout_GridXlsx* "")
(setq *PdfLayout_GridSheets* nil)
(setq *PdfLayout_GridSheetNames* nil)
(setq *PdfLayout_GridSheetFull* nil)
(setq *PdfLayout_GridSheetSel* "")
(setq *PdfLayout_GridNames* nil)
(setq *PdfLayout_GridPairs* nil)
(setq *PdfLayout_GridSelPairs* nil)
(setq *PdfLayout_GridResult* 0)
(setq *PdfLayout_GridProfiles* nil)
(setq *PdfLayout_GridProfile* "")
(setq *PdfLayout_GridHMode* "auto")
(setq *PdfLayout_GridMT* 0.0)
(setq *PdfLayout_GridMB* 0.0)
(setq *PdfLayout_GridML* 0.0)
(setq *PdfLayout_GridMR* 0.0)
(setq *PdfLayout_GridFirstX* 0.0)
(setq *PdfLayout_GridFirstY* 0.0)
(setq *PdfLayout_GridColDir* 1)
(setq *PdfLayout_GridRowDir* -1)
(setq *PdfLayout_HubAction* "NONE")
(setq *PdfLayout_DlgPdf* "")
(setq *PdfLayout_DlgXlsx* "")
(setq *PdfLayout_DlgPage* "0")
(setq *PdfLayout_DlgH* 0.05)
(setq *PdfLayout_DlgWhere* "M")
(setq *PdfLayout_DlgMode* "auto")
(setq *PdfLayout_DlgOrder* "2")
(setq *PdfLayout_DlgExcl* nil)
(setq *PdfLayout_LbdSelPairs* nil)
(setq *PdfLayout_ExactOrder* nil)
(setq *PdfLayout_LbdSelNames* nil)
(setq *PdfLayout_LbdSelMatches* nil)
(setq *PdfLayout_LbdManualLabels* nil)
(setq *PdfLayout_LastPdfFile* "")
(setq *PdfLayout_LastNamesXlsx* "")
(setq *PdfLayout_NamesXlsxList* nil)
(setq *PdfLayout_LayRule* "")
(setq *PdfLayout_LayLetters* "")
(setq *PdfLayout_LayPerGroup* 6)
(setq *PdfLayout_LayGStart* 1)
(setq *PdfLayout_ArrangeOnly* nil)
(setq *PdfLayout_ArrangeOnlyName* nil)
(setq *PdfLayout_SavedFd* nil)
(setq *PdfLayout_DclLines* (list
"// PdfLayout.dcl"
"// MAP文件工具箱 v2.16 - 对话框定义"
""
"PdfLayout : dialog {"
"  label = \"MAP文件工具箱 v2.16\";"
"  width = 62;"
""
"  : boxed_column {"
"    label = \"图纸识别（竖线标记模式）\";"
"    : row {"
"      : popup_list {"
"        label = \"竖线块名:\";"
"        key = \"marker_name\";"
"        edit_width = 22;"
"      }"
"    }"
"    : button {"
"      label = \"仅自动排序已导入的PDF(不建布局)\";"
"      key = \"btn_arrange\";"
"      width = 32;"
"    }"
"    : text {"
"      key = \"found_info\";"
"      label = \" \";"
"      width = 55;"
"    }"
"    : text {"
"      label = \"提示: 先用 PDFATTACH 导入PDF，再运行本命令自动排列底图并创建布局；竖线标记块默认名pdf\";"
"      width = 55;"
"    }"
"  }"
))

(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
""
"  : boxed_column {"
"    label = \"布局\";"
"    : popup_list {"
"      label = \"模板布局(含图框):\";"
"      key = \"tmpl_layout\";"
"      edit_width = 26;"
"    }"
"    : row {"
"      : edit_box { label = \"布局名来自Excel分表:\"; key = \"names_xlsx\"; edit_width = 16; }"
"      : button { label = \"选择...\"; key = \"btn_names_xlsx\"; width = 10; }"
"    }"
"    : text { label = \"填Excel后按分表顺序命名布局(数量=分表数)；留空用下方规则\"; width = 55; }"
"    : row {"
"      : edit_box {"
"        label = \"复制数量:\";"
"        key = \"count\";"
"        edit_width = 6;"
"        value = \"0\";"
"        allow_accept = true;"
"      }"
"      : toggle {"
"        label = \"覆盖同名布局\";"
"        key = \"overwrite\";"
"        value = \"0\";"
)))

(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"      }"
"    }"
"  }"
""
"  : boxed_column {"
"    label = \"命名规则\";"
"    : edit_box {"
"      label = \"规则:\";"
"      key = \"rule\";"
"      edit_width = 34;"
"      value = \"INV{G2}{L}{N2}\";"
"      allow_accept = true;"
"    }"
"    : row {"
"      : edit_box {"
"        label = \"字母列表:\";"
"        key = \"letters\";"
"        edit_width = 10;"
"        value = \"AB\";"
"        allow_accept = true;"
)))

(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"      }"
"      : edit_box {"
"        label = \"每组张数:\";"
"        key = \"per_group\";"
"        edit_width = 5;"
"        value = \"6\";"
"        allow_accept = true;"
"      }"
"      : edit_box {"
"        label = \"编号起始:\";"
"        key = \"g_start\";"
"        edit_width = 5;"
"        value = \"1\";"
"        allow_accept = true;"
"      }"
"    }"
"    : text {"
"      label = \"占位符: {G2}=编号(2位)  {L}=字母循环  {N2}=组内序号(2位)\";"
"      width = 58;"
"    }"
)))

(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"    : text {"
"      label = \"例: INV{G2}{L}{N2} + 字母AB + 每组6张 -> INV01A01..A06, INV01B01..B06, INV02A01..\";"
"      width = 58;"
"    }"
"    : list_box {"
"      label = \"名称预览:\";"
"      key = \"preview\";"
"      height = 9;"
"    }"
"  }"
""
"  : boxed_column {"
"    label = \"视口\";"
"    : edit_box {"
"      label = \"模板无视口时按边距创建(mm):\";"
"      key = \"margin\";"
"      edit_width = 6;"
"      value = \"5\";"
"      allow_accept = true;"
"    }"
"    : toggle {"
"      label = \"锁定视口显示(防误缩放)\";"
"      key = \"lock_vp\";"
"      value = \"0\";"
"    }"
"  }"
""
"  ok_cancel;"
"}"
)))



(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"PdfGrid : dialog {"
"  label = \"PDF网格批量生成(PDFGRID)\";"
"  : row {"
"    : column {"
"  : boxed_column {"
"    label = \"方案预设\";"
"    : row {"
"      : popup_list { label = \"方案:\"; key = \"g_prof\"; edit_width = 18; }"
"      : edit_box { label = \"方案名:\"; key = \"g_profname\"; edit_width = 10; }"
"    }"
"    : row {"
"      : button { label = \"保存为方案\"; key = \"g_saveprof\"; width = 12; }"
"      : button { label = \"删除方案\"; key = \"g_delprof\"; width = 12; }"
"    }"
"  }"
"  : boxed_column {"
"    label = \"网格\";"
"    : row {"
"      : edit_box { label = \"行数:\"; key = \"g_rows\"; edit_width = 5; value = \"4\"; }"
"      : edit_box { label = \"列数:\"; key = \"g_cols\"; edit_width = 5; value = \"5\"; }"
"    }"
"    : row {"
"      : edit_box { label = \"行距:\"; key = \"g_rowsp\"; edit_width = 8; value = \"10\"; }"
"      : edit_box { label = \"列距:\"; key = \"g_colsp\"; edit_width = 8; value = \"20\"; }"
"    }"
"    : row {"
"      : edit_box { label = \"上边距:\"; key = \"g_mt\"; edit_width = 6; value = \"0\"; }"
"      : edit_box { label = \"下边距:\"; key = \"g_mb\"; edit_width = 6; value = \"0\"; }"
"      : edit_box { label = \"左边距:\"; key = \"g_ml\"; edit_width = 6; value = \"0\"; }"
"      : edit_box { label = \"右边距:\"; key = \"g_mr\"; edit_width = 6; value = \"0\"; }"
"    }"
"    : radio_row {"
"      label = \"几何:\";"
"      : radio_button { label = \"按范围自动算(比例)\"; key = \"g_geoa\"; value = \"1\"; }"
"      : radio_button { label = \"固定绝对参数\"; key = \"g_geof\"; }"
"    }"
"    : row {"
"      : edit_box { label = \"字高比例(自动模式):\"; key = \"g_hratio\"; edit_width = 6; value = \"0.3\"; }"
"      : text { label = \"(字高=min(行距,列距)x比例)\"; }"
"    : radio_row {"
"      label = \"字高:\";"
"      : radio_button { label = \"按比例自动\"; key = \"g_hauto\"; value = \"1\"; }"
"      : radio_button { label = \"直接输入\"; key = \"g_hmanual\"; }"
"    }"
"    }"
"    : text { label = \"起点/范围: 0, 0（命令时点取/框选；文字按几何中心对齐，边距自范围边起算）\"; key = \"g_start\"; }"
"  }"
"  : boxed_column {"
"    label = \"文字\";"
"    : row {"
"      : edit_box { label = \"字高:\"; key = \"g_h\"; edit_width = 8; value = \"0.5\"; }"
"      : popup_list { label = \"旋转:\"; key = \"g_rot\"; edit_width = 10; }"
"    }"
"    : radio_row {"
"      label = \"背景:\";"
"      : radio_button { label = \"无\"; key = \"g_bgnone\"; }"
"      : radio_button { label = \"填充\"; key = \"g_bgon\"; value = \"1\"; }"
"    }"
"    : row {"
"    : row {"
"      : popup_list { label = \"背景色:\"; key = \"g_bgcolor\"; edit_width = 12; }"
"      : edit_box { label = \"自定义:\"; key = \"g_bgaci\"; edit_width = 4; value = \"1\"; }"
"      : edit_box { label = \"背景缩放%:\"; key = \"g_bgscale\"; edit_width = 5; value = \"100\"; }"
"    }"
"    : row {"
"      : popup_list { label = \"文字色:\"; key = \"g_txtcolor\"; edit_width = 12; }"
"      : edit_box { label = \"自定义:\"; key = \"g_txtaci\"; edit_width = 4; value = \"7\"; }"
"    }"
"    }"
"  }"
"  : boxed_radio_column {"
"    label = \"命名来源\";"
"    : radio_button { label = \"自动命名(前缀+编号)\"; key = \"g_srcauto\"; value = \"1\"; }"
""
"    : radio_button { label = \"从Excel导入(按分表)\"; key = \"g_srcxlsx\"; }"
"  }"
"  : boxed_column {"
"    label = \"自动命名(前缀+编号)[已停用]:\";"
"    : row {"
"      : edit_box { label = \"前缀:\"; key = \"g_prefix\"; edit_width = 8; value = \"CIR\"; }"
"      : edit_box { label = \"起始:\"; key = \"g_startn\"; edit_width = 5; value = \"1\"; }"
"      : edit_box { label = \"位数(0=不补零):\"; key = \"g_digits\"; edit_width = 4; value = \"2\"; }"
"    }"
"  }"
""
"  : boxed_column {"
"    label = \"从Excel导入(分表名=布局名):\";"
"    : row {"
"      : edit_box { label = \"Excel:\"; key = \"g_filexlsx\"; edit_width = 20; }"
"      : button { label = \"选择...\"; key = \"g_btnxlsx\"; width = 10; }"
"    }"
"    : row {"
"      : popup_list { label = \"分表:\"; key = \"g_xlsxsheet\"; edit_width = 30; }"
"      : button { label = \"重读\"; key = \"g_btnxlsxre\"; width = 10; }"
"    }"
"  }"
"  : boxed_radio_column {"
"    label = \"排序方式\";"
"    : radio_button { label = \"1 列优先: 左→右列、列内上→下\"; key = \"ord1\"; value = \"1\"; }"
"    : radio_button { label = \"2 行优先: 上→下行、行内左→右\"; key = \"ord2\"; }"
"    : radio_button { label = \"3 列优先: 右→左列、列内上→下\"; key = \"ord3\"; }"
"    : radio_button { label = \"4 行优先: 下→上行、行内左→右\"; key = \"ord4\"; }"
"    : radio_button { label = \"5 列优先: 左→右列、列内下→上\"; key = \"ord5\"; }"
"    : radio_button { label = \"6 列优先: 右→左列、列内下→上\"; key = \"ord6\"; }"
"    : radio_button { label = \"7 行优先: 上→下行、行内右→左\"; key = \"ord7\"; }"
"    : radio_button { label = \"8 行优先: 下→上行、行内右→左\"; key = \"ord8\"; }"
"  }"
"    }"
"    : column {"
"  : boxed_column {"
"    label = \"预览(左=顺序 右=名称):\";"
"    : row {"
"      : list_box { key = \"g_grid\"; height = 8; width = 26; }"
"      : list_box { key = \"g_names\"; height = 8; width = 22; }"
"    }"
"  }"
"    }"
"  }"
"  : text { key = \"g_info\"; label = \" \"; width = 60; }"
"  ok_cancel;"
"}"
)))

(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"PdfHub : dialog {"
"  label = \"PDF 布局工具箱\";"
"  : boxed_column {"
"    label = \"功能\";"
"    : button { label = \"1. PDF底图 LBD 识别填标签\"; key = \"hub_lbd\"; }"
"    : button { label = \"2. 批量生成网格文字\"; key = \"hub_grid\"; }"
"    : button { label = \"3. 图纸识别 / 布局管理\"; key = \"hub_layout\"; }"
"  }"
"  : boxed_column {"
"    label = \"维护\";"
"    : row {"
"      : button { label = \"Python 路径\"; key = \"hub_pypath\"; }"
"      : button { label = \"默认字高\"; key = \"hub_lbdh\"; }"
"    }"
"    : row {"
"      : button { label = \"调试开关\"; key = \"hub_debug\"; }"
"      : button { label = \"诊断\"; key = \"hub_diag\"; }"
"      : button { label = \"背景遮罩诊断\"; key = \"hub_mtdiag\"; }"
"      : button { label = \"自检\"; key = \"hub_test\"; }"
"    }"
"  }"
"  : text { key = \"hub_info\"; label = \"提示: 命令行仍可直接输入原命令\"; width = 60; }"
"  ok_cancel;"
"}"
)))
(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"PdfLbd : dialog {"
"  label = \"PDF底图 LBD 识别\";"
"  : boxed_column {"
"    label = \"文件\";"
"    : row {"
"      : edit_box { label = \"PDF底图原始PDF:\"; key = \"lbd_pdf\"; edit_width = 34; }"
"      : button { label = \"选择...\"; key = \"btn_pdf\"; width = 10; }"
"    }"
"    : row {"
"      : edit_box { label = \"标签Excel(分表名=布局名,可选):\"; key = \"lbd_xlsx\"; edit_width = 34; }"
"      : button { label = \"选择...\"; key = \"btn_xlsx\"; width = 10; }"
"    }"
"  }"
"  : boxed_column {"
"    label = \"识别选项\";"
"    : edit_box { label = \"只识别第几页(0=全部):\"; key = \"lbd_page\"; edit_width = 5; value = \"0\"; }"
"    : radio_row {"
"      label = \"标签写入位置:\";"
"      : radio_button { label = \"M模型空间\"; key = \"lbd_m\"; value = \"1\"; }"
"      : radio_button { label = \"L当前布局\"; key = \"lbd_l\"; }"
"      : radio_button { label = \"B两者\"; key = \"lbd_b\"; }"
"    }"
"    : edit_box { label = \"标签字高(模型单位):\"; key = \"lbd_h\"; edit_width = 6; value = \"0.15\"; }"
"    : popup_list { label = \"标签背景色(ACI):\"; key = \"lbd_bg\"; width = 8; }"
"    : toggle { label = \"框选排除干扰区域(右下角细节图等)\"; key = \"lbd_excl\"; value = \"0\"; }"
"  }"
"  ok_cancel;"
"}"
)))


(setq *PdfLayout_DclLines* (append *PdfLayout_DclLines* (list
"PdfLbdManual : dialog {"
"  label = \"PDFLBD 手动导入(按Excel LBD号)\" ;"
"  : boxed_column {"
"    label = \"标签Excel\";"
"    : row {"
"      : edit_box { label = \"Excel(分表名=布局名):\"; key = \"lm_xlsx\"; edit_width = 30; }"
"      : button { label = \"选择...\"; key = \"lm_btnxlsx\"; width = 10; }"
"    }"
"  }"
"  : boxed_column {"
"    label = \"填写顺序\";"
"    : row {"
"      : popup_list { label = \"排列顺序:\"; key = \"lm_order\"; edit_width = 28; }"
"      : edit_box { label = \"分行容差%:\"; key = \"lm_rowtol\"; edit_width = 5; value = \"10\"; }"
"    }"
"  }"
"  : boxed_column {"
"    label = \"预览(左=按顺序排序后的文字, 右=按Excel LBD号升序的标签):\";"
"    : row {"
"      : list_box { key = \"lm_grid\"; height = 10; width = 30; }"
"      : list_box { key = \"lm_names\"; height = 10; width = 26; }"
"    }"
"    : text { key = \"lm_info\"; label = \" \"; width = 60; }"
"  }"
"  ok_cancel;"
"}"
)))

(defun PdfLayout_ErrorHandler (msg)
  (if *PdfLayout_UndoOn*
    (vl-catch-all-apply
      '(lambda () (command "._UNDO" "_E"))
    )
  )
  (if *PdfLayout_Running*
    (progn
      (foreach n *PdfLayout_CreatedLayouts*
        (if (PdfLayout_LayoutExists n)
          (PdfLayout_DeleteLayout n)
        )
      )
      (princ (strcat "\nPDF布局工具出错，已删除已创建的 "
                     (itoa (length *PdfLayout_CreatedLayouts*))
                     " 个布局: " msg))
      (setq *PdfLayout_Running* nil)
      (setq *PdfLayout_CreatedLayouts* nil)
    )
    (princ (strcat "\nPDF布局工具错误: " msg))
  )
  ;; 出错时恢复文件对话框开关，避免 FILEDIA 停留在 0 导致不再弹窗
  (if *PdfLayout_SavedFd*
    (progn
      (setvar "FILEDIA" *PdfLayout_SavedFd*)
      (setq *PdfLayout_SavedFd* nil)
    )
  )
  (setvar "CMDECHO" 1)
  (setvar "EXPERT" 0)
  (princ)
)

(setq *error* PdfLayout_ErrorHandler)

;;;-------------------------------------------------------------
;;; 全局参数
;;;-------------------------------------------------------------
(defun PdfLayout_GetDefaults ()
  (list
    (cons "Mode"           "marker")
    (cons "Filter"         "")
    (cons "TemplateLayout" "")
    (cons "Count"          0)
    (cons "Rule"           "INV{G2}{L}{N2}")
    (cons "Letters"        "AB")
    (cons "PerGroup"       6)
    (cons "GroupStart"     1)
    (cons "Margin"         5)
    (cons "Overwrite"      0)
  )
)

(defun PdfLayout_GetParam (params key)
  (cdr (assoc key params))
)

;;;-------------------------------------------------------------
;;; 通用小工具
;;;-------------------------------------------------------------
(defun PdfLayout_PadZero (num digits / s len)
  (setq s (itoa num))
  (setq len (strlen s))
  (if (< len digits)
    (repeat (- digits len)
      (setq s (strcat "0" s))
    )
  )
  s
)

(defun PdfLayout_GetExtentsSafeObj (obj / bb pmin pmax)
  (setq bb (vl-catch-all-apply 'vla-GetBoundingBox (list obj 'pmin 'pmax)))
  (if (vl-catch-all-error-p bb)
    nil
    (list (vlax-safearray->list pmin) (vlax-safearray->list pmax))
  )
)

(defun PdfLayout_BBoxCenter (bbox / minPt maxPt)
  (setq minPt (car bbox) maxPt (cadr bbox))
  (list (/ (+ (car minPt) (car maxPt)) 2.0)
        (/ (+ (cadr minPt) (cadr maxPt)) 2.0))
)

(defun PdfLayout_HasDuplicate (lst / seen x dup)
  (setq seen nil dup nil)
  (foreach x lst
    (if (member x seen)
      (setq dup T)
      (setq seen (cons x seen))
    )
  )
  dup
)

(defun PdfLayout_ValidLayoutName (name / bad ok c)
  (setq bad (list ">" "<" "/" "\\" "\"" ":" ";" "?" "*" "|" "=" "," "`"))
  (setq ok T)
  (foreach c bad
    (if (vl-string-search c name)
      (setq ok nil)
    )
  )
  ok
)

;;;-------------------------------------------------------------
;;; 命名规则引擎
;;; 占位符：
;;;   {G} 或 {G2}   编号段：编号循环完成后自动+1，位数缺省2
;;;   {L}           字母段：循环使用字母列表（如 AB 或 A-Z）
;;;   {N} 或 {N2}   序号段：每组从1开始，数到"每组张数"后换下一字母/编号
;;; 示例：INV{G2}{L}{N2} + 字母AB + 每组6张
;;;       → INV01A01..A06, INV01B01..B06, INV02A01..
;;;-------------------------------------------------------------
(defun PdfLayout_ParseRule (rule / i j token seg segs)
  (setq segs nil i 0)
  (while (< i (strlen rule))
    (if (= (substr rule (1+ i) 1) "{")
      (progn
        (setq j (vl-string-search "}" rule i))
        (if j
          (progn
            (setq token (strcase (substr rule (+ i 2) (- j i 1))))
            (cond
              ((= token "L")         (setq seg (cons "L" nil)))
              ((= token "G")         (setq seg (cons "G" nil)))
              ((= token "N")         (setq seg (cons "N" nil)))
              ((wcmatch token "G#*") (setq seg (cons "G" (atoi (substr token 2)))))
              ((wcmatch token "N#*") (setq seg (cons "N" (atoi (substr token 2)))))
              (t                     (setq seg (cons "T" (strcat "{" token "}"))))
            )
            (setq segs (append segs (list seg)))
            (setq i (1+ j))
          )
          (progn
            (setq segs (append segs (list (cons "T" "{"))))
            (setq i (1+ i))
          )
        )
      )
      (progn
        (setq j (vl-string-search "{" rule i))
        (if (not j) (setq j (strlen rule)))
        (setq segs (append segs (list (cons "T" (substr rule (1+ i) (- j i))))))
        (setq i j)
      )
    )
  )
  segs
)

(defun PdfLayout_ParseLetters (str / len c1 c2 code out i c)
  (setq str (strcase str))
  (setq len (strlen str))
  (setq out nil)
  (if (and (= len 3) (= (substr str 2 1) "-"))
    (progn
      (setq c1 (substr str 1 1) c2 (substr str 3 1))
      (if (and (>= c1 "A") (<= c1 "Z") (>= c2 "A") (<= c2 "Z") (<= c1 c2))
        (progn
          (setq code (ascii c1))
          (while (<= code (ascii c2))
            (setq out (append out (list (chr code))))
            (setq code (1+ code))
          )
        )
      )
    )
  )
  (if (not out)
    (progn
      (setq i 1)
      (while (<= i len)
        (setq c (substr str i 1))
        (if (and (>= c "A") (<= c "Z"))
          (setq out (append out (list c)))
        )
        (setq i (1+ i))
      )
    )
  )
  out
)

(defun PdfLayout_BuildNamePlan (rule lettersStr pg gStart
                                / segs letters hasN hasL hasG lenL nWidth gWidth
                                  rev s typ val pace plan vals)
  (setq segs (PdfLayout_ParseRule rule))
  (setq letters (PdfLayout_ParseLetters lettersStr))
  (setq hasN (assoc "N" segs))
  (setq hasL (assoc "L" segs))
  (setq hasG (assoc "G" segs))
  (setq lenL (if hasL (length letters) 1))
  (setq nWidth (if (and hasN (cdr hasN)) (cdr hasN) 2))
  (setq gWidth (if (and hasG (cdr hasG)) (cdr hasG) 2))
  (setq plan nil)
  (setq pace 1)
  (setq rev (reverse segs))
  (foreach s rev
    (setq typ (car s))
    (cond
      ((= typ "T")
        (setq plan (cons s plan))
      )
      ((= typ "N")
        (setq vals (if (and (not hasL) (not hasG)) nil pg))
        (setq plan (cons (cons "N"
                               (list (cons "width" nWidth)
                                     (cons "start" 1)
                                     (cons "vals" vals)
                                     (cons "pace" pace)))
                         plan))
        (if vals (setq pace (* pace vals)))
      )
      ((= typ "L")
        (setq plan (cons (cons "L"
                               (list (cons "letters" letters)
                                     (cons "pace" pace)))
                         plan))
        (setq pace (* pace lenL))
      )
      ((= typ "G")
        (setq plan (cons (cons "G"
                               (list (cons "width" gWidth)
                                     (cons "start" gStart)
                                     (cons "pace" pace)))
                         plan))
      )
    )
  )
  plan
)

(defun PdfLayout_NameAt (plan i / out s typ p letters vals idx)
  (setq out "")
  (foreach s plan
    (setq typ (car s))
    (cond
      ((= typ "T")
        (setq out (strcat out (cdr s)))
      )
      ((= typ "G")
        (setq p (cdr s))
        (setq out (strcat out
                          (PdfLayout_PadZero
                            (+ (cdr (assoc "start" p))
                               (fix (/ i (cdr (assoc "pace" p)))))
                            (cdr (assoc "width" p)))))
      )
      ((= typ "L")
        (setq p (cdr s))
        (setq letters (cdr (assoc "letters" p)))
        (setq out (strcat out
                          (nth (rem (fix (/ i (cdr (assoc "pace" p))))
                                    (length letters))
                               letters)))
      )
      ((= typ "N")
        (setq p (cdr s))
        (setq vals (cdr (assoc "vals" p)))
        (setq idx (if vals
                    (rem (fix (/ i (cdr (assoc "pace" p)))) vals)
                    (fix (/ i (cdr (assoc "pace" p))))))
        (setq out (strcat out
                          (PdfLayout_PadZero
                            (+ (cdr (assoc "start" p)) idx)
                            (cdr (assoc "width" p)))))
      )
    )
  )
  out
)

(defun PdfLayout_MaxDistinct (plan / gEnt lEnt nEnt lInfo nInfo)
  (setq gEnt (assoc "G" plan))
  (setq lEnt (assoc "L" plan))
  (setq nEnt (assoc "N" plan))
  (cond
    (gEnt 0)
    ((and nEnt (not lEnt)) 0)
    (lEnt
      (setq lInfo (cdr lEnt))
      (setq nInfo (if nEnt (cdr nEnt) nil))
      (* (length (cdr (assoc "letters" lInfo)))
         (if nInfo (cdr (assoc "vals" nInfo)) 1))
    )
    (t 1)
  )
)

(defun PdfLayout_GenNames (rule lettersStr pg gStart count
                           / segs letters hasL plan names i maxD)
  (setq segs (PdfLayout_ParseRule rule))
  (setq letters (PdfLayout_ParseLetters lettersStr))
  (setq hasL (assoc "L" segs))
  (if (and hasL (not letters))
    nil
    (progn
      (setq plan (PdfLayout_BuildNamePlan rule lettersStr pg gStart))
      (setq maxD (PdfLayout_MaxDistinct plan))
      (if (and (/= maxD 0) (< maxD count))
        nil
        (progn
          (setq names nil i 0)
          (while (< i count)
            (setq names (append names (list (PdfLayout_NameAt plan i))))
            (setq i (1+ i))
          )
          names
        )
      )
    )
  )
)

(defun PdfLayout_ValidateRule (rule lettersStr
                               / segs letters hasL hasN hasG msg)
  (setq segs (PdfLayout_ParseRule rule))
  (setq letters (PdfLayout_ParseLetters lettersStr))
  (setq hasL (assoc "L" segs))
  (setq hasN (assoc "N" segs))
  (setq hasG (assoc "G" segs))
  (setq msg nil)
  (if (not (or hasL hasN hasG))
    (setq msg "命名规则中至少需要一个占位符 {G} / {L} / {N}，例如 INV{G2}{L}{N2}")
  )
  (if (and hasL (not letters))
    (setq msg (strcat "命名规则使用了 {L}，但字母列表无效: "
                      lettersStr
                      "（示例: AB 或 A-Z）"))
  )
  msg
)

;;;-------------------------------------------------------------
;;; 图纸识别（模型空间）
;;;-------------------------------------------------------------
(defun PdfLayout_ScanMarkers (markerName / doc ms obj name bbox lst)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq markerName (strcase (if markerName markerName "pdf")))
  (setq lst nil)
  (vlax-for obj ms
    (if (= (vla-get-ObjectName obj) "AcDbBlockReference")
      (progn
        (setq name (strcase (vla-get-Name obj)))
        (if (= name markerName)
          (progn
            (setq bbox (PdfLayout_GetExtentsSafeObj obj))
            (if bbox
              (setq lst (append lst (list (cons obj bbox))))
            )
          )
        )
      )
    )
  )
  ;; 排序：同一行先从左往右，行与行从上往下；
  ;; 按底端 y 精确分行（竖线块摆放齐平，不做容差合并），一行的竖线块全部识别完再开启下一行
  (PdfLayout_SortMarkersRowMajor lst)
)

(defun PdfLayout_IsUnderlay (objName / up)
  (setq up (strcase objName))
  (or (= up "ACDBPDFREFERENCE")
      (= up "ACDBUNDERLAYREFERENCE")
      (= up "ACDBDWFREFERENCE")
      (vl-string-search "PDF" up)
      (vl-string-search "UNDERLAY" up))
)

(defun PdfLayout_CountUnderlays (/ doc ms n obj)
  ;; 统计模型空间里现有的 PDF/底图对象数量，用于判断导入是否成功
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq n 0)
  (vlax-for obj ms
    (if (PdfLayout_IsUnderlay (vla-get-ObjectName obj))
      (setq n (1+ n))
    )
  )
  n
)

;;; 注：底图不再收进专用层、也不锁定（老版本的 PDFLOCK / PDFUNLOCK 已删除）


(defun PdfLayout_ListObjectNames (/ doc ms out obj)
  ;; 诊断用：列出模型空间所有对象的 ObjectName
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq out "")
  (vlax-for obj ms
    (setq out (strcat out (if (= out "") "" ", ") (vla-get-ObjectName obj)))
  )
  out
)

(defun PdfLayout_EntityNameList (/ doc ms out obj)
  ;; 收集模型空间所有实体的 ename，用于对比导入前后的新增对象
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq out nil)
  (vlax-for obj ms
    (setq out (cons (vlax-vla-object->ename obj) out))
  )
  out
)

(defun PdfLayout_ImportPdfFile (path / oldNames newNames newObjs oldFd ok before after)
  ;; 仅用 PDFATTACH 自动导入：整份 PDF 由 ZWCAD 按页生成参考底图对象，
  ;; 通过导入前后实体列表对比找出新增对象并返回；
  ;; 若导入页数与 PDF 页数不符，可在弹窗中勾选“弹窗选页”手动选择页面
  (setq oldNames (PdfLayout_EntityNameList))
  (if *PdfLayout_Debug*
    (progn
      (princ (strcat "\n[调试] 导入前实体数=" (itoa (length oldNames)) "  PDF=" path))
      (princ (strcat "\n[调试] 模型空间对象: " (PdfLayout_ListObjectNames)))
    )
  )
  (princ (strcat "\n正在导入 PDF: " path))
  (setq oldFd (getvar "FILEDIA"))
  (setq *PdfLayout_SavedFd* oldFd)
  (setvar "FILEDIA" 0)
  (setq ok nil)
  ;; 尝试1：路径 → 插入点(0,0) → 比例1 → 旋转0
  (setq before (length (PdfLayout_EntityNameList)))
  (vl-catch-all-apply
    '(lambda ()
      (command "._PDFATTACH" path "0,0" "1" "0")
      (command)
    )
  )
  (setq after (length (PdfLayout_EntityNameList)))
  (if (> after before) (setq ok T))
  ;; 尝试2：只给路径，让 ZWCAD 用默认值（诊断确认不会挂起）
  (if (not ok)
    (progn
      (setq before (length (PdfLayout_EntityNameList)))
      (vl-catch-all-apply
        '(lambda ()
          (command "._PDFATTACH" path)
          (command)
        )
      )
      (setq after (length (PdfLayout_EntityNameList)))
      (if (> after before) (setq ok T))
    )
  )
  (setq *PdfLayout_SavedFd* nil)
  (setvar "FILEDIA" oldFd)
  (setq newNames (PdfLayout_EntityNameList))
  (setq newObjs nil)
  (foreach e newNames
    (if (not (member e oldNames))
      (setq newObjs (cons (vlax-ename->vla-object e) newObjs))
    )
  )
  (if *PdfLayout_Debug*
    (progn
      (princ (strcat "\n[调试] 导入后实体数=" (itoa (length newNames))
                     "  新增对象数=" (itoa (length newObjs))))
      (princ (strcat "\n[调试] 模型空间对象: " (PdfLayout_ListObjectNames)))
    )
  )
  (if newObjs
    (progn
      (princ (strcat "\nPDF 导入成功，新增 " (itoa (length newObjs))
                     " 个底图（若少于 PDF 页数，可勾选“弹窗选页”重新导入）"))
      newObjs
    )
    (progn
      (PdfLayout_Alert "PDF 自动导入未完成：PDFATTACH 未能导入任何页面。\n请勾选“弹窗选页”手动选择页面后重试，或先手动执行 PDFATTACH 导入。")
      nil
    )
  )
)
(defun PdfLayout_ImportPdfDialog (path / oldNames newNames newObjs oldFd)
  ;; 启动 ZWCAD 原生 PDFATTACH 选页窗口：
  ;; 命令行模式下输入 ~ 强制弹出文件选择窗口（ZWCAD 官方机制），
  ;; 之后插入点/比例/旋转已自动填好，用户只需选文件、全选页面、点确定；
  ;; 完成后自动识别新增底图并返回，适合 144 页这类多页 PDF
  (setq oldNames (PdfLayout_EntityNameList))
  (princ "\n正在启动 PDFATTACH 选页窗口…")
  (princ "\n请在窗口中选择 PDF，并在页面列表按住 Ctrl 全选需要的页面（或点第一页、Shift 点最后一页），点确定；")
  (princ "\n插入点/比例/旋转已自动填好，无需输入。完成后程序自动识别新底图并排列。")
  (setq oldFd (getvar "FILEDIA"))
  (setq *PdfLayout_SavedFd* oldFd)
  (setvar "FILEDIA" 0)
  (vl-catch-all-apply
    '(lambda ()
      (command "._PDFATTACH" "~" "0,0" "1" "0")
      (command)
    )
  )
  (setq *PdfLayout_SavedFd* nil)
  (setvar "FILEDIA" oldFd)
  (setq newNames (PdfLayout_EntityNameList))
  (setq newObjs nil)
  (foreach e newNames
    (if (not (member e oldNames))
      (setq newObjs (cons (vlax-ename->vla-object e) newObjs))
    )
  )
  (if *PdfLayout_Debug*
    (progn
      (princ (strcat "\n[调试] 弹窗选页后新增对象数=" (itoa (length newObjs))))
      (princ (strcat "\n[调试] 模型空间对象: " (PdfLayout_ListObjectNames)))
    )
  )
  (if newObjs
    (progn
      (princ (strcat "\nPDF 导入成功，新增 " (itoa (length newObjs)) " 个底图"))
      newObjs
    )
    (progn
      (PdfLayout_Alert "未检测到新增 PDF 底图（可能已取消选页或未选择页面）。\n请重新运行，并在 PDFATTACH 窗口中按住 Ctrl 全选需要的页面后点击确定。")
      nil
    )
  )
)
(defun PdfLayout_PickPdfFile (/ fpath)
  (setq fpath (getfiled "选择要导入的 PDF 文件" "" "pdf" 4))
  (if fpath
    (progn
      (setq *PdfLayout_LastPdfFile* fpath)
      (set_tile "pdf_path" fpath)
    )
  )
)

(defun PdfLayout_PickNamesXlsx (/ fpath det)
  (setq fpath (getfiled "选择标签Excel(分表名=布局名)" "" "xlsx;xls" 4))
  (if fpath
    (progn
      (setq *PdfLayout_LastNamesXlsx* fpath)
      (set_tile "names_xlsx" fpath)
      (setq *PdfLayout_NamesXlsxList* (PdfLayout_GetXlsxSheetNames fpath))
      (if (not *PdfLayout_NamesXlsxList*)
        (PdfLayout_Alert "无法读取Excel分表名，请确认文件存在且未被占用。")
        (progn
          ;; 自动识别分表名的命名规律并记忆为方案
          (setq det (PdfLayout_DetectRuleFromNames *PdfLayout_NamesXlsxList*))
          (if det
            (progn
              (setq *PdfLayout_LayRule* (nth 0 det))
              (setq *PdfLayout_LayLetters* (nth 1 det))
              (setq *PdfLayout_LayPerGroup* (nth 2 det))
              (setq *PdfLayout_LayGStart* (nth 3 det))
              (set_tile "rule" *PdfLayout_LayRule*)
              (set_tile "letters" *PdfLayout_LayLetters*)
              (set_tile "per_group" (itoa *PdfLayout_LayPerGroup*))
              (set_tile "g_start" (itoa *PdfLayout_LayGStart*))
              (princ (strcat "\n已识别命名规律并记忆: " *PdfLayout_LayRule*))
              (PdfLayout_SaveSettings)
            )
            (princ "\n未能识别分表名的命名规律，将直接使用分表名作为布局名。")
          )
        )
      )
      (PdfLayout_UpdatePreview)
    )
  )
)

(defun PdfLayout_MatchMarkerUnderlay (pt / doc ms obj objName bb c d area
                                      containBest containArea nearest nearestD)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq containBest nil containArea nil nearest nil nearestD nil)
  (vlax-for obj ms
    (setq objName (vla-get-ObjectName obj))
    (if (PdfLayout_IsUnderlay objName)
      (progn
        (setq bb (PdfLayout_GetExtentsSafeObj obj))
        (if bb
          (progn
            (setq c (PdfLayout_BBoxCenter bb))
            (setq d (+ (* (- (car c) (car pt)) (- (car c) (car pt)))
                       (* (- (cadr c) (cadr pt)) (- (cadr c) (cadr pt)))))
            (if (and (>= (car pt) (car (car bb)))
                     (<= (car pt) (car (cadr bb)))
                     (>= (cadr pt) (cadr (car bb)))
                     (<= (cadr pt) (cadr (cadr bb))))
              (progn
                (setq area (* (- (car (cadr bb)) (car (car bb)))
                              (- (cadr (cadr bb)) (cadr (car bb)))))
                (if (or (not containArea) (< area containArea))
                  (progn
                    (setq containBest obj containArea area)
                  )
                )
              )
            )
            (if (or (not nearestD) (< d nearestD))
              (progn (setq nearest obj nearestD d))
            )
          )
        )
      )
    )
  )
  (if containBest containBest nearest)
)

(defun PdfLayout_ScanMarkerDrawings (markerName / markers out pt u bb objName)
  (setq markers (PdfLayout_ScanMarkers markerName))
  (if *PdfLayout_Debug*
    (princ (strcat "\n[调试] 标记识别到 " (itoa (length markers)) " 个"))
  )
  (setq out nil)
  (foreach m markers
    (setq pt (PdfLayout_BBoxCenter (cdr m)))
    (setq u (PdfLayout_MatchMarkerUnderlay pt))
    (setq bb (if u (PdfLayout_GetExtentsSafeObj u) (cdr m)))
    (if *PdfLayout_Debug*
      (progn
        (princ (strcat "\n[调试] 标记中心 "
                       (rtos (car pt) 2 2) "," (rtos (cadr pt) 2 2)))
        (if (and u bb)
          (progn
            (setq objName (vla-get-ObjectName u))
            (princ (strcat " -> 底图 " objName " 范围 "
                           (rtos (car (car bb)) 2 2) ","
                           (rtos (cadr (car bb)) 2 2) " - "
                           (rtos (car (cadr bb)) 2 2) ","
                           (rtos (cadr (cadr bb)) 2 2)))
          )
          (princ (if u " -> 底图已匹配但范围读取失败" " -> 未匹配到底图"))
        )
      )
    )
    (if bb
      (setq out (append out (list bb)))
    )
  )
  out
)
(defun PdfLayout_CmpCreationOrder (a b / ia ib)
  ;; 按底图创建/导入顺序排（对 PDFATTACH 一次导入的一批页 ≈ 页码顺序），纯数字比较，不读实体，防崩
  (setq ia (car a) ib (car b))
  (< ia ib)
)
(defun PdfLayout_ArrangePagesToMarkers (markers / doc ms pages obj objName bb pt i m p
                                        nDone res newBb)
  ;; 把模型空间里已导入的 PDF 底图/块先按 左→右/上→下 排序
  ;; （位置完全重叠时按实体顺序兜底，避免 vl-sort 丢项），
  ;; 再逐个移动到对应竖线标记的位置（页角对齐标记角），并包裹撤销；
  ;; 用 vla-Move 整体移动（ZWCAD 的 PDF 底图不支持直接改插入点），
  ;; 移动后校验新位置，未到位会给出警告
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq pages nil i 0 nDone 0)
  (vlax-for obj ms
    (setq objName (vla-get-ObjectName obj))
    (if (PdfLayout_IsUnderlay objName)
      (progn
        (setq bb (PdfLayout_GetExtentsSafeObj obj))
        (if bb
          (setq pages (append pages (list (cons i (cons obj bb)))))
        )
      )
    )
    (setq i (1+ i))
  )
  (setq pages (PdfLayout_StableSort pages 'PdfLayout_CmpCreationOrder))
  (setq i 0)
  (foreach m markers
    (setq p (if pages (nth i pages) nil))
    (if p
      (progn
        (setq p (cdr p))
        (setq obj (car p) bb (cdr p))
        (setq pt (car (cdr m)))
        (setq res (vl-catch-all-apply
                    'vla-Move
                    (list obj
                          (vlax-3d-point (car (car bb)) (cadr (car bb)) 0.0)
                          (vlax-3d-point (car pt) (cadr pt) 0.0))))
        (setq newBb (PdfLayout_GetExtentsSafeObj obj))
        (if (and newBb (not (vl-catch-all-error-p res))
                 (< (abs (- (car (car newBb)) (car pt))) 1e-6)
                 (< (abs (- (cadr (car newBb)) (cadr pt))) 1e-6))
          (setq nDone (1+ nDone))
          (princ (strcat "\n[警告] 第 " (itoa (1+ i)) " 个底图未移动到目标标记 ("
                         (rtos (car pt) 2 2) "," (rtos (cadr pt) 2 2) ")，可能被锁定或对象类型不支持移动"))
        )
      )
    )
    (setq i (1+ i))
  )
  (princ (strcat "\n已按 左→右/上→下 排列 " (itoa nDone)
                 " 个PDF底图到竖线标记位置（共 " (itoa (length pages))
                 " 个底图，" (itoa (length markers)) " 个标记）"))
)

(defun PdfLayout_ArrangeObjsToMarkers (objs markers / pages i m p pt bb obj nDone res newBb)
  ;; 把指定对象（新导入的底图）按 左→右/上→下 排序后移动到竖线标记位置，
  ;; 用 vla-Move 移动（对任何对象有效），不依赖对象名识别；移动后校验是否到位
  (setq pages nil i 0 nDone 0)
  (foreach obj objs
    (setq bb (PdfLayout_GetExtentsSafeObj obj))
    (if bb
      (setq pages (append pages (list (cons i (cons obj bb)))))
    )
    (setq i (1+ i))
  )
  (setq pages (PdfLayout_StableSort pages (quote PdfLayout_CmpCreationOrder)))
  (if (not markers)
    (princ "\n未识别到竖线标记，跳过自动排列（请确认已画好竖线标记块且块名与弹窗中一致）。")
  )
  (setq i 0)
  (foreach m markers
    (setq p (if pages (nth i pages) nil))
    (if p
      (progn
        (setq p (cdr p))
        (setq obj (car p) bb (cdr p))
        (setq pt (car (cdr m)))
        (setq res (vl-catch-all-apply
                    (quote vla-Move)
                    (list obj
                          (vlax-3d-point (car (car bb)) (cadr (car bb)) 0.0)
                          (vlax-3d-point (car pt) (cadr pt) 0.0))))
        (setq newBb (PdfLayout_GetExtentsSafeObj obj))
        (if (and newBb (not (vl-catch-all-error-p res))
                 (< (abs (- (car (car newBb)) (car pt))) 1e-6)
                 (< (abs (- (cadr (car newBb)) (cadr pt))) 1e-6))
          (setq nDone (1+ nDone))
          (princ (strcat "\n[警告] 第 " (itoa (1+ i)) " 个底图未移动到目标标记 ("
                         (rtos (car pt) 2 2) "," (rtos (cadr pt) 2 2) ")"))
        )
      )
    )
    (setq i (1+ i))
  )
  (princ (strcat "\n已按 左→右/上→下 排列 " (itoa nDone)
                 " 个新导入的 PDF 底图到竖线标记位置（标记数 " (itoa (length markers)) "）"))
)
(defun PdfLayout_ScanBlockDrawings (filter / doc ms obj name bbox lst)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq filter (if filter (strcase filter) ""))
  (setq lst nil)
  (vlax-for obj ms
    (if (= (vla-get-ObjectName obj) "AcDbBlockReference")
      (progn
        (setq name (vla-get-Name obj))
        (if (or (= filter "") (vl-string-search filter (strcase name)))
          (progn
            (setq bbox (PdfLayout_GetExtentsSafeObj obj))
            (if bbox
              (setq lst (append lst (list (cons obj bbox))))
            )
          )
        )
      )
    )
  )
  (PdfLayout_SortByPosition lst)
)

(defun PdfLayout_InsertSorted (lst x cmp / done out)
  ;; cmp 为命名比较函数（符号），中望不支持把 (quote (lambda ...)) 传给 apply
  (setq done nil out nil)
  (foreach y lst
    (if (and (not done) (apply cmp (list x y)))
      (progn
        (setq out (append out (list x)))
        (setq done T)
      )
    )
    (setq out (append out (list y)))
  )
  (if (not done) (setq out (append out (list x))))
  out
)

(defun PdfLayout_StableSort (lst cmp / out)
  ;; 稳定插入排序：不依赖中望 vl-sort；插入排序本身稳定，并列保持原顺序、不丢元素
  (setq out nil)
  (foreach x lst
    (setq out (PdfLayout_InsertSorted out x cmp))
  )
  out
)

(defun PdfLayout_SortIndexed (lst cmp)
  (PdfLayout_StableSort lst cmp)
)

;; 8 种精确排序比较器：a 排在 b 前返回 T
(defun PdfLayout_CmpPos (a b / c1 c2 y1 y2 x1 x2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq y1 (cadr c1) y2 (cadr c2) x1 (car c1) x2 (car c2))
  (if (equal y1 y2 1e-6) (< x1 x2) (> y1 y2))
)
(defun PdfLayout_CmpLR (a b / c1 c2 y1 y2 x1 x2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal x1 x2 1e-6) (> y1 y2) (< x1 x2))
)
(defun PdfLayout_CmpRL (a b / c1 c2 y1 y2 x1 x2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal x1 x2 1e-6) (> y1 y2) (> x1 x2))
)
(defun PdfLayout_CmpBT (a b / c1 c2 y1 y2 x1 x2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq y1 (cadr c1) y2 (cadr c2) x1 (car c1) x2 (car c2))
  (if (equal y1 y2 1e-6) (< x1 x2) (< y1 y2))
)
(defun PdfLayout_CmpLRBT (a b / c1 c2 x1 x2 y1 y2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal x1 x2 1e-6) (< y1 y2) (< x1 x2))
)
(defun PdfLayout_CmpRLBT (a b / c1 c2 x1 x2 y1 y2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal x1 x2 1e-6) (< y1 y2) (> x1 x2))
)
(defun PdfLayout_CmpTBR (a b / c1 c2 x1 x2 y1 y2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal y1 y2 1e-6) (> x1 x2) (> y1 y2))
)
(defun PdfLayout_CmpBTR (a b / c1 c2 x1 x2 y1 y2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (setq x1 (car c1) x2 (car c2) y1 (cadr c1) y2 (cadr c2))
  (if (equal y1 y2 1e-6) (> x1 x2) (< y1 y2))
)
;; 次方向比较器
(defun PdfLayout_CmpXAsc (a b / c1 c2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (< (car c1) (car c2))
)
(defun PdfLayout_CmpXDesc (a b / c1 c2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (> (car c1) (car c2))
)
(defun PdfLayout_CmpYAsc (a b / c1 c2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (< (cadr c1) (cadr c2))
)
(defun PdfLayout_CmpYDesc (a b / c1 c2)
  (setq c1 (PdfLayout_BBoxCenter (cdr a)))
  (setq c2 (PdfLayout_BBoxCenter (cdr b)))
  (> (cadr c1) (cadr c2))
)
;; 其他用途比较器
(defun PdfLayout_CmpYGreater (a b) (> (car a) (car b)))
(defun PdfLayout_CmpLbd (a b / ka kb)
  (setq ka (PdfLayout_NumKey (nth 1 a)))
  (setq kb (PdfLayout_NumKey (nth 1 b)))
  (if (= ka kb) (< (car a) (car b)) (< ka kb))
)
(defun PdfLayout_CmpRowTop (a b / ya yb)
  (setq ya (apply 'max (mapcar '(lambda (q) (cadr (PdfLayout_BBoxCenter (cdr q)))) a)))
  (setq yb (apply 'max (mapcar '(lambda (q) (cadr (PdfLayout_BBoxCenter (cdr q)))) b)))
  (> ya yb)
)
(defun PdfLayout_CmpRowBottom (a b / ya yb)
  ;; 竖线标记按底端 y 从高到低排序（a 排在 b 前返回 T）；
  ;; 用底端而不是中心点分行，竖线长短不一样也不影响同一行识别
  (setq ya (cadr (car (cdr a))))
  (setq yb (cadr (car (cdr b))))
  (> ya yb)
)
(defun PdfLayout_SortMarkersRowMajor (lst / sorted rows g out grp k prevK)
  ;; 竖线标记按行排序：同一行内从左往右，行与行从上往下，
  ;; 一行的竖线块全部识别完再开启下一行。
  ;; 按底端 y 精确分行（摆放齐平，不做容差合并），
  ;; 仅浮点误差范围（1e-6）内视为同一行
  (if (< (length lst) 2)
    lst
    (progn
      (setq sorted (PdfLayout_SortIndexed lst 'PdfLayout_CmpRowBottom))
      ;; 按底端 y 从高到低分行：底端差超过浮点误差即换行
      (setq rows nil g (list (car sorted))
            prevK (cadr (car (cdr (car sorted)))))
      (foreach p (cdr sorted)
        (setq k (cadr (car (cdr p))))
        (if (> (abs (- prevK k)) 1e-6)
          (progn
            (setq rows (append rows (list g)))
            (setq g (list p))
          )
          (setq g (append g (list p)))
        )
        (setq prevK k)
      )
      (setq rows (append rows (list g)))
      ;; 每行内从左往右，行与行按从上往下拼接
      (setq out nil)
      (foreach grp rows
        (setq grp (PdfLayout_SortIndexed grp 'PdfLayout_CmpXAsc))
        (setq out (append out grp))
      )
      out
    )
  )
)
(defun PdfLayout_CmpVpArea (a b) (> (cdr a) (cdr b)))

(defun PdfLayout_SortByPosition (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpPos))

(defun PdfLayout_SelectionBBox (ss / i ename obj bb pmin pmax minPt maxPt b)
  (setq i 0 minPt nil maxPt nil)
  (repeat (sslength ss)
    (setq ename (ssname ss i))
    (setq obj (vlax-ename->vla-object ename))
    (setq b (PdfLayout_GetExtentsSafeObj obj))
    (if b
      (progn
        (setq pmin (car b) pmax (cadr b))
        (if minPt
          (progn
            (setq minPt (list (min (car minPt) (car pmin))
                              (min (cadr minPt) (cadr pmin))
                              (min (caddr minPt) (caddr pmin))))
            (setq maxPt (list (max (car maxPt) (car pmax))
                              (max (cadr maxPt) (cadr pmax))
                              (max (caddr maxPt) (caddr pmax))))
          )
          (setq minPt pmin maxPt pmax)
        )
      )
    )
    (setq i (1+ i))
  )
  (if minPt (list minPt maxPt) nil)
)

(defun PdfLayout_SortByPositionLR (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpLR))

(defun PdfLayout_SortByPositionRL (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpRL))

(defun PdfLayout_SortByPositionBT (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpBT))
(defun PdfLayout_SortByPositionLRBT (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpLRBT))

(defun PdfLayout_SortByPositionRLBT (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpRLBT))

(defun PdfLayout_SortByPositionTBR (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpTBR))

(defun PdfLayout_SortByPositionBTR (lst) (PdfLayout_SortIndexed lst 'PdfLayout_CmpBTR))



(defun PdfLayout_SortPairsSmart (pairs order / cmpMain cmpSec axis xs ys xRange yRange tol
                                 sorted groups g gKey out grp c k)
  ;; 用户手动摆放位置不一定整齐，按“容差”分行/分列后再排序
  (setq cmpMain (cond
    ((= order "1") 'PdfLayout_CmpLR)
    ((= order "2") 'PdfLayout_CmpPos)
    ((= order "3") 'PdfLayout_CmpRL)
    ((= order "4") 'PdfLayout_CmpBT)
    ((= order "5") 'PdfLayout_CmpLRBT)
    ((= order "6") 'PdfLayout_CmpRLBT)
    ((= order "7") 'PdfLayout_CmpTBR)
    ((= order "8") 'PdfLayout_CmpBTR)
    (t nil)
  ))
  (if (null cmpMain)
    pairs
    (progn
      (setq cmpSec (cond
        ((member order '("1" "3")) 'PdfLayout_CmpYDesc)
        ((member order '("5" "6")) 'PdfLayout_CmpYAsc)
        ((member order '("2" "4")) 'PdfLayout_CmpXAsc)
        ((member order '("7" "8")) 'PdfLayout_CmpXDesc)
        (t 'PdfLayout_CmpXAsc)
      ))
      (setq axis (if (member order '("1" "3" "5" "6")) "X" "Y"))
      (setq xs (mapcar '(lambda (q) (car (PdfLayout_BBoxCenter (cdr q)))) pairs))
      (setq ys (mapcar '(lambda (q) (cadr (PdfLayout_BBoxCenter (cdr q)))) pairs))
      (setq xRange (- (apply 'max xs) (apply 'min xs)))
      (setq yRange (- (apply 'max ys) (apply 'min ys)))
      (setq tol (max 0.25 (* (if (and *PdfLayout_RowTol* (> *PdfLayout_RowTol* 0)) *PdfLayout_RowTol* 10)
                            0.001 (if (= axis "X") xRange yRange))))
      ;; 先按主方向排序
      (setq sorted (PdfLayout_SortIndexed pairs cmpMain))
      ;; 按容差分成行/列组
      (setq groups nil g nil gKey nil)
      (foreach p sorted
        (setq c (PdfLayout_BBoxCenter (cdr p)))
        (setq k (if (= axis "X") (car c) (cadr c)))
        (if (and gKey (<= (abs (- gKey k)) tol))
          (setq g (append g (list p)))
          (progn
            (if g (setq groups (append groups (list g))))
            (setq g (list p) gKey k)
          )
        )
      )
      (if g (setq groups (append groups (list g))))
      ;; 组内按次方向排序，按组拼接
      (setq out nil)
      (foreach grp groups
        (setq grp (PdfLayout_SortIndexed grp cmpSec))
        (setq out (append out grp))
      )
      out
    )
  )
)

(defun PdfLayout_PickDrawingsOnce (filter / ss i ename obj name bbox lst)
  (princ "\n请一次性框选所有图纸的块参照（可输入 ALL 全选），然后回车（Esc取消）: ")
  (setq ss (ssget))
  (if (not ss)
    (progn
      (princ "\n已取消图纸选择。")
      nil
    )
    (progn
      (setq lst nil i 0)
      (repeat (sslength ss)
        (setq ename (ssname ss i))
        (setq obj (vlax-ename->vla-object ename))
        (if (= (vla-get-ObjectName obj) "AcDbBlockReference")
          (progn
            (setq name (vla-get-Name obj))
            (if (or (not filter) (= filter "")
                    (vl-string-search (strcase filter) (strcase name)))
              (progn
                (setq bbox (PdfLayout_GetExtentsSafeObj obj))
                (if bbox
                  (setq lst (append lst (list (cons obj bbox))))
                )
              )
            )
          )
        )
        (setq i (1+ i))
      )
      (if (= (length lst) 0)
        (progn
          (princ "\n选择集中没有找到符合条件的图纸块。请确认图纸以参考底图或图块形式存在并框选到图纸块；或改用自动识别模式。")
          nil
        )
        (progn
          (princ (strcat "\n识别到 " (itoa (length lst))
                         " 张图纸，按 从左到右、从上到下 排序对应。"))
          (mapcar 'cdr (PdfLayout_SortByPositionLR lst))
        )
      )
    )
  )
)
(defun PdfLayout_PickDrawings (count / i ss bbox lst)
  (setvar "TILEMODE" 1)
  (setq i 1)
  (setq lst nil)
  (while (<= i count)
    (princ (strcat "\n请框选第 " (itoa i) "/" (itoa count)
                   " 张图纸的所有实体后回车（按Esc取消）: "))
    (setq ss (ssget))
    (if (not ss)
      (progn
        (princ "\n已取消图纸选择。")
        (setq lst nil)
        (setq i (1+ count))
      )
      (progn
        (setq bbox (PdfLayout_SelectionBBox ss))
        (if bbox
          (progn
            (setq lst (append lst (list bbox)))
            (setq i (1+ i))
          )
          (princ "\n所选对象没有有效范围，请重新选择。")
        )
      )
    )
  )
  lst
)

;;;-------------------------------------------------------------
;;; 布局操作
;;;-------------------------------------------------------------
(defun PdfLayout_GetLayoutNames (/ doc layouts out)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layouts (vla-get-Layouts doc))
  (setq out nil)
  (vlax-for l layouts
    (if (/= (strcase (vla-get-Name l)) "MODEL")
      (setq out (append out (list (vla-get-Name l))))
    )
  )
  out
)

(defun PdfLayout_GetLayoutObj (name / doc layouts result)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layouts (vla-get-Layouts doc))
  (setq result nil)
  (vlax-for l layouts
    (if (= (strcase (vla-get-Name l)) (strcase name))
      (setq result l)
    )
  )
  result
)

(defun PdfLayout_LayoutExists (name)
  (not (null (PdfLayout_GetLayoutObj name)))
)

(defun PdfLayout_DeleteLayout (name / doc l act other)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq l (PdfLayout_GetLayoutObj name))
  (if l
    (progn
      (setq act (vla-get-ActiveLayout doc))
      (if (and act (= (strcase (vla-get-Name act)) (strcase name)))
        (progn
          (setq other nil)
          (vlax-for x (vla-get-Layouts doc)
            (if (and (not other)
                     (/= (strcase (vla-get-Name x)) (strcase name)))
              (setq other x)
            )
          )
          (if other
            (vl-catch-all-apply
              '(lambda () (setvar "CTAB" (vla-get-Name other)))
              nil
            )
          )
        )
      )
      (vl-catch-all-apply 'vla-Delete (list l))
    )
  )
)

(defun PdfLayout_CopyLayout (src dst / doc layouts srcLay newLay srcBlk newBlk
                             objs arr cnt ok)
  (setq ok nil)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layouts (vla-get-Layouts doc))
  (setq srcLay (PdfLayout_GetLayoutObj src))
  (if (and srcLay (not (PdfLayout_LayoutExists dst)))
    (progn
      (setq newLay (vl-catch-all-apply 'vla-Add (list layouts dst)))
      (if (and newLay (not (vl-catch-all-error-p newLay)))
        (progn
          (vl-catch-all-apply 'vla-CopyFrom (list newLay srcLay))
          (setq srcBlk (vla-get-Block srcLay))
          (setq newBlk (vla-get-Block newLay))
          (setq objs nil)
          (vlax-for o srcBlk
            (if (/= (vla-get-ObjectName o) "AcDbViewport")
              (setq objs (append objs (list o)))
            )
          )
          (setq cnt (length objs))
          (if (> cnt 0)
            (progn
              (setq arr (vlax-make-safearray vlax-vbObject (cons 0 (1- cnt))))
              (vlax-safearray-fill arr objs)
              (vl-catch-all-apply 'vla-CopyObjects (list doc arr newBlk))
            )
          )
          (setq ok (PdfLayout_LayoutExists dst))
        )
      )
    )
  )
  ok
)

(defun PdfLayout_GetLayoutViewports (name / layout blk obj bb pmin pmax area vpList)
  (setq layout (PdfLayout_GetLayoutObj name))
  (setq vpList nil)
  (if layout
    (progn
      (setq blk (vla-get-Block layout))
      (vlax-for obj blk
        (if (= (vla-get-ObjectName obj) "AcDbViewport")
          (progn
            (setq bb (PdfLayout_GetExtentsSafeObj obj))
            (if bb
              (progn
                (setq pmin (car bb) pmax (cadr bb))
                (setq area (* (- (car pmax) (car pmin))
                              (- (cadr pmax) (cadr pmin))))
                (setq vpList (append vpList (list (cons obj area))))
              )
            )
          )
        )
      )
    )
  )
  vpList
)

(defun PdfLayout_GetViewportFrame (name / vps vp)
  (setq vps (PdfLayout_GetLayoutViewports name))
  (if vps
    (progn
      (setq vp (car (PdfLayout_StableSort vps 'PdfLayout_CmpVpArea)))
      (PdfLayout_GetExtentsSafeObj (car vp))
    )
  )
)

(defun PdfLayout_DeleteViewportsExcept (name keepObj / layout blk obj toDel)
  (setq layout (PdfLayout_GetLayoutObj name))
  (setq toDel nil)
  (if layout
    (progn
      (setq blk (vla-get-Block layout))
      (vlax-for obj blk
        (if (and (= (vla-get-ObjectName obj) "AcDbViewport")
                 (not (equal obj keepObj)))
          (setq toDel (append toDel (list obj)))
        )
      )
      (foreach o toDel
        (vl-catch-all-apply 'vla-Delete (list o))
      )
    )
  )
)

(defun PdfLayout_CreateViewport (pt1 pt2 / oldCmdEcho oldExpert ename result)
  (setq oldCmdEcho (getvar "CMDECHO"))
  (setq oldExpert (getvar "EXPERT"))
  (setvar "CMDECHO" 0)
  (setvar "EXPERT" 5)
  (command "._MVIEW" pt1 pt2 "")
  (setq ename (entlast))
  (if (and ename (= (cdr (assoc 0 (entget ename))) "VIEWPORT"))
    (setq result ename)
    (setq result nil)
  )
  (setvar "CMDECHO" oldCmdEcho)
  (setvar "EXPERT" oldExpert)
  result
)

(defun PdfLayout_CreateViewportFromMargin (margin / doc layout pw ph vpMin vpMax)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layout (vla-get-ActiveLayout doc))
  (setq pw (vla-get-PaperWidth layout))
  (setq ph (vla-get-PaperHeight layout))
  (setq vpMin (list margin margin 0.0))
  (setq vpMax (list (- pw margin) (- ph margin) 0.0))
  (PdfLayout_CreateViewport vpMin vpMax)
)

(defun PdfLayout_FitViewport (vpObj bbox lockVp
                              / bb pmin pmax pw ph minPt maxPt center w h
                                scale viewH ok oldCmdEcho oldExpert inset)
  (setq bb (PdfLayout_GetExtentsSafeObj vpObj))
  (if (and bb bbox)
    (progn
      (setq pmin (car bb) pmax (cadr bb))
      ;; 区域对准留白（*PdfLayout_ViewInset*）= 图纸在视口里占的比例：
      ;; 1.0 = 铺满视口；0.9 = 占 90%，四周留白；<1 越大越满，越小越空。
      ;; 注意：这个系数只能作用一次 —— 先用视口真实尺寸算「刚好铺满」的 scale，
      ;; 再把视图范围放大 1/inset。以前把 inset 乘进 pw/ph，又被 scale 约掉，
      ;; 结果留白完全不生效（界面改了数也不动），这里别再改回去。
      (setq inset (if (and *PdfLayout_ViewInset* (numberp *PdfLayout_ViewInset*)
                           (> *PdfLayout_ViewInset* 0.05) (<= *PdfLayout_ViewInset* 1.0))
                    *PdfLayout_ViewInset* 1.0))
      (setq pw (- (car pmax) (car pmin)))
      (setq ph (- (cadr pmax) (cadr pmin)))
      (setq minPt (car bbox) maxPt (cadr bbox))
      (setq center (list (/ (+ (car minPt) (car maxPt)) 2.0)
                         (/ (+ (cadr minPt) (cadr maxPt)) 2.0)
                         0.0))
      (setq w (- (car maxPt) (car minPt)))
      (setq h (- (cadr maxPt) (cadr minPt)))
      (if (and (> pw 0.0) (> ph 0.0) (> w 0.0) (> h 0.0))
        (progn
          (setq scale (min (/ pw w) (/ ph h)))
          (setq viewH (/ (/ ph scale) inset))
          (if *PdfLayout_Debug*
            (princ (strcat "\n[PDF布局调试] 图纸 " (rtos w 2 2) " x " (rtos h 2 2)
                           " | 视口 " (rtos pw 2 2) " x " (rtos ph 2 2)
                           " | 比例 " (rtos scale 2 4) " | 留白 " (rtos inset 2 3)
                           " | 视图高 " (rtos viewH 2 2)))
          )
          (setq oldCmdEcho (getvar "CMDECHO"))
          (setq oldExpert (getvar "EXPERT"))
          (setvar "CMDECHO" 0)
          (setvar "EXPERT" 5)
          ;; 方式一：ActiveX 直接设置视口视图（中望兼容更稳）
          (setq ok
            (not (vl-catch-all-error-p
                   (vl-catch-all-apply
                     '(lambda ()
                       (vla-put-ViewportOn vpObj :vlax-true)
                       (vla-put-ViewCenter vpObj (vlax-3d-point center))
                       (vla-put-ViewHeight vpObj viewH)
                     )
                     nil))))
          ;; 方式二：命令方式兜底
          (if (not ok)
            (progn
              (vl-catch-all-apply 'vla-put-ViewportOn (list vpObj :vlax-true))
              (command "._MSPACE")
              (command "._ZOOM" "_C" center viewH)
              (command "._PSPACE")
              (setq ok T)
            )
          )
          (if lockVp
            (vl-catch-all-apply 'vla-put-DisplayLocked (list vpObj :vlax-true))
            (vl-catch-all-apply 'vla-put-DisplayLocked (list vpObj :vlax-false))
          )
          (setvar "CMDECHO" oldCmdEcho)
          (setvar "EXPERT" oldExpert)
        )
      )
    )
  )
)

(defun PdfLayout_HideViewportFrame (vpObj / doc layers lname layer)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layers (vla-get-Layers doc))
  (setq lname "视口框")
  (setq layer nil)
  (vlax-for l layers
    (if (= (strcase (vla-get-Name l)) (strcase lname))
      (setq layer l)
    )
  )
  (if (not layer)
    (setq layer (vl-catch-all-apply 'vla-Add (list layers lname)))
  )
  (if (and layer (not (vl-catch-all-error-p layer)))
    (progn
      (if vpObj
        (vl-catch-all-apply 'vla-put-Layer (list vpObj lname))
      )
      (vl-catch-all-apply 'vla-put-LayerOn (list layer :vlax-false))
      (if (member "VLA-PUT-PLOTTABLE" (atoms-family 1))        (vl-catch-all-apply 'vla-put-Plottable (list layer :vlax-false))      )
    )
  )
)
(defun PdfLayout_SetupLayout (layoutName bbox margin framePts lockVp
                              / vps vp vpObj ename)
  (command ".-LAYOUT" "_S" layoutName "")
  (setq vps (PdfLayout_GetLayoutViewports layoutName))
  (if framePts
    (progn
      (PdfLayout_DeleteViewportsExcept layoutName nil)
      (setq ename (PdfLayout_CreateViewport (car framePts) (cadr framePts)))
      (if ename
        (progn
          (setq vpObj (vlax-ename->vla-object ename))
          (PdfLayout_FitViewport vpObj bbox lockVp)
        )
      )
    )
    (if vps
      (progn
        (setq vp (car (PdfLayout_StableSort vps 'PdfLayout_CmpVpArea)))
        (setq vpObj (car vp))
        (PdfLayout_DeleteViewportsExcept layoutName vpObj)
        (PdfLayout_FitViewport vpObj bbox lockVp)
      )
      (progn
        (setq ename (PdfLayout_CreateViewportFromMargin margin))
        (if ename
          (progn
          (setq vpObj (vlax-ename->vla-object ename))
          (PdfLayout_FitViewport vpObj bbox lockVp)
        )
        )
      )
    )
  )
)

;;;-------------------------------------------------------------
;;; 主流程
;;;-------------------------------------------------------------
(defun PdfLayout_Execute (/ params mode filter tmpl count rule lettersStr
                            pg gStart margin overwrite lockVp ok msg drawings nDraw
                            names i idx n conflict framePts p1 p2 created undoOn
                            failedNames msgText autoArrange dlgSel markers pdfFile newObjs
                            namesList)
  (setq params *PdfLayout_Params*)
  (setq mode "marker")
  (setq autoArrange (PdfLayout_GetParam params "AutoArrange"))
  (setq dlgSel (PdfLayout_GetParam params "DlgSel"))
  (setq pdfFile (PdfLayout_GetParam params "PdfFile"))
  (setq filter (PdfLayout_GetParam params "Filter"))
  (setq tmpl (PdfLayout_GetParam params "TemplateLayout"))
  (setq count (PdfLayout_GetParam params "Count"))
  (setq rule (PdfLayout_GetParam params "Rule"))
  (setq lettersStr (PdfLayout_GetParam params "Letters"))
  (setq pg (PdfLayout_GetParam params "PerGroup"))
  (setq gStart (PdfLayout_GetParam params "GroupStart"))
  (setq margin (PdfLayout_GetParam params "Margin"))
  (setq overwrite (PdfLayout_GetParam params "Overwrite"))
  (setq lockVp (PdfLayout_GetParam params "LockViewport"))
  (setq namesList (PdfLayout_GetParam params "NamesList"))
  (setq ok T)
  (if (not pg) (setq pg 6))
  (if (<= pg 0) (setq pg 6))
  (if (not gStart) (setq gStart 1))
  (if (<= gStart 0) (setq gStart 1))
  (if (not margin) (setq margin 5))
  (if (< margin 0) (setq margin 0))

  ;; 1. 模板布局校验
  (if (not (PdfLayout_GetLayoutObj tmpl))
    (progn
      (PdfLayout_Alert "模板布局无效或不存在，操作已取消。")
      (setq ok nil)
    )
  )

  ;; 2. 命名规则校验
  ;; sheet names given -> no naming rule needed
  (if (and ok (not namesList))
    (progn
      (setq msg (PdfLayout_ValidateRule rule lettersStr))
      (if msg
        (progn
          (PdfLayout_Alert msg)
          (setq ok nil)
        )
      )
    )
  )

  ;; 3. 识别图纸
  (if ok
    (progn
      (if (and pdfFile (/= pdfFile ""))
        (setq newObjs
          (if dlgSel
            (PdfLayout_ImportPdfDialog pdfFile)
            (PdfLayout_ImportPdfFile pdfFile)
          )
        )
      )
      (if autoArrange
        (cond
          (newObjs
            (PdfLayout_ArrangeObjsToMarkers newObjs (PdfLayout_ScanMarkers filter)))
          ((or (not pdfFile) (= pdfFile ""))
            ;; 未选择 PDF：排列模型空间里已有全部底图（对应手动导入后只排序的情况）
            (PdfLayout_ArrangePagesToMarkers (PdfLayout_ScanMarkers filter)))
          ;; 已选择 PDF 但导入失败或弹窗被取消：不排列旧底图，避免打乱
        )
      )
      (setq drawings (PdfLayout_ScanMarkerDrawings filter))
      (if (<= count 0) (setq count (length drawings)))
      (setq nDraw (length drawings))
      (if (= nDraw 0)
        (progn
          (PdfLayout_Alert "没有识别到任何图纸。请确认竖线标记块名与弹窗中一致、且 PDF 底图已导入；或改用手动模式一次性框选全部。")
          (setq ok nil)
        )
        (progn
          (if (and (or (= mode "auto") (= mode "marker")) (<= count 0))
            (setq count nDraw)
          )
          (if (> count nDraw)
            (progn
              (princ (strcat "\n识别到 " (itoa nDraw)
                             " 张图纸，少于设置的 " (itoa count)
                             " 个，按 " (itoa nDraw) " 个执行。"))
              (setq count nDraw)
            )
          )
        )
      )
    )
  )

  ;; 4. 生成布局名称
  (if ok
    (progn
      (if namesList
        (progn
          ;; 布局名来自Excel分表：按分表顺序截取 count 个
          (setq names nil i 0)
          (while (and (< i count) (< i (length namesList)))
            (setq names (append names (list (nth i namesList))))
            (setq i (1+ i))
          )
        )
        (setq names (PdfLayout_GenNames rule lettersStr pg gStart count))
      )
      (if (not names)
        (progn
          (PdfLayout_Alert "命名规则无法生成足够数量的不重复名称，请检查规则、字母列表和每组张数。")
          (setq ok nil)
        )
        (progn
          (if (PdfLayout_HasDuplicate names)
            (progn
              (PdfLayout_Alert "生成的布局名称存在重复，请调整命名规则。")
              (setq ok nil)
            )
            (progn
              (setq conflict nil)
              (foreach n names
                (if (not (PdfLayout_ValidLayoutName n))
                  (setq conflict n)
                )
              )
              (if conflict
                (progn
                  (PdfLayout_Alert (strcat "布局名称 " conflict
                                 " 包含非法字符(< > / \\ \" : ; ? * | , = 等)。"))
                  (setq ok nil)
                )
              )
            )
          )
          (if (and ok (vl-some '(lambda (n) (= (strcase n) (strcase tmpl))) names))
            (progn
              (PdfLayout_Alert "生成的名称中包含模板布局名，请调整命名规则或更换模板。")
              (setq ok nil)
            )
          )
          (if ok
            (progn
              (setq conflict nil)
              (foreach n names
                (if (and (PdfLayout_LayoutExists n) (not overwrite))
                  (setq conflict n)
                )
              )
              (if conflict
                (progn
                  (PdfLayout_Alert (strcat "布局 " conflict
                                 " 已存在。请勾选“覆盖同名布局”或修改命名规则。"))
                  (setq ok nil)
                )
              )
            )
          )
        )
      )
    )
  )

  ;; 5. 执行：复制布局 + 视口对应
  (if ok
    (progn
      (if overwrite
        (foreach n names
          (if (PdfLayout_LayoutExists n)
            (PdfLayout_DeleteLayout n)
          )
        )
      )
      ;; 模板布局视口/图框处理
      (setq framePts (PdfLayout_GetViewportFrame tmpl))
      (if (not framePts)
        (progn
          (command ".-LAYOUT" "_S" tmpl "")
          (setq p1 (getpoint "\n模板布局中没有视口，请点取图框第一角（回车则按纸张边距创建视口）: "))
          (if p1 (setq p2 (getpoint p1 "\n请点取图框对角: ")))
          (if (and p1 p2) (setq framePts (list p1 p2)))
        )
      )
      (setq created nil)
      (setq undoOn (= (logand (getvar "UNDOCTL") 1) 1))
      (setq *PdfLayout_UndoOn* undoOn)
      (if undoOn (command "._UNDO" "_BE"))
      (setq *PdfLayout_Running* T)
      (setq *PdfLayout_CreatedLayouts* nil)
      (setq idx 0)
      (foreach n names
        (vl-catch-all-apply 'PdfLayout_Prog
          (list (strcat "创建 " (itoa (1+ idx)) " / " (itoa (length names)))))
        (princ (strcat "\n  创建 " (itoa (1+ idx)) "/" (itoa (length names))
                       " : " n " ..."))
        (if (PdfLayout_CopyLayout tmpl n)
          (progn
            (setq created (append created (list n)))
            (setq *PdfLayout_CreatedLayouts* created)
            (PdfLayout_SetupLayout n (nth idx drawings) margin framePts lockVp)
            (princ " 成功")
          )
          (progn
            (princ " 失败")
            (setq failedNames (append failedNames (list n)))
          )
        )
        (setq idx (1+ idx))
      )
      (if undoOn (command "._UNDO" "_E"))
      (setq *PdfLayout_Running* nil)
      (setq *PdfLayout_CreatedLayouts* nil)
      (setq *PdfLayout_UndoOn* nil)
      (if created
        (command ".-LAYOUT" "_S" (car created) "")
      )
      (princ (strcat "\n完成：共创建 " (itoa (length created))
                     " 个布局，模型图纸已按顺序对应到各布局视口。"))
      (if failedNames
        (progn
          (princ (strcat " 失败 " (itoa (length failedNames)) " 个:"))
          (foreach f failedNames
            (princ (strcat " " f))
          )
        )
      )
      (setq msgText (strcat "布局生成完成\n\n成功创建 " (itoa (length created))
                            " / " (itoa (length names)) " 个布局"))
      (if failedNames
        (progn
          (setq msgText (strcat msgText "\n失败 " (itoa (length failedNames)) " 个："))
          (foreach f failedNames
            (setq msgText (strcat msgText " " f))
          )
        )
      )
      (PdfLayout_Alert msgText)
    )
  )
  ok
)

;;;-------------------------------------------------------------
;;; 查找DCL文件
;;;-------------------------------------------------------------
(defun PdfLayout_FileExists (path / f)
  (setq f (open path "r"))
  (if f
    (progn
      (close f)
      T
    )
    nil
  )
)

(defun PdfLayout_WriteDcl (dir / path f)
  (setq path (strcat dir "PdfLayout.dcl"))
  (setq f (open path "w"))
  (if f
    (progn
      (foreach line *PdfLayout_DclLines*
        (princ line f)
        (princ "\n" f)
      )
      (close f)
      T
    )
    nil
  )
)

(defun PdfLayout_FindDcl (/ dir)
  ;; 每次打开弹窗前都重写内置 DCL，防止系统临时目录残留旧版
  ;; DCL（缺少新控件）导致中望CAD报“类型不正确”错误
  (setq dir (getvar "TEMPPREFIX"))
  (if (not (PdfLayout_WriteDcl dir))
    (progn
      (setq dir (getvar "DWGPREFIX"))
      (PdfLayout_WriteDcl dir)
    )
  )
  (setq *PdfLayout_DclWritten* T)
  (strcat dir "PdfLayout.dcl")
)

;;;-------------------------------------------------------------
;;; 对话框
;;;-------------------------------------------------------------
(defun PdfLayout_InitDialog (/ layouts tmp activeName idx)
  (princ "\n[调试] 初始化主对话框")
  (setq layouts (PdfLayout_GetLayoutNames))
  (if layouts
    (progn
      (PdfLayout_SetList "tmpl_layout" layouts)
      (setq activeName (vla-get-Name (vla-get-ActiveLayout
                                      (vla-get-ActiveDocument
                                        (vlax-get-Acad-Object)))))
      (setq tmp (if (member activeName layouts) activeName (car layouts)))
      (setq idx 0)
      (foreach l layouts
        (if (= (strcase l) (strcase tmp))
          (set_tile "tmpl_layout" (itoa idx))
        )
        (setq idx (1+ idx))
      )
    )
  )
  (PdfLayout_SetList "marker_name" (PdfLayout_GetMarkerNameList))
  (set_tile "marker_name" (itoa (PdfLayout_MarkerNameIndex "pdf")))
  (set_tile "count" (itoa (length (PdfLayout_GetPdfUnderlays))))
  (set_tile "overwrite" "0")
  (if (and *PdfLayout_LastNamesXlsx* (/= *PdfLayout_LastNamesXlsx* ""))
    (set_tile "names_xlsx" *PdfLayout_LastNamesXlsx*)
  )  (if (and *PdfLayout_LayRule* (/= *PdfLayout_LayRule* ""))
    (progn
      (set_tile "rule" *PdfLayout_LayRule*)
      (set_tile "letters" *PdfLayout_LayLetters*)
      (set_tile "per_group" (itoa *PdfLayout_LayPerGroup*))
      (set_tile "g_start" (itoa *PdfLayout_LayGStart*))
    )
  )
  (set_tile "rule" "INV{G2}{L}{N2}")
  (set_tile "letters" "AB")
  (set_tile "per_group" "6")
  (set_tile "g_start" "1")
  (set_tile "margin" "5")
  (PdfLayout_UpdateFoundInfo)
  (PdfLayout_UpdatePreview)
)

(defun PdfLayout_UpdateFoundInfo (/ mnList mn n)
  (setq mnList (PdfLayout_GetMarkerNameList))
  (setq mn (nth (atoi (PdfLayout_GetTileStr "marker_name")) mnList))
  (if (not mn) (setq mn "pdf"))
  (setq n (length (PdfLayout_ScanMarkers mn)))
  (set_tile "found_info"
    (if (= n 0)
      (strcat "未识别到竖线标记“" mn "”，请检查竖线块名")
      (strcat "已识别到 " (itoa n) " 个竖线标记，按 行内左→右、行间上→下 匹配")
    )
  )
)

(defun PdfLayout_UpdatePreview (/ count rule lettersStr pg gStart names i s)
  (setq count (atoi (get_tile "count")))
  (setq rule (get_tile "rule"))
  (setq lettersStr (get_tile "letters"))
  (setq pg (atoi (get_tile "per_group")))
  (if (<= pg 0) (setq pg 1))
  (setq gStart (atoi (get_tile "g_start")))
  (if (<= gStart 0) (setq gStart 1))
  (if (and *PdfLayout_NamesXlsxList* (/= (PdfLayout_GetTileStr "names_xlsx") ""))
    (progn
      (setq names *PdfLayout_NamesXlsxList*)
      (setq s "")
      (setq i 0)
      (while (and (< i (length names)) (< i 40))
        (setq s (strcat s (nth i names) "\n"))
        (setq i (1+ i))
      )
      (if (> (length names) 40)
        (setq s (strcat s "…共 " (itoa (length names)) " 个分表"))
      )
      (set_tile "preview" s)
    )
    (if (<= count 0)
      (set_tile "preview" "复制数量：0 表示按识别到的标记数量")
      (progn
        (setq names (PdfLayout_GenNames rule lettersStr pg gStart count))
        (if names
          (progn
            (setq s "")
            (setq i 0)
            (while (and (< i count) (< i 40))
              (setq s (strcat s (nth i names) "\n"))
              (setq i (1+ i))
            )
            (if (> count 40)
              (setq s (strcat s "…共 " (itoa count) " 个"))
            )
            (set_tile "preview" s)
          )
          (set_tile "preview" "规则无法生成足够的不重复名称，请检查参数")
        )
      )
    )
  )
)

(defun PdfLayout_GetMarkerNameList (/ doc ms obj name names)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq names (list "pdf"))
  (vlax-for obj ms
    (if (= (vla-get-ObjectName obj) "AcDbBlockReference")
      (progn
        (setq name (vla-get-Name obj))
        (if (and name (= (type name) (quote STR))
                 (not (member (strcase name) (mapcar (quote strcase) names))))
          (setq names (append names (list name)))
        )
      )
    )
  )
  names
)

(defun PdfLayout_MarkerNameIndex (name / lst idx)
  (setq lst (PdfLayout_GetMarkerNameList))
  (setq idx 0)
  (while (and (< idx (length lst))
              (/= (strcase (nth idx lst)) (strcase name)))
    (setq idx (1+ idx))
  )
  (if (< idx (length lst)) idx 0)
)

(defun PdfLayout_OnAccept (/ mode filter tmpl count rule lettersStr pg gStart
                            margin overwrite lockVp mnList msg namesXlsx xNames)
  (setq mode "marker")
  (setq mnList (PdfLayout_GetMarkerNameList))
  (setq filter (nth (atoi (PdfLayout_GetTileStr "marker_name")) mnList))
  (if (not filter) (setq filter "pdf"))
  (setq tmpl (nth (atoi (get_tile "tmpl_layout"))
                  (PdfLayout_GetLayoutNames)))
  (setq count (atoi (get_tile "count")))
  (setq rule (get_tile "rule"))
  (setq lettersStr (get_tile "letters"))
  (setq pg (atoi (get_tile "per_group")))
  (setq gStart (atoi (get_tile "g_start")))
  (setq margin (atof (get_tile "margin")))
  (setq overwrite (= (get_tile "overwrite") "1"))
  (setq lockVp (= (get_tile "lock_vp") "1"))
  (setq namesXlsx (PdfLayout_GetTileStr "names_xlsx"))
  (setq xNames nil)
  (if (and namesXlsx (/= namesXlsx ""))
    (progn
      (setq xNames (PdfLayout_GetXlsxSheetNames namesXlsx))
      (if (not xNames)
        (PdfLayout_Alert "无法读取Excel分表名，请确认文件存在且未被占用。")
        (setq count (length xNames))
      )
    )
  )

  (if (not (PdfLayout_GetLayoutObj tmpl))
    (PdfLayout_Alert "请选择模板布局（当前图纸需至少有一个布局）")
    (progn
      (setq msg (PdfLayout_ValidateRule rule lettersStr))
      (if msg
        (PdfLayout_Alert msg)
        (if (and namesXlsx (/= namesXlsx "") (not xNames))
          nil
          (progn
            (setq *PdfLayout_Params*
              (list
                (cons "Mode"           mode)
                (cons "Filter"         filter)
                (cons "AutoArrange"    T)
                (cons "DlgSel"         nil)
                (cons "PdfFile"        "")
                (cons "TemplateLayout" tmpl)
                (cons "Count"          count)
                (cons "Rule"           rule)
                (cons "Letters"        lettersStr)
                (cons "PerGroup"       pg)
                (cons "GroupStart"     gStart)
                (cons "Margin"         margin)
                (cons "Overwrite"      overwrite)
                (cons "LockViewport"   lockVp)
                (cons "NamesList"      xNames)
              )
            )
            (done_dialog 1)
          )
        )
      )
    )
  )
)

(defun c:pdflayout (/ dcl_id dclPath result)
  (vl-load-com)
  (setq dclPath (PdfLayout_FindDcl))
  (if (not dclPath)
    (progn
      (PdfLayout_Alert "未找到 PdfLayout.dcl 文件，请把 PdfLayout.dcl 与插件放在同一目录后重试。")
    )
    (progn
      (setq dcl_id (load_dialog dclPath))
      (if (minusp dcl_id)
        (progn
          (PdfLayout_Alert "加载 PdfLayout.dcl 失败，请确认文件完整后重试。")
        )
        (progn
          (if (not (new_dialog "PdfLayout" dcl_id))
            (progn
              (unload_dialog dcl_id)
              (PdfLayout_Alert "启动对话框失败，请重新运行 PDFLAYOUT。")
            )
            (progn
              (PdfLayout_LoadSettings)
              (PdfLayout_InitDialog)
              (action_tile "rule"      "(PdfLayout_UpdatePreview)")
              (action_tile "letters"   "(PdfLayout_UpdatePreview)")
              (action_tile "per_group" "(PdfLayout_UpdatePreview)")
              (action_tile "g_start"   "(PdfLayout_UpdatePreview)")
              (action_tile "count"     "(PdfLayout_UpdatePreview)")
              (action_tile "marker_name" "(PdfLayout_UpdateFoundInfo)")
              (action_tile "btn_names_xlsx" "(PdfLayout_PickNamesXlsx)")
              (action_tile "btn_arrange"
                "(setq *PdfLayout_ArrangeOnly* T)
                 (setq *PdfLayout_ArrangeOnlyName*
                   (nth (atoi (get_tile \"marker_name\")) (PdfLayout_GetMarkerNameList)))
                 (done_dialog 2)")
              (action_tile "accept"    "(PdfLayout_OnAccept)")
              (action_tile "cancel"    "(done_dialog 0)")
              (setq result (start_dialog))
              (unload_dialog dcl_id)
              (if (= result 1)
                (PdfLayout_Execute)
                (if (= result 2)
                  (PdfLayout_DoArrangeOnly)
                )
              )
            )
          )
        )
      )
    )
  )
  (princ)
)

(defun PdfLayout_DoArrangeOnly (/ mn markers undoOn)
  ;; 只做自动排序：把模型空间里已导入的 PDF 底图按 行内左→右、行间上→下
  ;; 排到竖线标记上（不创建布局）；用于手动 PDFATTACH 导入后的排序
  (vl-load-com)
  (setq mn (if *PdfLayout_ArrangeOnlyName* *PdfLayout_ArrangeOnlyName* "pdf"))
  (setq markers (PdfLayout_ScanMarkers mn))
  (if (not markers)
    (PdfLayout_Alert (strcat "未识别到竖线标记“" mn "”，请检查竖线块名"))
    (progn
      (setq undoOn (= (logand (getvar "UNDOCTL") 1) 1))
      (if undoOn (command "._UNDO" "_BE"))
      (PdfLayout_ArrangePagesToMarkers markers)
      (if undoOn (command "._UNDO" "_E"))
    )
  )
  (setq *PdfLayout_ArrangeOnly* nil)
  (setq *PdfLayout_ArrangeOnlyName* nil)
  (princ)
)

;;;-------------------------------------------------------------
;;; 自检命令：PDFLAYOUTTEST（验证命名规则引擎，无需图纸）
;;;-------------------------------------------------------------
;;;-------------------------------------------------------------
;;; 多行文字按顺序命名
;;;-------------------------------------------------------------
(defun PdfLayout_NameAtPrefix (prefix num digits / s)
  (setq s (itoa num))
  (if (> digits (strlen s))
    (repeat (- digits (strlen s))
      (setq s (strcat "0" s))
    )
  )
  (strcat prefix s)
)

(defun PdfLayout_ReadNameFile (path / f line names comma first)
  (setq names nil)
  (setq f (open path "r"))
  (if f
    (progn
      (setq first T)
      (while (setq line (read-line f))
        (if first
          (progn
            (if (and (>= (strlen line) 3)
                     (= (ascii (substr line 1 1)) 239))
              (setq line (substr line 4))
            )
            (setq first nil)
          )
        )
        (setq line (vl-string-trim " " line))
        (if (/= line "")
          (progn
            (setq comma (vl-string-search "," line))
            (if comma
              (setq line (vl-string-trim " \"" (substr line 1 comma)))
            )
            (setq line (vl-string-trim " \"" line))
            (if (/= line "")
              (setq names (append names (list line)))
            )
          )
        )
      )
      (close f)
    )
  )
  names
)

(defun PdfLayout_NumKey (s / out i c)
  (setq out "" i 1)
  (while (<= i (strlen s))
    (setq c (substr s i 1))
    (if (and (>= c "0") (<= c "9"))
      (setq out (strcat out c))
    )
    (setq i (1+ i))
  )
  (if (= out "") 0 (atoi out))
)

(defun PdfLayout_JoinLabels (lca lcb / out)
  (setq out "")
  (if (/= lca "") (setq out lca))
  (if (/= lcb "")
    (setq out (if (= out "") lcb (strcat out "/" lcb)))
  )
  out
)

(defun PdfLayout_CommonPrefix (names / p i c ok)
  (setq p "" i 1 ok T)
  (if names
    (progn
      (while (and ok (<= i (strlen (car names))))
        (setq c (substr (car names) i 1))
        (setq ok T)
        (foreach n names
          (if (or (< (strlen n) i) (/= (substr n i 1) c))
            (setq ok nil)
          )
        )
        (if ok (setq p (strcat p c)))
        (setq i (1+ i))
      )
    )
  )
  p
)

(defun PdfLayout_CharKind (c / n)
  (setq n (ascii c))
  (cond
    ((and (>= n 48) (<= n 57)) "D")
    ((or (and (>= n 65) (<= n 90)) (and (>= n 97) (<= n 122))) "L")
    (t "O")
  )
)

(defun PdfLayout_RunShape (s / out i c kind)
  ;; 把字符串按 数字/字母/其他 切成连续段，返回 ((类型 文本) ...)
  (setq out nil i 1)
  (while (<= i (strlen s))
    (setq c (substr s i 1))
    (setq kind (PdfLayout_CharKind c))
    (if (and out (= (caar out) kind))
      (setq out (cons (list kind (strcat (cadar out) c)) (cdr out)))
      (setq out (cons (list kind c) out))
    )
    (setq i (1+ i))
  )
  (reverse out)
)

(defun PdfLayout_StrMember (s lst)
  (vl-some '(lambda (x) (= (strcase x) (strcase s))) lst)
)

(defun PdfLayout_DetectRuleFromNames (names / prefix rems shapes tpl same r kind txt
                                      rule letters seenL digitRun counts j lastD
                                      base cnt maxC gStart fv gen)
  ;; 从一组名称自动识别命名规律，返回 (规则 字母列表 每组张数 编号起始) 或 nil
  (setq names (vl-remove-if '(lambda (s) (or (null s) (= s ""))) names))
  (if (< (length names) 2)
    nil
    (progn
      (setq prefix (PdfLayout_CommonPrefix names))
      ;; 前缀末尾的数字属于变化的编号，去掉，避免吃掉编号
      (while (and (> (strlen prefix) 0)
                  (= (PdfLayout_CharKind (substr prefix (strlen prefix))) "D"))
        (setq prefix (substr prefix 1 (1- (strlen prefix))))
      )
      (setq rems (mapcar '(lambda (n) (substr n (1+ (strlen prefix)))) names))
      (setq shapes (mapcar 'PdfLayout_RunShape rems))
      (setq tpl (car shapes) same T)
      (foreach sh (cdr shapes)
        (if (or (/= (length sh) (length tpl))
                (not (apply 'and (mapcar '(lambda (a b)
                                            (and (= (car a) (car b))
                                                 (= (strlen (cadr a)) (strlen (cadr b)))))
                                          sh tpl))))
          (setq same nil)
        )
      )
      (if (not same)
        nil
        (progn
          ;; 字母列表：从所有名称中收集字母段，不只看第一个名称
          (setq letters "" seenL nil)
          (foreach n names
            (foreach r (PdfLayout_RunShape (substr n (1+ (strlen prefix))))
              (if (and (= (car r) "L") (not (member (cadr r) seenL)))
                (setq seenL (append seenL (list (cadr r))))
              )
            )
          )
          (if seenL (setq letters (apply 'strcat seenL)))
          (setq rule prefix digitRun 0)
          (foreach r tpl
            (setq kind (car r) txt (cadr r))
            (cond
              ((= kind "D")
                (setq digitRun (1+ digitRun))
                (if (= digitRun 1)
                  (setq rule (strcat rule "{G" (itoa (strlen txt)) "}"))
                  (setq rule (strcat rule "{N" (itoa (strlen txt)) "}"))
                )
              )
              ((= kind "L")
                (setq rule (strcat rule "{L}"))
              )
              (t
                (setq rule (strcat rule txt))
              )
            )
          )
          (if seenL (setq letters (apply 'strcat seenL)))
          ;; 每组张数：按“除最后一个数字段外的基准”分组，取最大组数
          (setq counts nil)
          (foreach n names
            (setq sh (PdfLayout_RunShape (substr n (1+ (strlen prefix)))))
            (setq lastD -1 j 0)
            (foreach r sh
              (if (= (car r) "D") (setq lastD j))
              (setq j (1+ j))
            )
            (setq base "")
            (setq j 0)
            (foreach r sh
              (if (/= j lastD) (setq base (strcat base (cadr r))))
              (setq j (1+ j))
            )
            (setq base (strcat prefix base))
            (setq cnt (if (assoc base counts) (cdr (assoc base counts)) 0))
            (setq counts (subst (cons base (1+ cnt)) (assoc base counts) counts))
          )
          (setq maxC 1)
          (foreach c counts
            (if (> (cdr c) maxC) (setq maxC (cdr c)))
          )
          (setq perGroup maxC)
          ;; 编号起始：第一个数字段的最小值
          (setq gStart nil)
          (foreach n names
            (setq sh (PdfLayout_RunShape (substr n (1+ (strlen prefix)))))
            (setq fv nil)
            (foreach r sh
              (if (and (null fv) (= (car r) "D"))
                (setq fv (atoi (cadr r)))
              )
            )
            (if (and fv (or (null gStart) (< fv gStart)))
              (setq gStart fv)
            )
          )
          (if (null gStart) (setq gStart 1))
          ;; 验证：用识别出的规则重新生成，与原名一致才算识别成功
          (setq gen (PdfLayout_GenNames rule letters perGroup gStart (length names)))
          (if (and gen (= (length gen) (length names))
                   (not (vl-some '(lambda (x) (not (PdfLayout_StrMember x names))) gen))
                   (not (vl-some '(lambda (x) (not (PdfLayout_StrMember x gen))) names)))
            (list rule letters perGroup gStart)
            nil
          )
        )
      )
    )
  )
)
(defun PdfLayout_GetXlsxSheetNames (path / xl wbs wb shs names i sh hadExcel)
  ;; 读取 Excel 工作簿的所有分表名（按表顺序），用于“布局名来自Excel分表”
  (setq names nil)
  (setq hadExcel (vl-catch-all-apply 'vlax-get-object (list "Excel.Application")))
  (setq hadExcel (and hadExcel (not (vl-catch-all-error-p hadExcel))))
  (setq xl (vl-catch-all-apply 'vlax-create-object (list "Excel.Application")))
  (if (and xl (not (vl-catch-all-error-p xl)))
    (progn
      (vl-catch-all-apply 'vlax-put-property (list xl 'Visible 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'DisplayAlerts 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'AskToUpdateLinks 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'AutomationSecurity 3))
      (setq wbs (vl-catch-all-apply 'vlax-get-property (list xl 'Workbooks)))
      (setq wb (vl-catch-all-apply 'vlax-invoke-method (list wbs 'Open path 0 1)))
      (if (and wb (not (vl-catch-all-error-p wb)))
        (progn
          (setq shs (vl-catch-all-apply 'vlax-get-property (list wb 'Sheets)))
          (if (and shs (not (vl-catch-all-error-p shs)))
            (progn
              (setq i 1)
              (while (<= i (vlax-get-property shs 'Count))
                (setq sh (vl-catch-all-apply 'vlax-get-property (list shs 'Item i)))
                (if (not (vl-catch-all-error-p sh))
                  (setq names (append names (list (vlax-get-property sh 'Name))))
                )
                (setq i (1+ i))
              )
            )
          )
          (vl-catch-all-apply 'vlax-invoke-method (list wb 'Close 0))
        )
      )
      ;; 原本没在运行才 Quit；并释放所有 COM 引用，避免 Excel 挂在后台占内存
      (if (not hadExcel)
        (vl-catch-all-apply 'vlax-invoke-method (list xl 'Quit))
      )
      (if (and shs (not (vl-catch-all-error-p shs)))
        (vl-catch-all-apply 'vlax-release-object (list shs))
      )
      (if (and sh (not (vl-catch-all-error-p sh)))
        (vl-catch-all-apply 'vlax-release-object (list sh))
      )
      (if (and wb (not (vl-catch-all-error-p wb)))
        (vl-catch-all-apply 'vlax-release-object (list wb))
      )
      (if (and wbs (not (vl-catch-all-error-p wbs)))
        (vl-catch-all-apply 'vlax-release-object (list wbs))
      )
      (if (and xl (not (vl-catch-all-error-p xl)))
        (vl-catch-all-apply 'vlax-release-object (list xl))
      )
    )
  )
  names
)

(defun PdfLayout_CellStr (v / s)
  (if (null v)
    ""
    (progn
      ;; ZWCAD 的单元格值是 VARIANT，先解包成普通值再转字符串
      (setq s (vl-catch-all-apply 'vlax-variant-value (list v)))
      (if (not (vl-catch-all-error-p s))
        (setq v s)
      )
      (if (null v)
        ""
        (progn
          (setq s (vl-catch-all-apply 'vl-princ-to-string (list v)))
          (if (vl-catch-all-error-p s) "" s)
        )
      )
    )
  )
)

(defun PdfLayout_JoinLabelsList (labels / out)
  (setq out "")
  (foreach s labels
    (if (and s (/= s ""))
      (setq out (if (= out "") s (strcat out "/" s)))
    )
  )
  out
)

(defun PdfLayout_SortPairsByOrder (pairs order)
  (cond
    ((= order "1") (PdfLayout_SortByPositionLR pairs))
    ((= order "2") (PdfLayout_SortByPosition pairs))
    ((= order "3") (PdfLayout_SortByPositionRL pairs))
    ((= order "4") (PdfLayout_SortByPositionBT pairs))
    ((= order "5") (PdfLayout_SortByPositionLRBT pairs))
    ((= order "6") (PdfLayout_SortByPositionRLBT pairs))
    ((= order "7") (PdfLayout_SortByPositionTBR pairs))
    ((= order "8") (PdfLayout_SortByPositionBTR pairs))
    (t pairs)
  )
)

(defun PdfLayout_BuildSchemeGrid (pairs order / sorted idxMap i p ys ymax ymin
                                  tol byY cur curY rows item rowX line out idx
                                  rowY)
  (while (> (length pairs) 2000)
    (setq pairs (reverse (cdr (reverse pairs))))
  )
  (setq sorted (PdfLayout_SortPairsSmart pairs order))
  (setq idxMap nil i 1)
  (foreach p sorted
    (setq idxMap (cons (cons p i) idxMap))
    (setq i (1+ i))
  )
  (setq ys (mapcar '(lambda (q) (cadr (PdfLayout_BBoxCenter (cdr q)))) pairs))
  (setq ymax (apply 'max ys) ymin (apply 'min ys))
  (setq tol (max 0.25 (* 0.001 (if (and *PdfLayout_RowTol* (> *PdfLayout_RowTol* 0)) *PdfLayout_RowTol* 10) (- ymax ymin))))
  (setq byY (PdfLayout_StableSort
              (mapcar '(lambda (q) (cons (cadr (PdfLayout_BBoxCenter (cdr q))) q)) pairs)
              'PdfLayout_CmpYGreater))
  (setq rows nil cur nil curY nil)
  (foreach item byY
    (if (and curY (> (- curY (car item)) tol))
      (progn
        (setq rows (append rows (list cur)))
        (setq cur nil)
      )
    )
    (setq cur (append cur (list (cdr item))))
    (setq curY (car item))
  )
  (if cur (setq rows (append rows (list cur))))
  ;; 行按最高点 Y 从大到小排序（上到下），保证显示顺序稳定
  (setq rows (PdfLayout_StableSort rows 'PdfLayout_CmpRowTop))
  ;; 示意图固定按物理位置从上到下显示，数字表示第几个被命名
  (setq out nil)
  (foreach row rows
    (setq rowX (PdfLayout_StableSort row 'PdfLayout_CmpXAsc))
    (setq line "")
    (foreach q rowX
      (setq idx (cdr (assoc q idxMap)))
      (if (= line "")
        (setq line (itoa idx))
        (setq line (strcat line "  " (if (< idx 10) (strcat " " (itoa idx)) (itoa idx))))
      )
    )
    (setq out (append out (list line)))
  )
  out
)

(defun PdfLayout_SetList (key items / s)
  (start_list key)
  (foreach s items
    (if (eq (type s) 'STR)
      (add_list s)
    )
  )
  (end_list)
)

(defun PdfLayout_LbdBgIndex (aci / i p idx)
  (setq idx 0 i 0)
  (foreach p *PdfLayout_LbdBgList*
    (if (= (cdr p) aci) (setq idx i))
    (setq i (1+ i))
  )
  idx
)
(defun PdfLayout_GetTileStr (key / v)
  (setq v (get_tile key))
  (if (eq (type v) 'STR) v "")
)

(defun PdfLayout_GetTileInt (key dflt / v)
  (setq v (PdfLayout_GetTileStr key))
  (if (= v "") dflt (atoi v))
)

(defun PdfLayout_GetTileReal (key dflt / v)
  (setq v (PdfLayout_GetTileStr key))
  (if (= v "") dflt (atof v))
)


(defun PdfLayout_OrderDesc (ord / out)
  (setq out (cond
    ((= ord "1") "1 列优先: 左→右列、列内上→下")
    ((= ord "2") "2 行优先: 上→下行、行内左→右")
    ((= ord "3") "3 列优先: 右→左列、列内上→下")
    ((= ord "4") "4 行优先: 下→上行、行内左→右")
    ((= ord "5") "5 列优先: 左→右列、列内下→上")
    ((= ord "6") "6 列优先: 右→左列、列内下→上")
    ((= ord "7") "7 行优先: 上→下行、行内右→左")
    ((= ord "8") "8 行优先: 下→上行、行内右→左")
    (t "1")
  ))
  out
)
(defun PdfLayout_OrderPreviewClear ()
  (foreach e *PdfLayout_OrderPreviewEnts*
    (vl-catch-all-apply 'vla-Delete (list (vlax-ename->vla-object e)))
  )
  (setq *PdfLayout_OrderPreviewEnts* nil)
)

(defun PdfLayout_OrderPreviewShow (/ doc sorted i obj owner lay hgt pt ins m)
  (PdfLayout_OrderPreviewClear)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq sorted (PdfLayout_SortPairsSmart *PdfLayout_PreviewPairs* *PdfLayout_PreviewOrder*))
  (setq i 1)
  (foreach pair sorted
    (setq obj (car pair))
    (setq owner (vl-catch-all-apply
                  '(lambda () (vlax-ename->vla-object
                                (cdr (assoc 330 (entget (vlax-vla-object->ename obj))))))
                  nil))
    (setq hgt (vl-catch-all-apply 'vla-get-Height (list obj)))
    (if (or (not hgt) (vl-catch-all-error-p hgt) (<= hgt 0.0))
      (setq hgt 0.05)
    )
    (setq pt (PdfLayout_BBoxCenter (cdr pair)))
    (setq ins (list (+ (car pt) (* hgt 0.4)) (- (cadr pt) (* hgt 0.4)) 0.0))
    (if (and owner (not (vl-catch-all-error-p owner)))
      (progn
        (setq m (vl-catch-all-apply 'vla-AddMText
                  (list owner (vlax-3d-point ins) (* hgt 6.0) (itoa i))))
        (if (and m (not (vl-catch-all-error-p m)))
          (progn
            (vl-catch-all-apply 'vla-put-Height (list m (* hgt 0.7)))
            (vl-catch-all-apply 'vla-put-Color (list m 1))
            (setq lay (PdfLayout_EnsureLayer "PDF布局_顺序预览"))
            (if (and lay (not (vl-catch-all-error-p lay)))
              (vl-catch-all-apply 'vla-put-Layer (list m "PDF布局_顺序预览"))
            )
            (setq *PdfLayout_OrderPreviewEnts*
                  (append *PdfLayout_OrderPreviewEnts*
                          (list (vlax-vla-object->ename m))))
          )
        )
      )
    )
    (setq i (1+ i))
  )
  (vl-catch-all-apply 'vla-Regen (list doc acAllViewports))
)

(defun PdfLayout_OrderPreviewRefresh ()
  (if (= (PdfLayout_GetTileStr "ord_prev") "1")
    (PdfLayout_OrderPreviewShow)
    (PdfLayout_OrderPreviewClear)
  )
)

(defun PdfLayout_SettingsPathLsp (/ dir)
  ;; LSP 目录取不到时（中望CAD），把 PdfLayout.ini 固定放在系统临时目录，
  ;; 这样换图纸、换目录后记忆和方案仍然存在
  (setq dir (if (and *PdfLayout_LspDir* (/= *PdfLayout_LspDir* ""))
              *PdfLayout_LspDir*
              (getvar "TEMPPREFIX")))
  (strcat dir "PdfLayout.ini")
)

(defun PdfLayout_LoadSettings (/ f line pos k v first)
  (princ "\n[调试] 读取记忆设置")
  (setq *PdfLayout_PreviewPrefix* "STR")
  (setq *PdfLayout_PreviewStart* 1)
  (setq *PdfLayout_PreviewDigits* 2)
  (setq *PdfLayout_PreviewOrder* "1")
  (setq *PdfLayout_PreviewSrc* "1")
  (setq *PdfLayout_PreviewFilePath* "")
  (setq *PdfLayout_PreviewBgMode* "0")
  (setq *PdfLayout_PreviewBgColor* 7)
  (setq *PdfLayout_PreviewBgScale* 1.5)
  (setq *PdfLayout_IniPairs* nil)
(setq *PdfLayout_PythonPath* "")
(setq *PdfLayout_LbdTextHeight* 0.15)
(setq *PdfLayout_LbdBgColor* 1)
(setq *PdfLayout_LbdGap* 1.0)
(setq *PdfLayout_LbdBgList* (list (cons "红" 1) (cons "黄" 2) (cons "绿" 3) (cons "青" 4) (cons "蓝" 5) (cons "洋红" 6) (cons "白" 7) (cons "灰" 8)))
(setq *PdfLayout_ExcludeRect* nil)
  (setq *PdfLayout_OrderPreviewEnts* nil)
(setq *PdfLayout_GridRows* 4)
  (setq *PdfLayout_GridCols* 5)
  (setq *PdfLayout_GridRowSp* 10.0)
  (setq *PdfLayout_GridColSp* 20.0)
  (setq *PdfLayout_GridH* 1.7)
  (setq *PdfLayout_GridHRatio* 0.3)
  (setq *PdfLayout_GridGeom* "1")
  (setq *PdfLayout_GridRot* 0)
  (setq *PdfLayout_GridBg* "fill")
  (setq *PdfLayout_GridBgColor* 1)
  (setq *PdfLayout_GridBgRGB* 255)
  (setq *PdfLayout_GridTxtColor* 7)
  (setq *PdfLayout_GridTxtRGB* 16777215)
  (setq *PdfLayout_GridTxtTrue* T)
  (setq *PdfLayout_GridBgScale* 1.0)
  (setq *PdfLayout_GridPrefix* "CIR")
  (setq *PdfLayout_GridStartN* 1)
  (setq *PdfLayout_GridDigits* 2)
  (setq *PdfLayout_GridSrc* "auto")
  (setq *PdfLayout_GridFile* "")
  (setq *PdfLayout_GridNames* nil)
  (setq *PdfLayout_GridStart* nil)
  (setq *PdfLayout_GridP1* nil)
  (setq *PdfLayout_GridP2* nil)
  (setq *PdfLayout_GridExtX* 0.0)
  (setq *PdfLayout_GridExtY* 0.0)
  (setq *PdfLayout_GridHMode* "auto")
  (setq *PdfLayout_GridMT* 0.0)
  (setq *PdfLayout_GridMB* 0.0)
  (setq *PdfLayout_GridML* 0.0)
  (setq *PdfLayout_GridMR* 0.0)
  (setq *PdfLayout_GridFirstX* 0.0)
  (setq *PdfLayout_GridFirstY* 0.0)
  (setq *PdfLayout_GridColDir* 1)
  (setq *PdfLayout_GridRowDir* -1)
  (setq *PdfLayout_LbdRows* nil)
  (setq *PdfLayout_PreviewLbds* nil)
  (setq f (open (PdfLayout_SettingsPathLsp) "r"))
  (if (not f)
    (setq f (open (strcat (getvar "TEMPPREFIX") "PdfLayout.ini") "r"))
  )
  (if f
    (progn
      (setq first T)
      (while (setq line (read-line f))
        (if first
          (progn
            (if (and (>= (strlen line) 3)
                     (= (ascii (substr line 1 1)) 239))
              (setq line (substr line 4))
            )
            (setq first nil)
          )
        )
        (setq pos (vl-string-search "=" line))
        (if pos
          (progn
            (setq k (vl-string-trim " " (substr line 1 pos)))
            ;; vl-string-search 返回 0 起始下标，substr 为 1 起始，
            ;; 值从 "=" 后一个字符开始，需 +2；旧版 ini 可能残留多余 "="，一并清掉
            (setq v (vl-string-trim " " (substr line (+ pos 2))))
            (while (= (substr v 1 1) "=")
              (setq v (substr v 2))
            )
            (setq *PdfLayout_IniPairs* (cons (cons k v) *PdfLayout_IniPairs*))
            (cond
              ((= k "Prefix") (setq *PdfLayout_PreviewPrefix* v))
              ((= k "Start") (setq *PdfLayout_PreviewStart* (atoi v)))
              ((= k "Digits") (setq *PdfLayout_PreviewDigits* (atoi v)))
              ((= k "Order") (setq *PdfLayout_PreviewOrder* v))
              ((= k "Src") (setq *PdfLayout_PreviewSrc* v))
              ((= k "FilePath") (setq *PdfLayout_PreviewFilePath* v))
              ((= k "BgMode") (setq *PdfLayout_PreviewBgMode* v))
              ((= k "BgColor") (setq *PdfLayout_PreviewBgColor* (atoi v)))
              ((= k "BgScale") (setq *PdfLayout_PreviewBgScale* (atof v)))
              ((= k "PythonPath") (setq *PdfLayout_PythonPath* v))
              ((= k "LbdTextHeight") (setq *PdfLayout_LbdTextHeight* (atof v)))
              ((= k "LbdBgColor") (setq *PdfLayout_LbdBgColor* (atoi v)))
              ((= k "RowTol") (setq *PdfLayout_RowTol* (atoi v)))
              ((= k "GridRows") (setq *PdfLayout_GridRows* (atoi v)))
              ((= k "GridCols") (setq *PdfLayout_GridCols* (atoi v)))
              ((= k "GridRowSp") (setq *PdfLayout_GridRowSp* (atof v)))
              ((= k "GridColSp") (setq *PdfLayout_GridColSp* (atof v)))
              ((= k "GridH") (setq *PdfLayout_GridH* (atof v)))
              ((= k "GridHRatio") (setq *PdfLayout_GridHRatio* (atof v)))
              ((= k "GridGeom") (setq *PdfLayout_GridGeom* v))
              ((= k "GridHMode") (setq *PdfLayout_GridHMode* v))
              ((= k "GridMT") (setq *PdfLayout_GridMT* (atof v)))
              ((= k "GridMB") (setq *PdfLayout_GridMB* (atof v)))
              ((= k "GridML") (setq *PdfLayout_GridML* (atof v)))
              ((= k "GridMR") (setq *PdfLayout_GridMR* (atof v)))
              ((= k "GridColDir") (setq *PdfLayout_GridColDir* (atoi v)))
              ((= k "GridRowDir") (setq *PdfLayout_GridRowDir* (atoi v)))
              ((= k "GridRot") (setq *PdfLayout_GridRot* (atoi v)))
              ((= k "GridBg") (setq *PdfLayout_GridBg* v))
              ((= k "GridBgColor") (setq *PdfLayout_GridBgColor* (atoi v)))
              ((= k "GridTxtColor") (setq *PdfLayout_GridTxtColor* (atoi v)) (setq *PdfLayout_GridTxtTrue* nil))
              ((= k "GridTxtTrue") (setq *PdfLayout_GridTxtTrue* (= v "1")))
              ((= k "GridTxtRGB") (setq *PdfLayout_GridTxtRGB* (atoi v)))
              ((= k "GridBgScale") (setq *PdfLayout_GridBgScale* (atof v))
                                  (if (> *PdfLayout_GridBgScale* 50)
                                    (setq *PdfLayout_GridBgScale* (/ *PdfLayout_GridBgScale* 100.0))))
              ((= k "GridPrefix") (setq *PdfLayout_GridPrefix* v))
              ((= k "GridStartN") (setq *PdfLayout_GridStartN* (atoi v)))
              ((= k "GridDigits") (setq *PdfLayout_GridDigits* (atoi v)))

              ((= k "LayRule") (setq *PdfLayout_LayRule* v))
              ((= k "LayLetters") (setq *PdfLayout_LayLetters* v))
              ((= k "LayPerGroup") (setq *PdfLayout_LayPerGroup* (atoi v)))
              ((= k "LayGStart") (setq *PdfLayout_LayGStart* (atoi v)))
              ((= k "LayXlsx") (setq *PdfLayout_LastNamesXlsx* v))
            )
          )
        )
      )
      (close f)
    )
  )
  (setq *PdfLayout_CurrentProfile* (PdfLayout_OrDefault (PdfLayout_IniGet "LastProfile") ""))
  (PdfLayout_LoadProfiles)
  (PdfLayout_GridLoadProfiles)
  (if (or (not *PdfLayout_PreviewStart*) (< *PdfLayout_PreviewStart* 1))
    (setq *PdfLayout_PreviewStart* 1)
  )
  (if (or (not *PdfLayout_PreviewDigits*) (< *PdfLayout_PreviewDigits* 0))
    (setq *PdfLayout_PreviewDigits* 2)
  )
  (if (not (member *PdfLayout_PreviewOrder* '("1" "2" "3" "4" "5" "6" "7" "8")))
    (setq *PdfLayout_PreviewOrder* "1")
  )
  (if (not (member *PdfLayout_PreviewSrc* '("1" "3")))
    (setq *PdfLayout_PreviewSrc* "1")
  )
  (if (not (member *PdfLayout_PreviewBgMode* '("0" "1" "2")))
    (setq *PdfLayout_PreviewBgMode* "0")
  )
  (if (not *PdfLayout_PreviewFilePath*) (setq *PdfLayout_PreviewFilePath* ""))
  (if (not *PdfLayout_PreviewBgMode*) (setq *PdfLayout_PreviewBgMode* "0"))
  (if (or (not *PdfLayout_PreviewBgColor*)
          (< *PdfLayout_PreviewBgColor* 1) (> *PdfLayout_PreviewBgColor* 255))
    (setq *PdfLayout_PreviewBgColor* 7)
  )
  (if (or (not *PdfLayout_PreviewBgScale*) (< *PdfLayout_PreviewBgScale* 1))
    (setq *PdfLayout_PreviewBgScale* 1.5)
  )
  (if (or (not *PdfLayout_RowTol*) (< *PdfLayout_RowTol* 1) (> *PdfLayout_RowTol* 50))
    (setq *PdfLayout_RowTol* 10)
  )
)

(defun PdfLayout_SaveSettings (/ f i pf pfname pfdata)
  (setq f (open (PdfLayout_SettingsPathLsp) "w"))
  (if (not f)
    (setq f (open (strcat (getvar "TEMPPREFIX") "PdfLayout.ini") "w"))
  )
  (if f
    (progn
      (princ (strcat "Prefix=" *PdfLayout_PreviewPrefix*) f)
      (princ "\n" f)
      (princ (strcat "Start=" (itoa *PdfLayout_PreviewStart*)) f)
      (princ "\n" f)
      (princ (strcat "Digits=" (itoa *PdfLayout_PreviewDigits*)) f)
      (princ "\n" f)
      (princ (strcat "Order=" *PdfLayout_PreviewOrder*) f)
      (princ "\n" f)
      (princ (strcat "Src=" *PdfLayout_PreviewSrc*) f)
      (princ "\n" f)
      (if *PdfLayout_PreviewFilePath*
        (princ (strcat "FilePath=" *PdfLayout_PreviewFilePath*) f)
      )
      (princ "\n" f)
      (princ (strcat "BgMode=" *PdfLayout_PreviewBgMode*) f)
      (princ "\n" f)
      (princ (strcat "BgColor=" (itoa *PdfLayout_PreviewBgColor*)) f)
      (princ "\n" f)
      (princ (strcat "BgScale=" (rtos *PdfLayout_PreviewBgScale* 2 2)) f)
      (princ "\n" f)
      (if (and *PdfLayout_PythonPath* (/= *PdfLayout_PythonPath* ""))
        (progn
          (princ (strcat "PythonPath=" *PdfLayout_PythonPath*) f)
          (princ "\n" f)
        )
      )
      (princ (strcat "RowTol=" (itoa *PdfLayout_RowTol*)) f)
(princ (strcat "LbdBgColor=" (itoa *PdfLayout_LbdBgColor*)) f)
(princ "\n" f)
      (princ "\n" f)
(princ (strcat "LayRule=" *PdfLayout_LayRule*) f)
(princ "\n" f)
(princ (strcat "LayLetters=" *PdfLayout_LayLetters*) f)
(princ "\n" f)
(princ (strcat "LayPerGroup=" (itoa *PdfLayout_LayPerGroup*)) f)
(princ "\n" f)
(princ (strcat "LayGStart=" (itoa *PdfLayout_LayGStart*)) f)
(princ "\n" f)
(if *PdfLayout_LastNamesXlsx*
  (princ (strcat "LayXlsx=" *PdfLayout_LastNamesXlsx*) f)
)
(princ "\n" f)
      (princ "\n" f)
      (princ (strcat "GridRows=" (itoa *PdfLayout_GridRows*)) f)
      (princ "\n" f)
      (princ (strcat "GridCols=" (itoa *PdfLayout_GridCols*)) f)
      (princ "\n" f)
      (princ (strcat "GridRowSp=" (rtos *PdfLayout_GridRowSp* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridColSp=" (rtos *PdfLayout_GridColSp* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridH=" (rtos *PdfLayout_GridH* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridHRatio=" (rtos *PdfLayout_GridHRatio* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridGeom=" *PdfLayout_GridGeom*) f)
      (princ "\n" f)
      (princ (strcat "GridHMode=" *PdfLayout_GridHMode*) f)
      (princ "\n" f)
      (princ (strcat "GridMT=" (rtos *PdfLayout_GridMT* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridMB=" (rtos *PdfLayout_GridMB* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridML=" (rtos *PdfLayout_GridML* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridMR=" (rtos *PdfLayout_GridMR* 2 2)) f)
      (princ "\n" f)
      (princ (strcat "GridColDir=" (itoa *PdfLayout_GridColDir*)) f)
      (princ "\n" f)
      (princ (strcat "GridRowDir=" (itoa *PdfLayout_GridRowDir*)) f)
      (princ "\n" f)
      (princ (strcat "GridRot=" (itoa *PdfLayout_GridRot*)) f)
      (princ "\n" f)
      (princ (strcat "GridBg=" *PdfLayout_GridBg*) f)
      (princ "\n" f)
      (princ (strcat "GridBgColor=" (itoa *PdfLayout_GridBgColor*)) f)
      (princ "\n" f)
      (princ (strcat "GridTxtColor=" (itoa *PdfLayout_GridTxtColor*)) f)
      (princ "\n" f)
      (princ (strcat "GridTxtTrue=" (if *PdfLayout_GridTxtTrue* "1" "0")) f)
      (princ "\n" f)
      (princ (strcat "GridTxtRGB=" (itoa *PdfLayout_GridTxtRGB*)) f)
      (princ "\n" f)
      (princ (strcat "GridBgScale=" (rtos *PdfLayout_GridBgScale* 2 2)) f)
      (princ "\n" f)
      (princ "\n" f)
      (if *PdfLayout_GridPrefix*
        (princ (strcat "GridPrefix=" *PdfLayout_GridPrefix*) f)
      )
      (princ "\n" f)
      (princ (strcat "GridStartN=" (itoa *PdfLayout_GridStartN*)) f)
      (princ "\n" f)
      (princ (strcat "GridDigits=" (itoa *PdfLayout_GridDigits*)) f)
      (princ "\n" f)
      (princ (strcat "GridProfileCount=" (itoa (length *PdfLayout_GridProfiles*))) f)
      (princ "\n" f)
      (setq i 1)
      (foreach pf *PdfLayout_GridProfiles*
        (setq pfname (car pf))
        (setq pfdata (cdr pf))
        (princ (strcat "GridProfile" (itoa i) "Name=" pfname) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Rows=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Rows") 4))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Cols=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Cols") 5))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "RowSp=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "RowSp") 10.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "ColSp=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "ColSp") 20.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "H=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "H") 0.5) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "HRatio=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "HRatio") 0.3) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Geom=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Geom") "1")) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "HMode=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "HMode") "auto")) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "MT=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "MT") 0.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "MB=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "MB") 0.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "ML=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "ML") 0.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "MR=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "MR") 0.0) 2 2)) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "ColDir=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "ColDir") 1))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "RowDir=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "RowDir") -1))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Rot=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Rot") 0))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Bg=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Bg") "fill")) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "BgColor=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "BgColor") 1))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "TxtColor=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "TxtColor") 7))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "TxtTrue=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "TxtTrue") "0")) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "TxtRGB=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "TxtRGB") 0))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "BgScale=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "BgScale") 1.0) 2 2)) f)
        (princ "\n" f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Prefix=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Prefix") "CIR")) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "StartN=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "StartN") 1))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Digits=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Digits") 2))) f)
        (princ "\n" f)
        (princ (strcat "GridProfile" (itoa i) "Order=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Order") "1")) f)
        (princ "\n" f)
        (setq i (1+ i))
      )
      (princ (strcat "LastProfile=" *PdfLayout_CurrentProfile*) f)
      (princ "\n" f)
      (princ (strcat "ProfileCount=" (itoa (length *PdfLayout_Profiles*))) f)
      (princ "\n" f)
      (setq i 1)
      (foreach pf *PdfLayout_Profiles*
        (setq pfname (car pf))
        (setq pfdata (cdr pf))
        (princ (strcat "Profile" (itoa i) "Name=" pfname) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "Prefix=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Prefix") "")) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "Start=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Start") 1))) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "Digits=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Digits") 2))) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "Order=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Order") "1")) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "Src=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "Src") "1")) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "FilePath=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "FilePath") "")) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "BgMode=" (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "BgMode") "0")) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "BgColor=" (itoa (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "BgColor") 7))) f)
        (princ "\n" f)
        (princ (strcat "Profile" (itoa i) "BgScale=" (rtos (PdfLayout_OrDefault (PdfLayout_ProfileGet pfdata "BgScale") 1.5) 2 2)) f)
        (princ "\n" f)
        (setq i (1+ i))
      )
      (close f)
    )
  )
)
(defun PdfLayout_IniGet (key / p)
  (setq p (assoc key *PdfLayout_IniPairs*))
  (if p (cdr p) nil)
)

(defun PdfLayout_ProfileGet (prof key / p)
  (setq p (assoc key prof))
  (if p (cdr p) nil)
)

;; 中望CAD(LISPSYS=1)的 or 函数有兼容性问题：会返回 T 而不是实际值，
;; 因此不能用 (or 取值 默认值) 的写法，统一改用本函数取“非 nil 值”。
(defun PdfLayout_OrDefault (val dflt / v)
  (setq v val)
  (if (null v) (setq v dflt))
  v
)

(defun PdfLayout_ProfileSet (prof key val / p)
  (if (assoc key prof)
    (subst (cons key val) (assoc key prof) prof)
    (append prof (list (cons key val)))
  )
)

(defun PdfLayout_ApplyProfile (prof)
  (setq *PdfLayout_PreviewPrefix* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "Prefix") "STR"))
  (setq *PdfLayout_PreviewStart* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "Start") 1))
  (setq *PdfLayout_PreviewDigits* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "Digits") 2))
  (setq *PdfLayout_PreviewOrder* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "Order") "1"))
  (setq *PdfLayout_PreviewSrc* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "Src") "1"))
  (if (not (member *PdfLayout_PreviewSrc* '("1" "3")))
    (setq *PdfLayout_PreviewSrc* "1")
  )
  (setq *PdfLayout_PreviewFilePath* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "FilePath") ""))
  (setq *PdfLayout_PreviewBgMode* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "BgMode") "0"))
  (setq *PdfLayout_PreviewBgColor* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "BgColor") 7))
  (setq *PdfLayout_PreviewBgScale* (PdfLayout_OrDefault (PdfLayout_ProfileGet prof "BgScale") 1.5))
)

(defun PdfLayout_LoadProfiles (/ i cnt name prof)
  (setq *PdfLayout_Profiles* nil)
  (setq i 1)
  (setq cnt (atoi (PdfLayout_OrDefault (PdfLayout_IniGet "ProfileCount") "0")))
  (while (<= i cnt)
    (setq name (PdfLayout_IniGet (strcat "Profile" (itoa i) "Name")))
    (if name
      (progn
        (setq prof nil)
        (setq prof (PdfLayout_ProfileSet prof "Prefix" (PdfLayout_IniGet (strcat "Profile" (itoa i) "Prefix"))))
        (setq prof (PdfLayout_ProfileSet prof "Start" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "Start")) "1"))))
        (setq prof (PdfLayout_ProfileSet prof "Digits" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "Digits")) "2"))))
        (setq prof (PdfLayout_ProfileSet prof "Order" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "Order")) "1")))
        (setq prof (PdfLayout_ProfileSet prof "Src" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "Src")) "1")))
        (setq prof (PdfLayout_ProfileSet prof "FilePath" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "FilePath")) "")))
        (setq prof (PdfLayout_ProfileSet prof "BgMode" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "BgMode")) "0")))
        (setq prof (PdfLayout_ProfileSet prof "BgColor" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "BgColor")) "7"))))
        (setq prof (PdfLayout_ProfileSet prof "BgScale" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "Profile" (itoa i) "BgScale")) "1.5"))))
        (setq *PdfLayout_Profiles* (append *PdfLayout_Profiles* (list (cons name prof))))
      )
    )
    (setq i (1+ i))
  )
)

(defun PdfLayout_SaveProfile (name / prof)
  (setq prof nil)
  (setq prof (PdfLayout_ProfileSet prof "Prefix" *PdfLayout_PreviewPrefix*))
  (setq prof (PdfLayout_ProfileSet prof "Start" *PdfLayout_PreviewStart*))
  (setq prof (PdfLayout_ProfileSet prof "Digits" *PdfLayout_PreviewDigits*))
  (setq prof (PdfLayout_ProfileSet prof "Order" *PdfLayout_PreviewOrder*))
  (setq prof (PdfLayout_ProfileSet prof "Src" *PdfLayout_PreviewSrc*))
  (setq prof (PdfLayout_ProfileSet prof "FilePath" *PdfLayout_PreviewFilePath*))
  (setq prof (PdfLayout_ProfileSet prof "BgMode" *PdfLayout_PreviewBgMode*))
  (setq prof (PdfLayout_ProfileSet prof "BgColor" *PdfLayout_PreviewBgColor*))
  (setq prof (PdfLayout_ProfileSet prof "BgScale" *PdfLayout_PreviewBgScale*))
  (setq *PdfLayout_Profiles*
    (vl-remove-if
      '(lambda (x) (= (strcase (car x)) (strcase name)))
      *PdfLayout_Profiles*))
  (setq *PdfLayout_Profiles* (append *PdfLayout_Profiles* (list (cons name prof))))
  (setq *PdfLayout_CurrentProfile* name)
  (PdfLayout_SaveSettings)
)
(defun c:pdflayoutdebug ()
  (setq *PdfLayout_Debug* (not *PdfLayout_Debug*))
  (princ (strcat "\nPDF布局调试输出: " (if *PdfLayout_Debug* "开" "关")))
  (princ)
)
(defun c:pdfdiag (/ oldFd fpath)
  ;; 诊断：查看 ZWCAD 的 PDFATTACH 命令行提示顺序（配合修复自动导入全部页）
  (vl-load-com)
  (setq oldFd (getvar "FILEDIA"))
  (setq *PdfLayout_SavedFd* oldFd)
  (setvar "FILEDIA" 0)
  (setq fpath (getfiled "选择用于测试的 PDF（观察提示后按 Esc 取消）" "" "pdf" 4))
  (if fpath
    (progn
      (princ "\nPDFATTACH 诊断开始：请观察命令行提示，看完按 Esc 取消。")
      (vl-catch-all-apply
        '(lambda () (command "._PDFATTACH" fpath))
      )
      (princ "\n诊断结束（若命令还挂起，请按 Esc）。")
    )
  )
  (setq *PdfLayout_SavedFd* nil)
  (setvar "FILEDIA" oldFd)
  (princ)
)
(defun c:pdflayouttest (/ cases passed failed case rule lettersStr pg gStart
                        expect got i allOk)
  (setq cases
    (list
      (list "INV{G2}{L}{N2}" "AB" 6 1
            (list "INV01A01" "INV01A02" "INV01A03" "INV01A04" "INV01A05" "INV01A06"
                  "INV01B01" "INV01B02" "INV01B03" "INV01B04" "INV01B05" "INV01B06"
                  "INV02A01" "INV02A02"))
      (list "图{N2}" "AB" 6 1
            (list "图01" "图02" "图03" "图04" "图05" "图06" "图07" "图08"))
      (list "A-{N3}" "AB" 6 1
            (list "A-001" "A-002" "A-003" "A-004" "A-005"))
      (list "{G2}{L}" "A-Z" 1 1
            (list "01A" "01B" "01C" "01D" "01E"))
      (list "DWG{G1}-{N1}" "AB" 3 5
            (list "DWG5-1" "DWG5-2" "DWG5-3" "DWG6-1" "DWG6-2"))
    )
  )
  (setq passed 0 failed 0)
  (princ "\n==== MAP文件工具箱 自检 ====")
  (foreach case cases
    (setq rule (nth 0 case))
    (setq lettersStr (nth 1 case))
    (setq pg (nth 2 case))
    (setq gStart (nth 3 case))
    (setq expect (nth 4 case))
    (setq got (PdfLayout_GenNames rule lettersStr pg gStart (length expect)))
    (if (and got (= (length got) (length expect)))
      (progn
        (setq i 0 allOk T)
        (while (< i (length expect))
          (if (/= (nth i got) (nth i expect))
            (setq allOk nil)
          )
          (setq i (1+ i))
        )
        (if allOk
          (progn
            (princ (strcat "\n[通过] " rule " + 字母" lettersStr " + 每组" (itoa pg) "张"))
            (setq passed (1+ passed))
          )
          (progn
            (princ (strcat "\n[失败] " rule "  期望: "))
            (foreach n expect (princ (strcat n " ")))
            (princ "  实际: ")
            (foreach n got (princ (strcat n " ")))
            (setq failed (1+ failed))
          )
        )
      )
      (progn
        (princ (strcat "\n[失败] " rule " 无法生成足够名称"))
        (setq failed (1+ failed))
      )
    )
  )
  (setq got (PdfLayout_ParseLetters "A-F"))
  (if (= (length got) 6)
    (progn
      (princ "\n[通过] 字母范围 A-F → 6 个字母")
      (setq passed (1+ passed))
    )
    (progn
      (princ (strcat "\n[失败] 字母范围 A-F 期望6个，实际 " (itoa (length got))))
      (setq failed (1+ failed))
    )
  )
  (princ (strcat "\n---- 结果: 通过 " (itoa passed) " 项，失败 " (itoa failed) " 项 ----"))
  (princ "\n==== 自检结束 ====")
  (princ)
)
;;;-------------------------------------------------------------
;;; PDF底图 LBD 识别与标签填写（需 pdf_extract.py + pypdf）
;;;-------------------------------------------------------------
(setq *PdfLayout_PyLines* (list
"# -*- coding: utf-8 -*-"
"# MAP文件工具箱 - PDF 文字与坐标提取（供 LBD 识别使用）"
"# 输出格式（制表符分隔，UTF-8）:"
"#   P\\t页号\\t页标题文本(前150字)"
"#   L\\t页号\\tfx\\tfy\\t文字片段   （fx/fy 为页内相对位置 0~1，原点左下）"
"# 进度文件（第5参数，可选）: READY / TOTAL n / PAGE m / DONE n / ERR:... / CANCELLED"
"# 用法: pdf_extract.py <pdf> <out.txt> [pageStart] [pageEnd] [prog.txt]"
"import sys, os"
""
"PROG = None"
"def prog(msg):"
"    if PROG:"
"        try:"
"            with open(PROG, \"w\", encoding=\"utf-8\") as f:"
"                f.write(msg)"
"        except Exception:"
"            pass"
""
"def main():"
"    if len(sys.argv) < 3:"
"        print(\"usage: pdf_extract.py <pdf> <out.txt> [pageStart] [pageEnd] [prog.txt]\")"
"        sys.exit(1)"
"    pdf, out = sys.argv[1], sys.argv[2]"
"    global PROG"
"    if len(sys.argv) > 5:"
"        PROG = sys.argv[5]"
"    try:"
"        from pypdf import PdfReader"
"    except ImportError:"
"        try:"
"            from PyPDF2 import PdfReader"
"        except ImportError:"
"            print(\"ERR:pypdf missing, run: python -m pip install pypdf\")"
"            prog(\"ERR:pypdf missing\")"
"            sys.exit(2)"
"    prog(\"READY\")"
"    try:"
"        reader = PdfReader(pdf)"
"        n = len(reader.pages)"
"    except Exception as e:"
"        print(\"ERR:open pdf failed: %s\" % e)"
"        prog(\"ERR:open pdf failed\")"
"        sys.exit(3)"
"    prog(\"TOTAL %d\" % n)"
"    p0 = int(sys.argv[3]) if len(sys.argv) > 3 else 1"
"    p1 = int(sys.argv[4]) if len(sys.argv) > 4 else n"
"    if p0 < 1: p0 = 1"
"    if p1 <= 0: p1 = n"
"    if p1 > n: p1 = n"
"    lines = []"
"    for idx in range(p0 - 1, p1):"
"        if PROG and os.path.exists(PROG + \".cancel\"):"
"            prog(\"CANCELLED\")"
"            print(\"CANCELLED at page %d\" % (idx + 1), flush=True)"
"            sys.exit(0)"
"        page = reader.pages[idx]"
"        try:"
"            cb = page.cropbox"
"            x0, y0 = float(cb.left), float(cb.bottom)"
"            pw = float(cb.right) - x0"
"            ph = float(cb.top) - y0"
"        except Exception:"
"            x0, y0, pw, ph = 0.0, 0.0, 1.0, 1.0"
"        if pw <= 0: pw = 1.0"
"        if ph <= 0: ph = 1.0"
"        items = []"
"        all_text = []"
"        def visit_text(text, cm, tm, font, size):"
"            if text:"
"                all_text.append(text)"
"                try:"
"                    m0 = cm[0]*tm[0] + cm[2]*tm[1]"
"                    m1 = cm[1]*tm[0] + cm[3]*tm[1]"
"                    m2 = cm[0]*tm[2] + cm[2]*tm[3]"
"                    m3 = cm[1]*tm[2] + cm[3]*tm[3]"
"                    m4 = cm[0]*tm[4] + cm[2]*tm[5] + cm[4]"
"                    m5 = cm[1]*tm[4] + cm[3]*tm[5] + cm[5]"
"                except Exception:"
"                    m0, m1, m2, m3, m4, m5 = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0"
"                try:"
"                    cs = float(size)"
"                except Exception:"
"                    cs = 0.0"
"                w = cs * 0.5 * len(text)"
"                h = cs"
"                xs = []"
"                ys = []"
"                for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):"
"                    xs.append(m0*tx + m2*ty + m4)"
"                    ys.append(m1*tx + m3*ty + m5)"
"                cx = (min(xs) + max(xs)) * 0.5"
"                cy = min(ys) - (max(ys) - min(ys)) * 0.15"
"                items.append([text, cx, cy])"
"        try:"
"            page.extract_text(visitor_text=visit_text)"
"        except Exception:"
"            items = []"
"        title = \"\".join(all_text[:100])"
"        lines.append(\"P\\t%d\\t%.2f\\t%.2f\\t%s\" % (idx + 1, pw, ph, title[:150].replace(\"\\t\", \" \").replace(\"\\n\", \" \")))"
"        for it in items:"
"            if \"LBD\" not in it[0].upper():"
"                continue"
"            cx, cy = it[1], it[2]"
"            if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:"
"                continue"
"            fx = (cx - x0) / pw"
"            fy = (cy - y0) / ph"
"            lines.append(\"L\\t%d\\t%.6f\\t%.6f\\t%s\" % (idx + 1, fx, fy, it[0].replace(\"\\t\", \" \").replace(\"\\n\", \" \")))"
"        prog(\"PAGE %d/%d\" % (idx + 1, n))"
"        print(\"page %d/%d\" % (idx + 1, n), flush=True)"
"    try:"
"        with open(out, \"w\", encoding=\"utf-8\") as f:"
"            f.write(\"\\n\".join(lines))"
"    except Exception as e:"
"        print(\"ERR:write out failed: %s\" % e)"
"        prog(\"ERR:write out failed\")"
"        sys.exit(4)"
"    prog(\"DONE %d\" % (p1 - p0 + 1))"
"    print(\"DONE %d\" % (p1 - p0 + 1))"
""
"main()"
))

(defun PdfLayout_WritePyScript (/ f)
  ;; 把内嵌的 PDF 提取脚本写到临时目录（中望取不到LSP目录时的兜底）
  (setq f (open (strcat (getvar "TEMPPREFIX") "pdf_extract.py") "w"))
  (if f
    (progn
      (foreach ln *PdfLayout_PyLines*
        (write-line ln f)
      )
      (close f)
    )
  )
)
(defun PdfLayout_ReadFileText (path / f txt ln)
  (setq f (open path "r") txt "")
  (if f
    (progn
      (while (setq ln (read-line f))
        (setq txt (strcat txt ln "\n"))
      )
      (close f)
    )
  )
  txt
)
(defun PdfLayout_ProgNum (txt tag / pos s i c num)
  (setq pos (vl-string-search (strcat tag " ") txt))
  (if pos
    (progn
      (setq s (substr txt (+ pos (strlen tag) 2)))
      (setq num "" i 1)
      (while (and (<= i (strlen s))
                  (= (PdfLayout_CharKind (substr s i 1)) "D"))
        (setq num (strcat num (substr s i 1)))
        (setq i (1+ i))
      )
      (if (> (strlen num) 0) (atoi num) nil)
    )
    nil
  )
)
(defun PdfLayout_GrreadEsc (/ r)
  ;; ZWCAD 的 grread 不支持超时参数（直接调用会报"参数太多"），
  ;; 因此统一用 DELAY 轮询，兼容 AutoCAD/ZWCAD；等待期间暂不支持 Esc 取消。
  (command "._DELAY" 500)
  nil
)
(defun PdfLayout_BundledPy (/ dir p)
  ;; 中望CAD 取不到 *load-truename*，依次尝试：
  ;; LSP目录 → 支持路径里找到的 PdfLayout.lsp 所在目录 → bundle 安装目录
  (setq p nil)
  (if (and *PdfLayout_LspDir* (/= *PdfLayout_LspDir* ""))
    (setq p (strcat *PdfLayout_LspDir* "python\\python.exe"))
  )
  (if (and (not p) (setq dir (findfile "PdfLayout.lsp")))
    (setq p (strcat (vl-filename-directory dir) "python\\python.exe"))
  )
  (if (and (not p) (getenv "APPDATA"))
    (setq p (strcat (getenv "APPDATA")
                    "\\Autodesk\\ApplicationPlugins\\PdfLayout.bundle\\Contents\\python\\python.exe"))
  )
  (if (and (not p) (getenv "PROGRAMFILES"))
    (setq p (strcat (getenv "PROGRAMFILES")
                    "\\Autodesk\\ApplicationPlugins\\PdfLayout.bundle\\Contents\\python\\python.exe"))
  )
  (if (not (findfile p)) (setq p nil))
  p
)

(defun PdfLayout_EnsurePython (/ py)
  ;; 依次尝试 ini 路径、随包 Python；都没有时让用户选一次含 pypdf 的 python.exe 并记住
  (setq py (if (and *PdfLayout_PythonPath* (/= *PdfLayout_PythonPath* ""))
             *PdfLayout_PythonPath*
             ""))
  (if (not (and py (findfile py)))
    (setq py (PdfLayout_BundledPy))
  )
  (if (not (and py (findfile py)))
    (progn
      (princ "\n未找到可用的 Python（pypdf），请手动选择含 pypdf 的 python.exe：")
      (setq py (getfiled "请选择含 pypdf 的 python.exe（推荐随包 python\\python.exe）"
                         (strcat (getenv "USERPROFILE") "\\Desktop") "exe" 4))
      (if (and py (findfile py))
        (progn
          (setq *PdfLayout_PythonPath* py)
          (PdfLayout_SaveSettings)
        )
        (setq py nil)
      )
    )
  )
  py
)

(defun PdfLayout_ModelToPaper (vp modelPt / ent ed vpc vc vh bb pmin pmax ph scale)
  ;; 用视口实体 DXF 数据换算：10=纸张中心 12=视图中心(模型点) 40=视图高度
  ;; 避免 ZWCAD 缺少 vla-get-ViewHeight / ViewCenter 接口的问题
  (setq ent (vlax-vla-object->ename vp))
  (setq ed (entget ent))
  (setq vpc (cdr (assoc 10 ed)))
  (setq vc (cdr (assoc 12 ed)))
  (setq vh (cdr (assoc 40 ed)))
  (setq bb (PdfLayout_GetExtentsSafeObj vp))
  (if (and vpc vc vh bb (> vh 0.0))
    (progn
      (setq pmin (car bb) pmax (cadr bb))
      (setq ph (- (cadr pmax) (cadr pmin)))
      (if (> ph 0.0)
        (progn
          (setq scale (/ ph vh))
          (list (+ (car vpc) (* (- (car modelPt) (car vc)) scale))
                (+ (cadr vpc) (* (- (cadr modelPt) (cadr vc)) scale))
                0.0)
        )
        nil
      )
    )
    nil
  )
)
(defun PdfLayout_LayoutBiggestVp (layout / blk obj bb best vp area)
  (setq blk (vla-get-Block layout))
  (setq best nil vp nil)
  (vlax-for obj blk
    (if (= (vla-get-ObjectName obj) "AcDbViewport")
      (progn
        (setq bb (PdfLayout_GetExtentsSafeObj obj))
        (if bb
          (progn
            (setq area (* (- (car (cadr bb)) (car (car bb)))
                          (- (cadr (cadr bb)) (cadr (car bb)))))
            (if (or (not best) (> area best))
              (setq best area vp obj)
            )
          )
        )
      )
    )
  )
  vp
)
(defun PdfLayout_PaperToModel (vp paperPt / ent ed vpc vc vh bb ph scale)
  ;; 纸张坐标 -> 模型坐标（视口 DXF 换算，兼容 ZWCAD）
  (setq ent (vlax-vla-object->ename vp))
  (setq ed (entget ent))
  (setq vpc (cdr (assoc 10 ed)))
  (setq vc (cdr (assoc 12 ed)))
  (setq vh (cdr (assoc 40 ed)))
  (setq bb (PdfLayout_GetExtentsSafeObj vp))
  (if (and vpc vc vh bb (> vh 0.0))
    (progn
      (setq ph (- (cadr (cadr bb)) (cadr (car bb))))
      (if (> ph 0.0)
        (progn
          (setq scale (/ ph vh))
          (list (+ (car vc) (/ (- (car paperPt) (car vpc)) scale))
                (+ (cadr vc) (/ (- (cadr paperPt) (cadr vpc)) scale))
                0.0)
        )
        nil
      )
    )
    nil
  )
)
(defun PdfLayout_PtInRect (pt rect)
  ;; 点是否在矩形内（rect = (xmin ymin xmax ymax)）
  (and rect
       (<= (car rect) (car pt) (caddr rect))
       (<= (cadr rect) (cadr pt) (cadddr rect)))
)
(defun PdfLayout_MTextRedWhite (obj / ename ed)
  ;; 红底白字 + 背景贴合文字：用 DXF 直接设置，兼容 ZWCAD（无 BackgroundFillColor 接口）
  (setq ename (if (= (type obj) 'VLA-OBJECT)
                (vlax-vla-object->ename obj)
                obj))
  (setq ed (entget ename))
  (if (assoc 45 ed) (setq ed (subst (cons 45 1) (assoc 45 ed) ed)) (setq ed (append ed (list (cons 45 1)))))
  (if (assoc 63 ed) (setq ed (subst (cons 63 (if *PdfLayout_LbdBgColor* *PdfLayout_LbdBgColor* 1)) (assoc 63 ed) ed)) (setq ed (append ed (list (cons 63 (if *PdfLayout_LbdBgColor* *PdfLayout_LbdBgColor* 1))))))
  (if (assoc 421 ed) (setq ed (vl-remove (assoc 421 ed) ed)))
  (if (assoc 90 ed) (setq ed (subst (cons 90 (if *PdfLayout_LbdGap* *PdfLayout_LbdGap* 1.0)) (assoc 90 ed) ed)) (setq ed (append ed (list (cons 90 (if *PdfLayout_LbdGap* *PdfLayout_LbdGap* 1.0))))))
  (entmod ed)
)
(defun PdfLayout_WriteBat (script pdf out prog log pgStart pgEnd / f pyUse)
  ;; 路径直接写入 bat（PythonPath 用 8.3 短路径避免中文/空格问题）；
  ;; 中望CAD 的 setenv 不会传给子进程，所以不用环境变量
  (setq pyUse (if (and *PdfLayout_PythonPath* (/= *PdfLayout_PythonPath* ""))
                *PdfLayout_PythonPath*
                (PdfLayout_BundledPy)))
  (if (not pyUse) (setq pyUse ""))
  (if (not (findfile pyUse)) (setq pyUse ""))
  (setq f (open (strcat (getvar "TEMPPREFIX") "pdflbd_run.bat") "w"))
  (if f
    (progn
      (princ (strcat "echo BATSTARTED > \"" (getvar "TEMPPREFIX") "pdflbd_bat.txt\"\r\n") f)
      (princ "@echo off\r\n" f)
      (if (/= pyUse "")
        (princ (strcat "set PY=\"" pyUse "\"\r\n") f)
        (progn
          (princ "set \"PY=\"\r\n" f)
          (princ "where python >nul 2>&1 && set \"PY=python\"\r\n" f)
          (princ "if not defined PY (where py >nul 2>&1 && set \"PY=py -3\")\r\n" f)
          (princ (strcat "if not defined PY (echo ERR:no python found > \"" log "\" & exit /b 1)\r\n") f)
        )
      )
      (princ (strcat "%PY% -c \"import sys;print('PYEXEC',sys.executable)\" > \"" log "\" 2>&1\r\n") f)
      (princ (strcat "%PY% -c \"import pypdf\" >> \"" log "\" 2>&1\r\n") f)
      (princ (strcat "if errorlevel 1 (echo ERR:pypdf missing, run: %PY% -m pip install pypdf >> \"" log "\" & exit /b 2)\r\n") f)
      (princ (strcat "%PY% \"" script "\" \"" pdf "\" \"" out "\" " pgStart " " pgEnd " \"" prog "\" >> \"" log "\" 2>&1\r\n") f)
      (close f)
    )
  )
)

(defun PdfLayout_SplitTab (s / out pos)
  (setq out nil)
  (while (setq pos (vl-string-search (chr 9) s))
    (setq out (append out (list (substr s 1 pos))))
    (setq s (substr s (+ pos 2)))
  )
  (append out (list s))
)
(defun PdfLayout_LbdNumFromText (s / pos i c num)
  ;; 从文字里提取 LBD 编号，如 "INV01A01-LBD-14" -> 14；找不到返回 nil
  (setq pos (vl-string-search "LBD" (strcase s)))
  (if pos
    (progn
      (setq i (+ pos 3) num "")
      (while (and (<= i (strlen s)) (= (strlen num) 0))
        (setq c (substr s i 1))
        (if (= (PdfLayout_CharKind c) "D")
          (progn
            (setq num c)
            (setq i (1+ i))
            (while (and (<= i (strlen s))
                        (= (PdfLayout_CharKind (substr s i 1)) "D"))
              (setq num (strcat num (substr s i 1)))
              (setq i (1+ i))
            )
          )
          (setq i (1+ i))
        )
      )
      (if (> (strlen num) 0) (atoi num) nil)
    )
    nil
  )
)

(defun PdfLayout_LbdSheetFromText (s / i n out tok nd nl)
  ;; 从片段文本提取分表名：INV + 数字段 + 一个字母 + 数字段（每段位数不固定）
  ;;   "INV01A01-LBD-14"   -> "INV01A01"
  ;;   "INV11A101-LBD-05"  -> "INV11A101"
  ;; （以前写死 2 位数字段，3 位的会被截成 INV11A10，对不上分表名 → 一个标签都填不上）
  (setq i 1 out nil)
  (while (and (<= i (strlen s)) (not out))
    (if (and (>= (strlen s) (+ i 2)) (= (strcase (substr s i 3)) "INV"))
      (progn
        (setq n (+ i 3) tok "" nd 0 nl 0)
        (while (and (<= n (strlen s)) (= (PdfLayout_CharKind (substr s n 1)) "D"))
          (setq tok (strcat tok (substr s n 1)) n (1+ n) nd (1+ nd))
        )
        (if (> nd 0)
          (progn
            (if (and (<= n (strlen s)) (= (PdfLayout_CharKind (substr s n 1)) "L"))
              (progn (setq tok (strcat tok (substr s n 1))) (setq n (1+ n)) (setq nl 1))
            )
            (if (= nl 1)
              (progn
                (while (and (<= n (strlen s)) (= (PdfLayout_CharKind (substr s n 1)) "D"))
                  (setq tok (strcat tok (substr s n 1)) n (1+ n))
                )
                (setq out (strcat "INV" (strcase tok)))
              )
            )
          )
        )
      )
    )
    (setq i (1+ i))
  )
  out
)
(defun PdfLayout_ReadExtractFile (path / f line parts pages items)
  ;; 读取 pdf_extract.py 的输出：P 行=页信息，L 行=LBD片段
  ;; 返回 (pages items)；pages=((页号 . 标题)...)，items=((页号 fx fy 文字)...)
  (setq f (open path "r"))
  (setq pages nil items nil)
  (if f
    (progn
      (while (setq line (read-line f))
        (setq parts (PdfLayout_SplitTab line))
        (if (> (length parts) 1)
          (cond
            ((= (car parts) "P")
              (setq pages (append pages (list (list (atoi (nth 1 parts))
                                                    (atof (nth 2 parts))
                                                    (atof (nth 3 parts))
                                                    (if (nth 4 parts) (nth 4 parts) "")))))
            )
            ((= (car parts) "L")
              (setq items (append items (list (list (atoi (nth 1 parts))
                                                    (atof (nth 2 parts))
                                                    (atof (nth 3 parts))
                                                    (if (nth 4 parts) (nth 4 parts) "")
                                                    (if (nth 5 parts) (atoi (nth 5 parts)) 0)
                                                    (if (nth 6 parts) (atof (nth 6 parts)) 0.0)))))
            )
          )
        )
      )
      (close f)
    )
  )
  (list pages items)
)
(defun PdfLayout_EnsureLayer (lname / doc layers l)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq layers (vla-get-Layers doc))
  (setq l (vl-catch-all-apply 'vla-Item (list layers lname)))
  (if (vl-catch-all-error-p l)
    (setq l (vl-catch-all-apply 'vla-Add (list layers lname)))
  )
  l
)
(defun PdfLayout_ReadAllLbdLabels (path / xl wbs wb shs out i sh sheet ur vals arr shCount rng hadExcel curLbd
                                   rows map lbd lab cur labels kv)
  ;; 一次读取 Excel 所有分表：返回 ((分表名 . ((LBD编号 . "标签A/标签B") ...)) ...)
  (setq out nil)
  (setq hadExcel (vl-catch-all-apply 'vlax-get-object (list "Excel.Application")))
  (setq hadExcel (and hadExcel (not (vl-catch-all-error-p hadExcel))))
  (setq xl (vl-catch-all-apply 'vlax-create-object (list "Excel.Application")))
  (if (and xl (not (vl-catch-all-error-p xl)))
    (progn
      (vl-catch-all-apply 'vlax-put-property (list xl 'Visible 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'DisplayAlerts 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'AskToUpdateLinks 0))
      (vl-catch-all-apply 'vlax-put-property (list xl 'AutomationSecurity 3))
      (setq wbs (vl-catch-all-apply 'vlax-get-property (list xl 'Workbooks)))
      (setq wb (vl-catch-all-apply 'vlax-invoke-method (list wbs 'Open path 0 1)))
      (if (and wb (not (vl-catch-all-error-p wb)))
        (progn
          (setq shs (vl-catch-all-apply 'vlax-get-property (list wb 'Sheets)))
          (if (and shs (not (vl-catch-all-error-p shs)))
            (progn
              (setq i 1)
              (setq shCount (if (and shs (not (vl-catch-all-error-p shs)))
                              (vlax-get-property shs 'Count) 0))
              (while (<= i shCount)
                (setq sh (vl-catch-all-apply 'vlax-get-property (list shs 'Item i)))
                (if (not (vl-catch-all-error-p sh))
                  (progn
                    (setq sheet (vlax-get-property sh 'Name))
                    (princ (strcat "\n  读取分表 " (itoa i) "/" (itoa shCount) " ..."))
                    ;; 用使用区域读取（ZWCAD 兼容；空表 .Value 可能返回 nil，需判空）
                    (setq ur (vl-catch-all-apply 'vlax-get-property (list sh 'UsedRange)))
                    (setq vals (if (and ur (not (vl-catch-all-error-p ur)))
                                 (vl-catch-all-apply 'vlax-get-property (list ur 'Value))
                                 nil))
                    (setq map nil curLbd nil)
                    (if (and vals (not (vl-catch-all-error-p vals)))
                          (progn
                            (setq arr (vlax-variant-value vals))
                            (setq rows (vlax-safearray->list arr))
                            (setq rows (mapcar '(lambda (r) (mapcar 'PdfLayout_CellStr r)) rows))
                            (foreach r rows
                              ;; 标签取 C 列(Item Code)；A 列为空的续行(负极)归入上一个 LBD
                              (setq lbd (nth 0 r) lab (nth 2 r))
                              (if (and lab (/= lab ""))
                                (progn
                                  (if (and lbd (/= lbd "") (PdfLayout_LbdNumFromText lbd))
                                    (setq n0 (PdfLayout_LbdNumFromText lbd) curLbd n0)
                                    (setq n0 curLbd)
                                  )
                                  (if n0
                                    (progn
                                      (setq cur (assoc n0 map))
                                      (if cur
                                        (setq map (subst (cons n0 (append (cdr cur) (list lab))) cur map))
                                        (setq map (append map (list (cons n0 (list lab)))))
                                      )
                                    )
                                  )
                                )
                              )
                            )
                            (setq labels nil)
                            (foreach kv map
                              (setq labels (append labels (list (cons (car kv)
                                                                       (PdfLayout_JoinLabelsList (cdr kv))))))
                            )
                            (setq out (append out (list (cons sheet labels))))
                          )
                        )
                      )
                    )
                (setq i (1+ i))
              )
            )
          )
          (vl-catch-all-apply 'vlax-invoke-method (list wb 'Close 0))
        )
      )
      ;; 原本没在运行才 Quit；并释放所有 COM 引用，避免 Excel 挂在后台占内存
      (if (not hadExcel)
        (vl-catch-all-apply 'vlax-invoke-method (list xl 'Quit))
      )
      (if (and shs (not (vl-catch-all-error-p shs)))
        (vl-catch-all-apply 'vlax-release-object (list shs))
      )
      (if (and sh (not (vl-catch-all-error-p sh)))
        (vl-catch-all-apply 'vlax-release-object (list sh))
      )
      (if (and wb (not (vl-catch-all-error-p wb)))
        (vl-catch-all-apply 'vlax-release-object (list wb))
      )
      (if (and wbs (not (vl-catch-all-error-p wbs)))
        (vl-catch-all-apply 'vlax-release-object (list wbs))
      )
      (if (and xl (not (vl-catch-all-error-p xl)))
        (vl-catch-all-apply 'vlax-release-object (list xl))
      )
    )
  )
  out
)
(defun PdfLayout_GetPdfUnderlays (/ doc ms out obj)
  (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
  (setq ms (vla-get-ModelSpace doc))
  (setq out nil)
  (vlax-for obj ms
    (if (= (strcase (vla-get-ObjectName obj)) "ACDBPDFREFERENCE")
      (setq out (append out (list obj)))
    )
  )
  out
)
(defun PdfLayout_LbdDialogInit ()
  (setq *PdfLayout_DlgH* *PdfLayout_LbdTextHeight*)
  (set_tile "lbd_pdf" *PdfLayout_DlgPdf*)
  (set_tile "lbd_xlsx" *PdfLayout_DlgXlsx*)
  (set_tile "lbd_page" *PdfLayout_DlgPage*)
  (set_tile "lbd_h" (rtos *PdfLayout_DlgH* 2 4))
  (PdfLayout_SetList "lbd_bg" (mapcar (function car) *PdfLayout_LbdBgList*))
  (set_tile "lbd_bg" (itoa (PdfLayout_LbdBgIndex *PdfLayout_LbdBgColor*)))
  (if (= *PdfLayout_DlgWhere* "L")
    (set_tile "lbd_l" "1")
    (if (= *PdfLayout_DlgWhere* "B")
      (set_tile "lbd_b" "1")
      (set_tile "lbd_m" "1")
    )
  )
  (if *PdfLayout_DlgExcl* (set_tile "lbd_excl" "1"))
)
(defun PdfLayout_LbdDialogPick (key / f dft flt)
  ;; 默认打开桌面目录；Excel/PDF 用各自的扩展名过滤；记住上次路径
  (setq dft (get_tile key))
  (if (or (not dft) (= dft ""))
    (setq dft (strcat (getenv "USERPROFILE") "\\Desktop"))
  )
  (setq flt (if (= key "lbd_pdf") "pdf" "xlsx;xls"))
  (setq f (getfiled "选择文件" dft flt 4))
  (if f (set_tile key f))
)
(defun PdfLayout_LbdDialogAccept ()
  (setq *PdfLayout_DlgPdf* (get_tile "lbd_pdf"))
  (setq *PdfLayout_DlgXlsx* (get_tile "lbd_xlsx"))
  (setq *PdfLayout_DlgPage* (get_tile "lbd_page"))
  (setq *PdfLayout_DlgH* (atof (get_tile "lbd_h")))
  (if (< *PdfLayout_DlgH* 0.001) (setq *PdfLayout_DlgH* 0.05))
  (setq *PdfLayout_DlgWhere*
    (if (= (get_tile "lbd_l") "1") "L"
      (if (= (get_tile "lbd_b") "1") "B" "M")))
  (setq *PdfLayout_DlgExcl* (= (get_tile "lbd_excl") "1"))
  (setq *PdfLayout_LbdBgColor* (cdr (nth (atoi (get_tile "lbd_bg")) *PdfLayout_LbdBgList*)))
  (setq *PdfLayout_DlgMode* "auto")
  (if (or (not *PdfLayout_DlgPdf*) (= *PdfLayout_DlgPdf* ""))
    (PdfLayout_Alert "请选择 PDF 文件。")
    (done_dialog 1)
  )
)



(defun PdfLayout_LbdDialogPreview (/ lines1 lines2 i m sorted)
  ;; 按 LBD 号显示匹配：左侧 LBD 号，右侧标签（未匹配标出）
  (setq lines1 nil lines2 nil i 0)
  (setq sorted (vl-sort *PdfLayout_LbdSelMatches*
                '(lambda (a b)
                   (if (and (cadr a) (cadr b))
                     (< (cadr a) (cadr b))
                     (if (cadr a) T nil)))))
  (foreach m sorted
    (setq lines1 (append lines1
      (list (strcat (itoa (1+ i)) ": LBD-"
                    (if (cadr m) (itoa (cadr m)) "?")))))
    (setq lines2 (append lines2 (list (if (caddr m) (caddr m) "（未找到）"))))
    (setq i (1+ i))
  )
  (PdfLayout_SetList "lbd_grid" lines1)
  (PdfLayout_SetList "lbd_names" lines2)
  (set_tile "lbd_pv_info"
    (strcat "共 " (itoa (length *PdfLayout_LbdSelMatches*))
            " 个，已匹配 "
            (itoa (length (vl-remove-if-not '(lambda (x) (caddr x))
                                            *PdfLayout_LbdSelMatches*)))
            " 个"))
)

(defun PdfLayout_LbdShowDialog (/ dclId dlgRes)
  ;; 显示 PDFLBD 主弹窗；手动模式第二次打开时预览选中文字
  (setq dclId (load_dialog (PdfLayout_FindDcl)))
  (if (and dclId (not (minusp dclId)))
    (progn
      (if (new_dialog "PdfLbd" dclId)
        (progn
          (PdfLayout_LbdDialogInit)
          (action_tile "btn_pdf" "(PdfLayout_LbdDialogPick \"lbd_pdf\")")
          (action_tile "btn_xlsx" "(PdfLayout_LbdDialogPick \"lbd_xlsx\")")
          (action_tile "accept" "(PdfLayout_LbdDialogAccept)")
          (action_tile "cancel" "(done_dialog 0)")
          (setq dlgRes (start_dialog))
          (unload_dialog dclId)
          (= dlgRes 1)
        )
        (progn
          (unload_dialog dclId)
          nil
        )
      )
    )
    nil
  )
)



(defun PdfLayout_LbdManualRun (/ ss en bb i done kv sorted)
  ;; 手动导入：框选文字 -> 独立弹窗(选Excel+八种顺序+分行容差) -> 按顺序把 Excel 的 LBD 标签依次填入
  (setq *PdfLayout_ExactOrder* nil)
  (princ "\n请框选要填写标签的多行文字(MTEXT): ")
  (setq ss (ssget '((0 . "MTEXT"))))
  (setq *PdfLayout_LbdSelPairs* nil)
  (if ss
    (progn
      (setq i 0)
      (while (setq en (ssname ss i))
        (setq bb (PdfLayout_GetExtentsSafeObj (vlax-ename->vla-object en)))
        (if bb
          (setq *PdfLayout_LbdSelPairs*
                (append *PdfLayout_LbdSelPairs* (list (cons en bb)))))
        (setq i (1+ i))
      )
    )
  )
  (if *PdfLayout_LbdSelPairs*
    (if (PdfLayout_LbdManualShow)
      (progn
        ;; 按弹窗里选的八种顺序 + 分行容差对选中文字排序
        (setq sorted (PdfLayout_SortPairsSmart *PdfLayout_LbdSelPairs* *PdfLayout_DlgOrder*))
        (setq done 0 i 0)
        (foreach pair sorted
          (setq kv (nth i *PdfLayout_LbdManualLabels*))
          (if kv
            (progn
              (vl-catch-all-apply 'vla-put-TextString
                (list (vlax-ename->vla-object (car pair)) (cdr kv)))
              (setq done (1+ done))
            )
          )
          (setq i (1+ i))
        )
        (princ (strcat "\n手动导入完成：按LBD号顺序填写 " (itoa done) " 个。"))
        (PdfLayout_Alert (strcat "手动导入完成\n\n按 Excel LBD 号顺序填写 " (itoa done) " 个"
                       (if (< done (length *PdfLayout_LbdSelPairs*))
                         "\n（选中文字多于标签，多余未改）" "")))
      )
      (princ "\n已取消。")
    )
    (princ "\n未选择文字。")
  )
  (princ)
)

(defun PdfLayout_LbdManualPick (/ f)
  (setq f (getfiled "选择标签Excel(分表名=布局名)" (strcat (getenv "USERPROFILE") "\\Desktop") "xlsx;xls" 4))
  (if f
    (progn
      (set_tile "lm_xlsx" f)
      (setq *PdfLayout_DlgXlsx* f)
      (PdfLayout_LbdManualLoadXlsx f)
    )
  )
)

(defun PdfLayout_LbdManualLoadXlsx (path / sheetMap sh)
  ;; 读 Excel：取当前布局分表（或第一个），按 LBD 号升序得到标签列表
  (setq *PdfLayout_LbdManualLabels* nil)
  (if (and path (/= path ""))
    (progn
      (setq sheetMap (PdfLayout_ReadAllLbdLabels path))
      (setq sh (if sheetMap
                 (assoc (vla-get-Name (vla-get-ActiveLayout (vla-get-ActiveDocument (vlax-get-Acad-Object))))
                        sheetMap)
                 nil))
      (if (not sh) (setq sh (if sheetMap (car sheetMap) nil)))
      (if sh
        (setq *PdfLayout_LbdManualLabels*
              (vl-sort (cdr sh) '(lambda (a b) (< (car a) (car b)))))
      )
    )
  )
  (PdfLayout_LbdManualPreview)
  (if *PdfLayout_LbdManualLabels* T nil)
)

(defun PdfLayout_LbdManualOrder ()
  (itoa (1+ (PdfLayout_GetTileInt "lm_order" 1)))
)

(defun PdfLayout_LbdManualPreview (/ order rowTol sorted lines1 lines2 i kv pair txt0)
  ;; 左列：按所选顺序排序后的文字序号+内容；右列：按 Excel LBD 号升序的标签
  (setq *PdfLayout_ExactOrder* nil)
  (setq order (PdfLayout_LbdManualOrder))
  (setq rowTol (max 1 (min 50 (PdfLayout_GetTileInt "lm_rowtol" 10))))
  (setq *PdfLayout_DlgOrder* order)
  (setq *PdfLayout_RowTol* rowTol)
  (setq sorted (PdfLayout_SortPairsSmart *PdfLayout_LbdSelPairs* order))
  (setq lines1 nil lines2 nil i 1)
  (foreach pair sorted
    (setq txt0 (vl-catch-all-apply 'vla-get-TextString
                 (list (vlax-ename->vla-object (car pair)))))
    (if (or (not txt0) (vl-catch-all-error-p txt0)) (setq txt0 ""))
    (setq lines1 (append lines1 (list (strcat (itoa i) ": " (substr txt0 1 22)))))
    (setq i (1+ i))
  )
  (setq i 1)
  (foreach kv *PdfLayout_LbdManualLabels*
    (setq lines2 (append lines2 (list (strcat "LBD-" (itoa (car kv)) ": " (cdr kv)))))
    (setq i (1+ i))
  )
  (PdfLayout_SetList "lm_grid" lines1)
  (PdfLayout_SetList "lm_names" lines2)
  (set_tile "lm_info"
    (strcat "选中文字 " (itoa (length *PdfLayout_LbdSelPairs*))
            " 个，标签 " (itoa (length *PdfLayout_LbdManualLabels*))
            " 个；顺序: " (PdfLayout_OrderDesc order)))
)

(defun PdfLayout_LbdManualShow (/ dclId dlgRes dclPath)
  (setq dclPath (PdfLayout_FindDcl))
  (if (not (findfile dclPath))
    (progn
      (PdfLayout_Alert "无法生成 PdfLayout.dcl，手动导入弹窗无法打开。")
      nil
    )
    (progn
      (setq dclId (load_dialog dclPath))
      (if (and dclId (not (minusp dclId)))
        (progn
          (if (new_dialog "PdfLbdManual" dclId)
            (progn
              (PdfLayout_SetList "lm_order"
                '("1 列优先: 左→右列、列内上→下"
                  "2 行优先: 上→下行、行内左→右"
                  "3 列优先: 右→左列、列内上→下"
                  "4 行优先: 下→上行、行内左→右"
                  "5 列优先: 左→右列、列内下→上"
                  "6 列优先: 右→左列、列内下→上"
                  "7 行优先: 上→下行、行内右→左"
                  "8 行优先: 下→上行、行内右→左"))
              (set_tile "lm_order" (itoa (- (atoi *PdfLayout_DlgOrder*) 1)))
              (set_tile "lm_rowtol" (itoa (if (and *PdfLayout_RowTol* (> *PdfLayout_RowTol* 0))
                                            *PdfLayout_RowTol* 10)))
              (PdfLayout_LbdManualPreview)
              (action_tile "lm_btnxlsx" "(PdfLayout_LbdManualPick)")
              (action_tile "lm_order" "(PdfLayout_LbdManualPreview)")
              (action_tile "lm_rowtol" "(PdfLayout_LbdManualPreview)")
              (action_tile "accept" "(PdfLayout_LbdManualAccept)")
              (action_tile "cancel" "(done_dialog 0)")
              (setq dlgRes (start_dialog))
              (unload_dialog dclId)
              (= dlgRes 1)
            )
            (progn
              (unload_dialog dclId)
              (PdfLayout_Alert "无法打开 PdfLbdManual 对话框。")
              nil
            )
          )
        )
        nil
      )
    )
  )
)

(defun PdfLayout_LbdManualAccept ()
  (setq *PdfLayout_DlgOrder* (PdfLayout_LbdManualOrder))
  (setq *PdfLayout_RowTol* (max 1 (min 50 (PdfLayout_GetTileInt "lm_rowtol" 10))))
  (PdfLayout_SaveSettings)
  (if *PdfLayout_LbdManualLabels*
    (done_dialog 1)
    (PdfLayout_Alert "请先选择标签 Excel 文件。")
  )
)

(defun c:pdflbd (/ pdfPath xlsxPath script outPath res pages items sheetMap underlays
                 ms nPage i u bb pmin pmax bw bh pItems cx cy done it num cur dOld dNew
                 sheetName sheetLabels labels mx my ptIns mObj nFill nMiss wait lay
                 pw ph pTitle shName orderWarn pg progPath logPath cancelPath cf txt ready extDone extErr cancelSent lastPage total waitMax pgNow pgStart pgEnd batOk txtH oldLbls mo dupLbl labelWhere paperItems actLayout pvp pblk ppt pmObj nPaper validItems noiseItems vped nChk oo txtScale exclMode ep1 ep2 itx ity nExcl pvp2 dclId dlgRes dlgOk needExcl exW exH exMx exMy ss en pairs sorted mNames sh layName nm modeK shN matches txt0 num0 shN0 sLbl lab0)
  (vl-load-com)
  (setq nFill 0 nMiss 0 orderWarn 0)
  (setq pdfPath nil xlsxPath nil)
  (setq dlgOk nil needExcl nil)
  (PdfLayout_LoadSettings)
  ;; 先问执行方式：手动模式先选择文字，再进弹窗
  (initget "A M")
  (setq modeK (getkword "\n执行方式 [A自动识别底图/M手动选择文字导入] <A>: "))
  (if (= modeK "M") (setq *PdfLayout_DlgMode* "manual") (setq *PdfLayout_DlgMode* "auto"))
  (if (= *PdfLayout_DlgMode* "manual")
    (PdfLayout_LbdManualRun)
    (progn
  (setq dlgOk (PdfLayout_LbdShowDialog))
  (if dlgOk
    (progn
      (setq pdfPath *PdfLayout_DlgPdf*)
      (setq xlsxPath *PdfLayout_DlgXlsx*)
      (if (= *PdfLayout_DlgPage* "0")
        (setq pgStart "1" pgEnd "0")
        (setq pgStart *PdfLayout_DlgPage* pgEnd *PdfLayout_DlgPage*)
      )
      (setq labelWhere *PdfLayout_DlgWhere*)
      (setq *PdfLayout_LbdTextHeight* *PdfLayout_DlgH*)
      (setq *PdfLayout_ExcludeRect* nil)
      (if *PdfLayout_DlgExcl* (setq needExcl T))
    )
  )
  (if (not dlgOk)
    (progn
      (if (= *PdfLayout_DlgMode* "manual")
        nil
        (progn
          (setq pdfPath (getfiled "选择PDF底图对应的原始PDF文件" (strcat (getenv "USERPROFILE") "\\Desktop") "pdf" 4))
          (if pdfPath
            (progn
              (setq xlsxPath (getfiled "选择标签Excel(分表名=布局名, 可选，回车跳过)" (strcat (getenv "USERPROFILE") "\\Desktop") "xlsx;xls" 4))
          (if (not xlsxPath) (setq xlsxPath ""))
          (progn
              (initget 6)
              (setq pgStart (getint "\n只测试第几页(回车=全部页面): "))
              (if (not pgStart)
                (setq pgStart "1" pgEnd "0")
                (setq pgStart (itoa pgStart) pgEnd pgStart)
              )
              (initget "M L B")
              (setq labelWhere (getkword "\n标签写入位置 [M模型空间/L当前布局/B两者] <M>: "))
              (if (not labelWhere) (setq labelWhere "M"))
              (initget 6)
              (setq txtScale (getreal (strcat "\n标签字高(模型单位, 当前 " (rtos *PdfLayout_LbdTextHeight* 2 3)
                                              ") <" (rtos *PdfLayout_LbdTextHeight* 2 3) ">: ")))
              (if (not txtScale) (setq txtScale *PdfLayout_LbdTextHeight*))
              (if (<= txtScale 0) (setq txtScale *PdfLayout_LbdTextHeight*))
              (setq *PdfLayout_LbdTextHeight* txtScale)
              (setq *PdfLayout_ExcludeRect* nil)
              (initget "N B")
              (setq exclMode (getkword "\n排除干扰区域? [N不排除/B框选排除] <N>: "))
              (if (not exclMode) (setq exclMode "N"))
              (if (= exclMode "B") (setq needExcl T))
              (setq dlgOk T)
          )
        )
        (princ "\n已取消。")
      )
      )
    )
    )
  )
  (if (not dlgOk)
    (princ "\n已取消。")
    (progn
      (if (and needExcl (= *PdfLayout_DlgMode* "auto"))
        (progn
          (princ "\n请在当前视图框选要排除的区域（例如右下角细节图）…")
          (setq ep1 (getpoint "\n排除区域第一角: "))
          (if ep1 (setq ep2 (getcorner ep1 "\n排除区域对角(拖动矩形): ")))
          ;; 统一转 WCS（避免当前 UCS 偏移导致框不中）
          (if ep1 (setq ep1 (trans ep1 1 0)))
          (if ep2 (setq ep2 (trans ep2 1 0)))
          (if (and ep1 ep2)
            (progn
              (if (/= (strcase (getvar "CTAB")) "MODEL")
                (progn
                  (princ (strcat "\n框选(纸张坐标): " (vl-princ-to-string ep1) " " (vl-princ-to-string ep2)))
                  (setq pvp2 (PdfLayout_LayoutBiggestVp
                               (vla-get-ActiveLayout (vla-get-ActiveDocument (vlax-get-Acad-Object)))))
                  (if pvp2
                    (progn
                      (setq ep1 (PdfLayout_PaperToModel pvp2 ep1))
                      (setq ep2 (PdfLayout_PaperToModel pvp2 ep2))
                    )
                  )
                )
              )
              (if (and ep1 ep2)
                (progn
                  ;; 范围向外扩 10%，避免细节图边缘的标记漏掉
                  (setq exW (- (max (car ep1) (car ep2)) (min (car ep1) (car ep2))))
                  (setq exH (- (max (cadr ep1) (cadr ep2)) (min (cadr ep1) (cadr ep2))))
                  (setq exMx (* exW 0.1) exMy (* exH 0.1))
                  (setq *PdfLayout_ExcludeRect*
                    (list (- (min (car ep1) (car ep2)) exMx)
                          (- (min (cadr ep1) (cadr ep2)) exMy)
                          (+ (max (car ep1) (car ep2)) exMx)
                          (+ (max (cadr ep1) (cadr ep2)) exMy)))
                  (princ (strcat "\n排除区域(模型坐标): " (vl-princ-to-string *PdfLayout_ExcludeRect*)))
                )
                (princ "\n排除区域换算失败，按不排除处理。")
              )
            )
            (princ "\n未选择排除区域，按不排除处理。")
          )
        )
      )
      ;; 手动模式：先框选已有多行文字，再从 Excel 分表导入 LBD 标签并按位置顺序改名
      (if (= *PdfLayout_DlgMode* "manual")
        nil
      )
      (if (and (= *PdfLayout_DlgMode* "auto") pdfPath xlsxPath)
        (progn
          (princ "\n正在启动PDF文字提取(未装Python会快速提示)…")
          (PdfLayout_WritePyScript)
          (setq script (strcat (getvar "TEMPPREFIX") "pdf_extract.py"))
          (setq outPath (strcat (getvar "TEMPPREFIX") "pdflbd_extract.txt"))
          (setq progPath (strcat (getvar "TEMPPREFIX") "pdflbd_progress.txt"))
          (setq logPath (strcat (getvar "TEMPPREFIX") "pdflbd_log.txt"))
          (setq cancelPath (strcat progPath ".cancel"))
          (foreach pf (list outPath progPath logPath cancelPath
                            (strcat (getvar "TEMPPREFIX") "pdflbd_bat.txt"))
            (if (findfile pf) (vl-file-delete pf))
          )
          (PdfLayout_LoadSettings)
          (PdfLayout_EnsurePython)
          (PdfLayout_WriteBat script pdfPath outPath progPath logPath pgStart pgEnd)
          (vl-catch-all-apply 'startapp
            (list (strcat (getvar "TEMPPREFIX") "pdflbd_run.bat")))
          (setq wait 0 ready nil extErr nil cancelSent nil batOk nil)
          (while (and (< wait 8) (not batOk))
            (if (findfile (strcat (getvar "TEMPPREFIX") "pdflbd_bat.txt"))
              (setq batOk T)
            )
            (if (not batOk)
              (progn
                (command "._DELAY" 500)
                (setq wait (1+ wait))
              )
            )
          )
          (if (not batOk)
            (progn
              (princ "\n直接启动失败，改用 cmd /c 启动…")
              (vl-catch-all-apply 'startapp
                (list (strcat "cmd /c \"" (getvar "TEMPPREFIX") "pdflbd_run.bat\"")))
              (setq wait 0)
              (while (and (< wait 8) (not batOk))
                (if (findfile (strcat (getvar "TEMPPREFIX") "pdflbd_bat.txt"))
                  (setq batOk T)
                )
                (if (not batOk)
                  (progn
                    (command "._DELAY" 500)
                    (setq wait (1+ wait))
                  )
                )
              )
            )
          )
          (if (not batOk)
            (progn
              (PdfLayout_Alert "无法启动PDF提取进程：startapp 无法运行批处理。")
              (setq ready 'cancel)
            )
          )
          (while (and (< wait 16) (not ready))
            (setq txt (PdfLayout_ReadFileText progPath))
            (if (and txt (vl-string-search "READY" (strcase txt)))
              (setq ready T)
            )
            (if (and (not ready) (PdfLayout_GrreadEsc))
              (setq ready 'cancel)
            )
            (if (not ready) (setq wait (1+ wait)))
          )
          (if (= ready 'cancel)
            (princ "\n已取消。")
            (if (not ready)
              (progn
                (setq txt (PdfLayout_ReadFileText logPath))
                (PdfLayout_Alert (strcat "PDF文字提取未能启动。\n"
                               "请确认已安装 Python 并执行过: python -m pip install pypdf"
                               (if (and txt (/= txt ""))
                                 (strcat "\n日志: " (substr txt 1 300))
                                 "")))
              )
              (progn
                (setq wait 0 extDone nil lastPage -1 total 0 waitMax 1200)
                (while (and (< wait waitMax) (not extDone))
                  (setq txt (PdfLayout_ReadFileText progPath))
                  (if (and (not cancelSent) (= total 0) txt)
                    (setq total (PdfLayout_ProgNum txt "TOTAL"))
                  )
                  (if (and (not cancelSent) total (> total 0))
                    (setq waitMax (min 3600 (* 2 (+ (* total 2) 30))))
                  )
                  (cond
                    ((and txt (vl-string-search "DONE" (strcase txt))) (setq extDone T))
                    ((and txt (vl-string-search "ERR" (strcase txt))) (setq extDone T extErr T))
                    ((and txt (vl-string-search "CANCELLED" (strcase txt))) (setq extDone T))
                    (T
                      (setq pgNow (PdfLayout_ProgNum txt "PAGE"))
                      (if (and pgNow (/= pgNow lastPage))
                        (progn
                          (princ (strcat "\n  正在提取第 " (itoa pgNow)
                                         (if (and total (> total 0))
                                           (strcat "/" (itoa total))
                                           "")
                                         " 页…"))
                          (setq lastPage pgNow)
                        )
                      )
                    )
                  )
                  (if (not extDone)
                    (progn
                      (if (PdfLayout_GrreadEsc)
                        (progn
                          (setq cf (open cancelPath "w"))
                          (if cf (progn (princ "CANCEL" cf) (close cf)))
                          (setq cancelSent T)
                          (princ "\n已按 Esc 取消，等待提取进程退出…")
                        )
                      )
                      (setq wait (1+ wait))
                    )
                  )
                )
                (cond
                  (extErr
                    (setq txt (PdfLayout_ReadFileText logPath))
                    (PdfLayout_Alert (strcat "PDF文字提取出错。\n"
                                   (if (and txt (/= txt ""))
                                     (substr txt 1 400)
                                     "请检查日志文件。"))))
                  ((and (not extDone) (not cancelSent))
                    (PdfLayout_Alert "PDF文字提取超时，请检查Python环境或改用分段提取。"))
                  (cancelSent
                    (princ "\n已取消本次提取。"))
                )
              )
            )
          )
          (if (and (not extErr) (not cancelSent) (findfile outPath))
            (progn
              (setq res (PdfLayout_ReadExtractFile outPath))
              (setq pages (car res) items (cadr res))
              ;; 把干扰片段（LBD 后没有编号的注释/图例文字）与有效标记分开
              (setq validItems nil noiseItems nil)
              (foreach it items
                (if (PdfLayout_LbdNumFromText (nth 3 it))
                  (setq validItems (append validItems (list it)))
                  (setq noiseItems (append noiseItems (list it)))
                )
              )
              (princ (strcat "\n已提取 " (itoa (length pages)) " 页，识别到 "
                             (itoa (length items)) " 个LBD片段：有效 "
                             (itoa (length validItems)) " 个，干扰 "
                             (itoa (length noiseItems)) " 个(已过滤)。"))
              (if *PdfLayout_Debug*
                (foreach nz noiseItems
                  (princ (strcat "\n[调试] 干扰片段(第" (itoa (car nz)) "页): " (nth 3 nz)))
                )
              )
              (if (and xlsxPath (/= xlsxPath ""))
                (progn
                  (princ "\n正在读取标签Excel分表…")
                  (setq sheetMap (PdfLayout_ReadAllLbdLabels xlsxPath))
                )
                (princ "\n未提供Excel标签，将按LBD编号填写。")
              )
              (princ "\n[步骤] 分表读取完成")
              (setq underlays (PdfLayout_GetPdfUnderlays))
              (princ (strcat "\n[步骤] 底图数=" (itoa (length underlays))))
              (setq ms (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-Acad-Object))))
              ;; 先删除旧的 LBD 标签（重复运行时避免叠加）
              (setq oldLbls nil)
              (vlax-for mo ms
                (if (and (= (vla-get-ObjectName mo) "AcDbMText")
                         (= (strcase (vla-get-Layer mo)) (strcase "LBD标签")))
                  (setq oldLbls (append oldLbls (list mo)))
                )
              )
              (foreach mo oldLbls
                (vl-catch-all-apply 'vla-Delete (list mo))
              )
              (if (/= (length underlays) (length pages))
                (princ (strcat "\n注意: 模型空间底图数(" (itoa (length underlays))
                               ")与PDF页数(" (itoa (length pages)) ")不一致，按顺序对应前"
                               (itoa (min (length underlays) (length pages))) "页。"))
              )
              (setq i 0)
              (princ "\n[步骤] 开始填写标签")
              (foreach u underlays
                (setq pgnum (1+ i))
                (setq bb (PdfLayout_GetExtentsSafeObj u))
                (if bb
                  (progn
                    (setq pmin (car bb) pmax (cadr bb))
                    (setq bw (- (car pmax) (car pmin)))
                    (setq bh (- (cadr pmax) (cadr pmin)))
                    (setq pw 1.0 ph 1.0 pTitle "")
                    (foreach pg pages
                      (if (= (car pg) pgnum)
                        (setq pw (cadr pg) ph (caddr pg) pTitle (cadddr pg))
                      )
                    )
                    ;; 底图比例与PDF页不一致时提示（可能旋转/裁剪）
                    (if (and (> pw 0.0) (> ph 0.0) (> bw 0.0) (> bh 0.0))
                      (if (or (> (/ bw bh) (* 1.15 (/ pw ph)))
                              (< (/ bw bh) (* 0.85 (/ pw ph))))
                        (princ (strcat "\n注意: 第" (itoa pgnum)
                                       "页底图比例与PDF不一致，可能旋转/裁剪，标签位置可能不准。"))
                      )
                    )
                    ;; 页序校验：该页标题应包含对应分表名
                    (if (and sheetMap (nth (1- pgnum) sheetMap))
                      (progn
                        (setq shName (car (nth (1- pgnum) sheetMap)))
                        (if (and pTitle shName
                                 (not (vl-string-search (strcase shName) (strcase pTitle))))
                          (setq orderWarn (1+ orderWarn))
                        )
                      )
                    )                    (setq pItems nil)
                    (foreach it validItems
                      (if (= (nth 0 it) pgnum)
                        (progn
                          (setq itx (+ (car pmin) (* (nth 1 it) bw)))
                          (setq ity (+ (cadr pmin) (* (nth 2 it) bh)))
                          (if (PdfLayout_PtInRect (list itx ity) *PdfLayout_ExcludeRect*)
                            (progn
                              (setq nExcl (1+ nExcl))
                              (if *PdfLayout_Debug*
                                (princ (strcat "\n[调试] 已排除 LBD-"
                                               (itoa (PdfLayout_LbdNumFromText (nth 3 it)))
                                               " fx=" (rtos (nth 1 it) 2 4)
                                               " fy=" (rtos (nth 2 it) 2 4)))
                              )
                            )
                            (setq pItems (append pItems (list it)))
                          )
                        )
                      )
                    )
                    ;; 去重：同一编号且位置几乎相同（距离<0.02）才视为重复；
                    ;; 同一页左右多个区域各有相同编号时，全部保留（各自填标签）
                    (setq done nil)
                    (foreach it pItems
                      (setq num (PdfLayout_LbdNumFromText (nth 3 it)))
                      (if num
                        (progn
                          (setq dupLbl nil)
                          (foreach d done
                            (if (and (= (car d) num)
                                     (< (distance (list (cadr d) (caddr d))
                                                  (list (nth 1 it) (nth 2 it)))
                                        0.02))
                              (setq dupLbl T)
                            )
                          )
                          (if (not dupLbl)
                            (setq done (append done (list (list num (nth 1 it) (nth 2 it)
                                                           (PdfLayout_LbdSheetFromText (nth 3 it))))))
                          )
                        )
                      )
                    )
                    (foreach d done
                      (setq num (car d) fx (cadr d) fy (caddr d) shN (nth 3 d))
                      (setq sheetLabels (if shN
                                          (cdr (assoc shN sheetMap))
                                          (if sheetMap (cdr (nth (1- pgnum) sheetMap)) nil)))
                      (setq labels (if sheetLabels (cdr (assoc num sheetLabels)) nil))
                      (if (and (not labels) (not sheetMap))
                        (setq labels (strcat "LBD-" (itoa num)))
                      )
                      (if labels
                        (progn
                          (setq mx (+ (car pmin) (* fx bw)))
                          (setq my (+ (cadr pmin) (* fy bh)))
                          (if *PdfLayout_Debug*
                            (princ (strcat "\n[调试] LBD-" (itoa num)
                                           " fx=" (rtos fx 2 4) " fy=" (rtos fy 2 4)
                                           " -> (" (rtos mx 2 2) "," (rtos my 2 2) ")"))
                          )
                          ;; 标签字高：固定模型单位高度（默认0.05），运行时可在 PDFLBD 里调整
                          (setq txtH *PdfLayout_LbdTextHeight*)
                          (if (not txtH) (setq txtH 0.05))
                          (if (< txtH 0.001) (setq txtH 0.001))
                          (if (> txtH 1000.0) (setq txtH 1000.0))
                          (if (and labels (/= labelWhere "M"))
                            (setq paperItems (append paperItems (list (list num mx my labels))))
                          )
                          (setq ptIns (list mx my 0.0))
                          (if (/= labelWhere "L")
                            (progn
                              (setq mObj (vl-catch-all-apply 'vla-AddMText
                                           (list ms (vlax-3d-point ptIns)
                                                 (* txtH (+ (* 0.8 (strlen labels)) 0.2)) labels)))
                              (if (and mObj (not (vl-catch-all-error-p mObj)))
                                (progn
                                  (vl-catch-all-apply 'vla-put-Height (list mObj txtH))
                                  (vl-catch-all-apply 'vla-put-AttachmentPoint (list mObj 5))
                                  ;; 置前，避免被 PDF 底图盖住
                                  (vl-catch-all-apply
                                    '(lambda () (command "._DRAWORDER"
                                                         (vlax-vla-object->ename mObj)
                                                         "" "_Front"))
                                    nil)
                                  (setq lay (PdfLayout_EnsureLayer "LBD标签"))
                                  (if (and lay (not (vl-catch-all-error-p lay)))
                                    (vl-catch-all-apply 'vla-put-Layer (list mObj "LBD标签"))
                                  )
                                  ;; 红底白字 + 背景贴合文字（DXF 设置，ZWCAD 兼容）
                                  (PdfLayout_MTextRedWhite mObj)

                                  (setq nFill (1+ nFill))
                                  (princ (strcat "\n第" (itoa pgnum) "页 LBD-" (itoa num)
                                                 " -> " labels))
                                )
                              )
                            )
                          )
                        )
                        (setq nMiss (1+ nMiss))
                      )
                    )
                  )
                )
                (setq i (1+ i))
              )
              (princ "\n[步骤] 模型空间填写完成，准备布局写入")
              ;; 把标签投影写入当前布局纸张空间（打印时一定可见）
              (if (and paperItems (/= labelWhere "M"))
                (progn
                  (setq actLayout (vla-get-ActiveLayout
                                    (vla-get-ActiveDocument (vlax-get-Acad-Object))))
                  (setq pvp (PdfLayout_LayoutBiggestVp actLayout))
                  (if pvp
                    (progn
                      (setq pblk (vla-get-Block actLayout))
                      (if *PdfLayout_Debug*
                        (progn
                          (setq vped (entget (vlax-vla-object->ename pvp)))
                          (princ (strcat "\n[调试] 视口DXF 10=" (vl-princ-to-string (cdr (assoc 10 vped)))
                                         " 12=" (vl-princ-to-string (cdr (assoc 12 vped)))
                                         " 40=" (vl-princ-to-string (cdr (assoc 40 vped)))))
                          (princ (strcat "\n[调试] 视口纸张范围=" (vl-princ-to-string (PdfLayout_GetExtentsSafeObj pvp))))
                          (princ (strcat "\n[调试] 写入布局名: " (vla-get-Name actLayout)))
                        )
                      )
                      ;; 先删除布局里旧的 LBD 标签（重复运行不叠加）
                      (setq oldLbls nil)
                      (vlax-for oo pblk
                        (if (and (= (vla-get-ObjectName oo) "AcDbMText")
                                 (= (strcase (vla-get-Layer oo)) (strcase "LBD标签")))
                          (setq oldLbls (append oldLbls (list oo)))
                        )
                      )
                      (foreach oo oldLbls
                        (vl-catch-all-apply 'vla-Delete (list oo))
                      )
                      (setq nPaper 0)
                      (foreach pi paperItems
                        (setq ppt (PdfLayout_ModelToPaper pvp (list (cadr pi) (caddr pi))))
                        (if ppt
                          (progn
                            (setq pmObj (vl-catch-all-apply 'vla-AddMText
                                          (list pblk (vlax-3d-point ppt)
                                                (* 5.0 (+ (* 0.8 (strlen (cadddr pi))) 0.2)) (cadddr pi))))
                            (if (and pmObj (not (vl-catch-all-error-p pmObj)))
                              (progn
                                (vl-catch-all-apply 'vla-put-Height (list pmObj 5.0))
                                (vl-catch-all-apply 'vla-put-AttachmentPoint (list pmObj 5))
                                (setq lay (PdfLayout_EnsureLayer "LBD标签"))
                                (if (and lay (not (vl-catch-all-error-p lay)))
                                  (vl-catch-all-apply 'vla-put-Layer (list pmObj "LBD标签"))
                                )
                                ;; 红底白字 + 背景贴合文字（DXF 设置，ZWCAD 兼容）
                                (PdfLayout_MTextRedWhite pmObj)

                                (vl-catch-all-apply
                                  '(lambda () (command "._DRAWORDER"
                                                       (vlax-vla-object->ename pmObj)
                                                       "" "_Front"))
                                  nil)
                                (setq nPaper (1+ nPaper))
                              )
                            )
                          )
                        )
                      )
                      (princ (strcat "\n已把 " (itoa nPaper) " 个标签写入当前布局(纸张空间)。"))
                      ;; 验证：确保图层打开，并统计布局内实际存在的标签
                      (setq lay (PdfLayout_EnsureLayer "LBD标签"))
                      (if (and lay (not (vl-catch-all-error-p lay)))
                        (vl-catch-all-apply 'vla-put-LayerOn (list lay :vlax-true))
                      )
                      (setq nChk 0)
                      (vlax-for oo pblk
                        (if (and (= (vla-get-ObjectName oo) "AcDbMText")
                                 (= (strcase (vla-get-Layer oo)) (strcase "LBD标签")))
                          (progn
                            (setq nChk (1+ nChk))
                            (if (<= nChk 3)
                              (princ (strcat "\n[调试] 布局标签#" (itoa nChk) " 插入点="
                                             (vl-princ-to-string
                                               (cdr (assoc 10 (entget (vlax-vla-object->ename oo)))))))
                            )
                          )
                        )
                      )
                      (princ (strcat "\n[调试] 布局内 LBD标签 图层多行文字数=" (itoa nChk)))
                      (vl-catch-all-apply '(lambda () (command "._REGENALL")) nil)
                    )
                    (princ "\n注意: 当前布局没有视口，无法投影到纸张，跳过布局写入。")
                  )
                )
              )
              (if (= labelWhere "L")
                (princ (strcat "\n完成：布局写入 " (itoa nPaper) " 个，未找到标签 " (itoa nMiss) " 个。"))
                (princ (strcat "\n完成：模型空间填写 " (itoa nFill) " 个"
                               (if (and (= labelWhere "B") (> nPaper 0))
                                 (strcat "，布局写入 " (itoa nPaper) " 个")
                                 "")
                               "，未找到标签 " (itoa nMiss) " 个。"))
              )
              (if (> nExcl 0)
                (princ (strcat "（已排除干扰区域 " (itoa nExcl) " 个）"))
              )
              (if (> orderWarn 0)
                (princ (strcat "\n警告: 有 " (itoa orderWarn)
                               " 页的分表名与PDF页内容对不上，页序可能错位，请核对。"))
              )            )
          )
        )
      )
    )
  )
  )
  )
  (princ)
)

;;;-------------------------------------------------------------
;;; 加载提示
;;;-------------------------------------------------------------
(defun c:pdfpydiag (/ dir py ini)
  (vl-load-com)
  (PdfLayout_LoadSettings)
  (setq dir (if (and *PdfLayout_LspDir* (/= *PdfLayout_LspDir* "")) *PdfLayout_LspDir* "(空)"))
  (setq py (if (and *PdfLayout_LspDir* (/= *PdfLayout_LspDir* ""))
             (strcat *PdfLayout_LspDir* "python\\python.exe")
             ""))
  (setq ini (PdfLayout_IniGet "PythonPath"))
  (if (not ini) (setq ini ""))
  (princ (strcat "\n[PDFPYDIAG] LSP目录: " dir))
  (princ (strcat "\n[PDFPYDIAG] 随包Python: " py
                 " -> " (if (findfile py) "存在" "不存在")))
  (princ (strcat "\n[PDFPYDIAG] ini PythonPath: " ini
                 (if (and ini (/= ini "") (findfile ini)) " (文件存在)" "")))
  (setenv "PDFPY_TEST" "OK")
  (princ (strcat "\n[PDFPYDIAG] setenv读写: " (getenv "PDFPY_TEST")))
  (princ "\n[PDFPYDIAG] 完成，请把以上输出发给我。")
  (princ)
)

(defun c:pdffitvp (/ underlays n u bb vp)
  ;; 把当前布局的最大视口对准指定底图（输入模型空间底图序号）
  (vl-load-com)
  (setq underlays (PdfLayout_GetPdfUnderlays))
  (if (not underlays)
    (princ "\\n模型空间没有识别到 PDF 底图。")
    (progn
      (princ (strcat "\\n模型空间 PDF 底图数: " (itoa (length underlays))
                     "（按导入顺序）"))
      (initget 6)
      (setq n (getint (strcat "\\n要对准第几张底图(1-" (itoa (length underlays)) "): ")))
      (if (and n (<= 1 n (length underlays)))
        (progn
          (setq u (nth (1- n) underlays))
          (setq bb (PdfLayout_GetExtentsSafeObj u))
          (if bb
            (progn
              (setq vp (PdfLayout_LayoutBiggestVp
                         (vla-get-ActiveLayout (vla-get-ActiveDocument (vlax-get-Acad-Object)))))
              (if vp
                (progn
                  (PdfLayout_FitViewport vp bb nil)
                  (princ (strcat "\\n已把当前布局视口对准第 " (itoa n) " 张底图。")))
                (princ "\\n当前布局没有视口。")
              )
            )
            (princ "\\n底图范围读取失败。")
          )
        )
        (princ "\\n已取消。")
      )
    )
  )
  (princ)
)
(setvar "FILEDIA" 1)
(princ "\n=====================================")
  (princ "\n  MAP文件工具箱 v2.16 已加载")
(princ "\n  命令: PDFLAYOUT    (对话框版)")
(princ "\n  命令: PDFLAYOUTTEST (命名引擎自检)")
(princ "\n  命令: PDFLAYOUTDEBUG (视口适配调试)")
(princ "\n  命令: PDFLBD      (识别底图LBD并填写标签)")
(princ "\n  命令: PDFGRID      (批量生成N×M网格多行文字并自动命名)")
(princ "\n  命令: PDFTOOL      (统一入口主菜单)")
(princ "\n  命令: PDFMTDIAG   (多行文字背景遮罩诊断)")
(princ "\n  流程: 识别模型空间图纸 → 复制模板布局")
(princ "\n        → 按规则自动改名 → 视口自动对应")
(princ "\n=====================================")
(princ)

;;;-------------------------------------------------------------
;;; PDFGRID：批量生成 N×M 网格多行文字并自动命名
;;; 方案预设 + 几何自适应（按范围自动算 / 固定绝对参数）
;;;-------------------------------------------------------------

(defun PdfLayout_ExcelCleanup (xl hadExcel objs / wbs cnt quitNow)
  ;; 释放 Excel 读取后遗留的 COM 引用，并退出不再需要的后台 Excel 实例，
  ;; 避免“读取表格后 Excel 一直挂在后台”。
  (while objs
    (if (car objs)
      (vl-catch-all-apply 'vlax-release-object (list (car objs)))
    )
    (setq objs (cdr objs))
  )
  ;; 是否退出该 Excel：本次新建（原来没会议）必须退出；或该实例已无任何打开的工作簿
  ;; （上次遗留的空后台）一并退出；若用户自己开着工作簿（Count>=1）则绝不退出。
  (setq quitNow (not hadExcel))
  (if (not quitNow)
    (progn
      (setq wbs (vl-catch-all-apply 'vlax-get-property (list xl 'Workbooks)))
      (if (and wbs (not (vl-catch-all-error-p wbs)))
        (progn
          (setq cnt (vl-catch-all-apply 'vlax-get-property (list wbs 'Count)))
          (if (and (not (vl-catch-all-error-p cnt)) (numberp cnt) (= cnt 0))
            (setq quitNow T)
          )
        )
      )
    )
  )
  (if quitNow
    (vl-catch-all-apply 'vlax-invoke-method (list xl 'Quit))
  )
  (if (and wbs (not (vl-catch-all-error-p wbs)))
    (vl-catch-all-apply 'vlax-release-object (list wbs))
  )
  (if xl
    (vl-catch-all-apply 'vlax-release-object (list xl))
  )
  (setq xl nil)
)


(defun PdfLayout_GridPairsFromGlobals (/ rows cols rowSp colSp fx fy i j pt out)
  (setq rows (max 1 *PdfLayout_GridRows*) cols (max 1 *PdfLayout_GridCols*))
  (setq rowSp *PdfLayout_GridRowSp* colSp *PdfLayout_GridColSp*)
  (setq fx *PdfLayout_GridFirstX* fy *PdfLayout_GridFirstY*)
  (setq out nil i 0)
  (while (< i rows)
    (setq j 0)
    (while (< j cols)
      (setq pt (list (+ fx (* j colSp *PdfLayout_GridColDir*))
                     (+ fy (* i rowSp *PdfLayout_GridRowDir*)) 0.0))
      (setq out (append out (list (cons nil (list pt pt)))))
      (setq j (1+ j))
    )
    (setq i (1+ i))
  )
  out
)

(defun PdfLayout_GridUpdate (/ pairs order sorted i name names lines grid colSp rowSp h uw uh sx sy bgIdx txtIdx srcDesc initCol initRow rotDeg w)
  (setq *PdfLayout_GridRows* (max 1 (min 100 (PdfLayout_GetTileInt "g_rows" 4))))
  (setq *PdfLayout_GridCols* (max 1 (min 100 (PdfLayout_GetTileInt "g_cols" 5))))
  (if (/= *PdfLayout_GridGeom* "S")
    (setq *PdfLayout_GridGeom* (if (= (PdfLayout_GetTileStr "g_geof") "1") "3" "1"))
  )
  (setq *PdfLayout_GridHMode* (if (= (PdfLayout_GetTileStr "g_hmanual") "1") "manual" "auto"))
  (setq *PdfLayout_GridHRatio* (max 0.01 (min 2.0 (PdfLayout_GetTileReal "g_hratio" 0.3))))
  (setq *PdfLayout_GridMMode* (if (= (PdfLayout_GetTileStr "g_mmode") "1") "custom" "auto"))
  (setq *PdfLayout_GridMT* (PdfLayout_GetTileReal "g_mt" 0.0))
  (setq *PdfLayout_GridMB* (PdfLayout_GetTileReal "g_mb" 0.0))
  (setq *PdfLayout_GridML* (PdfLayout_GetTileReal "g_ml" 0.0))
  (setq *PdfLayout_GridMR* (PdfLayout_GetTileReal "g_mr" 0.0))
  (if (= *PdfLayout_GridGeom* "1")
    (progn
  ;; Auto margin depends on text rotation (0/180 horizontal, 90/270 vertical)
  (setq initCol (if (> *PdfLayout_GridCols* 1) (/ *PdfLayout_GridExtX* (1- *PdfLayout_GridCols*)) *PdfLayout_GridExtX*))
  (setq initRow (if (> *PdfLayout_GridRows* 1) (/ *PdfLayout_GridExtY* (1- *PdfLayout_GridRows*)) *PdfLayout_GridExtY*))
  (setq h (min initCol initRow))
  (if (<= h 0.0) (setq h 1.0))
  (if (= *PdfLayout_GridHMode* "auto")
    (setq h (* h *PdfLayout_GridHRatio*))
    (setq h (PdfLayout_GetTileReal "g_h" 0.5)))
  (if (<= h 0.0) (setq h 1.0))
  (setq rotDeg (nth (max 0 (min 3 (PdfLayout_GetTileInt "g_rot" 0))) '(0 90 180 270)))
  (setq w (min (* h 4.0) initCol))
  (if (<= w 0.0) (setq w h))
  (if (member rotDeg '(90 270))
    (progn
      (setq *PdfLayout_GridMT* (* w 2.0))
      (setq *PdfLayout_GridMB* *PdfLayout_GridMT*)
      (setq *PdfLayout_GridML* (* h 0.5))
      (setq *PdfLayout_GridMR* *PdfLayout_GridML*))
    (progn
      (setq *PdfLayout_GridMT* (* h 2.0))
      (setq *PdfLayout_GridMB* *PdfLayout_GridMT*)
      (setq *PdfLayout_GridML* (* w 0.5))
      (setq *PdfLayout_GridMR* *PdfLayout_GridML*)))
      ;; 按范围自动算：列距=范围宽/(列数-1)，行距=范围高/(行数-1)，字高=min(行距,列距)×比例
  (if (equal *PdfLayout_GridMMode* "custom")
    (progn
      (setq *PdfLayout_GridMT* (PdfLayout_GetTileReal "g_mt" 0.0))
      (setq *PdfLayout_GridMB* (PdfLayout_GetTileReal "g_mb" 0.0))
      (setq *PdfLayout_GridML* (PdfLayout_GetTileReal "g_ml" 0.0))
      (setq *PdfLayout_GridMR* (PdfLayout_GetTileReal "g_mr" 0.0)))
  )
      (setq uw (max 0.0 (- *PdfLayout_GridExtX* *PdfLayout_GridML* *PdfLayout_GridMR*)))
      (setq uh (max 0.0 (- *PdfLayout_GridExtY* *PdfLayout_GridMT* *PdfLayout_GridMB*)))
      (setq colSp (if (> *PdfLayout_GridCols* 1)
                    (/ uw (1- *PdfLayout_GridCols*))
                    uw))
      (setq rowSp (if (> *PdfLayout_GridRows* 1)
                    (/ uh (1- *PdfLayout_GridRows*))
                    uh))
      (setq *PdfLayout_GridColSp* colSp)
      (setq *PdfLayout_GridRowSp* rowSp)
      (setq sx (if *PdfLayout_GridStart* (car *PdfLayout_GridStart*) 0.0))
      (setq sy (if *PdfLayout_GridStart* (cadr *PdfLayout_GridStart*) 0.0))
      (setq *PdfLayout_GridFirstX* (+ sx *PdfLayout_GridML*
                                     (if (> *PdfLayout_GridCols* 1) 0.0 (/ uw 2.0))))
      (setq *PdfLayout_GridFirstY* (- sy *PdfLayout_GridMT*
                                     (if (> *PdfLayout_GridRows* 1) 0.0 (/ uh 2.0))))
      (setq *PdfLayout_GridColDir* 1)
      (setq *PdfLayout_GridRowDir* -1)
      (if (= *PdfLayout_GridHMode* "auto")
        (progn
          (setq h (min rowSp colSp))
          (if (<= h 0.0) (setq h (max *PdfLayout_GridExtX* *PdfLayout_GridExtY*)))
          (if (<= h 0.0) (setq h 1.0))
          (setq *PdfLayout_GridH* (* h *PdfLayout_GridHRatio*))
          (if (<= *PdfLayout_GridH* 0.0) (setq *PdfLayout_GridH* 1.7))
          (set_tile "g_h" (rtos *PdfLayout_GridH* 2 2))
        )
        (setq *PdfLayout_GridH* (PdfLayout_GetTileReal "g_h" 0.5))
      )
      (set_tile "g_rowsp" (rtos *PdfLayout_GridRowSp* 2 2))
      (set_tile "g_colsp" (rtos *PdfLayout_GridColSp* 2 2))
    )
    (progn
      (setq *PdfLayout_GridRowSp* (PdfLayout_GetTileReal "g_rowsp" 10.0))
      (setq *PdfLayout_GridColSp* (PdfLayout_GetTileReal "g_colsp" 20.0))
      (setq *PdfLayout_GridH* (PdfLayout_GetTileReal "g_h" 0.5))
      (setq *PdfLayout_GridFirstX* (if *PdfLayout_GridStart* (car *PdfLayout_GridStart*) 0.0))
      (setq *PdfLayout_GridFirstY* (if *PdfLayout_GridStart* (cadr *PdfLayout_GridStart*) 0.0))
    )
  )
  (mode_tile "g_ml" (if (equal *PdfLayout_GridMMode* "custom") 0 1))
  (mode_tile "g_mr" (if (equal *PdfLayout_GridMMode* "custom") 0 1))
  (mode_tile "g_mt" (if (equal *PdfLayout_GridMMode* "custom") 0 1))
  (mode_tile "g_mb" (if (equal *PdfLayout_GridMMode* "custom") 0 1))
  (mode_tile "g_hratio" (if (and (= *PdfLayout_GridGeom* "1") (= *PdfLayout_GridHMode* "auto")) 0 1))
  (mode_tile "g_h" (if (and (= *PdfLayout_GridGeom* "1") (= *PdfLayout_GridHMode* "auto")) 1 0))
  (if (= *PdfLayout_GridGeom* "S")
    (progn
      (mode_tile "g_rows" 1)
      (mode_tile "g_cols" 1)
      (mode_tile "g_rowsp" 1)
      (mode_tile "g_colsp" 1)
      (mode_tile "g_geoa" 1)
      (mode_tile "g_geof" 1)
      (mode_tile "g_rot" 1)
    )
  )
  (setq *PdfLayout_GridRot* (nth (max 0 (min 3 (PdfLayout_GetTileInt "g_rot" 0)))
                                 '(0 90 180 270)))
(setq *PdfLayout_GridBg* (if (= (PdfLayout_GetTileStr "g_bgon") "1") "fill" "none"))
  (setq bgIdx (max 0 (min 11 (PdfLayout_GetTileInt "g_bgcolor" 0))))
  (if (< bgIdx 11)
    (setq *PdfLayout_GridBgColor* (nth bgIdx (PdfLayout_GridColorList)))
    (setq *PdfLayout_GridBgColor* (max 1 (min 255 (PdfLayout_GetTileInt "g_bgaci" 1))))
  )
  (setq txtIdx (max 0 (min 11 (PdfLayout_GetTileInt "g_txtcolor" 0))))
  (if (< txtIdx 11)
    (progn
      (setq *PdfLayout_GridTxtColor* (nth txtIdx (PdfLayout_GridColorList)))
      (setq *PdfLayout_GridTxtRGB* (nth txtIdx (PdfLayout_GridRgbList)))
      (setq *PdfLayout_GridTxtTrue* T)
    )
    (progn
      (setq *PdfLayout_GridTxtColor* (max 1 (min 255 (PdfLayout_GetTileInt "g_txtaci" 7))))
      (setq *PdfLayout_GridTxtRGB* 0)
      (setq *PdfLayout_GridTxtTrue* nil)
    )
  )
  (setq *PdfLayout_GridBgScale* (max 1.0 (min 5.0 (PdfLayout_GetTileReal "g_bgscale" 1.0))))
  (setq *PdfLayout_GridBgRGB* (PdfLayout_GridColorRGB *PdfLayout_GridBgColor*))
  (mode_tile "g_bgcolor" (if (= *PdfLayout_GridBg* "fill") 0 1))
  (mode_tile "g_bgaci" (if (and (= *PdfLayout_GridBg* "fill") (= bgIdx 11)) 0 1))
  (mode_tile "g_bgscale" (if (= *PdfLayout_GridBg* "fill") 0 1))
  (mode_tile "g_txtaci" (if (= txtIdx 11) 0 1))
  (setq *PdfLayout_GridSrc*
    (cond
      ((= (PdfLayout_GetTileStr "g_srcxlsx") "1") "xlsx")
            (t "auto")
    )
  )
  (setq *PdfLayout_GridPrefix* (PdfLayout_GetTileStr "g_prefix"))
  (if (= *PdfLayout_GridPrefix* "") (setq *PdfLayout_GridPrefix* "CIR"))
  (setq *PdfLayout_GridStartN* (max 1 (PdfLayout_GetTileInt "g_startn" 1)))
  (setq *PdfLayout_GridDigits* (max 0 (PdfLayout_GetTileInt "g_digits" 2)))
  (setq *PdfLayout_PreviewOrder* (cond
    ((= (PdfLayout_GetTileStr "ord1") "1") "1")
    ((= (PdfLayout_GetTileStr "ord2") "1") "2")
    ((= (PdfLayout_GetTileStr "ord3") "1") "3")
    ((= (PdfLayout_GetTileStr "ord4") "1") "4")
    ((= (PdfLayout_GetTileStr "ord5") "1") "5")
    ((= (PdfLayout_GetTileStr "ord6") "1") "6")
    ((= (PdfLayout_GetTileStr "ord7") "1") "7")
    ((= (PdfLayout_GetTileStr "ord8") "1") "8")
    (t *PdfLayout_PreviewOrder*)
  ))
  (setq pairs (if (= *PdfLayout_GridGeom* "S") *PdfLayout_GridSelPairs* (PdfLayout_GridPairsFromGlobals)))
  (setq *PdfLayout_GridPairs* pairs)
  (setq order *PdfLayout_PreviewOrder*)
  (if (= *PdfLayout_GridGeom* "S")
    (if pairs
      (setq grid (vl-catch-all-apply 'PdfLayout_BuildSchemeGrid (list pairs order)))
      (setq grid (list "（未选择文字）"))
    )
    (setq grid (vl-catch-all-apply 'PdfLayout_BuildSchemeGrid (list pairs order)))
  )
  (if (vl-catch-all-error-p grid)
    (setq grid (list "（无法生成示意图）"))
  )
  (PdfLayout_SetList "g_grid" grid)
  (setq names (if (equal *PdfLayout_GridSrc* "xlsx") *PdfLayout_GridNames* nil))
  (setq srcDesc (cond
    ((= *PdfLayout_GridSrc* "xlsx") (strcat "Excel分表" (if *PdfLayout_GridSheetSel* (strcat " [" *PdfLayout_GridSheetSel* "]") "")))
        (t "自动命名")
  ))
  (setq sorted (PdfLayout_SortPairsSmart pairs order))
  (setq i 0 lines nil)
  (foreach p sorted
    (setq name (if (and names (< i (length names)))
                  (nth i names)
                  (PdfLayout_NameAtPrefix *PdfLayout_GridPrefix*
                                          (+ *PdfLayout_GridStartN* i)
                                          *PdfLayout_GridDigits*)))
    (setq lines (append lines (list (strcat "第" (itoa (1+ i)) "个: " name))))
    (setq i (1+ i))
  )
  (PdfLayout_SetList "g_names" lines)
  (set_tile "g_info"
    (strcat "共 " (itoa (length pairs)) " 个多行文字"
            (if (and names (/= (length names) (length pairs)))
              (strcat "（名单 " (itoa (length names)) " 个，按文字/名单较少者执行）")
              "")
            "；几何: " (if (= *PdfLayout_GridGeom* "S") "选择已有文字" (if (= *PdfLayout_GridGeom* "1") "按范围自动" "固定参数"))
            "；字高: " (if (= *PdfLayout_GridHMode* "manual") "直接输入" "按比例")
            "；排序: " (PdfLayout_OrderDesc order) "；来源: " srcDesc))
)
(defun PdfLayout_GridStripName (s / up L)
  ;; 分表名只取到最后 ".dc" 之前（大小写不敏感），保留前面的 .数字
  (setq s (vl-string-trim " " s))
  (setq up (strcase s))
  (setq L (strlen up))
  (if (and (>= L 4) (= (substr up (- L 2) 3) ".DC"))
    (substr s 1 (- L 3))
    s
  )
)
(defun PdfLayout_GridPairNames (codes / out n a b)
  ;; 把 Item Code 列表两两一组，生成 "A/B" 名字
  (setq out nil)
  (setq n 0)
  (while (< n (length codes))
    (setq a (nth n codes))
    (setq b (nth (1+ n) codes))
    (if a
      (setq out (append out (list (if (and b (/= b "")) (strcat a "/" b) a)))))
    (setq n (+ n 2))
  )
  out
)

(defun PdfLayout_GridPickXlsx (/ fpath)
  (setq fpath (getfiled "选择Excel(分表名=布局名)" "" "xlsx;xls" 4))
  (if fpath
    (progn
      (set_tile "g_filexlsx" fpath)
      (setq *PdfLayout_GridXlsx* fpath)
      (PdfLayout_GridReadXlsx)
    )
  )
)

(defun PdfLayout_GridNamesFor (disp / i full)
  ;; 根据去后缀后的分表名(布局名)找到对应名单
  (setq i 0)
  (while (and (nth i *PdfLayout_GridSheetNames*)
              (not (string= (strcase (nth i *PdfLayout_GridSheetNames*)) (strcase disp))))
    (setq i (1+ i))
  )
  (setq full (nth i *PdfLayout_GridSheetFull*))
  (if (and full (assoc full *PdfLayout_GridSheets*))
    (cdr (assoc full *PdfLayout_GridSheets*))
    nil
  )
)

(defun PdfLayout_GridPickSheet (/ tab disp found)
  ;; 按当前布局名自动匹配同名分表；找不到用第一个分表
  (setq tab (getvar "CTAB"))
  (setq found nil)
  (foreach disp *PdfLayout_GridSheetNames*
    (if (string= (strcase disp) (strcase tab)) (setq found disp))
  )
  (if (not found) (setq found (car *PdfLayout_GridSheetNames*)))
  (setq *PdfLayout_GridSheetSel* found)
  (setq *PdfLayout_GridNames* (PdfLayout_GridNamesFor found))
)

(defun PdfLayout_GridSheetList (/ items idx i sheet)
  (setq items *PdfLayout_GridSheetNames*)
  (if (null items) (setq items (list "(无分表)")))
  (setq idx 0 i 0)
  (foreach sheet *PdfLayout_GridSheetNames*
    (if (string= (strcase sheet) (strcase *PdfLayout_GridSheetSel*))
      (setq idx i))
    (setq i (1+ i))
  )
  (PdfLayout_SetList "g_xlsxsheet" items)
  (set_tile "g_xlsxsheet" (itoa idx))
)

(defun PdfLayout_GridSheetChanged (/ idx disp)
  (setq idx (PdfLayout_GetTileInt "g_xlsxsheet" 0))
  (setq disp (nth idx *PdfLayout_GridSheetNames*))
  (if disp (setq *PdfLayout_GridSheetSel* disp))
  (setq *PdfLayout_GridNames* (PdfLayout_GridNamesFor disp))
  (PdfLayout_GridUpdate)
)

(defun PdfLayout_GridIsCode (s / i c ok)
  ;; 只认 2 个以上纯字母的 Item Code，过滤表头/标题等杂项
  (setq s (vl-string-trim " " s))
  (setq ok T i 1)
  (if (< (strlen s) 2) (setq ok nil))
  (while (and ok (<= i (strlen s)))
    (setq c (substr s i 1))
    (if (not (or (and (>= c "A") (<= c "Z")) (and (>= c "a") (<= c "z"))))
      (setq ok nil))
    (setq i (1+ i))
  )
  ok
)

(defun PdfLayout_GridReadXlsx (/ path xl hadExcel wbs wb shs i shCount sh sheet ur vals arr rows codes name j disp)
  (setq path (PdfLayout_GetTileStr "g_filexlsx"))
  (if (= path "") (setq path *PdfLayout_GridXlsx*))
  (if (= path "")
    (progn (alert "请先选择 Excel 文件。") nil)
    (progn
      (setq *PdfLayout_GridXlsx* path)
      (setq *PdfLayout_GridSrc* "xlsx")
      (set_tile "g_srcxlsx" "1")
      (setq *PdfLayout_GridSheets* nil)
      (setq *PdfLayout_GridSheetNames* nil)
      (setq *PdfLayout_GridSheetFull* nil)
      (setq hadExcel (vl-catch-all-apply 'vlax-get-object (list "Excel.Application")))
      (setq hadExcel (and hadExcel (not (vl-catch-all-error-p hadExcel))))
      (setq xl (vl-catch-all-apply 'vlax-create-object (list "Excel.Application")))
      (if (and xl (not (vl-catch-all-error-p xl)))
        (progn
          (vl-catch-all-apply 'vlax-put-property (list xl 'Visible 0))
          (vl-catch-all-apply 'vlax-put-property (list xl 'DisplayAlerts 0))
          (vl-catch-all-apply 'vlax-put-property (list xl 'AskToUpdateLinks 0))
          (vl-catch-all-apply 'vlax-put-property (list xl 'AutomationSecurity 3))
          (setq wbs (vl-catch-all-apply 'vlax-get-property (list xl 'Workbooks)))
          (setq wb (vl-catch-all-apply 'vlax-invoke-method (list wbs 'Open path 0 1)))
          (if (and wb (not (vl-catch-all-error-p wb)))
            (progn
              (setq shs (vl-catch-all-apply 'vlax-get-property (list wb 'Sheets)))
              (if (and shs (not (vl-catch-all-error-p shs)))
                (progn
                  (setq shCount (vl-catch-all-apply 'vlax-get-property (list shs 'Count)))
                  (setq i 1)
                  (while (<= i shCount)
                    (setq sh (vl-catch-all-apply 'vlax-get-property (list shs 'Item i)))
                    (if (not (vl-catch-all-error-p sh))
                      (progn
                        (setq sheet (vl-catch-all-apply 'vlax-get-property (list sh 'Name)))
                        (if (vl-catch-all-error-p sheet) (setq sheet (strcat "分表" (itoa i))))
                        (setq sheet (vl-string-trim " " sheet))
                        (setq ur (vl-catch-all-apply 'vlax-get-property (list sh 'UsedRange)))
                        (setq vals (if (and ur (not (vl-catch-all-error-p ur)))
                                     (vl-catch-all-apply 'vlax-get-property (list ur 'Value)) nil))
                        (setq codes nil)
                        (if (and vals (not (vl-catch-all-error-p vals)))
                          (progn
                            (setq arr (vl-catch-all-apply 'vlax-variant-value (list vals)))
                            (if (not (vl-catch-all-error-p arr))
                              (progn
                                (setq rows (vl-catch-all-apply 'vlax-safearray->list (list arr)))
                                (if (not (vl-catch-all-error-p rows))
                                  (progn
                                    (setq rows (mapcar '(lambda (r) (mapcar 'PdfLayout_CellStr r)) rows))
                                    (foreach r rows
                                      (setq name (nth 2 r))
                                      (if (and name (PdfLayout_GridIsCode name))
                                        (setq codes (append codes (list (vl-string-trim " " name))))
                                      )
                                    )
                                  )
                                )
                              )
                            )
                          )
                        )
                        (setq disp (PdfLayout_GridStripName sheet))
                        (setq *PdfLayout_GridSheets*
                              (append *PdfLayout_GridSheets* (list (cons sheet (PdfLayout_GridPairNames codes)))))
                        (setq *PdfLayout_GridSheetFull*
                              (append *PdfLayout_GridSheetFull* (list sheet)))
                        (setq *PdfLayout_GridSheetNames*
                              (append *PdfLayout_GridSheetNames* (list disp)))
                        (princ (strcat "\n  分表 [" sheet "] -> [" disp "] : " (itoa (length codes)) " 项"))
                      )
                    )
                    (setq i (1+ i))
                  )
                )
              )
              (vl-catch-all-apply 'vlax-invoke-method (list wb 'Close 0))
            )
          )
          (PdfLayout_ExcelCleanup xl hadExcel (list shs sh ur wb wbs))
        )
      )
      (if *PdfLayout_GridSheetNames*
        (progn
          (PdfLayout_GridPickSheet)
          (PdfLayout_GridSheetList)
          (PdfLayout_GridUpdate)
          (princ (strcat "\nPDFGRID: 已读取 " (itoa (length *PdfLayout_GridSheetNames*)) " 个分表。"))
        )
        (alert "无法读取 Excel，或文件中没有可识别的分表。")
      )
    )
  )
)
(defun PdfLayout_GridFillProfiles (/ items i)
  (setq items (list "默认(当前参数)"))
  (foreach pf *PdfLayout_GridProfiles*
    (if (eq (type (car pf)) 'STR)
      (setq items (append items (list (car pf))))
    )
  )
  (PdfLayout_SetList "g_prof" items)
  (setq i 0)
  (foreach pf *PdfLayout_GridProfiles*
    (setq i (1+ i))
    (if (= (strcase (car pf)) (strcase *PdfLayout_GridProfile*))
      (set_tile "g_prof" (itoa i))
    )
  )
  (set_tile "g_profname" (if (eq (type *PdfLayout_GridProfile*) 'STR) *PdfLayout_GridProfile* ""))
)

(defun PdfLayout_GridApplyProfile (idx / pf)
  (if (> idx 0)
    (progn
      (setq pf (nth (1- idx) *PdfLayout_GridProfiles*))
      (if pf
        (progn
          (setq *PdfLayout_GridRows* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Rows") 4))
          (setq *PdfLayout_GridCols* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Cols") 5))
          (setq *PdfLayout_GridRowSp* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "RowSp") 10.0))
          (setq *PdfLayout_GridColSp* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "ColSp") 20.0))
          (setq *PdfLayout_GridH* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "H") 0.5))
          (setq *PdfLayout_GridHRatio* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "HRatio") 0.3))
          (setq *PdfLayout_GridGeom* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Geom") "1"))
          (setq *PdfLayout_GridHMode* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "HMode") "auto"))
          (setq *PdfLayout_GridMT* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "MT") 0.0))
          (setq *PdfLayout_GridMB* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "MB") 0.0))
          (setq *PdfLayout_GridML* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "ML") 0.0))
          (setq *PdfLayout_GridMR* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "MR") 0.0))
          (setq *PdfLayout_GridColDir* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "ColDir") 1))
          (setq *PdfLayout_GridRowDir* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "RowDir") -1))
          (setq *PdfLayout_GridRot* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Rot") 0))
(setq *PdfLayout_GridBg* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Bg") "fill"))
          (setq *PdfLayout_GridBgColor* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "BgColor") 1))
          (setq *PdfLayout_GridTxtColor* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "TxtColor") 7))
          (setq *PdfLayout_GridTxtTrue* (= (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "TxtTrue") "0") "1"))
          (setq *PdfLayout_GridTxtRGB* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "TxtRGB") 0))
          (setq *PdfLayout_GridBgScale* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "BgScale") 1.0))
          (if (> *PdfLayout_GridBgScale* 50)
            (setq *PdfLayout_GridBgScale* (/ *PdfLayout_GridBgScale* 100.0)))
          (setq *PdfLayout_GridPrefix* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Prefix") "CIR"))
          (setq *PdfLayout_GridStartN* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "StartN") 1))
          (setq *PdfLayout_GridDigits* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Digits") 2))
          (setq *PdfLayout_PreviewOrder* (PdfLayout_OrDefault (PdfLayout_ProfileGet (cdr pf) "Order") "1"))
          (setq *PdfLayout_GridProfile* (car pf))
          (PdfLayout_GridInit)
        )
      )
    )
  )
)

(defun PdfLayout_GridSaveProfile (/ name prof)
  (setq name (PdfLayout_GetTileStr "g_profname"))
  (if (= name "")
    (alert "请先输入方案名。")
    (progn
      (PdfLayout_GridUpdate)
      (setq prof nil)
      (setq prof (PdfLayout_ProfileSet prof "Rows" *PdfLayout_GridRows*))
      (setq prof (PdfLayout_ProfileSet prof "Cols" *PdfLayout_GridCols*))
      (setq prof (PdfLayout_ProfileSet prof "RowSp" *PdfLayout_GridRowSp*))
      (setq prof (PdfLayout_ProfileSet prof "ColSp" *PdfLayout_GridColSp*))
      (setq prof (PdfLayout_ProfileSet prof "H" *PdfLayout_GridH*))
      (setq prof (PdfLayout_ProfileSet prof "HRatio" *PdfLayout_GridHRatio*))
      (setq prof (PdfLayout_ProfileSet prof "Geom" *PdfLayout_GridGeom*))
      (setq prof (PdfLayout_ProfileSet prof "HMode" *PdfLayout_GridHMode*))
      (setq prof (PdfLayout_ProfileSet prof "MT" *PdfLayout_GridMT*))
      (setq prof (PdfLayout_ProfileSet prof "MB" *PdfLayout_GridMB*))
      (setq prof (PdfLayout_ProfileSet prof "ML" *PdfLayout_GridML*))
      (setq prof (PdfLayout_ProfileSet prof "MR" *PdfLayout_GridMR*))
      (setq prof (PdfLayout_ProfileSet prof "ColDir" *PdfLayout_GridColDir*))
      (setq prof (PdfLayout_ProfileSet prof "RowDir" *PdfLayout_GridRowDir*))
      (setq prof (PdfLayout_ProfileSet prof "Rot" *PdfLayout_GridRot*))
(setq prof (PdfLayout_ProfileSet prof "Bg" *PdfLayout_GridBg*))
      (setq prof (PdfLayout_ProfileSet prof "BgColor" *PdfLayout_GridBgColor*))
      (setq prof (PdfLayout_ProfileSet prof "TxtColor" *PdfLayout_GridTxtColor*))
      (setq prof (PdfLayout_ProfileSet prof "TxtTrue" (if *PdfLayout_GridTxtTrue* "1" "0")))
      (setq prof (PdfLayout_ProfileSet prof "TxtRGB" *PdfLayout_GridTxtRGB*))
      (setq prof (PdfLayout_ProfileSet prof "BgScale" *PdfLayout_GridBgScale*))
      (setq prof (PdfLayout_ProfileSet prof "Prefix" *PdfLayout_GridPrefix*))
      (setq prof (PdfLayout_ProfileSet prof "StartN" *PdfLayout_GridStartN*))
      (setq prof (PdfLayout_ProfileSet prof "Digits" *PdfLayout_GridDigits*))
      (setq prof (PdfLayout_ProfileSet prof "Order" *PdfLayout_PreviewOrder*))
      (setq *PdfLayout_GridProfiles*
        (vl-remove-if
          '(lambda (x) (= (strcase (car x)) (strcase name)))
          *PdfLayout_GridProfiles*))
      (setq *PdfLayout_GridProfiles* (append *PdfLayout_GridProfiles* (list (cons name prof))))
      (setq *PdfLayout_GridProfile* name)
      (PdfLayout_SaveSettings)
      (PdfLayout_GridFillProfiles)
      (princ (strcat "\n网格方案已保存: " name))
    )
  )
)

(defun PdfLayout_GridDeleteProfile (/ idx sel name)
  (setq idx (PdfLayout_GetTileInt "g_prof" -1))
  (if (> idx 0)
    (progn
      (setq sel (nth (1- idx) *PdfLayout_GridProfiles*))
      (if sel
        (progn
          (setq name (car sel))
          (setq *PdfLayout_GridProfiles*
            (vl-remove-if
              '(lambda (x) (= (strcase (car x)) (strcase name)))
              *PdfLayout_GridProfiles*))
          (if (= (strcase *PdfLayout_GridProfile*) (strcase name))
            (setq *PdfLayout_GridProfile* "")
          )
          (PdfLayout_SaveSettings)
          (PdfLayout_GridFillProfiles)
          (set_tile "g_prof" "0")
          (set_tile "g_profname" "")
          (princ (strcat "\n网格方案已删除: " name))
        )
        (alert "请先选择要删除的方案。")
      )
    )
    (alert "请先选择要删除的方案。")
  )
)

(defun PdfLayout_GridLoadProfiles (/ i cnt name prof)
  (setq *PdfLayout_GridProfiles* nil)
  (setq i 1)
  (setq cnt (atoi (PdfLayout_OrDefault (PdfLayout_IniGet "GridProfileCount") "0")))
  (while (<= i cnt)
    (setq name (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Name")))
    (if name
      (progn
        (setq prof nil)
        (setq prof (PdfLayout_ProfileSet prof "Rows" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Rows")) "4"))))
        (setq prof (PdfLayout_ProfileSet prof "Cols" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Cols")) "5"))))
        (setq prof (PdfLayout_ProfileSet prof "RowSp" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "RowSp")) "10"))))
        (setq prof (PdfLayout_ProfileSet prof "ColSp" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "ColSp")) "20"))))
        (setq prof (PdfLayout_ProfileSet prof "H" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "H")) "0.5"))))
        (setq prof (PdfLayout_ProfileSet prof "HRatio" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "HRatio")) "0.3"))))
        (setq prof (PdfLayout_ProfileSet prof "Geom" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Geom")) "1")))
        (setq prof (PdfLayout_ProfileSet prof "HMode" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "HMode")) "auto")))
        (setq prof (PdfLayout_ProfileSet prof "MT" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "MT")) "0"))))
        (setq prof (PdfLayout_ProfileSet prof "MB" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "MB")) "0"))))
        (setq prof (PdfLayout_ProfileSet prof "ML" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "ML")) "0"))))
        (setq prof (PdfLayout_ProfileSet prof "MR" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "MR")) "0"))))
        (setq prof (PdfLayout_ProfileSet prof "ColDir" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "ColDir")) "1"))))
        (setq prof (PdfLayout_ProfileSet prof "RowDir" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "RowDir")) "-1"))))
        (setq prof (PdfLayout_ProfileSet prof "Rot" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Rot")) "0"))))
(setq prof (PdfLayout_ProfileSet prof "Bg" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Bg")) "fill")))
        (setq prof (PdfLayout_ProfileSet prof "BgColor" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "BgColor")) "1"))))
        (setq prof (PdfLayout_ProfileSet prof "TxtColor" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "TxtColor")) "7"))))
        (setq prof (PdfLayout_ProfileSet prof "TxtTrue" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "TxtTrue")) "0")))
        (setq prof (PdfLayout_ProfileSet prof "TxtRGB" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "TxtRGB")) "0"))))
        (setq prof (PdfLayout_ProfileSet prof "BgScale" (atof (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "BgScale")) "1"))))
        (setq prof (PdfLayout_ProfileSet prof "Prefix" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Prefix")) "CIR")))
        (setq prof (PdfLayout_ProfileSet prof "StartN" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "StartN")) "1"))))
        (setq prof (PdfLayout_ProfileSet prof "Digits" (atoi (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Digits")) "2"))))
        (setq prof (PdfLayout_ProfileSet prof "Order" (PdfLayout_OrDefault (PdfLayout_IniGet (strcat "GridProfile" (itoa i) "Order")) "1")))
        (setq *PdfLayout_GridProfiles* (append *PdfLayout_GridProfiles* (list (cons name prof))))
      )
    )
    (setq i (1+ i))
  )
)

(defun PdfLayout_GridInit (/ bgIdx txtIdx)
  (set_tile "g_rows" (itoa *PdfLayout_GridRows*))
  (set_tile "g_cols" (itoa *PdfLayout_GridCols*))
  (set_tile "g_rowsp" (rtos *PdfLayout_GridRowSp* 2 2))
  (set_tile "g_colsp" (rtos *PdfLayout_GridColSp* 2 2))
  (set_tile "g_h" (rtos *PdfLayout_GridH* 2 2))
  (PdfLayout_SetList "g_mmode" '("自动" "自定义"))
  (set_tile "g_mmode" (if (equal *PdfLayout_GridMMode* "custom") "1" "0"))
  (set_tile "g_mt" (rtos *PdfLayout_GridMT* 2 2))
  (set_tile "g_mb" (rtos *PdfLayout_GridMB* 2 2))
  (set_tile "g_ml" (rtos *PdfLayout_GridML* 2 2))
  (set_tile "g_mr" (rtos *PdfLayout_GridMR* 2 2))
  (set_tile "g_hratio" (rtos *PdfLayout_GridHRatio* 2 2))
  (if (/= *PdfLayout_GridGeom* "S")
    (set_tile (if (= *PdfLayout_GridGeom* "1") "g_geoa" "g_geof") "1")
  )
  (set_tile (if (= *PdfLayout_GridHMode* "manual") "g_hmanual" "g_hauto") "1")
  (PdfLayout_SetList "g_rot" '("0°" "90°" "180°" "270°"))
  (set_tile "g_rot" (itoa (cond
    ((= *PdfLayout_GridRot* 90) 1)
    ((= *PdfLayout_GridRot* 180) 2)
    ((= *PdfLayout_GridRot* 270) 3)
    (t 0)
  )))
(set_tile (if (= *PdfLayout_GridBg* "fill") "g_bgon" "g_bgnone") "1")
  (PdfLayout_SetList "g_bgcolor" '("红色" "黄色" "绿色" "青色" "蓝色" "品红" "白色" "灰色" "黑色" "橙色" "深灰" "自定义"))
  (PdfLayout_SetList "g_txtcolor" '("红色" "黄色" "绿色" "青色" "蓝色" "品红" "白色" "灰色" "黑色" "橙色" "深灰" "自定义"))
  (setq bgIdx (PdfLayout_GridColorIndex *PdfLayout_GridBgColor*))
  (setq txtIdx (if *PdfLayout_GridTxtTrue*
                  (PdfLayout_GridIndexByRGB *PdfLayout_GridTxtRGB*)
                  (PdfLayout_GridColorIndex *PdfLayout_GridTxtColor*)))
  (set_tile "g_bgcolor" (itoa bgIdx))
  (set_tile "g_txtcolor" (itoa txtIdx))
  (set_tile "g_bgaci" (itoa *PdfLayout_GridBgColor*))
  (set_tile "g_txtaci" (itoa *PdfLayout_GridTxtColor*))
  (set_tile "g_bgscale" (rtos *PdfLayout_GridBgScale* 2 2))
  (cond
    ((= *PdfLayout_GridSrc* "xlsx") (set_tile "g_srcxlsx" "1"))
        (t (set_tile "g_srcauto" "1"))
  )
  (set_tile "g_prefix" *PdfLayout_GridPrefix*)
  (set_tile "g_startn" (itoa *PdfLayout_GridStartN*))
  (set_tile "g_digits" (itoa *PdfLayout_GridDigits*))
  (set_tile "g_filexlsx" *PdfLayout_GridXlsx*)
  (PdfLayout_GridSheetList)
  (if (and (= *PdfLayout_GridSrc* "xlsx") (/= *PdfLayout_GridXlsx* "") (not *PdfLayout_GridSheets*))
    (PdfLayout_GridReadXlsx)
  )
  (set_tile "g_start" (if *PdfLayout_GridStart*
    (strcat "起点: " (rtos (car *PdfLayout_GridStart*) 2 2) ", " (rtos (cadr *PdfLayout_GridStart*) 2 2))
    "起点: 0, 0"))
  (if (member *PdfLayout_PreviewOrder* '("1" "2" "3" "4" "5" "6" "7" "8"))
    (set_tile (strcat "ord" *PdfLayout_PreviewOrder*) "1")
  )
  (PdfLayout_GridFillProfiles)
  (PdfLayout_GridUpdate)
)

(defun PdfLayout_GridAccept ()
  (PdfLayout_GridUpdate)
  (PdfLayout_SaveSettings)
  (setq *PdfLayout_GridResult* 1)
  (done_dialog 1)
)

(defun PdfLayout_GridShowDialog (/ dclPath dclId result nd)
  (setq dclPath (PdfLayout_FindDcl))
  (if (not dclPath)
    (progn
      "0"
    )
    (progn
      (setq dclId (load_dialog dclPath))
      (if (< dclId 0)
        (progn
          "0"
        )
        (progn
          (setq nd (vl-catch-all-apply 'new_dialog (list "PdfGrid" dclId)))
          (if (and nd (not (vl-catch-all-error-p nd)))
            (progn
              (PdfLayout_GridInit)
              (action_tile "g_prof" "(PdfLayout_GridApplyProfile (PdfLayout_GetTileInt \"g_prof\" -1))")
              (action_tile "g_saveprof" "(PdfLayout_GridSaveProfile)")
              (action_tile "g_delprof" "(PdfLayout_GridDeleteProfile)")
              (action_tile "g_rows" "(PdfLayout_GridUpdate)")
              (action_tile "g_cols" "(PdfLayout_GridUpdate)")
              (action_tile "g_rowsp" "(PdfLayout_GridUpdate)")
              (action_tile "g_colsp" "(PdfLayout_GridUpdate)")
              (action_tile "g_geoa" "(PdfLayout_GridUpdate)")
              (action_tile "g_geof" "(PdfLayout_GridUpdate)")
              (action_tile "g_hratio" "(PdfLayout_GridUpdate)")
              (action_tile "g_hauto" "(PdfLayout_GridUpdate)")
              (action_tile "g_hmanual" "(PdfLayout_GridUpdate)")
              (action_tile "g_h" "(PdfLayout_GridUpdate)")
              (action_tile "g_mmode" "(PdfLayout_GridUpdate)")
              (action_tile "g_mt" "(PdfLayout_GridUpdate)")
              (action_tile "g_mb" "(PdfLayout_GridUpdate)")
              (action_tile "g_ml" "(PdfLayout_GridUpdate)")
              (action_tile "g_mr" "(PdfLayout_GridUpdate)")
              (action_tile "g_rot" "(PdfLayout_GridUpdate)")
(action_tile "g_bgnone" "(PdfLayout_GridUpdate)")
              (action_tile "g_bgon" "(PdfLayout_GridUpdate)")
              (action_tile "g_bgcolor" "(PdfLayout_GridUpdate)")
              (action_tile "g_bgaci" "(PdfLayout_GridUpdate)")
              (action_tile "g_txtcolor" "(PdfLayout_GridUpdate)")
              (action_tile "g_txtaci" "(PdfLayout_GridUpdate)")
              (action_tile "g_bgscale" "(PdfLayout_GridUpdate)")
              (action_tile "g_srcauto" "(setq *PdfLayout_GridSrc* \"auto\") (PdfLayout_GridUpdate)")
              (action_tile "g_srcxlsx" "(setq *PdfLayout_GridSrc* \"xlsx\") (PdfLayout_GridUpdate)")
              (action_tile "g_prefix" "(PdfLayout_GridUpdate)")
              (action_tile "g_startn" "(PdfLayout_GridUpdate)")
              (action_tile "g_digits" "(PdfLayout_GridUpdate)")
              (action_tile "g_filexlsx" "(PdfLayout_GridReadXlsx)")
              (action_tile "g_btnxlsx" "(PdfLayout_GridPickXlsx)")
              (action_tile "g_xlsxsheet" "(PdfLayout_GridSheetChanged)")
              (action_tile "g_btnxlsxre" "(PdfLayout_GridReadXlsx)")
              (action_tile "ord1" "(setq *PdfLayout_PreviewOrder* \"1\") (PdfLayout_GridUpdate)")
              (action_tile "ord2" "(setq *PdfLayout_PreviewOrder* \"2\") (PdfLayout_GridUpdate)")
              (action_tile "ord3" "(setq *PdfLayout_PreviewOrder* \"3\") (PdfLayout_GridUpdate)")
              (action_tile "ord4" "(setq *PdfLayout_PreviewOrder* \"4\") (PdfLayout_GridUpdate)")
              (action_tile "ord5" "(setq *PdfLayout_PreviewOrder* \"5\") (PdfLayout_GridUpdate)")
              (action_tile "ord6" "(setq *PdfLayout_PreviewOrder* \"6\") (PdfLayout_GridUpdate)")
              (action_tile "ord7" "(setq *PdfLayout_PreviewOrder* \"7\") (PdfLayout_GridUpdate)")
              (action_tile "ord8" "(setq *PdfLayout_PreviewOrder* \"8\") (PdfLayout_GridUpdate)")
              (action_tile "accept" "(PdfLayout_GridAccept)")
              (action_tile "cancel" "(setq *PdfLayout_GridResult* 0) (done_dialog 0)")
              (setq *PdfLayout_GridResult* 0)
              (setq result (start_dialog))
              (unload_dialog dclId)
              (if (= *PdfLayout_GridResult* 1) "1" "0")
            )
            (progn
              (unload_dialog dclId)
              "0"
            )
          )
        )
      )
    )
  )
)

(defun PdfLayout_GridApplyStyle (e / ed obj fac)
  ;; 背景填充：DXF 45/63/90 + ActiveX 兜底；文字颜色用 420 真彩色。
  ;; 说明：ZWCAD 的组码90按“边界偏移因子”直接解释(1.0~5.0)，不是百分比；
  ;; MTEXT 的 420=实体真彩色、421=背景填充真彩色，两者不能混用。
  (if (= (type e) 'VLA-OBJECT)
    (setq e (vlax-vla-object->ename e))
  )
  (setq ed (entget e))
  ;; 文字颜色：预设色写 62 ACI + 420 真彩色(420优先，白=白、黑=黑)；
  ;; 自定义 ACI 只写 62 并移除 420，避免残留真彩色。
  (if *PdfLayout_GridTxtTrue*
    (progn
      (if (assoc 62 ed)
        (setq ed (subst (cons 62 *PdfLayout_GridTxtColor*) (assoc 62 ed) ed))
        (setq ed (append ed (list (cons 62 *PdfLayout_GridTxtColor*))))
      )
      (if (assoc 420 ed)
        (setq ed (subst (cons 420 *PdfLayout_GridTxtRGB*) (assoc 420 ed) ed))
        (setq ed (append ed (list (cons 420 *PdfLayout_GridTxtRGB*))))
      )
    )
    (progn
      (if (assoc 62 ed)
        (setq ed (subst (cons 62 *PdfLayout_GridTxtColor*) (assoc 62 ed) ed))
        (setq ed (append ed (list (cons 62 *PdfLayout_GridTxtColor*))))
      )
      (if (assoc 420 ed)
        (setq ed (vl-remove (assoc 420 ed) ed))
      )
    )
  )
  (setq fac (max 1.0 (min 5.0 *PdfLayout_GridBgScale*)))
  ;; 背景填充：45=1 + 63 ACI + 90 偏移因子；背景真彩色是 421，不能动 420。
  (if (= *PdfLayout_GridBg* "fill")
    (progn
      (if (assoc 45 ed)
        (setq ed (subst (cons 45 1) (assoc 45 ed) ed))
        (setq ed (append ed (list (cons 45 1))))
      )
      (if (assoc 63 ed)
        (setq ed (subst (cons 63 *PdfLayout_GridBgColor*) (assoc 63 ed) ed))
        (setq ed (append ed (list (cons 63 *PdfLayout_GridBgColor*))))
      )
      (if (assoc 421 ed)
        (setq ed (vl-remove (assoc 421 ed) ed))
      )
      (if (assoc 90 ed)
        (setq ed (subst (cons 90 fac) (assoc 90 ed) ed))
        (setq ed (append ed (list (cons 90 fac))))
      )
    )
    (progn
      (if (assoc 45 ed)
        (setq ed (subst (cons 45 0) (assoc 45 ed) ed))
        (setq ed (append ed (list (cons 45 0))))
      )
    )
  )
  (entmod ed)
  (setq obj (vlax-ename->vla-object e))
  (if (= *PdfLayout_GridBg* "fill")
    (progn
      (vl-catch-all-apply 'vla-put-BackgroundFill (list obj :vlax-true))
      (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillUseDrawingBackgroundColor :vlax-false)) nil)
      (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillColor *PdfLayout_GridBgColor*)) nil)
      (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillGapFactor fac)) nil)
      ;; 原生属性面板路径（setpropertyvalue），能走通时优先于 DXF
      (vl-catch-all-apply '(lambda () (setpropertyvalue e "BackgroundFill" "1")) nil)
      (vl-catch-all-apply '(lambda () (setpropertyvalue e "BackgroundFillUseDrawingBackgroundColor" "0")) nil)
      (vl-catch-all-apply '(lambda () (setpropertyvalue e "BackgroundFillColor" (itoa *PdfLayout_GridBgColor*))) nil)
      (foreach pn '("BackgroundScaleFactor" "BackgroundFillGapFactor" "BackgroundFillScaleFactor")
        (vl-catch-all-apply '(lambda () (setpropertyvalue e pn fac)) nil)
      )
      ;; ActiveX/属性面板可能把组码90覆盖成默认值，最后再用 DXF 写一次偏移因子保证生效
      (entmod ed)
    )
    (vl-catch-all-apply 'vla-put-BackgroundFill (list obj :vlax-false))
  )
  (entupd e)
  (vl-catch-all-apply 'vla-update (list obj))
  e
)

(defun PdfLayout_GridColorList ()
  ;; 预设颜色ACI表：红黄绿青蓝品红白灰黑橙深灰
  '(1 2 3 4 5 6 7 8 7 30 250)
)

(defun PdfLayout_GridRgbList ()
  ;; 与ACI表对应的真彩色RGB(0xRRGGBB)：黑=0
  '(255 65535 65280 65535 255 16711935 16777215 8421504 0 16753920 4210752)
)

(defun PdfLayout_GridColorRGB (aci / i)
  ;; 根据ACI返回对应RGB(真彩色)值，自定义返回 0
  (setq i (PdfLayout_GridColorIndex aci))
  (if (< i 11)
    (nth i (PdfLayout_GridRgbList))
    0
  )
)

(defun PdfLayout_GridColorIndex (aci / i)
  ;; 颜色索引号，0-10 对应预设颜色，11=自定义
  (setq i 0)
  (while (and (< i 11) (/= aci (nth i (PdfLayout_GridColorList))))
    (setq i (1+ i))
  )
  i
)

(defun PdfLayout_GridIndexByRGB (rgb / i)
  ;; 按真彩色RGB查找颜色索引（黑白按RGB区分），找不到返回11=自定义
  (setq i 0)
  (while (and (< i 11) (/= rgb (nth i (PdfLayout_GridRgbList))))
    (setq i (1+ i))
  )
  i
)

(defun PdfLayout_GridProcessExisting (/ pairs sorted i done name txtH)
  ;; 处理已有文字：排序更名 + 改高度 + 背景/颜色（PDFRENAME 命令专用）
  (setq pairs *PdfLayout_GridSelPairs*)
  (if pairs
    (progn
      (setq sorted (PdfLayout_SortPairsSmart pairs *PdfLayout_PreviewOrder*))
      (setq txtH *PdfLayout_GridH*)
      (setq i 0 done 0)
      (if (= (logand (getvar "UNDOCTL") 1) 1)
        (command "._UNDO" "_BE")
      )
      (foreach pair sorted
        (setq name (if (and (equal *PdfLayout_GridSrc* "xlsx") *PdfLayout_GridNames*
                            (< i (length *PdfLayout_GridNames*)))
                      (nth i *PdfLayout_GridNames*)
                      (PdfLayout_NameAtPrefix *PdfLayout_GridPrefix*
                                              (+ *PdfLayout_GridStartN* i)
                                              *PdfLayout_GridDigits*)))
        (if (and name (car pair))
          (progn
            (vl-catch-all-apply 'vla-put-TextString
              (list (vlax-ename->vla-object (car pair)) name))
            (vl-catch-all-apply 'vla-put-Height
              (list (vlax-ename->vla-object (car pair)) txtH))
            (PdfLayout_GridApplyStyle (car pair))
            (setq done (1+ done))
          )
        )
        (setq i (1+ i))
      )
      (if (= (logand (getvar "UNDOCTL") 1) 1)
        (command "._UNDO" "_E")
      )
      (princ (strcat "\nPDFRENAME: 已处理 " (itoa done) " 个。"))
      (alert (strcat "PDFRENAME 完成\n\n已按排序方向 " *PdfLayout_PreviewOrder*
                     " 处理 " (itoa done) " 个"
                     (if (< done (length sorted))
                       "\n（文字多于名称，多余的未改名）" "")))
    )
    (princ "\n未选择文字。")
  )
)

(defun c:pdfgrid (/ gm p1 p2 p3 res doc blk pairs sorted i done name txtH rad m ins lay pt bb pmin pmax tw sel en)
  (vl-load-com)
  (PdfLayout_OrderPreviewClear)
  (PdfLayout_LoadSettings)
  (initget "A F M")
  (setq gm (getkword "\n几何方式 [A]框选范围自动算 / [F]固定参数设置 / [M]手动点取行列距  <A>: "))
  (if (not gm) (setq gm "A"))
    (if (= gm "A")
      (progn
        (setq p1 (getpoint "\n点取网格范围第一角: "))
      (if p1
        (progn
          (setq p2 (getpoint p1 "\n点取网格范围对角: "))
          (if p2
            (progn
              (setq *PdfLayout_GridGeom* "1")
              (setq *PdfLayout_GridP1* p1 *PdfLayout_GridP2* p2)
              (setq *PdfLayout_GridExtX* (abs (- (car p2) (car p1))))
              (setq *PdfLayout_GridExtY* (abs (- (cadr p2) (cadr p1))))
              (setq *PdfLayout_GridStart*
                    (list (min (car p1) (car p2)) (max (cadr p1) (cadr p2)) 0.0))
            )
          )
        )
      )
    )
    (if (= gm "M")
      (progn
        (setq *PdfLayout_GridGeom* "3")
        (setq p1 (getpoint "\n点取网格起点(第一个文字的中心): "))
        (if p1
          (progn
            (setq *PdfLayout_GridStart* p1)
            (setq p2 (getpoint p1 "\n点取列距第一点: "))
            (if p2
              (progn
                (setq p3 (getpoint p2 "\n点取列距第二点(两点距离=列距，方向随拖动方向): "))
                (if p3
                  (progn
                    (setq *PdfLayout_GridColSp* (distance p2 p3))
                    (setq *PdfLayout_GridColDir* (if (> (car p3) (car p2)) 1 -1))
                  )
                )
              )
            )
            (setq p2 (getpoint p1 "\n点取行距第一点: "))
            (if p2
              (progn
                (setq p3 (getpoint p2 "\n点取行距第二点(两点距离=行距，方向随拖动方向): "))
                (if p3
                  (progn
                    (setq *PdfLayout_GridRowSp* (distance p2 p3))
                    (setq *PdfLayout_GridRowDir* (if (> (cadr p3) (cadr p2)) 1 -1))
                  )
                )
              )
            )
          )
        )
      )
      (progn
        (setq *PdfLayout_GridGeom* "3")
        (setq p1 (getpoint "\n点取网格起点: "))
        (if p1 (setq *PdfLayout_GridStart* p1))
        (setq *PdfLayout_GridColDir* 1)
        (setq *PdfLayout_GridRowDir* -1)
      )
    )
  )
  (if (not *PdfLayout_GridStart*) (setq *PdfLayout_GridStart* '(0 0 0)))
  (setq res (PdfLayout_GridShowDialog))
  (if (= res "1")
      (progn
        (setq pairs (PdfLayout_GridPairsFromGlobals))
      (setq sorted (PdfLayout_SortPairsSmart pairs *PdfLayout_PreviewOrder*))
      (setq doc (vla-get-ActiveDocument (vlax-get-Acad-Object)))
      (if (= (getvar "TILEMODE") 1)
        (setq blk (vla-get-ModelSpace doc))
        (setq blk (vla-get-Block (vla-get-ActiveLayout doc)))
      )
      (setq txtH *PdfLayout_GridH*)
      (setq rad (* *PdfLayout_GridRot* (/ pi 180.0)))
      (setq i 0 done 0)
      (setq lay (PdfLayout_EnsureLayer "PDF网格文字"))
      (if (= (logand (getvar "UNDOCTL") 1) 1)
        (command "._UNDO" "_BE")
      )
      ;; 用 vla-AddMText 创建（背景填充 DXF 生效路径与 PDFLBD 一致），
      ;; 改"正中"附着点后中望不重排文字，读出插入点整体移到网格点，保证中心=网格点
      (foreach pair sorted
        (setq name (if (and (equal *PdfLayout_GridSrc* "xlsx") *PdfLayout_GridNames*
                            (< i (length *PdfLayout_GridNames*)))
                      (nth i *PdfLayout_GridNames*)
                      (PdfLayout_NameAtPrefix *PdfLayout_GridPrefix*
                                              (+ *PdfLayout_GridStartN* i)
                                              *PdfLayout_GridDigits*)))
        (setq pt (PdfLayout_BBoxCenter (cdr pair)))
        (setq m (vl-catch-all-apply 'vla-AddMText
                  (list blk (vlax-3d-point pt) 0.0 name)))
        (if (and m (not (vl-catch-all-error-p m)))
          (progn
            (vl-catch-all-apply 'vla-put-Height (list m txtH))
            (vl-catch-all-apply 'vla-put-AttachmentPoint (list m 5))
            ;; 先量真实文字宽度，再收紧文字框，背景遮罩才不会左右留太多
;; Width auto by font height: ideal = 4 * height, capped by grid column spacing
(setq tw (* txtH 4.0))
(if (and *PdfLayout_GridColSp* (> *PdfLayout_GridColSp* 0.0))
  (setq tw (min tw *PdfLayout_GridColSp*)))
(if (> tw 0.0)
  (vl-catch-all-apply 'vla-put-Width (list m tw)))
            (setq ins (vl-catch-all-apply
                        '(lambda () (vlax-safearray->list
                                      (vlax-variant-value (vla-get-InsertionPoint m))))
                        nil))
            (if (and ins (not (vl-catch-all-error-p ins)))
              (vl-catch-all-apply 'vla-Move (list m (vlax-3d-point ins) (vlax-3d-point pt)))
            )
            (if (/= rad 0.0)
              (vl-catch-all-apply 'vla-put-Rotation (list m rad))
            )
            (if (and lay (not (vl-catch-all-error-p lay)))
              (vl-catch-all-apply 'vla-put-Layer (list m "PDF网格文字"))
            )
            (PdfLayout_GridApplyStyle m)
            (vl-catch-all-apply
              '(lambda () (command "._DRAWORDER" (vlax-vla-object->ename m) "" "_Front"))
              nil)
            (setq done (1+ done))
          )
        )
        (setq i (1+ i))
      )
      (if (= (logand (getvar "UNDOCTL") 1) 1)
        (command "._UNDO" "_E")
      )
      (princ (strcat "\nPDFGRID: 已按排序生成 " (itoa done) " 个多行文字。"))
      (alert (strcat "PDFGRID 完成\n\n已按排序生成 " (itoa done) " 个多行文字。"
                     (if (< done (length pairs)) "\n（部分文字创建失败，请检查参数）" "")))
      )
    (princ "\n已取消。")
  )
  (princ)
)


(defun c:pdfmtdiag (/ ss i e obj dump f ed ok1 ok2 ok3 ok4 path)
  ;; 诊断多行文字背景遮罩：转储 ActiveX 属性/方法到临时文件，
  ;; 并尝试用 DXF + ActiveX 两种方式设置黄底，判断 ZWCAD 支持哪些接口。
  (vl-load-com)
  (setq path (strcat (getvar "TEMPPREFIX") "pdfmt_diag.txt"))
  (princ "\n[PDFMTDIAG] 请选择一个或多个多行文字(MTEXT): ")
  (setq ss (ssget '((0 . "MTEXT"))))
  (if (and ss (setq f (open path "w")))
    (progn
      (setq i 0)
      (while (< i (sslength ss))
        (setq e (ssname ss i))
        (setq obj (vlax-ename->vla-object e))
        (princ (strcat "\n===== MTEXT " (itoa (1+ i)) " =====") f)
        (setq dump (vl-catch-all-apply 'vlax-dump-object (list obj T)))
        (if (vl-catch-all-error-p dump)
          (princ "\n(vlax-dump-object) 失败" f)
          (princ (strcat "\n" (vl-prin1-to-string dump)) f)
        )
        (setq ed (entget e))
        (princ (strcat "\nDXF 45=" (vl-prin1-to-string (cdr (assoc 45 ed)))
                       " 63=" (vl-prin1-to-string (cdr (assoc 63 ed)))
                       " 90=" (vl-prin1-to-string (cdr (assoc 90 ed)))
                       " 420=" (vl-prin1-to-string (cdr (assoc 420 ed)))) f)
        (setq ed (entget e))
        (if (assoc 45 ed)
          (setq ed (subst (cons 45 1) (assoc 45 ed) ed))
          (setq ed (append ed (list (cons 45 1))))
        )
        (if (assoc 63 ed)
          (setq ed (subst (cons 63 2) (assoc 63 ed) ed))
          (setq ed (append ed (list (cons 63 2))))
        )
        (if (assoc 421 ed)
        (setq ed (vl-remove (assoc 421 ed) ed))
      )
        (if (assoc 90 ed)
          (setq ed (subst (cons 90 1.0) (assoc 90 ed) ed))
          (setq ed (append ed (list (cons 90 1.0))))
        )
        (entmod ed)
        (entupd e)
        (princ "\nDXF方式(45=1 63=2 420=0 90=1.0): 已写入" f)
        (setq ok1 (vl-catch-all-apply 'vla-put-BackgroundFill (list obj :vlax-true)))
        (setq ok2 (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillUseDrawingBackgroundColor :vlax-false)) nil))
        (setq ok3 (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillColor 2)) nil))
        (setq ok4 (vl-catch-all-apply '(lambda () (vlax-put-property obj 'BackgroundFillGapFactor 1.0)) nil))
        (princ (strcat "\nActiveX: BackgroundFill=" (if (vl-catch-all-error-p ok1) "FAIL" "OK")
                       " UseDrawingBg=false=" (if (vl-catch-all-error-p ok2) "FAIL" "OK")
                       " Color=2=" (if (vl-catch-all-error-p ok3) "FAIL" "OK")
                       " Gap=1.0=" (if (vl-catch-all-error-p ok4) "FAIL" "OK")) f)
        (vl-catch-all-apply 'vla-update (list obj))
        (setq i (1+ i))
      )
      (close f)
      (princ (strcat "\n[PDFMTDIAG] 完成，诊断文件: " path))
      (princ "\n[PDFMTDIAG] 请检查文字是否出现黄底，并把该文件内容发回。")
    )
    (progn
      (if f (close f))
      (princ "\n[PDFMTDIAG] 未选择对象或无法写诊断文件")
    )
  )
  (princ)
)

;;;-------------------------------------------------------------
;;; PDFTOOL：统一入口主菜单
;;;-------------------------------------------------------------
(defun PdfLayout_HubSetPythonPath (/ f)
  (setq f (getfiled "选择 ZWCAD 内置 Python (python.exe)" "" "exe" 4))
  (if f
    (progn
      (setq *PdfLayout_PythonPath* f)
      (PdfLayout_SaveSettings)
      (princ (strcat "\nPythonPath=" f))
    )
  )
  (princ)
)

(defun PdfLayout_HubSetLbdHeight (/ v)
  (setq v (getreal (strcat "\n默认标签字高(模型单位, 当前 "
                           (rtos *PdfLayout_LbdTextHeight* 2 3)
                           ") <" (rtos *PdfLayout_LbdTextHeight* 2 3) ">: ")))
  (if v (setq *PdfLayout_LbdTextHeight* v))
  (PdfLayout_SaveSettings)
  (princ (strcat "\n默认字高=" (rtos *PdfLayout_LbdTextHeight* 2 3)))
  (princ)
)

(defun PdfLayout_HubToggleDebug ()
  (setq *PdfLayout_Debug* (not *PdfLayout_Debug*))
  (princ (strcat "\n调试输出: " (if *PdfLayout_Debug* "开" "关")))
  (princ)
)

(defun PdfLayout_HubShow (/ dclPath dclId result nd)
  (setq dclPath (PdfLayout_FindDcl))
  (if (not dclPath)
    (princ "\n[调试] 未找到 PdfLayout.dcl")
    (progn
      (setq dclId (load_dialog dclPath))
      (if (< dclId 0)
        (princ "\n[调试] PdfHub DCL 加载失败")
        (progn
          (setq nd (vl-catch-all-apply 'new_dialog (list "PdfHub" dclId)))
          (if (and nd (not (vl-catch-all-error-p nd)))
            (progn
              (setq *PdfLayout_HubAction* "NONE")
              (set_tile "hub_info" "提示: 命令行仍可直接输入原命令 (PDFLBD / PDFGRID / PDFLAYOUT)")
              (action_tile "hub_lbd" "(setq *PdfLayout_HubAction* \"LBD\") (done_dialog 1)")
                            (action_tile "hub_grid" "(setq *PdfLayout_HubAction* \"GRID\") (done_dialog 1)")
              (action_tile "hub_layout" "(setq *PdfLayout_HubAction* \"LAYOUT\") (done_dialog 1)")
              (action_tile "hub_pypath" "(setq *PdfLayout_HubAction* \"PYPATH\") (done_dialog 1)")
              (action_tile "hub_lbdh" "(setq *PdfLayout_HubAction* \"LBDH\") (done_dialog 1)")
              (action_tile "hub_debug" "(setq *PdfLayout_HubAction* \"DEBUG\") (done_dialog 1)")
              (action_tile "hub_diag" "(setq *PdfLayout_HubAction* \"DIAG\") (done_dialog 1)")
              (action_tile "hub_mtdiag" "(setq *PdfLayout_HubAction* \"MTDIAG\") (done_dialog 1)")
              (action_tile "hub_test" "(setq *PdfLayout_HubAction* \"TEST\") (done_dialog 1)")
              (setq result (start_dialog))
              (unload_dialog dclId)
              (cond
                ((= *PdfLayout_HubAction* "LBD") (c:pdflbd))
                ((= *PdfLayout_HubAction* "GRID") (c:pdfgrid))
                ((= *PdfLayout_HubAction* "LAYOUT") (c:pdflayout))
                ((= *PdfLayout_HubAction* "PYPATH") (PdfLayout_HubSetPythonPath))
                ((= *PdfLayout_HubAction* "LBDH") (PdfLayout_HubSetLbdHeight))
                ((= *PdfLayout_HubAction* "DEBUG") (PdfLayout_HubToggleDebug))
                ((= *PdfLayout_HubAction* "DIAG") (c:pdfdiag))
                ((= *PdfLayout_HubAction* "MTDIAG") (c:pdfmtdiag))
                ((= *PdfLayout_HubAction* "TEST") (c:pdflayouttest))
              )
            )
            (princ "\n[调试] PdfHub 弹窗打开失败（DCL 语法或内容问题）")
          )
        )
      )
    )
  )
  (princ)
)

(defun c:pdftool ()
  (vl-load-com)
  (PdfLayout_HubShow)
  (princ)
)


