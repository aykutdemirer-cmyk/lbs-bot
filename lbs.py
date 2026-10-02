"""Last Ball Standing - otomatik video üretici.

Kullanım:
  python lbs.py                # rastgele bir bölüm üretir, out/ klasörüne yazar
  python lbs.py --send         # üretir ve Telegram'a gönderir (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID gerekir)
  python lbs.py --seed 123     # aynı videoyu tekrar üretmek için
"""
import argparse, colorsys, json, math, os, random, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
W, H, FPS = 1080, 1920, 30
CX, CY, R, BR = 540, 1000, 440, 40
SUB, G, INTRO = 4, 900.0, 30

NAMES = {'tr':'Turkey','us':'USA','de':'Germany','jp':'Japan','br':'Brazil','fr':'France','gb':'UK','it':'Italy',
 'es':'Spain','kr':'S. Korea','cn':'China','in':'India','ru':'Russia','ca':'Canada','mx':'Mexico','az':'Azerbaijan',
 'nl':'Netherlands','sa':'Saudi Arabia','ar':'Argentina','pl':'Poland','pt':'Portugal','se':'Sweden','gr':'Greece',
 'eg':'Egypt','id':'Indonesia','au':'Australia','za':'South Africa','ng':'Nigeria','ua':'Ukraine','ch':'Switzerland',
 'be':'Belgium','at':'Austria','no':'Norway','dk':'Denmark','fi':'Finland','ie':'Ireland','ma':'Morocco',
 'pk':'Pakistan','co':'Colombia','cl':'Chile'}
THEMES = {  # başlık ve kadro varyasyonları
 'world':  ('World', list(NAMES)),
 'europe': ('Europe', ['de','fr','gb','it','es','nl','pl','pt','se','gr','ua','ch','be','at','no','dk','fi','ie','tr']),
 'giants': ('Biggest Economies', ['us','cn','de','jp','in','gb','fr','it','br','ca','ru','mx','kr','au','es','id','nl','sa','tr','ch']),
 'football':('Football Nations', ['br','ar','fr','de','es','it','gb','pt','nl','be','mx','co','cl','ma','tr','us','jp','kr','ng','eg']),
}
TITLES = ['{n} Countries Enter, Only 1 Survives 🏆', 'Which Country Survives? {n} Balls, 1 Winner 🌍',
          'Last Ball Standing: {theme} Edition 🏆', '{n} Countries Fight For The Crown 👑',
          'Only One Country Can Escape Elimination 😱', 'Can Your Country Win? {theme} Battle 🌍']

# ---------------------------------------------------------------- simülasyon
def simulate(seed, codes, max_t=70):
    rng = random.Random(seed); n = len(codes)
    pos = []
    while len(pos) < n:
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(0, R - BR - 10)
        p = np.array([CX + r * math.cos(a), CY + r * math.sin(a)])
        if all(np.linalg.norm(p - q) > 2 * BR + 4 for q in pos): pos.append(p)
    pos = np.array(pos); vel = np.array([[rng.uniform(-500, 500), rng.uniform(-500, 200)] for _ in range(n)])
    alive = np.ones(n, bool); out = np.zeros(n, bool)
    gap_ang, gap_w0 = rng.uniform(0, 2 * math.pi), math.radians(rng.uniform(22, 30))
    omega = math.radians(rng.uniform(55, 90)) * rng.choice([-1, 1])
    frames, events, order = [], [], []
    dt = 1 / FPS / SUB; f = 0; last_elim = 0; fin = None
    while True:
        gap_w = gap_w0 + math.radians(4) * max(0, (f - last_elim) / FPS - 4)
        bounces = []
        if f >= INTRO and fin is None:
            for _ in range(SUB):
                vel[:, 1] += G * dt; pos += vel * dt
                idx = np.where(alive & ~out)[0]
                for ii in range(len(idx)):
                    for jj in range(ii + 1, len(idx)):
                        i, j = idx[ii], idx[jj]; d = pos[j] - pos[i]; dist = math.hypot(*d)
                        if 0 < dist < 2 * BR:
                            nr = d / dist; ov = 2 * BR - dist; pos[i] -= nr * ov / 2; pos[j] += nr * ov / 2
                            rv = np.dot(vel[j] - vel[i], nr)
                            if rv < 0: vel[i] += rv * nr; vel[j] -= rv * nr
                for i in idx:
                    d = pos[i] - (CX, CY); dist = math.hypot(*d)
                    if dist > R - BR:
                        ang = math.atan2(d[1], d[0]) % (2 * math.pi)
                        if abs((ang - gap_ang + math.pi) % (2 * math.pi) - math.pi) < gap_w / 2 and dist < R + BR:
                            if dist > R + BR * .2: out[i] = True
                            continue
                        if dist >= R + BR * .2: continue
                        nr = d / dist; pos[i] = (CX, CY) + nr * (R - BR); vn = np.dot(vel[i], nr)
                        if vn > 0:
                            vel[i] -= 2 * vn * nr; sp = math.hypot(*vel[i])
                            if sp < 900: vel[i] *= 900 / sp
                            if sp > 1500: vel[i] *= 1500 / sp
                            bounces.append(int(i))
                gap_ang = (gap_ang + omega * dt) % (2 * math.pi)
            for i in range(n):
                if alive[i] and out[i]:
                    alive[i] = False; order.append(i); last_elim = f; events.append((f, 'elim', i))
            if alive.sum() == 1:
                fin = f; events.append((f, 'win', int(np.where(alive)[0][0])))
        elif fin is not None:
            w = int(np.where(alive)[0][0]); pos[w] += ((CX, CY) - pos[w]) * 0.08
            for i in range(n):
                if out[i]: vel[i, 1] += G / FPS; pos[i] += vel[i] / FPS
        frames.append((pos.copy(), alive.copy(), out.copy(), gap_ang, gap_w, sorted(set(bounces))))
        f += 1
        if fin is not None and f - fin > 4.5 * FPS: break
        if f / FPS > max_t: return None
    return frames, events, order, fin

def pick_episode(seed):
    rng = random.Random(seed)
    theme = rng.choice(list(THEMES)); tname, pool = THEMES[theme]
    n = rng.choice([12, 14, 16, 16, 18])
    codes = rng.sample(pool, min(n, len(pool)))
    for k in range(200):  # 20–40 sn arası, heyecanlı bir sonuç ara
        s = seed * 1000 + k
        r = simulate(s, codes)
        if r and 18 * FPS <= r[3] <= 40 * FPS:
            return dict(seed=seed, sim_seed=s, theme=tname, codes=codes, hue=rng.random()), r
    raise RuntimeError('uygun simülasyon bulunamadı')

# ---------------------------------------------------------------- çizim
def _download(url, dest):
    import urllib.request
    dest.parent.mkdir(exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r: dest.write_bytes(r.read())

def font(w, s):
    p = ROOT / 'fonts' / f'Inter-{w}.otf'
    if p.exists(): return ImageFont.truetype(str(p), s)
    v = ROOT / 'fonts' / 'Inter-var.ttf'
    if not v.exists():
        _download('https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf', v)
    f = ImageFont.truetype(str(v), s); f.set_variation_by_axes([32, {'Black': 900, 'Bold': 700}[w]]); return f

def flag_png(code):
    p = ROOT / 'flags' / f'{code}.png'
    if not p.exists():
        import cairosvg
        svg = ROOT / 'flags' / f'{code}.svg'
        _download(f'https://raw.githubusercontent.com/lipis/flag-icons/main/flags/1x1/{code}.svg', svg)
        cairosvg.svg2png(url=str(svg), write_to=str(p), output_width=200, output_height=200); svg.unlink()
    return p
fH1, fH2, fCnt = font('Black', 80), font('Black', 52), font('Black', 44)
fToast, fSmall, fWin, fWin2 = font('Black', 50), font('Bold', 26), font('Black', 110), font('Black', 48)

def circ_flag(code, d):
    im = Image.open(flag_png(code)).convert('RGBA').resize((d, d), Image.LANCZOS)
    m = Image.new('L', (d * 4, d * 4), 0); ImageDraw.Draw(m).ellipse([0, 0, d * 4 - 1, d * 4 - 1], fill=255)
    im.putalpha(m.resize((d, d), Image.LANCZOS)); return im

_BALL = {}
def ball_img(code, d):
    if (code, d) not in _BALL:
        pad = 8; im = Image.new('RGBA', (d + pad * 2, d + pad * 2), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        dr.ellipse([pad - 5, pad - 5, pad + d + 4, pad + d + 4], fill=(255, 255, 255, 255))
        im.alpha_composite(circ_flag(code, d), (pad, pad))
        hl = Image.new('RGBA', im.size, (0, 0, 0, 0))
        ImageDraw.Draw(hl).ellipse([pad + d * .18, pad + d * .1, pad + d * .55, pad + d * .35], fill=(255, 255, 255, 70))
        im.alpha_composite(hl.filter(ImageFilter.GaussianBlur(3))); _BALL[(code, d)] = im
    return _BALL[(code, d)]

def text_c(dr, xy, s, fnt, fill, stroke=6):
    dr.text(xy, s, font=fnt, fill=fill, anchor='mm', stroke_width=stroke, stroke_fill=(0, 0, 0))

def eyes(dr, x, y, r, vx, vy, scared=False):
    sp = math.hypot(vx, vy) + 1e-6; ux, uy = vx / sp, vy / sp
    for sx in (-1, 1):
        ex, ey = x + sx * r * .32, y - r * .12; ew, eh = r * .26, r * .32
        dr.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill='white', outline=(0, 0, 0), width=3)
        pr = r * (.09 if scared else .13); px, py = ex + ux * ew * .45, ey + uy * eh * .45
        dr.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(0, 0, 0))

def render(ep, sim, out_path):
    frames, events, order, ff = sim
    C = ep['codes']; N = len(C); hue0 = ep['hue']
    yy, xx = np.mgrid[0:H, 0:W]; d = np.sqrt((xx - CX) ** 2 + (yy - CY) ** 2) / 1000
    r, g, b = colorsys.hsv_to_rgb((hue0 + .7) % 1, .7, .55)
    bg = np.zeros((H, W, 3), np.float32) + (12, 10, 30) + np.clip(1 - d, 0, 1)[..., None] ** 2 * np.array([r, g, b]) * 160
    BG = Image.fromarray(np.clip(bg, 0, 255).astype('uint8'))
    small = {c: circ_flag(c, 56) for c in C}
    elim_at = {e[2]: e[0] for e in events if e[1] == 'elim'}
    place = {i: N - k for k, i in enumerate(order)}
    winner = [e[2] for e in events if e[1] == 'win'][0]; place[winner] = 1
    rng = random.Random(ep['seed'])
    conf = [[rng.uniform(0, W), rng.uniform(-600, -20), rng.uniform(-120, 120), rng.uniform(250, 520),
             rng.choice([(255, 196, 0), (255, 70, 90), (80, 200, 255), (120, 255, 150), (255, 255, 255)]), rng.uniform(0, 6)] for _ in range(160)]
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium',
                          str(out_path)], stdin=subprocess.PIPE)
    prev = frames[0][0]; flash = 0; bounce_log = []
    for f, (pos, alive, out, gap_ang, gap_w, bounces) in enumerate(frames):
        vel = (pos - prev) * FPS; prev = pos
        if bounces: bounce_log.append(f); flash = 1.0
        flash *= .8
        rr, gg, bb = colorsys.hsv_to_rgb((hue0 + f / 300) % 1, .75, 1); col = (int(rr * 255), int(gg * 255), int(bb * 255))
        # halka + parlama
        s = 4; gl = Image.new('RGB', (W // s, H // s)); gd = ImageDraw.Draw(gl)
        a0 = math.degrees(gap_ang + gap_w / 2); a1 = math.degrees(gap_ang - gap_w / 2) + 360
        gd.arc([(CX - R - 8) / s, (CY - R - 8) / s, (CX + R + 8) / s, (CY + R + 8) / s], a0, a1, fill=col, width=int(10 + 8 * flash))
        gl = gl.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        im = Image.fromarray(np.clip(np.asarray(BG, np.int16) + np.asarray(gl, np.int16) * (1.1 + flash), 0, 255).astype('uint8'))
        dr = ImageDraw.Draw(im, 'RGBA')
        dr.arc([CX - R - 8, CY - R - 8, CX + R + 8, CY + R + 8], a0, a1, fill=col, width=16)
        dr.arc([CX - R - 3, CY - R - 3, CX + R + 3, CY + R + 3], a0, a1, fill=(255, 255, 255), width=4)
        done = f >= ff
        text_c(dr, (W / 2, 150), 'LAST ONE WINS!', fH1, (255, 255, 255), 7)
        text_c(dr, (W / 2, 245), 'Which country survives?', fH2, (255, 196, 0), 5)
        left = int(alive.sum())
        dr.rounded_rectangle([W / 2 - 150, 315, W / 2 + 150, 385], radius=35, fill=(255, 255, 255, 30), outline=(255, 255, 255, 120), width=3)
        text_c(dr, (W / 2, 350), f'LEFT: {left}', fCnt, (255, 255, 255), 0)
        for i in [i for i in range(N) if out[i]] + [i for i in range(N) if alive[i]]:
            x, y = pos[i]
            if y > H + 100: continue
            dsz = BR * 2
            if done and i == winner:
                k = min(1, (f - ff) / 25); dsz = int(BR * 2 * (1 + 2.2 * (k * k * (3 - 2 * k))))
            if i in bounces and not done: dsz = int(dsz * 1.12)
            bi = ball_img(C[i], dsz); im.paste(bi, (int(x - bi.width / 2), int(y - bi.height / 2)), bi)
            if not (done and i != winner): eyes(dr, x, y, dsz / 2, vel[i][0], vel[i][1], scared=out[i])
            if alive[i] and left <= 4 and not done: text_c(dr, (x, y + BR + 26), NAMES[C[i]], fSmall, (255, 255, 255), 4)
        ty = 1590
        dr.text((W / 2, ty - 18), 'ELIMINATED', font=fSmall, fill=(255, 255, 255, 150), anchor='mm')
        cols = 8 if N <= 16 else 9; step = (W - 120) / cols
        for k, i in enumerate(order):
            if elim_at[i] > f: break
            gx = 60 + step / 2 + (k % cols) * step; gy = ty + 40 + (k // cols) * 108
            sm = small[C[i]]; gimg = Image.blend(Image.new('RGBA', sm.size, (12, 10, 30, 255)), sm, .55); gimg.putalpha(sm.getchannel('A'))
            im.paste(gimg, (int(gx - 28), int(gy - 20)), gimg)
            text_c(dr, (gx, gy + 56), f'{place[i]}.', fSmall, (255, 120, 120), 3)
        for i in order:
            t0 = elim_at[i]
            if 0 <= f - t0 < 32:
                k = (f - t0) / 32; a = 1 if k < .8 else (1 - k) / .2; sc = min(1, (f - t0) / 5)
                lay = Image.new('RGBA', (W, 110), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
                msg = f'{NAMES[C[i]]} OUT!  #{place[i]}'; tw = ld.textlength(msg, font=fToast) + 140
                ld.rounded_rectangle([(W - tw) / 2, 5, (W + tw) / 2, 100], radius=46, fill=(230, 40, 60, 240), outline=(255, 255, 255), width=4)
                lay.alpha_composite(small[C[i]].resize((70, 70)), (int((W - tw) / 2 + 18), 17))
                ld.text(((W - tw) / 2 + 105, 53), msg, font=fToast, fill='white', anchor='lm')
                lay = lay.resize((max(1, int(W * sc)), max(1, int(110 * sc))))
                lay.putalpha(lay.getchannel('A').point(lambda q: int(q * a)))
                im.paste(lay, (int((W - lay.width) / 2), int(455 + (110 - lay.height) / 2)), lay)
                dr = ImageDraw.Draw(im, 'RGBA'); break
        if done:
            k = min(1, (f - ff) / 20)
            text_c(dr, (W / 2, 480), 'WINNER', fWin, (255, 196, 0), 8)
            text_c(dr, (W / 2, 1420), NAMES[C[winner]].upper(), fWin, (255, 255, 255), 8)
            x, y = pos[winner]; rr_ = BR * (1 + 2.2 * k); c0 = y - rr_ - 10
            if k > .5:
                dr.polygon([(x - 90, c0), (x - 100, c0 - 90), (x - 45, c0 - 40), (x, c0 - 110), (x + 45, c0 - 40), (x + 100, c0 - 90), (x + 90, c0)],
                           fill=(255, 196, 0), outline=(0, 0, 0), width=5)
            if f - ff > 30: text_c(dr, (W / 2, 1505), 'Rematch? Comment your country!', fWin2, (255, 196, 0), 5)
            tt = (f - ff) / FPS
            for c_ in conf:
                cx_ = c_[0] + c_[2] * tt + 20 * math.sin(tt * 4 + c_[5]); cy_ = c_[1] + c_[3] * tt
                if 0 < cy_ < H: dr.rectangle([cx_, cy_, cx_ + 14, cy_ + 22], fill=c_[4])
        p.stdin.write(im.tobytes())
    p.stdin.close(); p.wait()
    return dict(n=len(frames), bounces=bounce_log, elims=sorted(elim_at.values()), win=ff), place, winner

# ---------------------------------------------------------------- ses (telifsiz, kodla üretilir)
def make_audio(cues, path, seed):
    SR = 44100; rng = np.random.default_rng(seed); DUR = cues['n'] / FPS + .1
    out = np.zeros(int(SR * DUR))
    def add(a, sig, g=1):
        a = int(a * SR); L = min(len(sig), len(out) - a)
        if L > 0 and a >= 0: out[a:a + L] += g * sig[:L]
    n2f = lambda n: 440 * 2 ** ((n - 69) / 12)
    def marimba(n):
        tt = np.arange(int(.35 * SR)) / SR; f = n2f(n)
        return np.exp(-tt * 12) * (np.sin(2 * np.pi * f * tt) + .35 * np.sin(2 * np.pi * 4 * f * tt) * np.exp(-tt * 30))
    root = int(rng.integers(55, 63)); scale = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21]
    mel = list(rng.integers(0, 8, 16)); last = -1
    for k, f in enumerate(cues['bounces']):
        if f / FPS - last < .06: continue
        last = f / FPS; add(last, marimba(root + scale[mel[k % 16]] + (12 if k % 32 >= 16 else 0)), .22)
    def pop():
        tt = np.arange(int(.5 * SR)) / SR
        return .6 * np.exp(-tt * 9) * np.sin(2 * np.pi * (700 * np.exp(-tt * 8) + 120) * tt) + .2 * rng.standard_normal(len(tt)) * np.exp(-tt * 25)
    for e in cues['elims']: add(e / FPS, pop(), .5)
    beat = 60 / 120
    for b in range(2, int(cues['win'] / FPS / beat) + 1):
        tt = np.arange(int(.25 * SR)) / SR; add(b * beat, np.exp(-tt * 18) * np.sin(2 * np.pi * (45 + 90 * np.exp(-tt * 30)) * tt), .35)
    w = cues['win'] / FPS
    for i, n in enumerate([67, 72, 76, 79, 84]):
        tt = np.arange(int(.9 * SR)) / SR; f = n2f(n)
        add(w + .12 * i, np.exp(-tt * 3) * (np.sign(np.sin(2 * np.pi * f * tt)) * .3 + np.sin(2 * np.pi * f * tt)), .14)
    tt = np.arange(int(2.5 * SR)) / SR
    for n in [60, 64, 67, 72]: add(w + .7, np.exp(-tt * 1.2) * np.sin(2 * np.pi * n2f(n) * tt), .12)
    out = np.tanh(out * 1.2); out /= np.abs(out).max() * 1.1; fo = int(.6 * SR); out[-fo:] *= np.linspace(1, 0, fo)
    with wave.open(str(path), 'wb') as wv:
        wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(SR)
        wv.writeframes((np.stack([out, out], 1) * 32767).astype('<i2').tobytes())

# ---------------------------------------------------------------- metin + telegram
def metadata(ep, place, winner):
    C = ep['codes']; n = len(C); rng = random.Random(ep['seed'] + 7)
    title = rng.choice(TITLES).format(n=n, theme=ep['theme']) + ' #shorts'
    top3 = sorted(range(n), key=lambda i: place[i])[:3]
    desc = (f"{n} country balls. One spinning arena. Only ONE survives. 🏆\n\n"
            f"Last Ball Standing — {ep['theme']} edition. Every ball that escapes through the gap is eliminated.\n"
            f"Did your country make the final? Comment below and it might join the next battle! 🌍\n"
            f"🔔 Subscribe for a new battle every day.\n\n"
            f"Countries: {', '.join(NAMES[c] for c in C)}\n\n"
            "#countryballs #ballrace #marblerace #simulation #satisfying #lastballstanding #shorts")
    tags = 'country balls,countryballs,ball race,marble race,country ball battle,last ball standing,simulation,satisfying,which country wins,escape the circle'
    spoiler = ' > '.join(NAMES[C[i]] for i in top3)
    return dict(title=title, description=desc, tags=tags, podium=spoiler)

def tg(method, token, data, files=None):
    import requests
    r = requests.post(f'https://api.telegram.org/bot{token}/{method}', data=data, files=files, timeout=300)
    r.raise_for_status(); return r.json()

def send_telegram(video, meta, ep):
    token, chat = os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID']
    cap = f"🎬 Yeni bölüm hazır (seed {ep['seed']})\n🏆 Podyum: {meta['podium']}"
    with open(video, 'rb') as fh:
        tg('sendVideo', token, {'chat_id': chat, 'caption': cap, 'supports_streaming': 'true'}, {'video': fh})
    # başlık / açıklama / etiketler ayrı mesajlarda: telefondan tek dokunuşla kopyalamak için
    tg('sendMessage', token, {'chat_id': chat, 'text': meta['title']})
    tg('sendMessage', token, {'chat_id': chat, 'text': meta['description']})
    tg('sendMessage', token, {'chat_id': chat, 'text': meta['tags']})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--send', action='store_true')
    ap.add_argument('--out', default='out')
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else random.randrange(1, 10 ** 6)
    out = Path(a.out); out.mkdir(exist_ok=True)
    ep, sim = pick_episode(seed)
    print('bölüm:', ep['theme'], len(ep['codes']), 'ülke, süre', round(sim[3] / FPS, 1), 'sn')
    raw, wav, final = out / 'raw.mp4', out / 'audio.wav', out / f'lbs_{seed}.mp4'
    cues, place, winner = render(ep, sim, raw)
    make_audio(cues, wav, seed)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)], check=True)
    raw.unlink(); wav.unlink()
    meta = metadata(ep, place, winner)
    (out / f'lbs_{seed}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if a.send: send_telegram(final, meta, ep); print('Telegram\'a gönderildi')

if __name__ == '__main__':
    main()
