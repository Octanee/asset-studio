"""WP-01 / R-12: is the character consistent across many different poses?

Builds 10 exercise poses as OpenPose COCO-18 skeletons from joint angles, then runs the
approved MVP pipeline in ComfyUI (SDXL + OpenPose ControlNet + IP-Adapter reference) once per
pose with the same character reference, and writes a contact sheet.

Usage:
  python r12_poses.py skeletons <comfy_input_dir>                     # writes r12_pose_*.png
  python r12_poses.py generate <ref_image_name> [--url http://127.0.0.1:8188]
  python r12_poses.py sheet <comfy_output_dir> <out.png> [tag]
  generate options: --only a,b  --tag r12b  --ipa-weight 0.4  --ipa-end 0.6  --cn 1.0  --cn-model <file>
"""

import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SEG = {"head": 70, "torso": 240, "uarm": 130, "farm": 120, "thigh": 215, "shin": 210}
LIMBS = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11),
         (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]
COLORS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
          (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
          (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]

# Angles in degrees, image coordinates: 0 = right, 90 = down, 180 = left, 270 = up.
# Side views face right; R = near limbs, L = far limbs. "front" spreads shoulders and hips.
POSES = {
    "standing": dict(torso=90, head=285, rarm=(95, 95), larm=(85, 85), rleg=(92, 90), lleg=(88, 90),
                     text="standing upright, arms relaxed, side view"),
    "squat": dict(torso=112, head=300, rarm=(5, 5), larm=(8, 8), rleg=(8, 100), lleg=(12, 102),
                  text="performing a bodyweight squat, thighs parallel to the floor, arms forward, side view"),
    "lunge": dict(torso=90, head=280, rarm=(92, 90), larm=(88, 90), rleg=(5, 90), lleg=(118, 172),
                  text="performing a forward lunge, back knee close to the floor, side view"),
    "plank": dict(torso=176, head=350, rarm=(90, 90), larm=(88, 90), rleg=(177, 178), lleg=(176, 178),
                  text="holding a high plank on straight arms, body in a straight line, side view"),
    "pushup": dict(torso=178, head=355, rarm=(125, 55), larm=(122, 58), rleg=(178, 179), lleg=(177, 179),
                   text="doing a push-up in the low position, chest near the floor, side view"),
    "bridge": dict(torso=345, head=260, rarm=(5, 0), larm=(8, 2), rleg=(315, 85), lleg=(318, 88),
                   text="doing a glute bridge lying on the back, hips raised, feet on the floor, side view"),
    "deadlift": dict(torso=148, head=330, rarm=(90, 90), larm=(92, 90), rleg=(80, 96), lleg=(84, 96),
                     text="performing a kettlebell deadlift, hip hinge, flat back, side view"),
    "highknees": dict(torso=90, head=285, rarm=(120, 60), larm=(60, 330), rleg=(0, 90), lleg=(92, 90),
                      text="running high knees, one knee raised to hip height, side view"),
    "toetouch": dict(torso=235, head=100, rarm=(95, 92), larm=(92, 90), rleg=(90, 90), lleg=(91, 90),
                     text="standing forward fold, hands reaching toward the toes, side view"),
    "jumpingjack": dict(front=True, torso=90, head=270, rarm=(225, 235), larm=(315, 305),
                        rleg=(105, 103), lleg=(75, 77),
                        text="doing jumping jacks, arms raised overhead, legs apart, front view"),
}


def _d(a: float, length: float) -> tuple[float, float]:
    return length * math.cos(math.radians(a)), length * math.sin(math.radians(a))


def keypoints(p: dict) -> dict[int, tuple[float, float]]:
    n = (0.0, 0.0)
    front = p.get("front", False)
    tx, ty = _d(p["torso"], SEG["torso"])
    hip = (n[0] + tx, n[1] + ty)
    sh_off, hip_off = (70, 45) if front else (6, 6)
    k: dict[int, tuple[float, float]] = {1: n}
    k[2], k[5] = (n[0] - sh_off, n[1]), (n[0] + sh_off, n[1])
    k[8], k[11] = (hip[0] - hip_off, hip[1]), (hip[0] + hip_off, hip[1])
    for sh, el, wr, (a1, a2) in ((2, 3, 4, p["rarm"]), (5, 6, 7, p["larm"])):
        dx, dy = _d(a1, SEG["uarm"]); k[el] = (k[sh][0] + dx, k[sh][1] + dy)
        dx, dy = _d(a2, SEG["farm"]); k[wr] = (k[el][0] + dx, k[el][1] + dy)
    for hp, kn, an, (a1, a2) in ((8, 9, 10, p["rleg"]), (11, 12, 13, p["lleg"])):
        dx, dy = _d(a1, SEG["thigh"]); k[kn] = (k[hp][0] + dx, k[hp][1] + dy)
        dx, dy = _d(a2, SEG["shin"]); k[an] = (k[kn][0] + dx, k[kn][1] + dy)
    hx, hy = _d(p["head"], SEG["head"])
    k[0] = (n[0] + hx, n[1] + hy)
    side = 0 if front else 1
    for idx, ox in ((14, -12), (15, 12), (16, -28), (17, 28)):
        k[idx] = (k[0][0] + ox * (1 - side) + (-10 if idx in (16, 17) else 4) * side, k[0][1] - 8)
    return k


def draw(k: dict[int, tuple[float, float]]) -> Image.Image:
    xs, ys = [x for x, _ in k.values()], [y for _, y in k.values()]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    s = 0.78 * SIZE / max(w, h)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    pts = {i: ((x - cx) * s + SIZE / 2, (y - cy) * s + SIZE / 2) for i, (x, y) in k.items()}
    img = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, (a, b) in enumerate(LIMBS):
        d.line([pts[a], pts[b]], fill=tuple(int(c * 0.6) for c in COLORS[i]), width=12)
    for i, (x, y) in pts.items():
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=COLORS[i])
    return img


CHAR = ("flat vector illustration, athletic woman with short black ponytail, teal tank top, "
        "dark grey leggings, white sneakers, {t}, full body, plain white background, clean lines")
NEG = "photo, realistic, text, watermark, extra limbs, deformed hands, blurry, cropped"


def workflow(pose_img: str, ref_img: str, text: str, seed: int, prefix: str,
             ipa_weight: float = 0.6, ipa_end: float = 1.0, cn: float = 0.9,
             cn_model: str = "control-lora-openposeXL2-rank256.safetensors") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "sdxl_vae_fp16fix.safetensors"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": CHAR.format(t=text), "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": SIZE, "height": SIZE, "batch_size": 1}},
        "10": {"class_type": "ControlNetLoader",
               "inputs": {"control_net_name": cn_model}},
        "11": {"class_type": "LoadImage", "inputs": {"image": pose_img}},
        "12": {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["3", 0], "negative": ["4", 0], "control_net": ["10", 0], "image": ["11", 0],
            "strength": cn, "start_percent": 0.0, "end_percent": 1.0}},
        "20": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus_sdxl_vit-h.safetensors"}},
        "21": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "22": {"class_type": "LoadImage", "inputs": {"image": ref_img}},
        "23": {"class_type": "IPAdapterAdvanced", "inputs": {
            "model": ["1", 0], "ipadapter": ["20", 0], "image": ["22", 0], "clip_vision": ["21", 0],
            "weight": ipa_weight, "weight_type": "linear", "combine_embeds": "concat",
            "start_at": 0.0, "end_at": ipa_end, "embeds_scaling": "V only"}},
        "6": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 25, "cfg": 6.5, "sampler_name": "dpmpp_2m", "scheduler": "karras",
            "denoise": 1.0, "model": ["23", 0], "positive": ["12", 0], "negative": ["12", 1],
            "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["7", 0]}},
    }


def _post(url: str, wf: dict) -> str:
    req = urllib.request.Request(f"{url}/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:  # noqa: S310 (local spike)
        return json.loads(r.read())["prompt_id"]


def _wait(url: str, pid: str) -> str:
    while True:
        with urllib.request.urlopen(f"{url}/history/{pid}") as r:  # noqa: S310
            h = json.loads(r.read())
        if pid in h:
            return h[pid]["status"].get("status_str", "?")
        time.sleep(1)


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "skeletons":
        out = Path(sys.argv[2])
        for name, p in POSES.items():
            draw(keypoints(p)).save(out / f"r12_pose_{name}.png")
    elif cmd == "generate":
        ref = sys.argv[2]
        def opt(name: str, default: str) -> str:
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

        url = opt("--url", "http://127.0.0.1:8188")
        only = set(opt("--only", ",".join(POSES)).split(","))
        tag = opt("--tag", "r12")
        kw = {"ipa_weight": float(opt("--ipa-weight", "0.6")), "ipa_end": float(opt("--ipa-end", "1.0")),
              "cn": float(opt("--cn", "0.9")),
              "cn_model": opt("--cn-model", "control-lora-openposeXL2-rank256.safetensors")}
        t0 = time.time()
        for i, (name, p) in enumerate(POSES.items()):
            if name not in only:
                continue
            t = time.time()
            st = _wait(url, _post(url, workflow(f"r12_pose_{name}.png", ref, p["text"], 3000 + i,
                                                f"{tag}_{i:02d}_{name}", **kw)))
            print(json.dumps({"pose": name, "status": st, "seconds": round(time.time() - t, 1)}), flush=True)
        print(json.dumps({"total_seconds": round(time.time() - t0, 1)}))
    elif cmd == "sheet":
        src, out = Path(sys.argv[2]), Path(sys.argv[3])
        tag = sys.argv[4] if len(sys.argv) > 4 else "r12"
        files = sorted(src.glob(f"{tag}_[0-9][0-9]_*.png"))[:10]
        cell = 320
        sheet = Image.new("RGB", (cell * 5, cell * ((len(files) + 4) // 5)), "white")
        for i, f in enumerate(files):
            sheet.paste(Image.open(f).convert("RGB").resize((cell, cell)), ((i % 5) * cell, (i // 5) * cell))
        sheet.save(out)


if __name__ == "__main__":
    main()
