import sys

path = sys.argv[1]
enc = sys.argv[2] if len(sys.argv) > 2 else "gbk"
lines = open(path, encoding=enc).read().splitlines()
lo = int(sys.argv[3]) if len(sys.argv) > 3 else 0
hi = int(sys.argv[4]) if len(sys.argv) > 4 else -1
depth = 0
instr = False
for ln, line in enumerate(lines, 1):
    i = 0
    while i < len(line):
        ch = line[i]
        if instr:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                instr = False
        else:
            if ch == ";":
                break
            if ch == '"':
                instr = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    print("NEGATIVE at line", ln, ":", line)
                    depth = 0
        i += 1
    if line.strip().startswith("(defun"):
        print("line %d  depth_before_defun=%d  %s" % (ln, depth, line.strip()[:60]))
    if lo <= ln <= hi:
        print("  line %d  depth=%d  %s" % (ln, depth, line.rstrip()[:70]))
print("FINAL depth =", depth, " in_string =", instr)
