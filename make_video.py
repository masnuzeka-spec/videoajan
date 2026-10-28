import json, re, subprocess, sys, time, requests
from urllib.parse import quote

k = json.load(open("konu.json", encoding="utf-8"))

def run(c):
    subprocess.run(c, check=True)

# 1) Ses + altyazı: önce Edge TTS, olmazsa Google gTTS
def ssd(t):
    return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(t*1000)%1000:03d}"

def sure(f):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", f]))

def edge():
    try:
        run(["edge-tts", "--voice", "tr-TR-AhmetNeural", "--text", k["senaryo"],
             "--write-media", "ses.mp3", "--write-subtitles", "alt.vtt"])
        run(["ffmpeg", "-y", "-i", "alt.vtt", "alt.srt"])
        return True
    except Exception as e:
        print("Edge TTS olmadi, gTTS'e geciliyor:", e)
        return False

def gtts():
    run([sys.executable, "-m", "pip", "install", "gTTS"])
    from gtts import gTTS
    cumleler = [c.strip() for c in re.split(r"(?<=[.?!])\s+", k["senaryo"]) if c.strip()]
    t, srt, liste = 0.0, [], []
    for i, c in enumerate(cumleler):
        f = f"c{i}.mp3"
        gTTS(c, lang="tr").save(f)
        d = sure(f)
        srt.append(f"{i+1}\n{ssd(t)} --> {ssd(t+d)}\n{c}\n")
        liste.append(f"file '{f}'")
        t += d
    open("ses_liste.txt", "w").write("\n".join(liste))
    open("alt.srt", "w", encoding="utf-8").write("\n".join(srt))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ses_liste.txt",
         "-c:a", "libmp3lame", "ses.mp3"])

if not edge():
    gtts()
dur = sure("ses.mp3")

# 2) Pollinations ile görsel üret (anahtar gerekmez) + yakınlaşma efekti
STIL = ", cinematic, soft light, no people, no humans, no text, vertical"
sahneler = k["gorseller"]
her = dur / len(sahneler) + 0.2
kare = int(her * 30)
liste = []
for i, q in enumerate(sahneler):
    url = ("https://image.pollinations.ai/prompt/" + quote(q + STIL)
           + f"?width=1080&height=1920&nologo=true&seed={i + 7}")
    img = f"g{i}.jpg"
    for deneme in range(5):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200 and len(r.content) > 5000:
                open(img, "wb").write(r.content)
                break
        except requests.RequestException:
            pass
        time.sleep(10)
    else:
        raise SystemExit(f"Görsel üretilemedi: {q}")
    out = f"s{i}.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", str(her),
         "-vf", f"scale=2160:3840,zoompan=z='min(zoom+0.0006,1.2)':d={kare}:s=1080x1920:fps=30,setsar=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])
    liste.append(f"file '{out}'")
    time.sleep(3)
open("liste.txt", "w").write("\n".join(liste))

# 3) Birleştir: video + ses + altyazı
stil = "FontName=Noto Sans,FontSize=10,Bold=1,Outline=2,Alignment=2,MarginV=60"
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "liste.txt", "-i", "ses.mp3",
     "-vf", f"subtitles=alt.srt:force_style='{stil}'",
     "-map", "0:v", "-map", "1:a", "-t", str(dur + 0.5),
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "video.mp4"])

# 4) Başlık ve açıklamayı kaydet
with open("aciklama.txt", "w", encoding="utf-8") as f:
    f.write(k["baslik"] + "\n\n" + k["aciklama"])
print("Hazır: video.mp4")
