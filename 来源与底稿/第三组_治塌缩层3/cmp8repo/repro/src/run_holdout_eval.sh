#!/bin/bash
# ★ 留出集评测（预注册 PREREG-HOLDOUT-2026-10-24.md v2）
#   ① 合并 13 题重训策略（排除 A02/A05）→ merged13
#   ② 留出清单 = A02 + A05（预注册的"按名单排除"，不按数量截取）
#   ③ 三策略 × 3 臂 × R=8 × 2 题 ⇒ 主指标=钻牛角尖率（零判官）
#   ④ 出成对方向检验表
set -u
cd /workspace/lab/routes/COLLAPSE || exit 1
R=/workspace/lab/routes/COLLAPSE/runs
H=$R/holdout13
mkdir -p "$H"

echo "════ [1/4] 合并 13 题重训策略 ════"
python3 -B merge_policies.py "$H/pl_2026110*" --out "$H/policy_merged13.json" 2>&1 | tail -8
python3 - <<'PY'
import json
d=json.load(open("/workspace/lab/routes/COLLAPSE/runs/holdout13/policy_merged13.json"))
m=d.get("meta",{}); p=d["policy"]
print("  meta: n_runs=%s n_samples=%s m_shape=%s pad=%s"%(m.get("n_runs"),m.get("n_samples"),m.get("m_shape"),m.get("m_pad_cells")))
print("  per_source_samples=%s"%(m.get("per_source_samples"),))
for k in ("u","v","t","arb","nf","mm"):
    if k in p: print("  %-4s"%k,[round(x,2) for x in p[k]])
PY

echo "════ [2/4] 留出清单（A02 + A05，按名单）════"
python3 - <<'PY'
import json
src="/workspace/lab/routes/DEV/DEV-ADV-2026-10-24.json"
d=json.load(open(src)); ts=d["tasks"] if isinstance(d,dict) and "tasks" in d else d
keep=[t for t in ts if t.get("task_id") in ("A02","A05")]
out=dict(d) if isinstance(d,dict) else {"tasks":[]}
out["tasks"]=keep
out["holdout_note"]="★ 预注册留出清单：A02（路径多样）+ A05（路径单一）⇒ 按名单，不按数量"
p="/workspace/lab/routes/COLLAPSE/runs/holdout13/devset_A02_A05.json"
json.dump(out,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("  留出题:",[t["task_id"] for t in keep],"→",p)
PY

echo "════ [3/4] 三策略并行评测（R=8）════"
DS=$H/devset_A02_A05.json
# 对照策略（lookup / uniform）若不存在则造
for v in lookup uniform; do
  [ -f "$R/policy_$v.json" ] || python3 -B -c "
import sys,os,json; sys.path.insert(0,'/workspace/lab/routes/COLLAPSE')
import workflow as W
pol = W.ActionPolicy.from_lookup() if '$v'=='lookup' else W.ActionPolicy()
json.dump(dict(policy=pol.export(), meta=dict(kind='$v')), open('$R/policy_$v.json','w'), ensure_ascii=False, indent=2)
print('  造策略 $v')"
done
for v in merged13 lookup uniform; do
  case $v in
    merged13) PF=$H/policy_merged13.json ;;
    *) PF=$R/policy_$v.json ;;
  esac
  [ -f "$PF" ] || { echo "  ★ 缺 $PF ⇒ 跳过 $v"; continue; }
  out=$H/valid_$v
  setsid nohup python3 -B -u run_dev.py --devset "$DS" --tasks 2 --reps 8 --slots 3 --rounds 2 \
    --arms B0_direct,B0_bestof3,W_train_L3 --action-mode policy --policy-file "$PF" \
    --judge minimax --judge-model MiniMax-M2.5 --out "$out" \
    > "$H/valid_$v.log" 2>&1 &
  echo "  启动 $v pid=$! → $out"
  sleep 3
done

echo "════ [4/4] 等齐 + 出成对方向检验表 ════"
NEED=$((2 * 3 * 8))   # 2 题 × 3 臂 × 8 rep = 48
for i in $(seq 1 150); do
  n=0; det=""
  for v in merged13 lookup uniform; do
    c=0; [ -f "$H/valid_$v/arms.jsonl" ] && c=$(wc -l < "$H/valid_$v/arms.jsonl")
    det="$det $v=$c"; [ "$c" -ge "$NEED" ] && n=$((n+1))
  done
  echo "  [+$((i*30))s] 齐了 $n/3 |$det"
  [ "$n" = "3" ] && break
  sleep 30
done

python3 - <<'PY' | tee "$H/holdout_table.txt"
import json, os, statistics
H="/workspace/lab/routes/COLLAPSE/runs/holdout13"
def load(v):
    f=os.path.join(H,"valid_%s"%v,"arms.jsonl")
    if not os.path.exists(f): return []
    return [json.loads(l) for l in open(f,encoding="utf-8") if l.strip()]
data={v:load(v) for v in ("merged13","lookup","uniform")}
print("="*96)
print("★ 留出集评测（★ 预注册 PREREG-HOLDOUT-2026-10-24.md v2）★ 题 = A02（路径多样）+ A05（路径单一）")
print("="*96)
def trap(rows, arm, task=None):
    rs=[r for r in rows if r.get("arm")==arm and (task is None or r.get("task_id")==task)]
    return rs
def rate(rows, arm, task=None):
    rs=trap(rows,arm,task)
    h=[bool((r.get("pc") or {}).get("hit")) for r in rs]
    return (sum(h),len(h)) if h else (0,0)
def dims(rows, arm, task=None):
    rs=trap(rows,arm,task); d=[r.get("n_dims") for r in rs if r.get("n_dims") is not None]
    return statistics.median(d) if d else None
print("\n【主指标 · 钻牛角尖率（零判官）】")
print("  %-6s %-16s %-14s %-14s %-14s" % ("臂","策略","A02(路径多样)","A05(路径单一)","合计"))
for arm in ("W_train_L3","B0_direct","B0_bestof3"):
    for v in ("merged13","lookup","uniform"):
        a2=rate(data[v],arm,"A02"); a5=rate(data[v],arm,"A05"); tt=rate(data[v],arm)
        print("  %-6s %-16s %-14s %-14s %-14s"%(arm,v,"%d/%d"%a2,"%d/%d"%a5,"%d/%d"%tt))
print("\n【辅助 · 承重维度中位（同厂商判官 MiniMax-M2.5）】")
for arm in ("W_train_L3",):
    for v in ("merged13","lookup","uniform"):
        a2=dims(data[v],arm,"A02"); a5=dims(data[v],arm,"A05")
        print("  %-14s %-10s A02=%-6s A05=%-6s"%(arm,v,a2,a5))
print("\n【负对照臂 B0_bestof3（三策略应持平 ⇒ 排除整体漂移）】")
for v in ("merged13","lookup","uniform"):
    print("  %-10s A02=%d/%d  A05=%d/%d"%(v,*rate(data[v],"B0_bestof3","A02"),*rate(data[v],"B0_bestof3","A05")))
print("\n【★ 成对方向检验（预注册写死的判读）】")
def better(v, task, arm="W_train_L3"):
    h,n=rate(data[v],arm,task)
    return h,n
for task,label in (("A02","路径多样"),("A05","路径单一")):
    line=[]
    for v in ("merged13","lookup","uniform"):
        h,n=better(v,task); line.append("%s=%d/%d"%(v,h,n))
    m=rate(data["merged13"],arm="W_train_L3",task=task)
    l=rate(data["lookup"],arm="W_train_L3",task=task)
    u=rate(data["uniform"],arm="W_train_L3",task=task)
    m_only = m[0] < l[0] and m[0] < u[0]
    same_all = (m[0]==l[0]==u[0])
    print("  %s（%s）: %s"%(task,label,"  ".join(line)))
    if m_only:   print("     ⇒ ★ merged13 独优 ⇒ 支持『学到的是何时该发散』")
    elif same_all: print("     ⇒ 三者持平 ⇒ 写【不可分辨】")
    else:        print("     ⇒ 未形成分离 ⇒ 写【不可分辨】（2 题检出力不足）")
PY
echo "✔ 留出评测完成 → $H/holdout_table.txt"
