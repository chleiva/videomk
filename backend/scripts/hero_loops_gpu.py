#!/usr/bin/env python3
"""Render the 3D hero background loops (blender_hero_loops.py) on ONE short-lived GPU instance, through the GPU lab and its guardrails. docs/HERO_LOOPS_3D.md.

This adds nothing to the guardrails of gpu_lab.py, it only reuses them (one instance, QA only, eu-north-1, shutdown timer at boot, terminate on shutdown, outside
backstop, no inbound port, disk deleted on termination). On top: the instance and its disk also carry the tag task=videomk-hero3d, and the boot script starts
the work by itself, so no minute of the paid hour waits for a person:
  boot: install Blender 4.2 LTS + ffmpeg, render the low-cost TEST frames (720p, one frame per look) and upload them, then work through the job queue.
  queue: one small file per loop in S3 (lab/avatars/hero3d/queue/NN_name.job = "name palette mode seed density"); a finished loop is encoded (4K master,
         1080p with a keyframe every second for the engine, poster) and uploaded at once (lab/avatars/hero3d/out/name/), while the next loop renders.
The instance may only touch lab/avatars/* (the lab role); `publish` copies the finished files to backgrounds/loops/ with the operator's own credentials.

  hero_loops_gpu.py up [--type g5.xlarge] [--minutes 60]       upload the inputs, start the instance (prints the worst-case cost first)
  hero_loops_gpu.py job 10_ember "ember-dark ember dark 23 1.0"   add a loop to the queue (also works before `up`)
  hero_loops_gpu.py status                                      the instance's own status file (frames done, GPU use, log tails)
  hero_loops_gpu.py publish index.json name=id [name=id ...]    copy out/name/* to backgrounds/loops/id/ and write the index
  gpu_lab.py run '...' / status / down                          everything else (shell on the instance, cost so far, terminate)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu_lab as lab  # noqa: E402

TASK_TAG = {"Key": "task", "Value": "videomk-hero3d"}
WORK = lab.LAB_PREFIX + "hero3d/"            # inside the only prefix the lab role may use
BUCKET_REGION = "eu-west-1"
PUBLISH_PREFIX = "backgrounds/loops/"
BLENDER_URL = "https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz"
RENDER_ARGS = "--res 3840x2160 --seconds 10 --fps 15 --samples 32 --device OPTIX --denoiser OPTIX"   # the settings of the first (brand dark) loop
# name palette mode seed density: one 720p frame each (0.8 s on an A10G), looked at before any full loop is paid for. Light mode needs density 12 to 20:
# at 1 to 4 (the first test sheet of 2026-11-27) it is an almost blank page.
TESTS = """ember-dark ember dark 31 1.0
aurora-dark aurora dark 11 1.0
brand-light brand light 7 20
brand-light-d12 brand light 7 12
aurora-light aurora light 11 20
ember-light ember light 31 20
"""

BOOT = r"""#!/bin/bash
# runs as root from user data, after the shutdown timer has been set
export HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
B=s3://__BUCKET__/__WORK__; R="--region __REGION__"
cd /lab/hero3d && mkdir -p queue done tests
date -u +"boot %H:%M:%S" > times.txt
( while true; do bash status.sh > status.txt 2>&1; aws s3 cp --quiet status.txt $B/out/status.txt $R; sleep 20; done ) &
# the package lists of a fresh image are stale: without the update the X libraries Blender links against are not found
( export DEBIAN_FRONTEND=noninteractive; apt-get -o DPkg::Lock::Timeout=900 update -qq > apt.log 2>&1; apt-get -o DPkg::Lock::Timeout=900 install -y ffmpeg libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libxkbcommon0 libsm6 libegl1 >> apt.log 2>&1; echo "apt exit $?" >> times.txt ) &
curl -sSfL -o blender.tar.xz __BLENDER__ && mkdir -p blender && tar -xJf blender.tar.xz -C blender --strip-components=1 && rm blender.tar.xz
for i in $(seq 90); do ./blender/blender -b --version > blender_version.txt 2>&1 && break; sleep 10; done
date -u +"blender ready %H:%M:%S" >> times.txt
# the brand loop already exists as a 4K master: only its engine 1080p and poster are made here (CPU, in the background)
( aws s3 cp --quiet s3://__BUCKET__/lab/avatars/hero/dark_4k.mp4 brand-dark_4k.mp4 $R; for i in $(seq 120); do command -v ffmpeg >/dev/null && break; sleep 10; done; bash encode.sh brand-dark small > enc_brand-dark.log 2>&1 ) &
while read NAME PAL MODE SEED DENS; do
  [ -z "$NAME" ] && continue
  ./blender/blender -b -P blender_hero_loops.py -- --out tests/$NAME --palette $PAL --mode $MODE --seed $SEED --density $DENS --res 1280x720 --seconds 10 --fps 15 \
     --samples 32 --device OPTIX --denoiser OPTIX --format JPEG --start 60 --end 60 < /dev/null > tests/$NAME.log 2>&1
  aws s3 cp --quiet tests/$NAME/f_0060.jpg $B/out/tests/$NAME.jpg $R
done < tests.txt
date -u +"tests done %H:%M:%S" >> times.txt
while true; do
  aws s3 sync --quiet $B/queue/ queue/ $R
  job=""
  for j in $(ls queue/*.job 2>/dev/null | sort); do n=$(basename $j .job); [ -e done/$n ] || { job=$j; break; }; done
  [ -z "$job" ] && { sleep 10; continue; }
  n=$(basename $job .job); read NAME PAL MODE SEED DENS < $job; touch done/$n
  date -u +"$NAME render start %H:%M:%S" >> times.txt
  ./blender/blender -b -P blender_hero_loops.py -- --out $NAME --palette $PAL --mode $MODE --seed $SEED --density $DENS __RENDER_ARGS__ < /dev/null > $NAME.log 2>&1
  date -u +"$NAME render end %H:%M:%S ($(ls $NAME/f_*.png 2>/dev/null | wc -l) frames)" >> times.txt
  if [ "$(ls $NAME/f_*.png 2>/dev/null | wc -l)" -ge 150 ]; then ( for i in $(seq 120); do command -v ffmpeg >/dev/null && break; sleep 10; done; bash encode.sh $NAME full > enc_$NAME.log 2>&1 ) & fi
done
"""

ENCODE = r"""#!/bin/bash
# encode.sh NAME full|small : frames NAME/f_0001..0150.png (15 fps, 10 s) -> NAME_4k.mp4 (30 fps), then the engine 1080p (keyframe every second) and the poster
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
B=s3://__BUCKET__/__WORK__; R="--region __REGION__"
cd /lab/hero3d
N=$1
if [ "$2" = full ]; then
  cp $N/f_0001.png $N/f_0151.png      # the loop closes on frame 1: the blend of the last interval needs it
  ffmpeg -v error -y -framerate 15 -i $N/f_%04d.png -sws_dither ed \
    -vf "framerate=fps=30:interp_start=0:interp_end=255:scene=100,noise=alls=1:allf=u,format=yuv420p" \
    -frames:v 300 -c:v libx264 -preset slow -crf 15 -profile:v high -level 5.1 -movflags +faststart -an ${N}_4k.mp4
  aws s3 cp --quiet ${N}_4k.mp4 $B/out/$N/4k.mp4 $R
  aws s3 cp --quiet $N.log $B/out/$N/render.log $R
fi
# the 1080p the engine plays: crf 18, quantiser biased to the dark areas (aq-mode 3) and one more level of grain AFTER the reduction (the reduction averages the
# master's grain away). Measured on the brand loop: crf 22 without this left 109 one-level stairs in 104 sampled rows of dark gradient, this leaves 4.
ffmpeg -v error -y -i ${N}_4k.mp4 -vf "scale=1920:1080:flags=lanczos,noise=alls=2:allf=t+u,format=yuv420p" -c:v libx264 -preset medium -crf 18 -g 30 -keyint_min 30 \
  -sc_threshold 0 -x264-params aq-mode=3:deblock=-2,-2 -pix_fmt yuv420p -movflags +faststart -an ${N}_1080.mp4
ffmpeg -v error -y -i ${N}_1080.mp4 -frames:v 1 -q:v 3 ${N}_poster.jpg
aws s3 cp --quiet ${N}_1080.mp4 $B/out/$N/1080.mp4 $R
aws s3 cp --quiet ${N}_poster.jpg $B/out/$N/poster.jpg $R
date -u +"$N encoded and uploaded %H:%M:%S" >> times.txt
ls -la ${N}_4k.mp4 ${N}_1080.mp4 ${N}_poster.jpg
"""

STATUS = r"""date -u
cat times.txt 2>/dev/null
nvidia-smi --query-gpu=name,utilization.gpu,memory.used --format=csv,noheader 2>/dev/null
for d in */; do c=$(ls $d 2>/dev/null | grep -c '^f_.*png$'); [ "$c" -gt 0 ] && echo "$d $c frames"; done
ls done queue 2>/dev/null | tr '\n' ' '; echo
for f in *.log; do echo "--- $f"; tail -n 3 $f; done
df -h /lab | tail -1
"""


def _fill(text: str) -> str:
    return (text.replace("__BUCKET__", lab.BUCKET).replace("__WORK__", WORK.rstrip("/")).replace("__REGION__", BUCKET_REGION)
            .replace("__BLENDER__", BLENDER_URL).replace("__RENDER_ARGS__", RENDER_ARGS))


def s3(s):
    return s.client("s3", region_name=BUCKET_REGION)


def cmd_up(s, itype: str, minutes: int):
    c = s3(s)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "blender_hero_loops.py"), "rb") as f:
        c.put_object(Bucket=lab.BUCKET, Key=WORK + "in/blender_hero_loops.py", Body=f.read())
    for name, body in (("boot.sh", _fill(BOOT)), ("encode.sh", _fill(ENCODE)), ("status.sh", STATUS), ("tests.txt", TESTS)):
        c.put_object(Bucket=lab.BUCKET, Key=WORK + "in/" + name, Body=body.encode())
    base = lab.user_data
    start = (f"export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; mkdir -p /lab/hero3d && aws s3 cp s3://{lab.BUCKET}/{WORK}in/ /lab/hero3d/ --recursive --region {BUCKET_REGION} "
             "&& nohup bash /lab/hero3d/boot.sh > /lab/hero3d/boot.log 2>&1 &\n")
    lab.user_data = lambda m: base(m) + start
    lab.cmd_up(s, itype, minutes)          # every refusal and guardrail of the lab applies
    ec2 = s.client("ec2")
    for i in lab.lab_instances(ec2):
        vols = [m["Ebs"]["VolumeId"] for m in i.get("BlockDeviceMappings", []) if "Ebs" in m]
        ec2.create_tags(Resources=[i["InstanceId"]] + vols, Tags=[TASK_TAG, {"Key": "Name", "Value": "videomk-hero3d"}])
        print("tagged", i["InstanceId"], vols, "task=videomk-hero3d")


def cmd_job(s, name: str, line: str):
    parts = line.split()
    if len(parts) != 5 or parts[1] not in ("brand", "ember", "aurora") or parts[2] not in ("dark", "light"):
        sys.exit('a job is "name palette mode seed density"')
    int(parts[3]), float(parts[4])
    s3(s).put_object(Bucket=lab.BUCKET, Key=f"{WORK}queue/{name}.job", Body=(line.strip() + "\n").encode())
    print("queued", name, "->", line)


def cmd_status(s):
    try:
        print(s3(s).get_object(Bucket=lab.BUCKET, Key=WORK + "out/status.txt")["Body"].read().decode())
    except Exception as e:
        print("no status yet:", type(e).__name__)


def cmd_publish(s, index_path: str, pairs):
    """Server-side copies (nothing passes through this computer), then the index. The index file is written by hand: it carries the judgement (mood, text colour)."""
    c = s3(s)
    with open(index_path) as f:
        index = json.load(f)
    ids = {lp["id"] for lp in index["loops"]}
    types = {"1080.mp4": "video/mp4", "4k.mp4": "video/mp4", "poster.jpg": "image/jpeg"}
    for pair in pairs:
        name, lid = pair.split("=")
        if lid not in ids:
            sys.exit(f"{lid} is not in the index")
        for fn, ct in types.items():
            c.copy_object(Bucket=lab.BUCKET, Key=f"{PUBLISH_PREFIX}{lid}/{fn}", CopySource={"Bucket": lab.BUCKET, "Key": f"{WORK}out/{name}/{fn}"},
                          ContentType=ct, MetadataDirective="REPLACE", CacheControl="max-age=31536000, immutable")
            print("copied", f"s3://{lab.BUCKET}/{PUBLISH_PREFIX}{lid}/{fn}")
    c.put_object(Bucket=lab.BUCKET, Key=PUBLISH_PREFIX + "index.json", Body=json.dumps(index, indent=1).encode(), ContentType="application/json")
    print("wrote", f"s3://{lab.BUCKET}/{PUBLISH_PREFIX}index.json", len(index["loops"]), "loops")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("up"); up.add_argument("--type", default="g5.xlarge"); up.add_argument("--minutes", type=int, default=60)
    job = sub.add_parser("job"); job.add_argument("name"); job.add_argument("line")
    sub.add_parser("status")
    pub = sub.add_parser("publish"); pub.add_argument("index"); pub.add_argument("pairs", nargs="+")
    a = ap.parse_args()
    s = lab.session()
    {"up": lambda: cmd_up(s, a.type, a.minutes), "job": lambda: cmd_job(s, a.name, a.line), "status": lambda: cmd_status(s),
     "publish": lambda: cmd_publish(s, a.index, a.pairs)}[a.cmd]()


if __name__ == "__main__":
    main()
