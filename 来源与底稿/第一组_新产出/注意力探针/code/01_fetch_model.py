#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 第一步：按预注册的 revision 拉权重（必须走 hf-mirror），并逐文件算 sha256。

★ 预注册固定项（PREREG_T-L1-01.md §4）：
  模型    Qwen/Qwen3-0.6B
  revision c1899de289a04d12100db370d81485cdf75e47ca
  权重来源 必须 hf-mirror.com（HF 直连实测 000）
  model.safetensors 1,503,300,328 B / sha256 f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b
  其余 6 文件 sha256 由执行者现场重算 → 写进 ENV 段

★ 本脚本不做任何静默兜底：sha 不符就退出非零。
"""
import os, sys, json, hashlib, time

sys.dont_write_bytecode = True

REPO_ID = "Qwen/Qwen3-0.6B"
REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
EXPECT_SAFETENSORS_SHA = "f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b"
EXPECT_SAFETENSORS_SIZE = 1_503_300_328
ENDPOINT = "https://hf-mirror.com"

OUT_ROOT = "/workspace/hf_cache"
MANIFEST = "/workspace/run/00_model_manifest.json"


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    os.environ["HF_ENDPOINT"] = ENDPOINT
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import snapshot_download

    local = None
    for attempt in range(1, 6):
        try:
            local = snapshot_download(
                repo_id=REPO_ID,
                revision=REVISION,
                local_dir=os.path.join(OUT_ROOT, "Qwen3-0.6B"),
                endpoint=ENDPOINT,
                max_workers=4,
            )
            break
        except Exception as e:
            print("  下载第 %d 次失败：%s" % (attempt, str(e)[:160]), flush=True)
            time.sleep(5 * attempt)
    if local is None:
        print("⛔ 下载连续失败")
        return 1

    files = sorted(os.listdir(local))
    rec = {"repo_id": REPO_ID, "revision": REVISION, "endpoint": ENDPOINT,
           "local_dir": local, "files": {}}
    for name in files:
        p = os.path.join(local, name)
        if not os.path.isfile(p):
            continue
        size = os.path.getsize(p)
        rec["files"][name] = {"bytes": size, "sha256": sha256_of(p)}
        print("  %-28s %12d B  %s" % (name, size, rec["files"][name]["sha256"]), flush=True)

    # ★ 硬校验：主权重的大小与 sha256 必须与预注册一致
    st = rec["files"].get("model.safetensors")
    if st is None:
        print("⛔ 没有 model.safetensors")
        return 1
    ok_size = (st["bytes"] == EXPECT_SAFETENSORS_SIZE)
    ok_sha = (st["sha256"] == EXPECT_SAFETENSORS_SHA)
    rec["safetensors_matches_prereg"] = bool(ok_size and ok_sha)
    rec["safetensors_size_expected"] = EXPECT_SAFETENSORS_SIZE
    rec["safetensors_sha_expected"] = EXPECT_SAFETENSORS_SHA
    print("  model.safetensors 与预注册一致：%s（size %s / sha %s）"
          % (rec["safetensors_matches_prereg"], ok_size, ok_sha))

    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    print("→ %s" % MANIFEST)
    return 0 if rec["safetensors_matches_prereg"] else 2


if __name__ == "__main__":
    sys.exit(main())
