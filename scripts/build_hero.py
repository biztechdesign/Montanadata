"""Build a smooth, seamlessly looping hero montage from downloaded Freepik clips.

Usage:
    python scripts/build_hero.py v1     # -> img/hero-fiber.mp4 (+ -sm, poster)
    python scripts/build_hero.py v2     # -> img/hero-v2.mp4    (+ -sm, poster)

Smoothness measures:
  * every clip is motion-interpolated to a common 30 fps (no duplicated frames)
  * clean 1.5 s crossfades between clips (not ffmpeg's grainy 'dissolve')
  * the last clip crossfades back into the opening clip, and the montage starts
    where that dissolve ends, so the loop point is invisible
"""
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.gettempdir()
FPS = 30
XF = 1.5          # crossfade length (s)
LOOP = 1.8        # how much of clip A is reused for the loop seam (s); must exceed XF

# (freepik id, in, out) — out-in is the clip's on-screen length before dissolves
SEQ = {
    "v1": [("8411209", 0.0, 3.6), ("9758233", 0.8, 4.4), ("7269630", 2.0, 5.6), ("6499576", 0.0, 6.8)],
    "v2": [("7084088", 0.0, 3.6), ("8534221", 1.0, 4.6), ("3883272", 0.0, 3.8), ("6535397", 0.0, 6.8)],
}
OUT = {"v1": "hero-fiber", "v2": "hero-v2"}


def src(vid):
    p = os.path.join(TMP, "freepik-%s.mp4" % vid)
    if not os.path.exists(p):
        sys.exit("missing %s — run: python scripts/freepik_hero.py get %s" % (p, vid))
    return p


def run(args):
    print("  $ ffmpeg ...", args[-1])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y"] + args)


def main(key):
    seq = SEQ[key]
    name = OUT[key]
    inputs, chains, labels = [], [], []
    # clip A is split: the first LOOP seconds go to the tail for the seam, the
    # montage itself starts at A[in+LOOP]
    for i, (vid, t0, t1) in enumerate(seq):
        inputs += ["-i", src(vid)]
        start = t0 + LOOP if i == 0 else t0
        chains.append(
            "[%d:v]trim=%.3f:%.3f,setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,"
            "minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,format=yuv420p[c%d]"
            % (i, start, t1, FPS, i))
        labels.append("c%d" % i)
    # tail = opening of clip A, dissolved in at the end for the loop seam
    a_vid, a0, _ = seq[0]
    chains.append(
        "[0:v]trim=%.3f:%.3f,setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,"
        "minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,format=yuv420p[tail]"
        % (a0, a0 + LOOP + XF, FPS))
    labels.append("tail")

    # chain the dissolves; offset accumulates (len_so_far - XF)
    lens = [(t1 - (t0 + LOOP if i == 0 else t0)) for i, (v, t0, t1) in enumerate(seq)] + [LOOP + XF]
    cur, total = labels[0], lens[0]
    for i in range(1, len(labels)):
        off = total - XF
        nxt = "x%d" % i
        chains.append("[%s][%s]xfade=transition=fade:duration=%.3f:offset=%.3f[%s]" % (cur, labels[i], XF, off, nxt))
        cur, total = nxt, total + lens[i] - XF
    # cut the tail so the final frame == first frame (A at in+LOOP)
    # composite time of tail-local LOOP is (total - XF); cutting there makes the
    # final frame identical to the first frame
    chains.append("[%s]trim=0:%.3f,setpts=PTS-STARTPTS,format=yuv420p[v]" % (cur, total - XF))

    big = os.path.join(ROOT, "img", name + ".mp4")
    sm = os.path.join(ROOT, "img", name + "-sm.mp4")
    poster = os.path.join(ROOT, "img", ("hero-poster-fiber.jpg" if key == "v1" else "hero-poster-v2.jpg"))
    run(inputs + ["-filter_complex", ";".join(chains), "-map", "[v]", "-an", "-r", str(FPS),
                  "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-g", "60", "-movflags", "+faststart", big])
    run(["-i", big, "-vf", "scale=1280:-2", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "26",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", sm])
    run(["-ss", "0.2", "-i", big, "-frames:v", "1", "-q:v", "3", poster])
    print("done:", big, "(%.1fs)" % (total - XF))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SEQ:
        sys.exit(__doc__)
    main(sys.argv[1])
