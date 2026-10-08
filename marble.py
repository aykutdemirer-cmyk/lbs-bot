"""Uzun, engebeli misket yarışları (kamera takipli). Stiller: race (klasik), elim (eleme yarışı)."""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import lbs
from lbs import W, H, FPS, CX, NAMES, font, circ_flag, ball_img, eyes, text_c, fit_font
from games import _ffmpeg, _confetti, _winner_screen

R = 26; WALL = 40; GATE_T = 3.0


# ----------------------------------------------------------------------- pist üretimi
def build_track(rng, n_sections):
    segs = []; pegs = []; bumpers = []; spins = []; marks = []
    def poly(pts, kind=0):
        for a, b in zip(pts[:-1], pts[1:]): segs.append((a[0], a[1], b[0], b[1], kind))
    y = 560
    poly([(WALL, 300), (WALL, 99999)]); poly([(W - WALL, 300), (W - WALL, 99999)])
    gate = len(segs); segs.append((WALL, 520, W - WALL, 520, 2))  # başlangıç kapısı
    kinds = []
    pool = ['zig', 'zig', 'pegs', 'bump', 'spin', 'funnel', 'zig']
    last = None
    for k in range(n_sections):
        c = rng.choice([p for p in pool if p != last]) if k else 'pegs'; kinds.append(c); last = c  # adil başlangıç: herkes aynı çizgiden çivi tarlasına düşer
        top = y
        if c == 'zig':  # engebeli zikzak rampalar
            side = rng.choice([0, 1])
            for j in range(rng.choice([2, 3])):
                x0, x1 = (WALL, W - WALL - 150) if side == 0 else (W - WALL, WALL + 150)
                dy = rng.uniform(250, 310); per = rng.uniform(150, 210); ph = rng.uniform(0, 6)
                amp = .8 * (dy / (W - 2 * WALL - 150)) * per / (2 * math.pi)  # tümsekler var ama çukur yok -> takılma olmaz
                pts = []
                for s in np.linspace(0, 1, 60):
                    x = x0 + (x1 - x0) * s; yy = y + dy * s - amp * math.sin(s * abs(x1 - x0) / per * 2 * math.pi + ph)
                    pts.append((x, yy))
                poly(pts, 0); y += dy + rng.uniform(170, 200); side ^= 1
        elif c == 'pegs':
            for row in range(9):
                off = 0 if row % 2 else 50
                for kx in range(12):
                    x = 95 + off + kx * 100
                    if WALL + 80 < x < W - WALL - 80: pegs.append((x, y + 40 + row * 95))
            y += 9 * 95 + 80
        elif c == 'bump':  # pinball tamponları
            for row in range(4):
                for kx in range(3 if row % 2 else 4):
                    x = (W / 4) * (kx + (1 if row % 2 else .5)); bumpers.append((x + rng.uniform(-30, 30), y + 80 + row * 210, rng.choice([42, 50, 58])))
            y += 4 * 210 + 60
        elif c == 'spin':
            for j in range(3):
                spins.append((rng.choice([300, CX, W - 300]) + rng.uniform(-40, 40), y + 120 + j * 300,
                              rng.choice([-1, 1]) * rng.uniform(1.6, 2.8), rng.uniform(150, 190)))
            y += 3 * 300 + 40
        elif c == 'funnel':  # huni
            g = 2 * R + 46
            poly([(WALL, y), (CX - g / 2, y + 330)]); poly([(W - WALL, y), (CX + g / 2, y + 330)])
            spins.append((CX, y + 500, rng.choice([-1, 1]) * 2.2, 160))
            y += 680
        marks.append((top, y, c))
    finish = y + 120
    poly([(WALL, finish + 160), (W - WALL, finish + 160)], 3)  # bitiş zemini
    return dict(segs=np.array(segs, float), pegs=np.array(pegs or [(-999, -999)], float), bumpers=bumpers, spins=spins,
                marks=marks, finish=finish, gate=gate, height=finish + 400)


# ----------------------------------------------------------------------- simülasyon
def simulate(seed, codes, style='race', n_sections=9, max_t=75):
    rng = random.Random(seed); n = len(codes); codes = list(codes); rng.shuffle(codes)
    T = build_track(rng, n_sections)
    segs = T['segs']; A = segs[:, :2]; B = segs[:, 2:4]; AB = B - A; L2 = (AB ** 2).sum(1); kind = segs[:, 4]
    pegs = T['pegs']; PR = 12
    bum = np.array([(x, y, r) for x, y, r in T['bumpers']] or [(-999, -999, 1)], float)
    pos = np.array([[WALL + 45 + i * (W - 2 * WALL - 90) / max(1, n - 1), 490.0] for i in range(n)])  # tek sıra, aynı yükseklik
    vel = np.zeros((n, 2)); alive = np.ones(n, bool); done = np.zeros(n, bool)
    order = []; elims = []; frames = []; hits = []; bounces = []; stuck = np.zeros(n)
    G = 1500.0; dt = 1 / FPS / 5; f = 0; fin = None
    # eleme kontrol noktaları: son bölümler hariç her bölüm sonu
    cps = [m[1] for m in T['marks'][:-1]]
    need = max(0, n - 3) if style == 'elim' else 0
    if need: cps = [cps[int(round(i * (len(cps) - 1) / max(1, need - 1)))] for i in range(need)] if need <= len(cps) else cps
    if style == 'elim':
        # her noktada en az 1 eleme; nokta sayısı yetmezse bazı noktalarda 2 eleme
        per = [need // len(cps) + (1 if i < need % len(cps) else 0) for i in range(len(cps))]
    else: per = []
    crossed = [set() for _ in cps]; cpi = 0
    while True:
        t = f / FPS; ev_hit = False; ev_b = False
        open_gate = t >= GATE_T
        if fin is None and t >= 1.0:
            for _ in range(5):
                act = alive & ~done
                vel[act, 1] += G * dt; pos[act] += vel[act] * dt
                idx = np.where(act)[0]
                if len(idx) == 0: break
                P = pos[idx]
                # segmentler
                tt = np.clip(((P[:, None, :] - A[None]) * AB[None]).sum(2) / np.maximum(L2, 1e-9)[None], 0, 1)
                C = A[None] + tt[..., None] * AB[None]; D = P[:, None, :] - C; dist = np.sqrt((D ** 2).sum(2))
                if open_gate: dist[:, T['gate']] = 1e9
                for a_, s_ in zip(*np.where(dist < R)):
                    i = idx[a_]; d = dist[a_, s_]
                    nr = D[a_, s_] / d if d > 1e-6 else np.array([0., -1.])
                    pos[i] += nr * (R - d); vn = vel[i] @ nr
                    if vn < 0:
                        e = .32 if kind[s_] != 3 else .1
                        vel[i] -= (1 + e) * vn * nr
                        if vn < -260: ev_b = True
                    vel[i] *= .9995
                # çiviler
                if len(pegs):
                    Dp = pos[idx][:, None, :] - pegs[None]; dp = np.sqrt((Dp ** 2).sum(2))
                    for a_, s_ in zip(*np.where(dp < R + PR)):
                        i = idx[a_]; nr = Dp[a_, s_] / dp[a_, s_]; pos[i] = pegs[s_] + nr * (R + PR); vn = vel[i] @ nr
                        if vn < 0: vel[i] -= 1.5 * vn * nr; vel[i, 0] += rng.uniform(-50, 50); ev_b = True
                # tamponlar
                Db = pos[idx][:, None, :] - bum[None, :, :2]; db = np.sqrt((Db ** 2).sum(2))
                for a_, s_ in zip(*np.where(db < R + bum[:, 2][None])):
                    i = idx[a_]; nr = Db[a_, s_] / db[a_, s_]; pos[i] = bum[s_, :2] + nr * (R + bum[s_, 2]); vn = vel[i] @ nr
                    if vn < 50: vel[i] -= vn * nr; vel[i] += nr * 480 + np.array([-nr[1], nr[0]]) * rng.uniform(-220, 220); ev_hit = True
                # dönen çubuklar
                for sx, sy, w, ln in T['spins']:
                    a = t * w; u = np.array([math.cos(a), math.sin(a)])
                    for i in idx:
                        rel = pos[i] - (sx, sy); s = np.clip(rel @ u, -ln, ln); cp = np.array([sx, sy]) + u * s; dd = pos[i] - cp; ds = math.hypot(*dd)
                        if 0 < ds < R + 9:
                            nr = dd / ds; pos[i] = cp + nr * (R + 9); vn = vel[i] @ nr
                            vt = np.array([-u[1], u[0]]) * w * s  # çubuğun yüzey hızı
                            vel[i] += -min(0, vn) * 1.5 * nr + nr * 60 + .5 * (vt @ nr) * nr; ev_hit = True
                # misket-misket
                P = pos[idx]; Dm = P[None] - P[:, None]; dm = np.sqrt((Dm ** 2).sum(2)) + np.eye(len(idx)) * 1e9
                for a_, b_ in zip(*np.where(np.triu(dm < 2 * R, 1))):
                    i, j = idx[a_], idx[b_]; d = dm[a_, b_]; nr = Dm[a_, b_] / d; ov = 2 * R - d
                    pos[i] -= nr * ov / 2; pos[j] += nr * ov / 2; rv = (vel[j] - vel[i]) @ nr
                    if rv < 0: vel[i] += .9 * rv * nr; vel[j] -= .9 * rv * nr
                sp = np.hypot(vel[:, 0], vel[:, 1]); big = sp > 1300; vel[big] *= (1300 / sp[big])[:, None]
            # takılma önleyici
            if open_gate and f % 30 == 0:  # 1 sn'de 40px ilerlemeyen misket dürtülür
                if f > GATE_T * FPS + 30:
                    for i in np.where(alive & ~done & (pos[:, 1] - stuck < 40))[0]:
                        vel[i] = ((1 if pos[i, 0] < CX else -1) * rng.uniform(180, 300), -rng.uniform(250, 380))
                stuck = pos[:, 1].copy()
            # kontrol noktaları / eleme
            if style == 'elim':
                while cpi < len(cps):
                    new = [int(i) for i in np.where(alive & (pos[:, 1] > cps[cpi]))[0] if int(i) not in crossed[cpi]]
                    crossed[cpi].update(new)
                    al = np.where(alive)[0]; rest = [i for i in al if i not in crossed[cpi]]
                    if len(rest) <= per[cpi] and len(al) - per[cpi] >= 1:
                        out = rest + sorted(new, key=lambda i: pos[i, 1])[:per[cpi] - len(rest)]
                        for i in out: alive[i] = False; done[i] = False; elims.append((f, int(i)))
                        order[:] = [o for o in order if alive[o]]
                        cpi += 1
                    else: break
            for i in np.where(alive & ~done & (pos[:, 1] > T['finish']))[0]:
                done[i] = True; order.append(int(i))
            if fin is None and (len(order) >= 1 and cpi >= len(cps) if style == 'elim' else len(order) >= min(3, n)): fin = f
        if ev_b: bounces.append(f)
        if ev_hit: hits.append(f)
        frames.append((pos.copy(), alive.copy(), done.copy(), list(order), t))
        f += 1
        if fin is not None and f - fin > 6 * FPS: break
        if t > max_t: return None
    T.update(frames=frames, order=order, fin=fin, codes=codes, elims=elims, bounces=bounces, hits=hits, style=style, cps=cps)
    return T


# ----------------------------------------------------------------------- çizim
PAL = [(255, 80, 140), (0, 200, 255), (255, 196, 0), (120, 255, 150), (190, 120, 255), (255, 140, 60)]

def world_image(T, seed):
    Hh = int(T['height']); rng = random.Random(seed)
    yy = np.linspace(0, 1, Hh)[:, None]
    c0 = np.array([14, 10, 34]); c1 = np.array([6, 24, 40])
    bg = (c0 * (1 - yy) + c1 * yy)[:, None, :] * np.ones((1, W, 1))
    im = Image.fromarray(bg.astype('uint8')); dr = ImageDraw.Draw(im)
    for k, (a, b, c) in enumerate(T['marks']):  # bölüm şeritleri
        col = PAL[k % len(PAL)]; dr.rectangle([0, a, W, b], fill=tuple(int(v * .10 + 10) for v in col))
    glow = Image.new('RGB', im.size); gd = ImageDraw.Draw(glow)
    def segcol(y):
        for k, (a, b, c) in enumerate(T['marks']):
            if a - 200 <= y <= b + 50: return PAL[k % len(PAL)]
        return (200, 210, 255)
    for x0, y0, x1, y1, kd in T['segs']:
        if kd == 2: continue
        col = (200, 210, 255) if x0 == x1 else segcol((y0 + y1) / 2); y1c = min(y1, Hh)
        gd.line([(x0, y0), (x1, y1c)], fill=col, width=26); dr.line([(x0, y0), (x1, y1c)], fill=col, width=12)
    for x, y in T['pegs']:
        gd.ellipse([x - 18, y - 18, x + 18, y + 18], fill=(120, 140, 255)); dr.ellipse([x - 12, y - 12, x + 12, y + 12], fill=(235, 240, 255))
    for x, y, r in T['bumpers']:
        gd.ellipse([x - r - 8, y - r - 8, x + r + 8, y + r + 8], fill=(255, 80, 140))
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(255, 80, 140), outline='white', width=6); dr.ellipse([x - r * .45, y - r * .45, x + r * .45, y + r * .45], fill='white')
    glow = glow.resize((W // 4, Hh // 4)).filter(ImageFilter.GaussianBlur(6)).resize((W, Hh))
    im = Image.fromarray(np.clip(np.asarray(im, np.int16) + (np.asarray(glow, np.int16) * .7).astype(np.int16), 0, 255).astype('uint8'))
    dr = ImageDraw.Draw(im); fy = T['finish']
    for k in range(WALL, W - WALL, 40):  # dama bitiş çizgisi
        for row in range(2):
            c = (k // 40 + row) % 2
            dr.rectangle([k, fy + row * 20, k + 20, fy + row * 20 + 20], fill='white' if c else 'black')
            dr.rectangle([k + 20, fy + row * 20, k + 40, fy + row * 20 + 20], fill='black' if c else 'white')
    text_c(dr, (CX, fy + 110), 'FINISH', font('Black', 70), (255, 196, 0), 6)
    for y in T.get('cps', []) if T['style'] == 'elim' else []:
        for k in range(WALL, W - WALL, 50): dr.rectangle([k, y, k + 28, y + 8], fill=(255, 60, 60))
    return im


def render(T, out_path, seed):
    frames, C, order, ff = T['frames'], T['codes'], T['order'], T['fin']; n = len(C); elim = T['style'] == 'elim'
    world = world_image(T, seed); Hh = world.height; medal = lbs.MEDAL
    p = _ffmpeg(out_path); conf = _confetti(seed); cam = 0.0; prev = frames[0][0]
    el_at = {fr: i for fr, i in T['elims']}; last_el = None; pops = []
    for f, (pos, alive, done, ordr, t) in enumerate(frames):
        vel = (pos - prev) * FPS; prev = pos
        live = np.where(alive & ~done)[0]
        if len(live):
            ys = pos[live, 1]; lead, back = ys.max(), ys.min()
            tgt = back - 1000 if elim else lead - 1150
        else: tgt = T['finish'] - 900
        tgt = min(max(tgt, 0), Hh - H); cam = tgt if f == 0 else cam + (tgt - cam) * .12
        cy = int(cam); im = world.crop((0, cy, W, cy + H)); dr = ImageDraw.Draw(im, 'RGBA')
        if t < GATE_T:  # kapı
            gy = 520 - cy; dr.rectangle([WALL, gy - 6, W - WALL, gy + 6], fill=(255, 196, 0))
        for sx, sy, w, ln in T['spins']:
            if -300 < sy - cy < H + 300:
                a = t * w; ux, uy = math.cos(a), math.sin(a); y0 = sy - cy
                dr.line([(sx - ux * ln, y0 - uy * ln), (sx + ux * ln, y0 + uy * ln)], fill=(255, 80, 140), width=18)
                dr.ellipse([sx - 14, y0 - 14, sx + 14, y0 + 14], fill='white')
        rank = sorted([i for i in range(n) if alive[i]], key=lambda i: (-(i in ordr), ordr.index(i) if i in ordr else -pos[i, 1]))
        for i in range(n):
            if not alive[i] or done[i]: continue
            x, y = pos[i, 0], pos[i, 1] - cy
            if -60 < y < H + 60:
                bi = ball_img(C[i], 2 * R); im.paste(bi, (int(x - R), int(y - R)), bi); eyes(dr, x, y, R, vel[i][0], vel[i][1] + 1)
                if elim and len(live) > 1 and i == rank[-1] and t > GATE_T:
                    dr.ellipse([x - R - 8, y - R - 8, x + R + 8, y + R + 8], outline=(255, 60, 60), width=5)
        if f in el_at: last_el = (f, el_at[f]); pops.append((f, pos[el_at[f]].copy()))
        for pf, pp in pops:  # patlama halkası
            k = (f - pf) / 12
            if 0 <= k < 1:
                rr = R + 90 * k; y0 = pp[1] - cy; dr.ellipse([pp[0] - rr, y0 - rr, pp[0] + rr, y0 + rr], outline=(255, 80, 80, int(255 * (1 - k))), width=8)
        # üst başlık
        dr.rectangle([0, 0, W, 300], fill=(0, 0, 0, 120))
        text_c(dr, (CX, 95), 'ELIMINATION RACE' if elim else 'MARBLE RACE', font('Black', 84), (255, 255, 255), 7)
        sub = f'Last one at each red line is OUT · {int(alive.sum())} left' if elim else f'{n} countries · first to the bottom wins'
        text_c(dr, (CX, 175), sub, fit_font(dr, sub, 'Black', 44, 1000), (255, 196, 0), 5)
        # canlı sıralama (ilk 5)
        for k, i in enumerate(rank[:5]):
            yy = 245 + k * 0; xx = 120 + k * 210
            sm = circ_flag(C[i], 56); im.paste(sm, (xx - 28, 210), sm)
            dr.text((xx + 34, 238), f'{k + 1}', font=font('Black', 34), fill=medal[k] if k < 3 else (255, 255, 255), anchor='lm', stroke_width=4, stroke_fill=(0, 0, 0))
        # mini harita
        mx = W - 22; dr.rectangle([mx - 5, 330, mx + 5, H - 140], fill=(255, 255, 255, 50))
        for i in range(n):
            if alive[i]:
                my = 330 + (H - 470) * min(1, pos[i, 1] / T['finish']); dr.ellipse([mx - 9, my - 9, mx + 9, my + 9], fill=(255, 196, 0) if i == (rank[0] if rank else -1) else (255, 255, 255))
        if t < GATE_T:
            k = GATE_T - t; s = str(int(k) + 1) if k > .0 else 'GO'
            text_c(dr, (CX, 900), s, font('Black', 260), (255, 255, 255), 12)
        elif t < GATE_T + .8: text_c(dr, (CX, 900), 'GO!', font('Black', 260), (120, 255, 150), 12)
        if last_el and f - last_el[0] < 45:
            s = f'{NAMES[C[last_el[1]]].upper()} IS OUT!'; text_c(dr, (CX, 420), s, fit_font(dr, s, 'Black', 64, 980), (255, 80, 80), 6)
        elif not elim and 0 < len(ordr) < 3:
            s = f'{NAMES[C[ordr[-1]]]} FINISHED #{len(ordr)}!'; text_c(dr, (CX, 420), s, fit_font(dr, s, 'Black', 54, 980), (120, 255, 150), 5)
        if ff is not None and f >= ff + 10:
            k = (f - ff - 10) / 25; im = Image.blend(im, Image.new('RGB', (W, H)), min(.6, k)); dr = ImageDraw.Draw(im, 'RGBA')
            _winner_screen(im, dr, C[ordr[0]], k, conf, (f - ff) / FPS, 'Race again? Comment your country!')
            if not elim:
                for kk, i in enumerate(ordr[:3]): text_c(dr, (CX, 1500 + kk * 62), f'#{kk + 1}  {NAMES[C[i]]}', font('Black', 46), medal[kk], 4)
        p.stdin.write(im.tobytes())
    p.stdin.close(); p.wait()
    return dict(n=len(frames), bounces=T['bounces'], hits=T['hits'], elims=[e for e, _ in T['elims']], win=ff + 10)


def make(style, seed, out_dir, codes=None):
    """style: race | elim -> (final, meta, ep)"""
    import subprocess
    rng = random.Random(seed); out_dir.mkdir(exist_ok=True)
    raw, wav, final = out_dir / 'raw.mp4', out_dir / 'audio.wav', out_dir / f'lbs_{seed}.mp4'
    codes = list(codes) if codes else rng.sample(list(NAMES), rng.choice([10, 12, 12, 14]) if style == 'race' else rng.choice([10, 12]))
    lo, hi = (35, 50) if style == 'race' else (32, 50)   # video 1 dk altında
    sim = None
    for k in range(40):
        s = simulate(seed * 100 + k, codes, style, n_sections=rng.choice([13, 14]) if style == 'race' else 13, max_t=hi + 5)
        if s and lo * FPS <= s['fin'] <= hi * FPS: sim = s; break
        sim = sim or s
    cues = render(sim, raw, seed); lbs.make_audio(cues, wav, seed)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-t', '59', '-movflags', '+faststart', str(final)], check=True)
    raw.unlink(); wav.unlink()
    C = sim['codes']; win = NAMES[C[sim['order'][0]]]; n = len(C)
    if style == 'race':
        title = rng.choice([f'{n} Countries Marble Race 🏁 Who Wins?', 'Bumpy Marble Race: Which Country Is Fastest? 🏁',
                            f'Epic {n}-Country Marble Race 🏁 Watch Till The End!'])
        desc = (f"🏁 {n} country balls race down a long, bumpy track — ramps, bumpers, spinners and pegs. First to the finish wins!\n")
        podium = ' > '.join(NAMES[C[i]] for i in sim['order'][:3])
    else:
        title = rng.choice([f'Marble Elimination Race: {n} Countries, 1 Winner 🏁', 'Last Marble At Each Line Is OUT! 🏁 Who Survives?',
                            f'{n} Countries Elimination Marble Race 😱🏁'])
        desc = (f"🏁 {n} country balls race — the last one to cross each red line is eliminated! Who survives to the finish?\n")
        podium = f'Kazanan: {win}'
    desc += ("Which country did you cheer for? Comment below 👇\n🔔 Subscribe for a new race every day.\n\n"
             f"Countries: {', '.join(NAMES[c] for c in C)}\n\n#countryballs #marblerace #marblerun #simulation #satisfying #shorts")
    tags = 'marble race,marble run,country balls,countryballs,elimination race,simulation,satisfying,which country wins'
    return final, dict(title=title + ' #shorts', description=desc, tags=tags, podium=podium), dict(mode=style, seed=seed)
