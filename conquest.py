"""Harita Fethi: her ülke topu kendi bölgesinde seker, düşman karesine çarptıkça onu boyar.
Topun bulunduğu kare başkasına geçerse o ülke elenir ve kalan toprakları fetheden ülkeye geçer."""
import math, random, subprocess
import numpy as np
from PIL import Image, ImageDraw
import lbs
from lbs import W, H, FPS, CX, NAMES, font, circ_flag, ball_img, eyes, text_c, fit_font
from games import _ffmpeg, _confetti, _winner_screen

N = 32; MX, MY, MS = 60, 400, 960; CS = MS / N; BR = 19
PAL = {'red': (225, 45, 55), 'green': (110, 200, 60), 'cyan': (20, 185, 205), 'dark': (55, 58, 66), 'lblue': (95, 155, 230),
       'dgreen': (30, 150, 85), 'blue': (40, 85, 210), 'white': (235, 235, 240), 'orange': (240, 165, 20), 'purple': (125, 80, 210),
       'pink': (235, 95, 170), 'yellow': (245, 220, 50), 'brown': (150, 95, 55), 'teal': (0, 128, 128), 'lime': (190, 235, 90), 'navy': (30, 40, 110)}
PREF = {'tr': 'red', 'br': 'green', 'jp': 'white', 'de': 'dark', 'fr': 'blue', 'it': 'dgreen', 'es': 'orange', 'us': 'purple',
        'ru': 'lblue', 'az': 'cyan', 'gb': 'navy', 'nl': 'orange', 'ca': 'red', 'cn': 'red', 'in': 'orange', 'ar': 'lblue',
        'mx': 'dgreen', 'kr': 'white', 'sa': 'dgreen', 'ua': 'yellow', 'pt': 'dgreen', 'se': 'yellow', 'au': 'navy', 'eg': 'dark',
        'pl': 'pink', 'gr': 'lblue', 'ng': 'lime', 'pk': 'teal', 'id': 'pink', 'co': 'yellow', 'be': 'yellow', 'ch': 'red'}


def colors_for(codes):
    used = set(); out = []
    for c in codes:
        k = PREF.get(c)
        if not k or k in used: k = next(x for x in PAL if x not in used)
        used.add(k); out.append(np.array(PAL[k], float))
    return out


def simulate(seed, codes, max_t=80):
    rng = random.Random(seed); n = len(codes); tot = N * N
    # Voronoi + gürültü ile başlangıç bölgeleri
    seeds = []
    while len(seeds) < n:
        p = (rng.uniform(3, N - 3), rng.uniform(3, N - 3))
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > N / math.sqrt(n) * .75 for q in seeds): seeds.append(p)
    yy, xx = np.mgrid[0:N, 0:N] + .5
    nz = np.random.default_rng(seed).normal(0, 1, (n, N, N)); nz = (nz + np.roll(nz, 1, 1) + np.roll(nz, 1, 2) + np.roll(nz, -1, 1)) / 4
    own = (np.stack([np.hypot(xx - sx, yy - sy) for sx, sy in seeds]) + nz * 1.6).argmin(0)
    for i in range(n): own[int(seeds[i][1]), int(seeds[i][0])] = i
    def newball(i, x, y):
        a = rng.uniform(0, 2 * math.pi); return [i, np.array([x, y], float), np.array([math.cos(a), math.sin(a)])]
    balls = [newball(i, MX + sx * CS, MY + sy * CS) for i, (sx, sy) in enumerate(seeds)]
    alive = np.ones(n, bool); bonus = np.zeros(n, int); low = np.zeros(n)
    frames = []; bounces = []; elims = []; spawns = []; f = 0; fin = None
    DIRS = [(math.cos(k * math.pi / 6), math.sin(k * math.pi / 6)) for k in range(12)]
    cc = (np.mgrid[0:N, 0:N] + .5) * CS  # hücre merkezleri (y, x)
    while True:
        t = f / FPS; mult = 1 + max(0, t - 1.5) / 30 + max(0, t - 30) / 4   # 30 sn sonra hızlanır (video 1 dk altında kalsın)
        cnt = np.bincount(own.ravel(), minlength=n); share = cnt / tot
        rad = BR * (.75 + 3.5 * share)                                 # büyüyen ülkenin topu büyür
        hit = False
        if t >= 1.5 and fin is None:
            sub = 10; step = 480 * mult / FPS / sub
            for _ in range(sub):
                for b in balls:
                    i, pos, vel = b; r = rad[i]
                    p = pos + vel * step * (.7 + 3 * share[i])   # büyük ülke daha hızlı
                    for ax, lo, hi in ((0, MX, MX + MS), (1, MY, MY + MS)):
                        if p[ax] - r < lo: p[ax] = lo + r; vel[ax] = abs(vel[ax])
                        if p[ax] + r > hi: p[ax] = hi - r; vel[ax] = -abs(vel[ax])
                    for k in rng.sample(range(12), 12):
                        dx, dy = DIRS[k]; qx, qy = p[0] + dx * r, p[1] + dy * r
                        cx, cy = int((qx - MX) / CS), int((qy - MY) / CS)
                        if 0 <= cx < N and 0 <= cy < N and own[cy, cx] != i and vel @ (dx, dy) > 0:
                            d_ = own[cy, cx]; pr = CS * min(4.0 + max(0, t - 30) / 3, max(.55, .8 * (share[i] / max(share[d_], .002)) ** 1.7))  # güçlü olan daha çok toprak alır
                            m = (np.hypot(cc[1] - (qx - MX), cc[0] - (qy - MY)) < pr) & (own == d_)
                            m[cy, cx] = True; own[m] = i; hit = True
                            v = vel - 2 * (vel @ (dx, dy)) * np.array([dx, dy])
                            a = math.atan2(v[1], v[0]) + rng.uniform(-.25, .25); vel[:] = (math.cos(a), math.sin(a)); p = pos.copy()
                            break
                    b[1] = p
                # toplar birbirinin içinden geçmesin
                for x in range(len(balls)):
                    for y in range(x + 1, len(balls)):
                        A, B = balls[x], balls[y]; dd = B[1] - A[1]; ds = math.hypot(*dd); rr = rad[A[0]] + rad[B[0]]
                        if 0 < ds < rr:
                            nr = dd / ds; A[1] -= nr * (rr - ds) / 2; B[1] += nr * (rr - ds) / 2
                            if (B[2] - A[2]) @ nr < 0: A[2], B[2] = A[2] - (A[2] @ nr) * 2 * nr * (A[2] @ nr > 0), B[2] - (B[2] @ nr) * 2 * nr * (B[2] @ nr < 0)
            cnt = np.bincount(own.ravel(), minlength=n); share = cnt / tot
            for i in np.where(alive)[0]:
                # %25 ve %45'te yeni top
                for th in (.25, .45):
                    if share[i] >= th and bonus[i] < (1 if th == .25 else 2):
                        ys, xs = np.where(own == i); j = rng.randrange(len(ys))
                        balls.append(newball(i, MX + (xs[j] + .5) * CS, MY + (ys[j] + .5) * CS)); bonus[i] += 1; spawns.append((f, int(i)))
                # toprağı biten ülke düşer
                low[i] = low[i] + 1 if cnt[i] <= 3 else 0
                if low[i] > FPS * .7 or cnt[i] == 0:
                    alive[i] = False; balls = [b for b in balls if b[0] != i]
                    ys, xs = np.where(own == i)
                    nb = np.concatenate([own[np.clip(ys + dy, 0, N - 1), np.clip(xs + dx, 0, N - 1)] for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0))]) if len(ys) else np.array([], int)
                    nb = nb[nb != i]; o = int(np.bincount(nb).argmax()) if len(nb) else int(cnt.argmax())
                    own[own == i] = o; elims.append((f, int(i), o))
            if alive.sum() == 1: fin = f
        if hit: bounces.append(f)
        frames.append((own.copy(), [(b[0], b[1].copy(), b[2].copy()) for b in balls], alive.copy(), t, mult, rad.copy()))
        f += 1
        if fin is not None and f - fin > 6 * FPS: break
        if t > max_t: return None
    return dict(frames=frames, codes=list(codes), fin=fin, elims=elims, spawns=spawns, bounces=bounces, winner=int(np.where(alive)[0][0]))


def render(sim, out_path, seed):
    C = sim['codes']; n = len(C); cols = colors_for(C); frames, ff = sim['frames'], sim['fin']
    tab = np.array(cols); chk = ((np.add.outer(np.arange(N), np.arange(N)) % 2) * 2 - 1) * .07  # dama dokusu
    rep = int(MS / N)
    bg = Image.new('RGB', (W, H), (14, 14, 20)); bd = ImageDraw.Draw(bg)
    text_c(bd, (CX, 140), 'WHICH COUNTRY WILL', font('Black', 80), (255, 255, 255), 7)
    text_c(bd, (CX, 235), 'CONQUER THE MAP?', font('Black', 80), (255, 255, 255), 7)
    text_c(bd, (CX, 330), 'Comment your guess!', font('Black', 46), (255, 196, 0), 5)
    medal = lbs.MEDAL; conf = _confetti(seed); el_at = {e[0]: e for e in sim['elims']}; last_el = None; p = _ffmpeg(out_path)
    sp_at = {e[0]: e for e in sim['spawns']}; last_sp = None
    flag_cache = {}
    for f, (own, balls, alive, t, mult, rad) in enumerate(frames):
        rgb = tab[own] * (1 + chk[..., None]); rgb = np.clip(rgb, 0, 255)
        big = np.repeat(np.repeat(rgb, rep, 0), rep, 1); ob = np.repeat(np.repeat(own, rep, 0), rep, 1)
        edge = np.zeros(ob.shape, bool); edge[:, 1:] |= ob[:, 1:] != ob[:, :-1]; edge[1:, :] |= ob[1:, :] != ob[:-1, :]
        edge[:, :-1] |= edge[:, 1:]; edge[:-1, :] |= edge[1:, :]
        big[edge] *= .45
        im = bg.copy(); im.paste(Image.fromarray(big.astype('uint8')), (MX, MY)); dr = ImageDraw.Draw(im)
        dr.rectangle([MX - 4, MY - 4, MX + MS + 3, MY + MS + 3], outline=(255, 255, 255), width=4)
        cnt = np.bincount(own.ravel(), minlength=n); tot = N * N
        # ülke isimleri bölge merkezinde
        yy, xx = np.mgrid[0:N, 0:N]
        for i in range(n):
            if cnt[i] < 14: continue
            m = own == i; cxm, cym = xx[m].mean(), yy[m].mean()
            nm = NAMES[C[i]]; fs = 30 if cnt[i] > 60 else 24
            dr.text((MX + (cxm + .5) * CS, MY + (cym + .5) * CS + 34), nm, font=font('Black', fs), fill='white', anchor='mm', stroke_width=4, stroke_fill=(0, 0, 0))
        for i, (x, y), v in (balls if ff is None or f < ff + 10 else []):
            r = int(rad[i]); bi = flag_cache.setdefault((C[i], r), ball_img(C[i], 2 * r))
            dr.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill='white'); im.paste(bi, (int(x - r), int(y - r)), bi)
            eyes(dr, x, y, r, v[0], v[1])
        # renk çubuğu
        x0 = MX
        order = sorted(range(n), key=lambda i: -cnt[i])
        for i in order:
            w = MS * cnt[i] / tot
            if w > 0: dr.rectangle([x0, 1390, x0 + w, 1420], fill=tuple(int(v) for v in cols[i])); x0 += w
        dr.rectangle([MX - 3, 1387, MX + MS + 3, 1423], outline=(255, 255, 255), width=3)
        for k, i in enumerate(order[:4]):
            y = 1490 + k * 78; fl = circ_flag(C[i], 56); im.paste(fl, (MX + 4, int(y - 28)), fl)
            col = medal[k] if k < 3 else (255, 255, 255)
            dr.text((MX + 80, y), f'{k + 1}. {NAMES[C[i]]}', font=font('Black', 44), fill=col, anchor='lm', stroke_width=4, stroke_fill=(0, 0, 0))
            dr.text((MX + 640, y), f'{100 * cnt[i] / tot:.1f}%', font=font('Black', 44), fill='white', anchor='rm', stroke_width=4, stroke_fill=(0, 0, 0))
        text_c(dr, (870, 1560), str(int(alive.sum())), font('Black', 150), (255, 196, 0), 8)
        text_c(dr, (870, 1680), 'COUNTRIES LEFT', font('Black', 34), (255, 255, 255), 4)
        text_c(dr, (870, 1735), f'⚡ SPEED x{mult:.1f}'.replace('⚡ ', ''), font('Black', 34), (255, 90, 90), 4)
        if f in el_at: last_el = el_at[f]
        if f in sp_at: last_sp = sp_at[f]
        if last_sp and f - last_sp[0] < 40 and not (last_el and f - last_el[0] < 50):
            s = f'{NAMES[C[last_sp[1]]].upper()} GETS A NEW BALL!'
            text_c(dr, (CX, MY + MS / 2), s, fit_font(dr, s, 'Black', 60, 1000), (255, 196, 0), 8)
        if last_el and f - last_el[0] < 50 and (ff is None or f < ff + 10):
            s = f'{NAMES[C[last_el[1]]].upper()} IS OUT!'
            text_c(dr, (CX, MY + MS / 2), s, fit_font(dr, s, 'Black', 60, 1000), (255, 255, 255), 8)
        if t < 1.5: text_c(dr, (CX, MY + MS / 2), 'GO!' if t > 1 else f'{n} COUNTRIES', font('Black', 110), (255, 255, 255), 9)
        if ff is not None and f >= ff + 10:
            k = (f - ff - 10) / 25; im = Image.blend(im, Image.new('RGB', (W, H)), min(.6, k)); dr = ImageDraw.Draw(im)
            _winner_screen(im, dr, C[sim['winner']], k, conf, (f - ff) / FPS, 'Who should fight next? Comment!')
        p.stdin.write(im.tobytes())
    p.stdin.close(); p.wait()
    return dict(n=len(frames), bounces=sim['bounces'], hits=[], elims=[e[0] for e in sim['elims']], win=ff + 10)


def make(seed, out_dir, codes=None):
    rng = random.Random(seed); out_dir.mkdir(exist_ok=True)
    raw, wav, final = out_dir / 'raw.mp4', out_dir / 'audio.wav', out_dir / f'lbs_{seed}.mp4'
    codes = list(codes)[:16] if codes else rng.sample(list(NAMES), rng.choice([8, 10, 10, 12]))
    rng.shuffle(codes); sim = None
    for k in range(30):
        s = simulate(seed * 100 + k, codes, max_t=52)
        if s and 30 * FPS <= s['fin'] <= 50 * FPS: sim = s; break
        sim = sim or s
    cues = render(sim, raw, seed); lbs.make_audio(cues, wav, seed)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-t', '59', '-movflags', '+faststart', str(final)], check=True)
    raw.unlink(); wav.unlink()
    C = sim['codes']; nm = len(C); win = NAMES[C[sim['winner']]]
    title = rng.choice([f'Which Country Will Conquer The Map? 🗺️ {nm} Countries', f'{nm} Countries Fight For The Map 🗺️ Who Wins?',
                        'Territory War: Last Country Standing Takes The Map 🗺️'])
    desc = (f"🗺️ {nm} country balls fight for territory! Every bounce captures enemy squares, bigger countries get bigger balls and bonus balls at 25% and 45%. Run out of land and you're out!\n"
            "Guess the winner in the comments 👇\n🔔 Subscribe for a new battle every day.\n\n"
            f"Countries: {', '.join(NAMES[c] for c in C)}\n\n#countryballs #territorywar #mapgame #simulation #satisfying #shorts")
    tags = 'territory war,map conquest,country balls,countryballs,simulation,satisfying,which country wins,last ball standing'
    return final, dict(title=title + ' #shorts', description=desc, tags=tags, podium=f'Kazanan: {win}'), dict(mode='map', seed=seed)
