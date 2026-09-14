import sys
import pythoncom
import win32com.client as win32

pythoncom.CoInitialize()
acad = None
for progid in ("ZWCAD.Application", "AutoCAD.Application"):
    try:
        acad = win32.GetActiveObject(progid)
        print("connected(active)", progid)
        break
    except Exception:
        acad = None
    if not acad:
        try:
            acad = win32.DispatchEx(progid)
            print("started", progid)
            break
        except Exception as e:
            print("start fail", progid, e)
if not acad:
    print("NO CAD")
    sys.exit(1)
try:
    acad.Visible = True
except Exception:
    pass
dwg = r"C:/Users/szk/Desktop/测试.dwg"
doc = acad.Documents.Open(dwg)
ms = doc.ModelSpace
print("modelspace count", ms.Count)
for i in range(ms.Count):
    o = ms.Item(i)
    try:
        ot = o.ObjectName
    except Exception:
        ot = "?"
    if any(k in ot for k in ("Underlay", "Raster", "Image", "PDF")):
        try:
            ins = o.InsertionPoint
        except Exception:
            ins = None
        try:
            sc = o.ScaleFactor
        except Exception:
            sc = None
        try:
            nm = o.Name
        except Exception:
            nm = None
        try:
            fn = o.FullName
        except Exception:
            fn = None
        print("obj", i, ot, "ins", list(ins) if ins else None,
              "scale", sc, "name", nm, "full", fn)
try:
    doc.Close(False)
except Exception:
    pass
