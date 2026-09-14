# -*- coding: utf-8 -*-
"""本地网页版：上传PDF -> 切块识别(Node/Typical) -> 网页调框 -> 导出JSON。
运行: python server.py [--port 8800] [--model path\\best.pt]
浏览器打开 http://127.0.0.1:8800
"""
import os, sys, io, json, base64, tempfile, subprocess, argparse, threading, re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from PIL import Image, ImageDraw
from pypdf import PdfReader
from ultralytics import YOLO

PDFTOPPM = r"C:\Users\szk\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
TILE, STRIDE, IMGSZ = 2000, 1600, 768
NAMES = ["Node", "Typical"]
MODEL = None
PAGE_STORE = {}
FEEDBACK_DIR = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\feedback"


def load_model(path):
    global MODEL
    MODEL = YOLO(path)


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return inter / min(aa, ab) if min(aa, ab) > 0 else 0.0


def nms(boxes, t=0.4):
    keep = []
    for b in sorted(boxes, key=lambda x: -x["conf"]):
        if all(iou(b["bbox"], k["bbox"]) <= t or b["cls"] != k["cls"] for k in keep):
            keep.append(b)
    return keep


def detect_page(img, conf):
    W, H = img.size
    raw = []
    tmp = os.path.join(tempfile.gettempdir(), "_ws_tile.jpg")
    for y in range(0, H, STRIDE):
        for x in range(0, W, STRIDE):
            x2, y2 = min(x + TILE, W), min(y + TILE, H)
            if x2 - x < 400 or y2 - y < 400:
                continue
            img.crop((x, y, x2, y2)).save(tmp, quality=90)
            res = MODEL.predict(tmp, conf=conf, imgsz=IMGSZ, verbose=False)[0]
            for b in res.boxes:
                bx1, by1, bx2, by2 = [float(v) for v in b.xyxy[0]]
                raw.append({"bbox": [bx1 + x, by1 + y, bx2 + x, by2 + y],
                            "cls": int(b.cls), "conf": float(b.conf[0])})
    return nms(raw, 0.4)


def parse_pages(spec, total):
    spec = (spec or "").strip().lower()
    if spec in ("", "all", "全部", "*"):
        return list(range(1, total + 1))
    out = []
    for part in re.split(r"[,\s]+", spec):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            for p in range(int(a), int(b) + 1):
                if 1 <= p <= total:
                    out.append(p)
        elif part.isdigit():
            p = int(part)
            if 1 <= p <= total:
                out.append(p)
    return sorted(set(out))


def lbd_from_table(reader, page_no):
    items = []
    pg = reader.pages[page_no - 1]

    def visit(t, cm, tm, font, size):
        if t and "LBD" in t.upper():
            items.append(t.upper())
    try:
        pg.extract_text(visitor_text=visit)
    except Exception:
        pass
    found = set()
    for t in items:
        for m in re.findall(r"[A-Z0-9]+-LBD-\d+", t):
            found.add(m)
    return sorted(found)


def recognize(pdf_path, pages_spec, dpi, rot, conf):
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    pages = parse_pages(pages_spec, total)
    out = []
    tmpdir = tempfile.mkdtemp(prefix="ws_pdf_")
    for p in pages:
        subprocess.run([PDFTOPPM, "-png", "-r", str(dpi), "-f", str(p), "-l", str(p),
                        pdf_path, os.path.join(tmpdir, "p")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        files = [f for f in os.listdir(tmpdir) if f.lower().endswith(".png")]
        if not files:
            continue
        img = Image.open(os.path.join(tmpdir, files[0])).convert("RGB")
        os.remove(os.path.join(tmpdir, files[0]))
        if rot:
            img = img.rotate(rot, expand=True)
        full_path = os.path.join(tempfile.gettempdir(), "ws_full_%d.png" % p)
        img.save(full_path)
        PAGE_STORE[p] = {"path": full_path, "w": img.size[0], "h": img.size[1]}
        boxes = detect_page(img, conf)
        W, H = img.size
        disp = img
        if W > 2400:
            disp = img.resize((2400, int(H * 2400 / W)))
        sc = disp.size[0] / W
        disp_boxes = [{"x1": b["bbox"][0] * sc, "y1": b["bbox"][1] * sc,
                       "x2": b["bbox"][2] * sc, "y2": b["bbox"][3] * sc,
                       "cls": b["cls"], "conf": round(b["conf"], 3)} for b in boxes]
        buf = io.BytesIO()
        disp.save(buf, format="JPEG", quality=80)
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        lbd = lbd_from_table(reader, p)
        out.append({"n": p, "w": disp.size[0], "h": disp.size[1],
                    "img": "data:image/jpeg;base64," + img_b64,
                    "boxes": disp_boxes, "lbd": lbd,
                    "nodeCount": sum(1 for b in boxes if b["cls"] == 0),
                    "typicalCount": sum(1 for b in boxes if b["cls"] == 1),
                    "lbdCount": len(lbd)})
    return {"total": total, "pages": out}


HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>PDF 框识别与调整</title>
<style>
body{margin:0;font:14px/1.5 system-ui,'Microsoft YaHei';background:#111;color:#eee}
#top{padding:10px 14px;background:#1c1c22;display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #333}
button{background:#2563eb;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer}
button.gray{background:#3a3a44}button.red{background:#b91c1c}
input[type=text]{background:#0b0b10;color:#eee;border:1px solid #444;border-radius:6px;padding:5px 8px}
#info{margin-left:auto;color:#9aa}
#wrap{position:relative;overflow:auto;height:calc(100vh - 56px);background:#0b0b10}
canvas{display:block;margin:0 auto}
#msg{color:#ff6b6b;font-weight:bold}
label{color:#9aa}
</style></head><body>
<div id="top">
  <input type="file" id="pdf" accept="application/pdf">
  <label>页码 <input type="text" id="pages" value="13" size="12" placeholder="13 / 13-15 / 全部"></label>
  <button id="allpg" class="gray">全部页</button>
  <label>旋转 <select id="rot" style="background:#0b0b10;color:#eee;border:1px solid #444;border-radius:6px;padding:5px">
    <option value="0">0(默认,按页面)</option><option value="90">90</option><option value="270">270</option></select></label>
  <label>置信 <input type="text" id="conf" value="0.4" size="4"></label>
  <label>线宽 <input type="text" id="lw" value="1.5" size="3"></label>
  <button id="go">开始识别</button>
  <button id="prev" class="gray">&lt; 上一页</button>
  <span id="pg">-</span>
  <button id="next" class="gray">下一页 &gt;</button>
  <button id="addNode" class="gray">画Node框</button>
  <button id="addTyp" class="gray">画Typical框</button>
  <button id="del" class="red">删除选中</button>
  <button id="exp">导出 JSON</button>
  <button id="fb" style="background:#059669">加入训练集</button>
  <span id="info"></span>
  <span id="msg"></span>
</div>
<div id="wrap"><canvas id="cv"></canvas></div>
<script>
let pages=[], cur=0, sel=-1, img=new Image(), addMode=null, drag=null, LW=1.5;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const COL={0:'#ff2d2d',1:'#2d8cff'};
function curPage(){return pages[cur];}
function draw(){
  const p=curPage(); if(!p)return;
  cv.width=p.w; cv.height=p.h;
  ctx.drawImage(img,0,0,p.w,p.h);
  p.boxes.forEach((b,i)=>{
    ctx.lineWidth=(i===sel)?LW+1:LW; ctx.strokeStyle=(i===sel)?'#00ff88':COL[b.cls];
    ctx.strokeRect(b.x1,b.y1,b.x2-b.x1,b.y2-b.y1);
    ctx.fillStyle=COL[b.cls]; ctx.font='13px sans-serif';
    ctx.fillText((b.cls===0?'N':'T'),b.x1+3,b.y1+14);
  });
  const p2=curPage();
  document.getElementById('pg').textContent=(cur+1)+'/'+pages.length+' 页'+p.n;
  document.getElementById('info').textContent='Node='+p.boxes.filter(b=>b.cls===0).length+
     '  Typical='+p.boxes.filter(b=>b.cls===1).length+'  表LBD='+p.lbdCount+
     (p.lbdCount&&p.boxes.filter(b=>b.cls===0).length!==p.lbdCount?'  ⚠Node数≠LBD数':'');
}
function load(){img=new Image();img.onload=draw;img.src=curPage().img;}
function hit(x,y){const p=curPage();for(let i=p.boxes.length-1;i>=0;i--){const b=p.boxes[i];
  if(x>=b.x1-6&&x<=b.x2+6&&y>=b.y1-6&&y<=b.y2+6)return i;}return -1;}
cv.addEventListener('mousedown',e=>{
  const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,p=curPage();if(!p)return;
  if(addMode!==null){p.boxes.push({x1:x,y1:y,x2:x+40,y2:y+40,cls:addMode,conf:1});sel=p.boxes.length-1;addMode=null;draw();return;}
  const i=hit(x,y); sel=i;
  if(i>=0){const b=p.boxes[i];
    const corner = (Math.abs(x-b.x2)<12&&Math.abs(y-b.y2)<12)?'br':'move';
    drag={i,corner,ox:x,oy:y,orig:{...b}};
  }
  draw();
});
cv.addEventListener('mousemove',e=>{
  if(!drag)return; const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  const b=curPage().boxes[drag.i],o=drag.orig,dx=x-drag.ox,dy=y-drag.oy;
  if(drag.corner==='move'){b.x1=o.x1+dx;b.y1=o.y1+dy;b.x2=o.x2+dx;b.y2=o.y2+dy;}
  else{b.x2=o.x2+dx;b.y2=o.y2+dy;}
  draw();
});
window.addEventListener('mouseup',()=>{drag=null});
window.addEventListener('keydown',e=>{if(e.key==='Delete'&&sel>=0){curPage().boxes.splice(sel,1);sel=-1;draw();}});
document.getElementById('prev').onclick=()=>{if(cur>0){cur--;sel=-1;load();}};
document.getElementById('lw').oninput=e=>{LW=parseFloat(e.target.value)||1.5;draw();};
document.getElementById('allpg').onclick=()=>{document.getElementById('pages').value='全部';msg('已设为全部页(注意: 每页约1分钟)');};
document.getElementById('next').onclick=()=>{if(cur<pages.length-1){cur++;sel=-1;load();}};
document.getElementById('addNode').onclick=()=>{addMode=0;msg('在图上拖点一下画Node框');};
document.getElementById('addTyp').onclick=()=>{addMode=1;msg('在图上拖点一下画Typical框');};
document.getElementById('del').onclick=()=>{if(sel>=0){curPage().boxes.splice(sel,1);sel=-1;draw();}};
function msg(t){document.getElementById('msg').textContent=t;}
document.getElementById('go').onclick=async()=>{
  const f=document.getElementById('pdf').files[0]; if(!f){msg('请先选择PDF');return;}
  const pv=document.getElementById('pages').value.trim().toLowerCase();
  const rt=document.getElementById('rot').value, cf=document.getElementById('conf').value;
  try{
    const buf=await f.arrayBuffer();
    const isAll=(pv===''||pv==='all'||pv==='全部'||pv==='*');
    let list;
    if(isAll){
      msg('读取页数...');
      const ij=await (await fetch('/api/info',{method:'POST',headers:{'Content-Type':'application/pdf'},body:buf})).json();
      if(!ij.ok){msg('错误: '+ij.error);return;}
      list=[]; for(let n=1;n<=ij.total;n++) list.push(n);
    } else { list=[pv]; }
    pages=[]; cur=0; sel=-1;
    for(let i=0;i<list.length;i++){
      msg('识别中 '+(i+1)+'/'+list.length+' (第'+list[i]+'页)...');
      const url='/api/recognize?pages='+encodeURIComponent(list[i])+'&rot='+encodeURIComponent(rt)+'&conf='+encodeURIComponent(cf);
      const j=await (await fetch(url,{method:'POST',headers:{'Content-Type':'application/pdf'},body:buf})).json();
      if(!j.ok){msg('错误: '+j.error);return;}
      if(j.pages&&j.pages.length){ pages=pages.concat(j.pages); if(pages.length===1) load(); }
    }
    msg('完成: 共'+pages.length+'页, 可翻页/调框/加入训练集'); load();
  }catch(e){msg('错误: '+e.message);}
};
window.addEventListener('error',e=>{msg('JS错误: '+e.message);});
document.getElementById('exp').onclick=()=>{
  const out={pages:pages.map(p=>({page:p.n,width:p.w,height:p.h,lbdCount:p.lbdCount,
    boxes:p.boxes.map(b=>({cls:b.cls,clsName:['Node','Typical'][b.cls],conf:b.conf,
      x1:+(b.x1/p.w).toFixed(6),y1:+(b.y1/p.h).toFixed(6),
      x2:+(b.x2/p.w).toFixed(6),y2:+(b.y2/p.h).toFixed(6)}))}))};
  const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='detect_result.json';a.click();
};
document.getElementById('fb').onclick=async()=>{
  if(!pages.length){msg('先识别');return;}
  let total=0;
  for(const p of pages){
    const body={name:(document.getElementById('pdf').files[0]||{}).name||'fb',page:p.n,w:p.w,h:p.h,
      boxes:p.boxes.map(b=>({x1:b.x1,y1:b.y1,x2:b.x2,y2:b.y2,cls:b.cls}))};
    const r=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.ok) total++;
  }
  msg('已加入训练集: '+total+' 页 -> frame_detect\\feedback');
};
</script></body></html>"""


def save_feedback(name, page, dispw, disph, boxes):
    info = PAGE_STORE.get(int(page))
    if not info:
        raise RuntimeError("page not recognized yet")
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_\-\. ]", "_", str(name)) + "_p%03d" % int(page)
    img = Image.open(info["path"]).convert("RGB")
    fw, fh = img.size
    sx, sy = fw / float(dispw), fh / float(disph)
    shapes = []
    for b in boxes:
        x1 = b["x1"] * sx; y1 = b["y1"] * sy; x2 = b["x2"] * sx; y2 = b["y2"] * sy
        shapes.append({"label": NAMES[int(b["cls"])], "score": None,
                       "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                       "group_id": None, "description": "", "difficult": False,
                       "shape_type": "rectangle", "flags": {}, "attributes": {},
                       "kie_linking": []})
    img.save(os.path.join(FEEDBACK_DIR, stem + ".png"))
    with open(os.path.join(FEEDBACK_DIR, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump({"version": "4.0.0-beta.11", "flags": {}, "checked": False,
                   "shapes": shapes, "imagePath": stem + ".png", "imageData": None,
                   "imageHeight": fh, "imageWidth": fw}, f, ensure_ascii=False, indent=2)
    return os.path.join(FEEDBACK_DIR, stem + ".json")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"{}")

    def do_POST(self):
        path = urlparse(self.path).path
        print("POST", path, flush=True)
        if path == "/api/feedback":
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or b"{}")
                print("  feedback page", req.get("page"), "boxes",
                      len(req.get("boxes", [])), flush=True)
                p = save_feedback(req.get("name", "feedback"), req["page"],
                                  req["w"], req["h"], req["boxes"])
                self._send(200, json.dumps({"ok": True, "saved": p}).encode("utf-8"))
            except Exception as e:
                traceback.print_exc()
                self._send(200, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return
        if path == "/api/info":
            try:
                n = int(self.headers.get("Content-Length", 0))
                pdf = self.rfile.read(n) or b""
                tmp = os.path.join(tempfile.gettempdir(), "ws_info.pdf")
                open(tmp, "wb").write(pdf)
                total = len(PdfReader(tmp).pages)
                self._send(200, json.dumps({"ok": True, "total": total}).encode("utf-8"))
            except Exception as e:
                traceback.print_exc()
                self._send(200, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return
        if path != "/api/recognize":
            self._send(404, b"{}")
            return
        try:
            q = parse_qs(urlparse(self.path).query)
            pages = q.get("pages", [""])[0]
            rot = int(q.get("rot", ["0"])[0])
            conf = float(q.get("conf", ["0.4"])[0])
            n = int(self.headers.get("Content-Length", 0))
            pdf = self.rfile.read(n) or b""
            print("  recognize pages=%s pdfMB=%.1f" % (pages, len(pdf) / 1048576.0), flush=True)
            tmp = os.path.join(tempfile.gettempdir(), "ws_upload.pdf")
            open(tmp, "wb").write(pdf)
            res = recognize(tmp, pages, 250, rot, conf)
            res["ok"] = True
            self._send(200, json.dumps(res).encode("utf-8"))
        except Exception as e:
            traceback.print_exc()
            self._send(200, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\tiles\weights\best.pt")
    a = ap.parse_args()
    print("loading model:", a.model)
    load_model(a.model)
    print("open http://127.0.0.1:%d" % a.port)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
