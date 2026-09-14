// PdfLayout.dcl
// MAP文件工具箱 v2.16 - 对话框定义

PdfLayout : dialog {
  label = "MAP文件工具箱 v2.16";
  width = 62;

  : boxed_column {
    label = "图纸识别（竖线标记模式）";
    : row {
      : popup_list {
        label = "竖线块名:";
        key = "marker_name";
        edit_width = 22;
      }
    }
    : button {
      label = "仅自动排序已导入的PDF(不建布局)";
      key = "btn_arrange";
      width = 32;
    }
    : text {
      key = "found_info";
      label = " ";
      width = 55;
    }
    : text {
      label = "提示: 先用 PDFATTACH 导入PDF，再运行本命令自动排列底图并创建布局；竖线标记块默认名pdf";
      width = 55;
    }
  }

  : boxed_column {
    label = "布局";
    : popup_list {
      label = "模板布局(含图框):";
      key = "tmpl_layout";
      edit_width = 26;
    }
    : row {
      : edit_box { label = "布局名来自Excel分表:"; key = "names_xlsx"; edit_width = 16; }
      : button { label = "选择..."; key = "btn_names_xlsx"; width = 10; }
    }
    : text { label = "填Excel后按分表顺序命名布局(数量=分表数)；留空用下方规则"; width = 55; }
    : row {
      : edit_box {
        label = "复制数量:";
        key = "count";
        edit_width = 6;
        value = "0";
        allow_accept = true;
      }
      : toggle {
        label = "覆盖同名布局";
        key = "overwrite";
        value = "0";
      }
    }
  }

  : boxed_column {
    label = "命名规则";
    : edit_box {
      label = "规则:";
      key = "rule";
      edit_width = 34;
      value = "INV{G2}{L}{N2}";
      allow_accept = true;
    }
    : row {
      : edit_box {
        label = "字母列表:";
        key = "letters";
        edit_width = 10;
        value = "AB";
        allow_accept = true;
      }
      : edit_box {
        label = "每组张数:";
        key = "per_group";
        edit_width = 5;
        value = "6";
        allow_accept = true;
      }
      : edit_box {
        label = "编号起始:";
        key = "g_start";
        edit_width = 5;
        value = "1";
        allow_accept = true;
      }
    }
    : text {
      label = "占位符: {G2}=编号(2位)  {L}=字母循环  {N2}=组内序号(2位)";
      width = 58;
    }
    : text {
      label = "例: INV{G2}{L}{N2} + 字母AB + 每组6张 -> INV01A01..A06, INV01B01..B06, INV02A01..";
      width = 58;
    }
    : list_box {
      label = "名称预览:";
      key = "preview";
      height = 9;
    }
  }

  : boxed_column {
    label = "视口";
    : edit_box {
      label = "模板无视口时按边距创建(mm):";
      key = "margin";
      edit_width = 6;
      value = "5";
      allow_accept = true;
    }
    : toggle {
      label = "锁定视口显示(防误缩放)";
      key = "lock_vp";
      value = "0";
    }
  }

  ok_cancel;
}

PdfRenamePreview : dialog {
  label = "多行文字命名方案";
  : boxed_column {
    label = "方案预设";
    : row {
      : popup_list { label = "方案:"; key = "prof_list"; edit_width = 18; }
    }
    : row {
      : edit_box { label = "方案名:"; key = "prof_name"; edit_width = 12; }
      : button { label = "保存为方案"; key = "btn_saveprof"; width = 14; }
      : button { label = "删除方案"; key = "btn_delprof"; width = 14; }
    }
  }
  : boxed_radio_column {
    label = "名称来源";
    : radio_button { label = "自动生成（前缀+编号）[已停用]"; key = "srcauto"; value = "1"; }
    : radio_button { label = "从CSV文件导入"; key = "srcfile"; }
    : radio_button { label = "从CSV导入(LBD标签两列)"; key = "srcfile2"; }
  }
  : row {
    : edit_box { label = "文件:"; key = "file_path"; edit_width = 22; }
    : button { label = "选择..."; key = "btn_file"; width = 10; }
  }
  : row {
    : edit_box { label = "前缀:"; key = "prefix"; edit_width = 8; }
    : edit_box { label = "起始编号:"; key = "start"; edit_width = 5; }
    : edit_box { label = "位数(0=不补零):"; key = "digits"; edit_width = 4; }
  }
  : boxed_column {
    label = "文字背景";
    : radio_row {
      : radio_button { label = "保持现状"; key = "bgkeep"; value = "1"; }
      : radio_button { label = "开启填充"; key = "bgon"; }
      : radio_button { label = "关闭填充"; key = "bgoff"; }
    }
    : row {
      : edit_box { label = "颜色(ACI):"; key = "bg_color"; edit_width = 4; }
      : edit_box { label = "缩放系数:"; key = "bg_scale"; edit_width = 4; }
    }
  }
  : boxed_radio_column {
    label = "排序方式";
: radio_button { label = "1 列优先: 左→右列、列内上→下"; key = "ord1"; value = "1"; }
: radio_button { label = "2 行优先: 上→下行、行内左→右"; key = "ord2"; }
    : radio_button { label = "3 列优先: 右→左列、列内上→下"; key = "ord3"; }
    : radio_button { label = "4 行优先: 下→上行、行内左→右"; key = "ord4"; }
    : radio_button { label = "5 列优先: 左→右列、列内下→上"; key = "ord5"; }
    : radio_button { label = "6 列优先: 右→左列、列内下→上"; key = "ord6"; }
    : radio_button { label = "7 行优先: 上→下行、行内右→左"; key = "ord7"; }
    : radio_button { label = "8 行优先: 下→上行、行内右→左"; key = "ord8"; }
  }
  : row {
    : edit_box { label = "行列容差(默认10~1%范围):"; key = "row_tol"; edit_width = 5; value = "10"; }
    : toggle { label = "在图上显示顺序号(1,2,3...)，退出保留到下次运行"; key = "ord_prev"; value = "0"; }
  }
  : boxed_column {
    label = "方案预览（左=顺序 右=名称）";
    : row {
      : list_box { key = "scheme_grid"; height = 8; width = 26; }
      : list_box { key = "name_list"; height = 8; width = 22; }
    }
  }
  : text { key = "info_text"; label = " "; width = 60; }
  ok_cancel;
}

PdfGrid : dialog {
  label = "PDF网格批量生成(PDFGRID)";
  : row {
    : column {
  : boxed_column {
    label = "方案预设";
    : row {
      : popup_list { label = "方案:"; key = "g_prof"; edit_width = 18; }
      : edit_box { label = "方案名:"; key = "g_profname"; edit_width = 10; }
    }
    : row {
      : button { label = "保存为方案"; key = "g_saveprof"; width = 12; }
      : button { label = "删除方案"; key = "g_delprof"; width = 12; }
    }
  }
  : boxed_column {
    label = "网格";
    : row {
      : edit_box { label = "行数:"; key = "g_rows"; edit_width = 5; value = "4"; }
      : edit_box { label = "列数:"; key = "g_cols"; edit_width = 5; value = "5"; }
    }
    : row {
      : edit_box { label = "行距:"; key = "g_rowsp"; edit_width = 8; value = "10"; }
      : edit_box { label = "列距:"; key = "g_colsp"; edit_width = 8; value = "20"; }
    }
    : row {
      : edit_box { label = "上边距:"; key = "g_mt"; edit_width = 6; value = "0"; }
      : edit_box { label = "下边距:"; key = "g_mb"; edit_width = 6; value = "0"; }
      : edit_box { label = "左边距:"; key = "g_ml"; edit_width = 6; value = "0"; }
      : edit_box { label = "右边距:"; key = "g_mr"; edit_width = 6; value = "0"; }
    }
    : radio_row {
      label = "几何:";
      : radio_button { label = "按范围自动算(比例)"; key = "g_geoa"; value = "1"; }
      : radio_button { label = "固定绝对参数"; key = "g_geof"; }
    }
    : row {
      : edit_box { label = "字高比例(自动模式):"; key = "g_hratio"; edit_width = 6; value = "0.3"; }
      : text { label = "(字高=min(行距,列距)x比例)"; }
    : radio_row {
      label = "字高:";
      : radio_button { label = "按比例自动"; key = "g_hauto"; value = "1"; }
      : radio_button { label = "直接输入"; key = "g_hmanual"; }
    }
    }
    : text { label = "起点/范围: 0, 0（命令时点取/框选；文字按几何中心对齐，边距自范围边起算）"; key = "g_start"; }
  }
  : boxed_column {
    label = "文字";
    : row {
      : edit_box { label = "字高:"; key = "g_h"; edit_width = 8; value = "0.5"; }
      : popup_list { label = "旋转:"; key = "g_rot"; edit_width = 10; }
    }
    : radio_row {
      label = "背景:";
      : radio_button { label = "无"; key = "g_bgnone"; }
      : radio_button { label = "填充"; key = "g_bgon"; value = "1"; }
    }
    : row {
    : row {
      : popup_list { label = "背景色:"; key = "g_bgcolor"; edit_width = 12; }
      : edit_box { label = "自定义:"; key = "g_bgaci"; edit_width = 4; value = "1"; }
      : edit_box { label = "背景缩放%:"; key = "g_bgscale"; edit_width = 5; value = "100"; }
    }
    : row {
      : popup_list { label = "文字色:"; key = "g_txtcolor"; edit_width = 12; }
      : edit_box { label = "自定义:"; key = "g_txtaci"; edit_width = 4; value = "7"; }
    }
    }
  }
  : boxed_radio_column {
    label = "命名来源";
    : radio_button { label = "自动命名(前缀+编号)"; key = "g_srcauto"; value = "1"; }

    : radio_button { label = "从Excel导入(按分表)"; key = "g_srcxlsx"; }
  }
  : boxed_column {
    label = "自动命名(前缀+编号)[已停用]:";
    : row {
      : edit_box { label = "前缀:"; key = "g_prefix"; edit_width = 8; value = "CIR"; }
      : edit_box { label = "起始:"; key = "g_startn"; edit_width = 5; value = "1"; }
      : edit_box { label = "位数(0=不补零):"; key = "g_digits"; edit_width = 4; value = "2"; }
    }
  }

  : boxed_column {
    label = "从Excel导入(分表名=布局名):";
    : row {
      : edit_box { label = "Excel:"; key = "g_filexlsx"; edit_width = 20; }
      : button { label = "选择..."; key = "g_btnxlsx"; width = 10; }
    }
    : row {
      : popup_list { label = "分表:"; key = "g_xlsxsheet"; edit_width = 30; }
      : button { label = "重读"; key = "g_btnxlsxre"; width = 10; }
    }
  }
  : boxed_radio_column {
    label = "排序方式";
    : radio_button { label = "1 列优先: 左→右列、列内上→下"; key = "ord1"; value = "1"; }
    : radio_button { label = "2 行优先: 上→下行、行内左→右"; key = "ord2"; }
    : radio_button { label = "3 列优先: 右→左列、列内上→下"; key = "ord3"; }
    : radio_button { label = "4 行优先: 下→上行、行内左→右"; key = "ord4"; }
    : radio_button { label = "5 列优先: 左→右列、列内下→上"; key = "ord5"; }
    : radio_button { label = "6 列优先: 右→左列、列内下→上"; key = "ord6"; }
    : radio_button { label = "7 行优先: 上→下行、行内右→左"; key = "ord7"; }
    : radio_button { label = "8 行优先: 下→上行、行内右→左"; key = "ord8"; }
  }
    }
    : column {
  : boxed_column {
    label = "预览(左=顺序 右=名称):";
    : row {
      : list_box { key = "g_grid"; height = 8; width = 26; }
      : list_box { key = "g_names"; height = 8; width = 22; }
    }
  }
    }
  }
  : text { key = "g_info"; label = " "; width = 60; }
  ok_cancel;
}



PdfHub : dialog {
  label = "PDF 布局工具箱";
  : boxed_column {
    label = "功能";
    : button { label = "① PDF底图 LBD 识别填标签"; key = "hub_lbd"; }
    : button { label = "② 多行文字按顺序改名"; key = "hub_rename"; }
    : button { label = "③ 批量生成网格文字"; key = "hub_grid"; }
    : button { label = "④ 图纸识别 / 布局管理"; key = "hub_layout"; }
  }
  : boxed_column {
    label = "维护";
    : row {
      : button { label = "Python 路径"; key = "hub_pypath"; }
      : button { label = "默认字高"; key = "hub_lbdh"; }
    }
    : row {
      : button { label = "调试开关"; key = "hub_debug"; }
      : button { label = "诊断"; key = "hub_diag"; }
      : button { label = "自检"; key = "hub_test"; }
    }
  }
  : text { key = "hub_info"; label = "提示: 命令行仍可直接输入原命令"; width = 60; }
  ok_cancel;
}

PdfLbd : dialog {
  label = "PDF底图 LBD 识别";
  : boxed_column {
    label = "文件";
    : row {
      : edit_box { label = "PDF底图原始PDF:"; key = "lbd_pdf"; edit_width = 34; }
      : button { label = "选择..."; key = "btn_pdf"; width = 10; }
    }
    : row {
      : edit_box { label = "标签Excel(分表名=布局名):"; key = "lbd_xlsx"; edit_width = 34; }
      : button { label = "选择..."; key = "btn_xlsx"; width = 10; }
    }
  }
  : boxed_column {
    label = "识别选项";
    : edit_box { label = "只识别第几页(0=全部):"; key = "lbd_page"; edit_width = 5; value = "0"; }
    : radio_row {
      label = "标签写入位置:";
      : radio_button { label = "M模型空间"; key = "lbd_m"; value = "1"; }
      : radio_button { label = "L当前布局"; key = "lbd_l"; }
      : radio_button { label = "B两者"; key = "lbd_b"; }
    }
    : edit_box { label = "标签字高(模型单位):"; key = "lbd_h"; edit_width = 6; value = "0.15"; }
: popup_list { label = "标签背景色(ACI):"; key = "lbd_bg"; width = 8; }
    : toggle { label = "框选排除干扰区域(右下角细节图等)"; key = "lbd_excl"; value = "0"; }
  }
  ok_cancel;
}

