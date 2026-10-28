import glob, json, os, re, subprocess, sys, textwrap, time
import numpy as np
import requests
from urllib.parse import quote

TEST = os.environ.get("TEST") == "1"
konular = json.load(open("konular.json", encoding="utf-8"))
sira = int(open("sira.txt").read().strip() or 0) if os.path.exists("sira.txt") else 0
k = konular[sira % len(konular)]
print("Konu:", sira % len(konular) + 1, k["baslik"])

def run(c):
    subprocess.run(c, check=True)

def sure(f):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", f]))

def ssd(t):
    return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(t*1000)%1000:03d}"

# ---------- 1) SES + ALTYAZI ----------
def cumleler():
    return [c.strip() for c in re.split(r"(?<=[.?!])\s+", k["senaryo"]) if c.strip()]

def cumle_cumle(uret):
    t, srt, liste = 0.0, [], []
    for i, c in enumerate(cumleler()):
        f = f"c{i}.wav"
        uret(c, f)
        d = sure(f)
        srt.append(f"{i+1}\n{ssd(t)} --> {ssd(t+d+0.15)}\n{c}\n")
        liste.append(f"file '{f}'")
        t += d
    open("ses_liste.txt", "w").write("\n".join(liste))
    open("alt.srt", "w", encoding="utf-8").write("\n".join(srt))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ses_liste.txt",
         "-c:a", "libmp3lame", "ses.mp3"])

def ses_test():
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=220:d=20", "ses.mp3"])
    open("alt.srt", "w", encoding="utf-8").write(
        "1\n00:00:00,000 --> 00:00:05,000\nDeneme altyazi bir.\n\n"
        "2\n00:00:05,000 --> 00:00:12,000\nDeneme altyazi iki, biraz daha uzun bir cumle.\n")

def ses_edge():
    run(["edge-tts", "--voice", "tr-TR-AhmetNeural", "--text", k["senaryo"],
         "--write-media", "ses.mp3", "--write-subtitles", "alt.vtt"])
    run(["ffmpeg", "-y", "-i", "alt.vtt", "alt.srt"])

def ses_piper():
    run([sys.executable, "-m", "pip", "install", "piper-tts"])
    os.makedirs("voices", exist_ok=True)
    run([sys.executable, "-m", "piper.download_voices", "tr_TR-dfki-medium",
         "--data-dir", "voices"])
    def uret(c, f):
        subprocess.run([sys.executable, "-m", "piper", "-m", "tr_TR-dfki-medium",
                        "--data-dir", "voices", "-f", f],
                       input=c.encode("utf-8"), check=True)
    cumle_cumle(uret)

def ses_gtts():
    run([sys.executable, "-m", "pip", "install", "gTTS"])
    from gtts import gTTS
    def uret(c, f):
        gTTS(c, lang="tr").save("tmp.mp3")
        run(["ffmpeg", "-y", "-i", "tmp.mp3", f, "-loglevel", "error"])
    cumle_cumle(uret)

if TEST:
    ses_test()
else:
    for yontem in (ses_edge, ses_piper, ses_gtts):
        try:
            yontem()
            print("Ses yontemi:", yontem.__name__)
            break
        except Exception as e:
            print(yontem.__name__, "olmadi:", e)
    else:
        raise SystemExit("Hicbir ses yontemi calismadi")

dur = sure("ses.mp3")

# ---------- 2) GORSELLER + KAMERA HAREKETI ----------
STIL = ", cinematic, soft warm light, no people, no humans, no text, vertical"
sahneler = k["gorseller"]
n = len(sahneler)
her = dur / n
L = her + 0.5
kare = int(L * 30)

def gorsel(i, q):
    img = f"g{i}.jpg"
    if TEST:
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920",
             "-frames:v", "1", img, "-loglevel", "error"])
        return img
    url = ("https://image.pollinations.ai/prompt/" + quote(q + STIL)
           + f"?width=1080&height=1920&nologo=true&seed={i + 11}")
    for _ in range(5):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200 and len(r.content) > 5000:
                open(img, "wb").write(r.content)
                return img
        except requests.RequestException:
            pass
        time.sleep(10)
    raise SystemExit(f"Gorsel uretilemedi: {q}")

HAREKET = [
    "z='min(zoom+0.0007,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",   # yakinlas
    "z='if(eq(on,0),1.25,max(zoom-0.0007,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",  # uzaklas
    "z=1.25:x='(iw-iw/zoom)*on/%d':y='ih/2-(ih/zoom/2)'" % kare,              # sagdan sola kay
    "z=1.25:x='(iw-iw/zoom)*(1-on/%d)':y='ih/2-(ih/zoom/2)'" % kare,          # soldan saga kay
]
for i, q in enumerate(sahneler):
    img = gorsel(i, q)
    run(["ffmpeg", "-y", "-i", img, "-vf",
         f"scale=1620:2880,zoompan={HAREKET[i % 4]}:d={kare}:s=1080x1920:fps=30,setsar=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", f"s{i}.mp4", "-loglevel", "error"])
    if not TEST:
        time.sleep(3)

# ---------- 3) SULUN ISIK TOZU KATMANI (kodla uretilir) ----------
def toz(sn, out="toz.mp4"):
    W, H, FPS = 540, 960, 30
    nf = int(sn * FPS)
    rng = np.random.default_rng(3)
    P = 70
    x = rng.uniform(0, W, P); y = rng.uniform(0, H, P)
    hiz = rng.uniform(10, 35, P) / FPS
    ph = rng.uniform(0, 6.28, P); boy = rng.integers(0, 3, P)
    spr = []
    for r in (3, 5, 8):
        yy, xx = np.mgrid[-r:r+1, -r:r+1]
        spr.append(np.exp(-(xx**2 + yy**2) / (2 * (r / 2.2) ** 2)).astype(np.float32))
    renk = np.array([255, 205, 130], np.float32) / 255
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", out,
         "-loglevel", "error"], stdin=subprocess.PIPE)
    for f in range(nf):
        fr = np.zeros((H, W, 3), np.float32)
        for j in range(P):
            xi = int(x[j] + 10 * np.sin(f / 40 + ph[j])) % W
            yi = int(y[j] - hiz[j] * f) % H
            a = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(f / 22 + ph[j]))
            s = spr[boy[j]]; r = s.shape[0] // 2
            y0, y1 = max(0, yi - r), min(H, yi + r + 1)
            x0, x1 = max(0, xi - r), min(W, xi + r + 1)
            sub = s[y0 - (yi - r):y1 - (yi - r), x0 - (xi - r):x1 - (xi - r)]
            fr[y0:y1, x0:x1] += sub[:, :, None] * renk * a
        p.stdin.write((np.clip(fr, 0, 1) * 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()

toz(dur + 2)

# ---------- 4) BIRLESTIR: gecis + toz + baslik + kaynak + altyazi ----------
fontlar = (glob.glob("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf")
           + glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True))
font = fontlar[0]
open("baslik.txt", "w", encoding="utf-8").write(textwrap.fill(k["baslik"], 20))
open("kaynak.txt", "w", encoding="utf-8").write(
    textwrap.fill("Kaynak: " + k["kaynak"], 32))

girdi = []
for i in range(n):
    girdi += ["-i", f"s{i}.mp4"]
girdi += ["-i", "toz.mp4", "-i", "ses.mp3"]

f = []
onceki = "0:v"
for i in range(1, n):
    f.append(f"[{onceki}][{i}:v]xfade=transition=fade:duration=0.5:offset={i*her:.3f}[x{i}]")
    onceki = f"x{i}"
f.append(f"[{n}:v]scale=1080:1920,format=gbrp[d]")
f.append(f"[{onceki}]format=gbrp[b]")
f.append("[b][d]blend=all_mode=screen:all_opacity=0.75,format=yuv420p,vignette=PI/5[bl]")
ba = "if(lt(t,0.3),0,if(lt(t,1),(t-0.3)/0.7,if(lt(t,3),1,max(0,(3.6-t)/0.6))))"
ka = f"if(lt(t,{dur-4:.2f}),0,min(1,(t-{dur-4:.2f})/0.6))"
stil = "FontName=Noto Sans,FontSize=10,Bold=1,Outline=2,Alignment=2,MarginV=60"
f.append(
    f"[bl]drawtext=fontfile={font}:textfile=baslik.txt:fontsize=64:fontcolor=white"
    f":shadowcolor=black:shadowx=3:shadowy=3:x=(w-text_w)/2:y=h*0.14:alpha='{ba}'[t1]")
f.append(
    f"[t1]drawtext=fontfile={font}:textfile=kaynak.txt:fontsize=38:fontcolor=white"
    f":shadowcolor=black:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h*0.07:alpha='{ka}'[t2]")
f.append(f"[t2]subtitles=alt.srt:force_style='{stil}'[v]")

run(["ffmpeg", "-y"] + girdi + ["-filter_complex", ";".join(f),
     "-map", "[v]", "-map", f"{n+1}:a", "-t", f"{dur+0.5:.2f}",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "video.mp4",
     "-loglevel", "error"])

with open("aciklama.txt", "w", encoding="utf-8") as fa:
    fa.write(k["baslik"] + "\n\n" + k["aciklama"] + "\n\nKaynak: " + k["kaynak"])

if not TEST:
    open("sira.txt", "w").write(str((sira + 1) % len(konular)))
print("Hazir: video.mp4")
