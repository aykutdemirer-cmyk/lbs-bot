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
# ---------------------------------------------------------------- modlar
MODES = {
 # key: (başlık, alt başlık, sayaç, toast, tepsi, başlık şablonları)
 'classic': ('LAST ONE WINS!', 'Which country survives?', 'LEFT', 'OUT!', 'ELIMINATED',
             ['{n} Countries Enter, Only 1 Survives 🏆', 'Which Country Survives? {n} Balls, 1 Winner 🌍',
              'Last Ball Standing: {theme} Edition 🏆']),
 'double':  ('TWO EXITS!', 'Last one inside wins', 'LEFT', 'OUT!', 'ELIMINATED',
             ['Two Exits, {n} Countries, 1 Survivor 😱', 'Double Trouble: {theme} Edition 🌍']),
 'shrink':  ('THE ARENA SHRINKS!', 'Last one inside wins', 'LEFT', 'OUT!', 'ELIMINATED',
             ['The Arena Is Shrinking! {n} Countries Fight 😰', 'No Room Left: {theme} Edition 🏆']),
 'grow':    ('BOUNCE = GROW!', 'Every bounce makes you bigger', 'LEFT', 'OUT!', 'ELIMINATED',
             ['Every Bounce Makes Them BIGGER 🎈 {n} Countries', 'Growing Balls Battle: {theme} Edition 🌍']),
 'escape':  ('FIRST TO ESCAPE WINS!', 'Only 3 medals. Who gets out?', 'ESCAPED', 'ESCAPED!', 'PODIUM',
             ['First Country To Escape Wins 🏃 {n} Balls', 'Escape Race: {theme} Edition 🥇']),
 'hp':      ('BATTLE ROYALE!', 'Every hit costs 1 HP', 'LEFT', 'KNOCKED OUT!', 'ELIMINATED',
             ['{n} Countries Battle Royale ⚔️ Only 1 Survives', 'Country Ball Battle Royale: {theme} Edition ⚔️']),
}
MODE_ORDER = ['classic', 'escape', 'hp', 'shrink', 'grow', 'double']
HP0 = 10

# ---------------------------------------------------------------- simülasyon
def simulate(seed, codes, mode='classic', max_t=70):
    rng = random.Random(seed); n = len(codes)
    rad = np.full(n, float(BR)); hp = np.full(n, HP0); cool = np.zeros((n, n))
    pos = []
    while len(pos) < n:
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(0, R - BR - 10)
        p = np.array([CX + r * math.cos(a), CY + r * math.sin(a)])
        if all(np.linalg.norm(p - q) > 2 * BR + 4 for q in pos): pos.append(p)
    pos = np.array(pos); vel = np.array([[rng.uniform(-500, 500), rng.uniform(-500, 200)] for _ in range(n)])
    alive = np.ones(n, bool); out = np.zeros(n, bool)
    gap_ang = rng.uniform(0, 2 * math.pi)
    gap_w0 = math.radians({'escape': 6, 'double': 18}.get(mode, rng.uniform(22, 30)))
    gaps = [] if mode == 'hp' else ([0, math.pi] if mode == 'double' else [0])
    omega = math.radians(rng.uniform(55, 90)) * rng.choice([-1, 1])
    frames, events, order = [], [], []
    dt = 1 / FPS / SUB; f = 0; last_ev = 0; fin = None; winner = None
    while True:
        ta = max(0, (f - INTRO) / FPS)
        Rn = R - 190 * min(1, ta / 22) if mode == 'shrink' else R
        gap_w = gap_w0 + math.radians(4) * max(0, (f - last_ev) / FPS - (7 if mode == 'escape' else 4))
        bounces, hits = [], []
        if f >= INTRO and fin is None:
            for _ in range(SUB):
                vel[:, 1] += G * dt; pos += vel * dt; cool -= dt
                idx = np.where(alive & ~out)[0]
                for ii in range(len(idx)):
                    for jj in range(ii + 1, len(idx)):
                        i, j = idx[ii], idx[jj]; d = pos[j] - pos[i]; dist = math.hypot(*d); md = rad[i] + rad[j]
                        if 0 < dist < md:
                            nr = d / dist; ov = md - dist; pos[i] -= nr * ov / 2; pos[j] += nr * ov / 2
                            rv = np.dot(vel[j] - vel[i], nr)
                            if rv < 0:
                                vel[i] += rv * nr; vel[j] -= rv * nr
                                if mode == 'hp' and cool[i, j] <= 0:
                                    hp[i] -= 1; hp[j] -= 1; cool[i, j] = cool[j, i] = .35; hits += [int(i), int(j)]
                for i in idx:
                    d = pos[i] - (CX, CY); dist = math.hypot(*d); ri = rad[i]
                    if dist > Rn - ri:
                        ang = math.atan2(d[1], d[0]) % (2 * math.pi)
                        in_gap = any(abs((ang - (gap_ang + g) + math.pi) % (2 * math.pi) - math.pi) < gap_w / 2 for g in gaps)
                        if in_gap and dist < Rn + ri:
                            if dist > Rn + ri * .2: out[i] = True
                            continue
                        if dist >= Rn + ri * .2: continue
                        nr = d / dist; pos[i] = (CX, CY) + nr * (Rn - ri); vn = np.dot(vel[i], nr)
                        if vn > 0:
                            vel[i] -= 2 * vn * nr; sp = math.hypot(*vel[i])
                            if sp < 900: vel[i] *= 900 / sp
                            if sp > 1500: vel[i] *= 1500 / sp
                            bounces.append(int(i))
                            if mode == 'grow': rad[i] = min(78, rad[i] + 1.6)
                            if mode == 'hp' and (f - last_ev) / FPS > 5: hp[i] -= 1; hits.append(int(i))
                gap_ang = (gap_ang + omega * dt) % (2 * math.pi)
            for i in range(n):
                if alive[i] and (out[i] or (mode == 'hp' and hp[i] <= 0)):
                    alive[i] = False; out[i] = True; order.append(i); last_ev = f; events.append((f, 'elim', i))
                    if mode == 'hp': vel[i] = (rng.uniform(-200, 200), -600)
            if mode == 'escape':
                if len(order) >= 3: fin = f; winner = order[0]
            elif alive.sum() == 1:
                fin = f; winner = int(np.where(alive)[0][0])
            if fin is not None: events.append((f, 'win', winner))
        elif fin is not None:
            pos[winner] += ((CX, CY) - pos[winner]) * 0.08; vel[winner] = 0
            for i in range(n):
                if out[i] and i != winner: vel[i, 1] += G / FPS; pos[i] += vel[i] / FPS
        frames.append((pos.copy(), alive.copy(), out.copy(), gap_ang, gap_w, sorted(set(bounces)), rad.copy(), hp.copy(), Rn, sorted(set(hits))))
        f += 1
        if fin is not None and f - fin > 4.5 * FPS: break
        if f / FPS > max_t: return None
    return dict(frames=frames, events=events, order=order, fin=fin, winner=winner, gaps=gaps)

def pick_episode(seed, mode=None):
    rng = random.Random(seed)
    theme = rng.choice(list(THEMES)); tname, pool = THEMES[theme]
    mode = mode or rng.choice(MODE_ORDER)
    n = rng.choice([12, 14, 16, 16]) if mode == 'grow' else rng.choice([12, 14, 16, 16, 18])
    codes = rng.sample(pool, min(n, len(pool)))
    for k in range(300):  # 18–45 sn arası bir sonuç ara
        s = seed * 1000 + k
        r = simulate(s, codes, mode)
        if r and (14 if mode in ('escape', 'hp') else 18) * FPS <= r['fin'] <= 45 * FPS:
            return dict(seed=seed, sim_seed=s, theme=tname, mode=mode, codes=codes, hue=rng.random()), r
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

def fit_font(dr, text, weight, size, maxw):
    while size > 30:
        f = font(weight, size)
        if dr.textlength(text, font=f) <= maxw: return f
        size -= 4
    return font(weight, size)

MEDAL = [(255, 196, 0), (200, 205, 215), (205, 127, 50)]

def render(ep, sim, out_path):
    frames, events, order, ff, winner, gaps = sim['frames'], sim['events'], sim['order'], sim['fin'], sim['winner'], sim['gaps']
    mode = ep['mode']; h1, h2, cnt_lbl, toast_lbl, tray_lbl, _ = MODES[mode]
    C = ep['codes']; N = len(C); hue0 = ep['hue']
    yy, xx = np.mgrid[0:H, 0:W]; d = np.sqrt((xx - CX) ** 2 + (yy - CY) ** 2) / 1000
    r, g, b = colorsys.hsv_to_rgb((hue0 + .7) % 1, .7, .55)
    bg = np.zeros((H, W, 3), np.float32) + (12, 10, 30) + np.clip(1 - d, 0, 1)[..., None] ** 2 * np.array([r, g, b]) * 160
    BG = Image.fromarray(np.clip(bg, 0, 255).astype('uint8'))
    tmp = ImageDraw.Draw(BG.copy()); fT1 = fit_font(tmp, h1, 'Black', 80, 1010); fT2 = fit_font(tmp, h2, 'Black', 52, 1000)
    small = {c: circ_flag(c, 56) for c in C}
    elim_at = {e[2]: e[0] for e in events if e[1] == 'elim'}
    if mode == 'escape':
        place = {i: k + 1 for k, i in enumerate(order)}
    else:
        place = {i: N - k for k, i in enumerate(order)}; place[winner] = 1
    rng = random.Random(ep['seed'])
    conf = [[rng.uniform(0, W), rng.uniform(-600, -20), rng.uniform(-120, 120), rng.uniform(250, 520),
             rng.choice([(255, 196, 0), (255, 70, 90), (80, 200, 255), (120, 255, 150), (255, 255, 255)]), rng.uniform(0, 6)] for _ in range(160)]
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium',
                          str(out_path)], stdin=subprocess.PIPE)
    prev = frames[0][0]; flash = 0; bounce_log = []; hit_log = []; hitflash = np.zeros(N)
    for f, (pos, alive, out, gap_ang, gap_w, bounces, rad, hp, Rn, hits) in enumerate(frames):
        vel = (pos - prev) * FPS; prev = pos
        if bounces: bounce_log.append(f); flash = 1.0
        if hits: hit_log.append(f)
        flash *= .8; hitflash *= .75
        for i in hits: hitflash[i] = 1
        rr, gg, bb = colorsys.hsv_to_rgb((hue0 + f / 300) % 1, .75, 1); col = (int(rr * 255), int(gg * 255), int(bb * 255))
        if mode == 'hp': col = (255, 60, 60) if (f // 6) % 2 and len(hits) else col
        # halka: boşluklar arasındaki yaylar
        if gaps:
            cs = sorted((gap_ang + gg_) % (2 * math.pi) for gg_ in gaps)
            segs = [(math.degrees(cs[k] + gap_w / 2), math.degrees(cs[(k + 1) % len(cs)] - gap_w / 2) + (360 if k == len(cs) - 1 else 0)) for k in range(len(cs))]
        else:
            segs = [(0, 360)]
        s_ = 4; gl = Image.new('RGB', (W // s_, H // s_)); gd = ImageDraw.Draw(gl)
        for a0, a1 in segs:
            gd.arc([(CX - Rn - 8) / s_, (CY - Rn - 8) / s_, (CX + Rn + 8) / s_, (CY + Rn + 8) / s_], a0, a1, fill=col, width=int(10 + 8 * flash))
        gl = gl.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        im = Image.fromarray(np.clip(np.asarray(BG, np.int16) + np.asarray(gl, np.int16) * (1.1 + flash), 0, 255).astype('uint8'))
        dr = ImageDraw.Draw(im, 'RGBA')
        for a0, a1 in segs:
            dr.arc([CX - Rn - 8, CY - Rn - 8, CX + Rn + 8, CY + Rn + 8], a0, a1, fill=col, width=16)
            dr.arc([CX - Rn - 3, CY - Rn - 3, CX + Rn + 3, CY + Rn + 3], a0, a1, fill=(255, 255, 255), width=4)
        done = f >= ff
        text_c(dr, (W / 2, 150), h1, fT1, (255, 255, 255), 7)
        text_c(dr, (W / 2, 245), h2, fT2, (255, 196, 0), 5)
        left = int(alive.sum())
        cval = f'{min(3, len([i for i in order if elim_at[i] <= f]))}/3' if mode == 'escape' else str(left)
        dr.rounded_rectangle([W / 2 - 170, 315, W / 2 + 170, 385], radius=35, fill=(255, 255, 255, 30), outline=(255, 255, 255, 120), width=3)
        text_c(dr, (W / 2, 350), f'{cnt_lbl}: {cval}', fCnt, (255, 255, 255), 0)
        draw_order = [i for i in range(N) if out[i] and i != winner] + [i for i in range(N) if alive[i] and i != winner] + [winner]
        for i in draw_order:
            x, y = pos[i]
            if y > H + 150 or y < -200: continue
            if done and mode == 'escape' and i != winner: continue
            dsz = int(rad[i] * 2) // 2 * 2
            if done and i == winner:
                k = min(1, (f - ff) / 25); dsz = int(rad[i] * 2 * (1 + (2.2 * 40 / rad[i]) * (k * k * (3 - 2 * k)))) // 2 * 2
            if i in bounces and not done: dsz = int(dsz * 1.12) // 2 * 2
            bi = ball_img(C[i], dsz); im.paste(bi, (int(x - bi.width / 2), int(y - bi.height / 2)), bi)
            if hitflash[i] > .05 and not done:
                dr.ellipse([x - dsz / 2, y - dsz / 2, x + dsz / 2, y + dsz / 2], fill=(255, 40, 40, int(150 * hitflash[i])))
            if not (done and i != winner): eyes(dr, x, y, dsz / 2, vel[i][0], vel[i][1], scared=bool(out[i]) or hitflash[i] > .3)
            if mode == 'hp' and alive[i] and not done:
                bw = dsz * .9; frac = max(0, hp[i]) / HP0
                dr.rounded_rectangle([x - bw / 2, y + dsz / 2 + 6, x + bw / 2, y + dsz / 2 + 16], radius=5, fill=(0, 0, 0, 170))
                hc = (int(255 * (1 - frac)), int(220 * frac + 30), 60)
                dr.rounded_rectangle([x - bw / 2, y + dsz / 2 + 6, x - bw / 2 + max(6, bw * frac), y + dsz / 2 + 16], radius=5, fill=hc)
            elif alive[i] and left <= 4 and not done and mode != 'escape':
                text_c(dr, (x, y + rad[i] + 26), NAMES[C[i]], fSmall, (255, 255, 255), 4)
        ty = 1590
        dr.text((W / 2, ty - 18), tray_lbl, font=fSmall, fill=(255, 255, 255, 150), anchor='mm')
        cols = 8 if N <= 16 else 9; step = (W - 120) / cols
        shown = [i for i in order if elim_at[i] <= f]
        if mode == 'escape':
            for k, i in enumerate(shown[:3]):
                gx = W / 2 + (k - 1) * 220; gy = ty + 60
                dr.ellipse([gx - 44, gy - 44, gx + 44, gy + 44], fill=MEDAL[k])
                sm = circ_flag(C[i], 76); im.paste(sm, (int(gx - 38), int(gy - 38)), sm)
                text_c(dr, (gx, gy + 70), f'#{k + 1} {NAMES[C[i]]}', fSmall, MEDAL[k], 3)
        else:
            for k, i in enumerate(shown):
                gx = 60 + step / 2 + (k % cols) * step; gy = ty + 40 + (k // cols) * 108
                sm = small[C[i]]; gimg = Image.blend(Image.new('RGBA', sm.size, (12, 10, 30, 255)), sm, .55); gimg.putalpha(sm.getchannel('A'))
                im.paste(gimg, (int(gx - 28), int(gy - 20)), gimg)
                text_c(dr, (gx, gy + 56), f'{place[i]}.', fSmall, (255, 120, 120), 3)
        for i in order:
            t0 = elim_at[i]
            if 0 <= f - t0 < 32 and not (mode == 'escape' and place[i] > 3):
                k = (f - t0) / 32; a = 1 if k < .8 else (1 - k) / .2; sc = min(1, (f - t0) / 5)
                lay = Image.new('RGBA', (W, 110), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
                msg = f'{NAMES[C[i]]} {toast_lbl}  #{place[i]}'; tw = ld.textlength(msg, font=fToast) + 140
                tcol = (30, 170, 90, 240) if mode == 'escape' else (230, 40, 60, 240)
                ld.rounded_rectangle([(W - tw) / 2, 5, (W + tw) / 2, 100], radius=46, fill=tcol, outline=(255, 255, 255), width=4)
                lay.alpha_composite(small[C[i]].resize((70, 70)), (int((W - tw) / 2 + 18), 17))
                ld.text(((W - tw) / 2 + 105, 53), msg, font=fToast, fill='white', anchor='lm')
                lay = lay.resize((max(1, int(W * sc)), max(1, int(110 * sc))))
                lay.putalpha(lay.getchannel('A').point(lambda q: int(q * a)))
                im.paste(lay, (int((W - lay.width) / 2), int(455 + (110 - lay.height) / 2)), lay)
                dr = ImageDraw.Draw(im, 'RGBA'); break
        if done:
            k = min(1, (f - ff) / 20)
            text_c(dr, (W / 2, 480), 'WINNER', fWin, (255, 196, 0), 8)
            text_c(dr, (W / 2, 1420), NAMES[C[winner]].upper(), fit_font(dr, NAMES[C[winner]].upper(), 'Black', 110, 1000), (255, 255, 255), 8)
            x, y = pos[winner]; kk = min(1, (f - ff) / 25); c0 = y - rad[winner] * (1 + (2.2 * 40 / rad[winner]) * (kk * kk * (3 - 2 * kk))) - 10
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
    return dict(n=len(frames), bounces=bounce_log, hits=hit_log, elims=sorted(elim_at.values()), win=ff), place, winner

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
    for e in cues.get('cheer', []):  # gol sevinci: kalabalık uğultusu
        L = int(2.5 * SR); nz = rng.standard_normal(L); nz = np.convolve(nz, np.ones(25) / 25, 'same')
        add(e / FPS, nz * np.sin(np.linspace(0, np.pi, L)) ** .5 * 2.2, .5)
    def thud():
        tt = np.arange(int(.12 * SR)) / SR
        return np.exp(-tt * 40) * np.sin(2 * np.pi * 180 * tt) + .3 * rng.standard_normal(len(tt)) * np.exp(-tt * 60)
    lh = -1
    for f in cues.get('hits', []):
        if f / FPS - lh > .08: lh = f / FPS; add(lh, thud(), .25)
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

# ---------------------------------------------------------------- maç modu (ülke topları futbol oynar)
FL, FR_, FT, FB = 100, W - 100, 560, 1380     # saha sınırları (sol, sağ, tavan, zemin)
GOAL_H, GOAL_D = 230, 70                     # kale yüksekliği ve derinliği
PR, BBR = 66, 30                             # oyuncu ve top yarıçapı
MATCH_T = 42                                 # maç süresi (sn) -> 90 dakikaya ölçeklenir

def simulate_match(seed, max_goals=7):
    rng = random.Random(seed)
    dt = 1 / FPS / SUB
    def kickoff():
        return (np.array([[CX - 260, FB - PR], [CX + 260, FB - PR]], float), np.zeros((2, 2)),
                np.array([CX, FT + 180.]), np.array([rng.uniform(-60, 60), 0.]))
    P, V, B, BV = kickoff()
    score = [0, 0]; frames = []; events = []; jcd = [0., 0.]; freeze = 0; f = 0
    total = INTRO + int(MATCH_T * FPS)
    while f < total + int(4.5 * FPS):
        playing = INTRO <= f < total
        kicks = []
        if playing and freeze <= 0:
            for _ in range(SUB):
                V[:, 1] += 2200 * dt; BV[1] += 1500 * dt
                for k in range(2):
                    side = 1 if k == 0 else -1               # 0: sola savunur, sağa atar
                    target = B[0] - side * 45
                    V[k, 0] += np.clip(target - P[k, 0], -1, 1) * 2600 * dt
                    V[k, 0] *= .995
                    jcd[k] -= dt
                    if P[k, 1] >= FB - PR - 1 and jcd[k] <= 0 and abs(B[0] - P[k, 0]) < 260 and B[1] < FB - 40:
                        V[k, 1] = -rng.uniform(850, 1250); jcd[k] = rng.uniform(.25, .7)
                P += V * dt; B += BV * dt; BV *= .9995
                for k in range(2):  # oyuncu - duvar
                    if P[k, 1] > FB - PR: P[k, 1] = FB - PR; V[k, 1] = 0; V[k, 0] *= .9
                    if P[k, 1] < FT + PR: P[k, 1] = FT + PR; V[k, 1] = abs(V[k, 1]) * .5
                    lo, hi = FL + PR + 10, FR_ - PR - 10
                    if P[k, 0] < lo: P[k, 0] = lo; V[k, 0] = abs(V[k, 0]) * .5
                    if P[k, 0] > hi: P[k, 0] = hi; V[k, 0] = -abs(V[k, 0]) * .5
                d = P[1] - P[0]; dist = math.hypot(*d)   # oyuncu - oyuncu
                if 0 < dist < 2 * PR:
                    nr = d / dist; ov = 2 * PR - dist; P[0] -= nr * ov / 2; P[1] += nr * ov / 2
                    rv = np.dot(V[1] - V[0], nr)
                    if rv < 0: V[0] += rv * nr; V[1] -= rv * nr
                for k in range(2):  # oyuncu - top
                    d = B - P[k]; dist = math.hypot(*d)
                    if 0 < dist < PR + BBR:
                        nr = d / dist; B[:] = P[k] + nr * (PR + BBR)
                        rel = np.dot(BV - V[k], nr)
                        if rel < 0: BV -= 1.8 * rel * nr
                        side = 1 if k == 0 else -1
                        BV += nr * 260 + np.array([side * rng.uniform(250, 520), -rng.uniform(150, 420)])
                        sp = math.hypot(*BV)
                        if sp > 1900: BV *= 1900 / sp
                        kicks.append(k)
                # top - duvar / kale
                in_mouth = B[1] > FB - GOAL_H + BBR
                if B[1] > FB - BBR: B[1] = FB - BBR; BV[1] = -abs(BV[1]) * .72; BV[0] *= .985
                if B[1] < FT + BBR: B[1] = FT + BBR; BV[1] = abs(BV[1]) * .8
                if B[0] < FL + BBR:
                    if in_mouth and B[0] < FL - 10: events.append((f, 'goal', 1)); score[1] += 1; freeze = 70; break
                    elif not in_mouth: B[0] = FL + BBR; BV[0] = abs(BV[0]) * .85
                if B[0] > FR_ - BBR:
                    if in_mouth and B[0] > FR_ + 10: events.append((f, 'goal', 0)); score[0] += 1; freeze = 70; break
                    elif not in_mouth: B[0] = FR_ - BBR; BV[0] = -abs(BV[0]) * .85
                # üst direk (kale ağzının üst köşesi)
                for gx in (FL, FR_):
                    cp = np.array([gx, FB - GOAL_H]); d = B - cp; dist = math.hypot(*d)
                    if 0 < dist < BBR + 8:
                        nr = d / dist; B[:] = cp + nr * (BBR + 8); rel = np.dot(BV, nr)
                        if rel < 0: BV -= 1.9 * rel * nr; events.append((f, 'post', 0))
        elif freeze > 0:
            freeze -= 1
            if freeze == 0: P, V, B, BV = kickoff()
        frames.append((P.copy(), V.copy(), B.copy(), tuple(score), freeze, kicks))
        f += 1
    return dict(frames=frames, events=events, score=tuple(score), total=total)

def pick_match(seed, home, away):
    for k in range(200):
        r = simulate_match(seed * 1000 + k)
        g = sum(r['score'])
        if 2 <= g <= 6: return r
    return r

def render_match(home, away, sim, out_path, seed):
    frames, events, total = sim['frames'], sim['events'], sim['total']
    goals = {e[0]: e[2] for e in events if e[1] == 'goal'}
    yy, xx = np.mgrid[0:H, 0:W]
    bg = np.zeros((H, W, 3), np.float32) + (10, 16, 30)
    d = np.sqrt((xx - CX) ** 2 + (yy - 980) ** 2) / 1100
    bg += np.clip(1 - d, 0, 1)[..., None] ** 2 * np.array([20, 70, 60])
    BG = Image.fromarray(np.clip(bg, 0, 255).astype('uint8')); bd = ImageDraw.Draw(BG)
    # çim saha
    for i in range(10):
        x0 = FL + i * (FR_ - FL) / 10
        bd.rectangle([x0, FT, x0 + (FR_ - FL) / 10, FB], fill=(36, 140, 70) if i % 2 else (44, 158, 80))
    bd.line([(CX, FT), (CX, FB)], fill=(255, 255, 255), width=5)
    bd.ellipse([CX - 110, (FT + FB) / 2 - 110, CX + 110, (FT + FB) / 2 + 110], outline=(255, 255, 255), width=5)
    bd.rectangle([FL, FT, FR_, FB], outline=(255, 255, 255), width=6)
    for gx, sgn in ((FL, -1), (FR_, 1)):  # kaleler + ağ
        x0, x1 = (gx - GOAL_D, gx) if sgn < 0 else (gx, gx + GOAL_D)
        bd.rectangle([x0, FB - GOAL_H, x1, FB], fill=(25, 60, 45))
        for yy_ in range(int(FB - GOAL_H), int(FB), 18): bd.line([(x0, yy_), (x1, yy_)], fill=(200, 210, 210), width=1)
        for xx_ in range(int(x0), int(x1), 18): bd.line([(xx_, FB - GOAL_H), (xx_, FB)], fill=(200, 210, 210), width=1)
        bd.line([(gx, FB - GOAL_H), (gx, FB)], fill=(255, 255, 255), width=10)
        bd.line([(x0, FB - GOAL_H), (x1, FB - GOAL_H)], fill=(255, 255, 255), width=10)
    fb_ = Image.new('RGBA', (BBR * 2 + 4, BBR * 2 + 4), (0, 0, 0, 0)); fd = ImageDraw.Draw(fb_)
    fd.ellipse([1, 1, BBR * 2 + 2, BBR * 2 + 2], fill='white', outline=(0, 0, 0), width=3)
    for a in range(5):
        an = a * 2 * math.pi / 5; cx_, cy_ = BBR + 2 + math.cos(an) * BBR * .55, BBR + 2 + math.sin(an) * BBR * .55
        fd.regular_polygon((cx_, cy_, BBR * .22), 5, fill=(20, 20, 20))
    fd.regular_polygon((BBR + 2, BBR + 2, BBR * .3), 5, fill=(20, 20, 20))
    big = {0: circ_flag(home, 90), 1: circ_flag(away, 90)}
    rng = random.Random(seed); conf = []
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium',
                          str(out_path)], stdin=subprocess.PIPE)
    last_goal = None; kick_log = []; rot = 0
    for f, (P, V, B, score, freeze, kicks) in enumerate(frames):
        if kicks: kick_log.append(f)
        if f in goals:
            last_goal = (f, goals[f])
            col = (255, 196, 0)
            conf = [[rng.uniform(0, W), rng.uniform(-500, 0), rng.uniform(-150, 150), rng.uniform(300, 600),
                     rng.choice([(255, 255, 255), (255, 196, 0), (255, 60, 80), (80, 200, 255)]), rng.uniform(0, 6), f] for _ in range(120)]
        im = BG.copy(); dr = ImageDraw.Draw(im, 'RGBA')
        # skor tabelası
        dr.rounded_rectangle([60, 130, W - 60, 330], radius=40, fill=(0, 0, 0, 150), outline=(255, 255, 255, 90), width=3)
        im.paste(big[0], (100, 185), big[0]); im.paste(big[1], (W - 190, 185), big[1])
        text_c(dr, (CX, 225), f'{score[0]} - {score[1]}', font('Black', 110), (255, 255, 255), 6)
        dr.text((145, 300), NAMES[home].upper(), font=fSmall, fill='white', anchor='mm')
        dr.text((W - 145, 300), NAMES[away].upper(), font=fSmall, fill='white', anchor='mm')
        minute = 0 if f < INTRO else min(90, int((f - INTRO) / (total - INTRO) * 90))
        clock = 'FT' if f >= total else f"{minute}'"
        dr.rounded_rectangle([CX - 70, 300, CX + 70, 352], radius=20, fill=(255, 196, 0))
        dr.text((CX, 326), clock, font=fCnt, fill=(15, 15, 25), anchor='mm')
        text_c(dr, (CX, 70), 'MATCH DAY!', font('Black', 70), (255, 196, 0), 6)
        text_c(dr, (CX, 420), 'Who wins? Comment your prediction!', font('Black', 44), (255, 255, 255), 5)
        # oyuncular ve top
        for k in range(2):
            x, y = P[k]; code = home if k == 0 else away
            bi = ball_img(code, PR * 2); im.paste(bi, (int(x - bi.width / 2), int(y - bi.height / 2)), bi)
            look = (B - P[k]); eyes(dr, x, y, PR, look[0], look[1])
        rot += math.hypot(*V[0]) * 0 + 1
        bx, by = B; im.paste(fb_, (int(bx - BBR - 2), int(by - BBR - 2)), fb_)
        dr = ImageDraw.Draw(im, 'RGBA')
        if last_goal and 0 <= f - last_goal[0] < 70:
            k = f - last_goal[0]; s = min(1, k / 6) * (1 + .08 * math.sin(k / 3))
            who = home if last_goal[1] == 0 else away
            lay = Image.new('RGBA', (W, 300), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
            ld.text((W / 2, 110), 'GOAL!', font=font('Black', 190), fill=(255, 196, 0), anchor='mm', stroke_width=10, stroke_fill=(0, 0, 0))
            ld.text((W / 2, 240), NAMES[who].upper() + ' SCORES!', font=font('Black', 60), fill='white', anchor='mm', stroke_width=6, stroke_fill=(0, 0, 0))
            lay = lay.resize((max(1, int(W * s)), max(1, int(300 * s))))
            im.paste(lay, (int((W - lay.width) / 2), int(780 + (300 - lay.height) / 2)), lay)
        if conf:
            tt = (f - conf[0][6]) / FPS
            if tt < 3:
                for c_ in conf:
                    cx_ = c_[0] + c_[2] * tt + 20 * math.sin(tt * 4 + c_[5]); cy_ = c_[1] + c_[3] * tt
                    if 0 < cy_ < H: dr.rectangle([cx_, cy_, cx_ + 14, cy_ + 22], fill=c_[4])
        if f >= total:
            k = min(1, (f - total) / 15)
            sc = sim['score']; res = 'DRAW!' if sc[0] == sc[1] else NAMES[home if sc[0] > sc[1] else away].upper() + ' WINS!'
            dr.rounded_rectangle([60, 1440, W - 60, 1620], radius=40, fill=(0, 0, 0, int(200 * k)))
            text_c(dr, (CX, 1500), 'FULL TIME', font('Black', 60), (255, 196, 0), 5)
            text_c(dr, (CX, 1575), res, fit_font(dr, res, 'Black', 64, 900), (255, 255, 255), 5)
            text_c(dr, (CX, 1700), 'Rematch? Comment the next match!', font('Black', 42), (255, 196, 0), 5)
        if f < INTRO + 20:
            a = 1 if f < INTRO else 1 - (f - INTRO) / 20
            ov = Image.new('RGBA', (W, H), (0, 0, 0, int(160 * a))); od = ImageDraw.Draw(ov)
            od.text((CX, 900), NAMES[home].upper(), font=font('Black', 100), fill=(255, 255, 255, int(255 * a)), anchor='mm', stroke_width=6, stroke_fill=(0, 0, 0))
            od.text((CX, 1010), 'VS', font=font('Black', 80), fill=(255, 196, 0, int(255 * a)), anchor='mm')
            od.text((CX, 1120), NAMES[away].upper(), font=font('Black', 100), fill=(255, 255, 255, int(255 * a)), anchor='mm', stroke_width=6, stroke_fill=(0, 0, 0))
            im = Image.alpha_composite(im.convert('RGBA'), ov).convert('RGB')
        p.stdin.write(im.tobytes())
    p.stdin.close(); p.wait()
    return dict(n=len(frames), bounces=kick_log, hits=[], elims=sorted(goals), win=total)

def match_metadata(home, away, sim):
    a, b = NAMES[home], NAMES[away]; sc = sim['score']
    title = random.choice([f'{a} vs {b} ⚽ Country Ball Match Day', f'{a} vs {b} — Who Wins? ⚽ #shorts', f'Match Day: {a} vs {b} ⚽'])
    if '#shorts' not in title: title += ' #shorts'
    desc = (f"⚽ MATCH DAY: {a} vs {b}! Country balls play football in a physics simulation.\n"
            f"The real match is today — who do you think wins? Comment your prediction! 👇\n"
            f"🔔 Subscribe for a new battle every day.\n\n"
            "This is an animated simulation for fun, not a real match result.\n\n"
            f"#{a.replace(' ', '')} #{b.replace(' ', '')} #football #countryballs #matchday #simulation #shorts")
    tags = f'{a} vs {b},{a},{b},football,soccer,country balls,countryballs,match day,simulation,last ball standing'
    return dict(title=title, description=desc, tags=tags, podium=f'{a} {sc[0]} - {sc[1]} {b}')

# ---------------------------------------------------------------- metin + telegram
def metadata(ep, place, winner):
    C = ep['codes']; n = len(C); rng = random.Random(ep['seed'] + 7)
    title = rng.choice(MODES[ep['mode']][5]).format(n=n, theme=ep['theme']) + ' #shorts'
    top3 = sorted(place, key=lambda i: place[i])[:3]
    rules = {'classic': 'Every ball that escapes through the gap is eliminated. Last one inside wins.',
             'double': 'TWO gaps spin around the ring. Escape = eliminated. Last one inside wins.',
             'shrink': 'The arena keeps shrinking. Escape = eliminated. Last one inside wins.',
             'grow': 'Every bounce makes a ball bigger. Escape = eliminated. Last one inside wins.',
             'escape': 'Reverse rules! The FIRST three balls to escape win gold, silver and bronze.',
             'hp': 'Battle royale: every hit costs 1 HP. Last ball standing wins.'}[ep['mode']]
    desc = (f"{n} country balls. One spinning arena. {MODES[ep['mode']][0].title()} 🏆\n\n"
            f"Last Ball Standing — {ep['theme']} edition. {rules}\n"
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
    cap = f"🎬 Yeni bölüm hazır — mod: {ep['mode']} (seed {ep['seed']})\n🏆 Podyum: {meta['podium']}"
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
    ap.add_argument('--mode', choices=list(MODES), default=None)
    ap.add_argument('--index', type=int, default=0, help='aynı gün birden fazla video için sıra')
    ap.add_argument('--match', default=None, help='maç modu, ör. tr-es (ev sahibi-deplasman)')
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else random.randrange(1, 10 ** 6)
    out = Path(a.out); out.mkdir(exist_ok=True)
    import datetime
    match = a.match
    fx = ROOT / 'fixtures.txt'   # satır: 2026-10-05 it tr  (o gün maç videosu yapılır)
    if not match and a.index == 0 and fx.exists():
        today = datetime.date.today().isoformat()
        for line in fx.read_text().splitlines():
            p_ = line.split('#')[0].split()
            if len(p_) == 3 and p_[0] == today: match = f'{p_[1]}-{p_[2]}'
    if match:
        home, away = match.lower().split('-')
        sim = pick_match(seed, home, away)
        print('maç:', home, away, sim['score'])
        raw, wav, final = out / 'raw.mp4', out / 'audio.wav', out / f'lbs_{seed}.mp4'
        cues = render_match(home, away, sim, raw, seed); cues['cheer'] = cues['elims']
        make_audio(cues, wav, seed)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                        '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)], check=True)
        raw.unlink(); wav.unlink()
        meta = match_metadata(home, away, sim)
        (out / f'lbs_{seed}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        if a.send: send_telegram(final, meta, dict(mode='match', seed=seed))
        return
    mode = a.mode or MODE_ORDER[(datetime.date.today().toordinal() + a.index) % len(MODE_ORDER)]  # her gün farklı mod
    ep, sim = pick_episode(seed, mode)
    print('bölüm:', ep['mode'], ep['theme'], len(ep['codes']), 'ülke, süre', round(sim['fin'] / FPS, 1), 'sn')
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
