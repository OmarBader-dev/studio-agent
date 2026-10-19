"""Motion: short vertical videos (Reels, TikTok, Stories) made from a design.

The design's own page gets an entrance animation: the photo slowly zooms, then the logo, the headline, the text and
the button come in one after another, and it holds so people can read it. The headless browser captures every frame
and ffmpeg joins them into an MP4 (H.264, 30 fps), the format Instagram, TikTok and Facebook take.

No music is added: when posting, Instagram and TikTok let you pick a track from their own licensed library, which is
both free and allowed. Videos without ffmpeg on the machine are skipped (the reel script is still in the caption pack).
"""
import pathlib
import shutil
import subprocess
import tempfile

from . import design

FPS = 30
# Only `from` keyframes: each element animates from hidden to however the design already shows it, so no style's
# own opacity, rotation or position is overwritten. translate/scale are separate from transform for the same reason.
MOTION_CSS = """
@keyframes m-rise{from{opacity:0;translate:0 5rem}}
@keyframes m-fade{from{opacity:0}}
@keyframes m-pop{0%{opacity:0;scale:.8}70%{opacity:1;scale:1.05}}
@keyframes m-grow{from{scale:0 1}}
@keyframes m-zoom{from{scale:1}to{scale:1.1}}
.bg,.ph,.t1,.t2,.sky,.sun,.rays,.mesh{animation:m-zoom var(--m-dur) linear both;transform-origin:50% 42%}
.s-split .ph{animation:none}
.logo-wrap,.wordmark,.kick,.meta,.num,.inset{animation:m-fade .7s ease-out .2s both}
.eyebrow{animation:m-rise .7s cubic-bezier(.2,.8,.2,1) .45s both}
.hl{animation:m-rise .9s cubic-bezier(.2,.8,.2,1) .75s both}
.medallion,.big,.bigicon{animation:m-pop .8s ease-out 1.1s both}
.bar,.rule{animation:m-grow .6s ease-out 1.45s both;transform-origin:0 50%}
.sub,.bullets{animation:m-rise .8s cubic-bezier(.2,.8,.2,1) 1.6s both}
.cta,.arrow{animation:m-pop .7s ease-out 2.3s both}
.foot,.badge,.deco,.sticker{animation:m-fade .8s ease-out 2.75s both}
"""
STEP_JS = "(t) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } return true; }"


def ffmpeg():
    return shutil.which("ffmpeg")


def available():
    return bool(ffmpeg())


def render(renderer, spec, out_path, seconds=7.5, fps=FPS):
    """Render a design spec as an MP4. Returns the path, or None when ffmpeg isn't installed or it failed."""
    if not available():
        return None
    fmt = spec.get("format", "story")
    w, h = design.FORMATS[fmt]
    page = renderer._page(w, h, design.build(spec))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="motion-"))
    out_path = pathlib.Path(out_path)
    try:
        page.evaluate(design.FIT_JS)                           # sizes are fitted first, exactly like the still
        page.add_style_tag(content=":root{--m-dur:%ss}" % seconds + MOTION_CSS)
        page.wait_for_timeout(50)
        frames = int(seconds * fps)
        for i in range(frames):
            page.evaluate(STEP_JS, i * 1000 / fps)
            page.screenshot(path=str(tmp / f"{i:04d}.jpg"), type="jpeg", quality=92,
                            clip={"x": 0, "y": 0, "width": w, "height": h})
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run = subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "%04d.jpg"),
                              "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                              "-movflags", "+faststart", str(out_path)], capture_output=True, text=True, timeout=300)
        if run.returncode != 0 or not out_path.exists():
            print("Video failed:", run.stderr[-400:])
            return None
        cover = out_path.with_suffix(".jpg")                   # the finished frame, for previews and the cover
        shutil.copy(tmp / f"{frames - 1:04d}.jpg", cover)
        return out_path
    except Exception as e:                                     # a video is a bonus; never stop the run for it
        print("Video failed:", str(e)[:300])
        return None
    finally:
        page.close()
        shutil.rmtree(tmp, ignore_errors=True)
