"""Ekstra oyun stilleri: Misket Yarışı (plinko), Sumo Turnuvası, Penaltı Atışları."""
import math, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import lbs
from lbs import W, H, FPS, CX, NAMES, font, circ_flag, ball_img, eyes, text_c, fit_font

def _ffmpeg(out_path):
    return subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                             '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium',
                             str(out_path)], stdin=subprocess.PIPE)

def _bg(top=(12, 10, 30), glow=(60, 25, 110), cy=1000):
    yy, xx = np.mgrid[0:H, 0:W]; d = np.sqrt((xx - CX) ** 2 + (yy - cy) ** 2) / 1100
    a = np.zeros((H, W, 3), np.float32) + top + np.clip(1 - d, 0, 1)[..., None] ** 2 * np.array(glow)
    return Image.fromarray(np.clip(a, 0, 255).astype('uint8'))

def _confetti(seed):
    rng = random.Random(seed)
    return [[rng.uniform(0, W), rng.uniform(-600, -20), rng.uniform(-120, 120), rng.uniform(250, 520),
             rng.choice([(255, 196, 0), (255, 70, 90), (80, 200, 255), (120, 255, 150), (255, 255, 255)]), rng.uniform(0, 6)] for _ in range(150)]

def _draw_confetti(dr, conf, tt):
    for c_ in conf:
        x = c_[0] + c_[2] * tt + 20 * math.sin(tt * 4 + c_[5]); y = c_[1] + c_[3] * tt
        if 0 < y < H: dr.rectangle([x, y, x + 14, y + 22], fill=c_[4])

def _winner_screen(im, dr, code, k, conf, tt, sub='Rematch? Comment your country!'):
    x, y = CX, 980; d = int(80 + 180 * min(1, k))
    bi = ball_img(code, d // 2 * 2); im.paste(bi, (int(x - bi.width / 2), int(y - bi.height / 2)), bi)
    eyes(dr, x, y, d / 2, 0, -1)
    c0 = y - d / 2 - 10
    dr.polygon([(x - 90, c0), (x - 100, c0 - 90), (x - 45, c0 - 40), (x, c0 - 110), (x + 45, c0 - 40), (x + 100, c0 - 90), (x + 90, c0)],
               fill=(255, 196, 0), outline=(0, 0, 0), width=5)
    text_c(dr, (CX, 560), 'WINNER', font('Black', 110), (255, 196, 0), 8)
    nm = NAMES[code].upper(); text_c(dr, (CX, 1300), nm, fit_font(dr, nm, 'Black', 110, 1000), (255, 255, 255), 8)
    text_c(dr, (CX, 1400), sub, font('Black', 46), (255, 196, 0), 5)
    _draw_confetti(dr, conf, tt)

# ======================================================================= MİSKET YARIŞI (plinko)
def simulate_race(seed, codes, max_t=60):
    rng = random.Random(seed); n = len(codes); r = 24; G = 700.0
    pegs = []
    for row in range(14):
        y = 520 + row * 82; off = 0 if row % 2 else 46
        for k in range(12):
            x = 80 + off + k * 92
            if 70 < x < W - 70: pegs.append((x, y))
    pegs = np.array(pegs, float); PR = 11
    spin = [(300, 900, rng.choice([-1, 1]) * rng.uniform(1.5, 2.6)), (780, 1250, rng.choice([-1, 1]) * rng.uniform(1.5, 2.6))]
    pos = np.array([[90 + i * (W - 180) / max(1, n - 1) + rng.uniform(-8, 8), 430 + rng.uniform(-15, 15)] for i in range(n)])
    rng.shuffle(codes := list(codes))
    vel = np.array([[rng.uniform(-60, 60), 0] for _ in range(n)])
    done = np.zeros(n, bool); order = []; frames = []; f = 0; dt = 1 / FPS / 4; fin = None
    FINISH = 1720
    while True:
        hits = []
        if f >= 30 and fin is None:
            ang = f / FPS
            for _ in range(4):
                act = np.where(~done)[0]
                vel[act, 1] += G * dt; pos[act] += vel[act] * dt
                for i in act:
                    d = pos[i] - pegs; dist = np.hypot(d[:, 0], d[:, 1]); j = np.argmin(dist)
                    if dist[j] < r + PR:
                        nr = d[j] / dist[j]; pos[i] = pegs[j] + nr * (r + PR); vn = np.dot(vel[i], nr)
                        if vn < 0: vel[i] -= 1.55 * vn * nr; vel[i, 0] += rng.uniform(-40, 40); hits.append(int(i))
                    for sx, sy, w in spin:  # dönen çubuklar
                        a = ang * w; ux, uy = math.cos(a), math.sin(a)
                        rel = pos[i] - (sx, sy); t = np.clip(rel[0] * ux + rel[1] * uy, -140, 140)
                        cp = np.array([sx + ux * t, sy + uy * t]); dd = pos[i] - cp; ds = math.hypot(*dd)
                        if 0 < ds < r + 9:
                            nr = dd / ds; pos[i] = cp + nr * (r + 9); vn = np.dot(vel[i], nr)
                            if vn < 0: vel[i] -= 1.6 * vn * nr + nr * 120; hits.append(int(i))
                    if pos[i, 0] < 40 + r: pos[i, 0] = 40 + r; vel[i, 0] = abs(vel[i, 0]) * .8
                    if pos[i, 0] > W - 40 - r: pos[i, 0] = W - 40 - r; vel[i, 0] = -abs(vel[i, 0]) * .8
                    sp = math.hypot(*vel[i])
                    if sp > 900: vel[i] *= 900 / sp
                for ii in range(len(act)):
                    for jj in range(ii + 1, len(act)):
                        a_, b_ = act[ii], act[jj]; d = pos[b_] - pos[a_]; ds = math.hypot(*d)
                        if 0 < ds < 2 * r:
                            nr = d / ds; ov = 2 * r - ds; pos[a_] -= nr * ov / 2; pos[b_] += nr * ov / 2
                            rv = np.dot(vel[b_] - vel[a_], nr)
                            if rv < 0: vel[a_] += rv * nr; vel[b_] -= rv * nr
                for i in act:
                    if pos[i, 1] > FINISH and not done[i]: done[i] = True; order.append(int(i)); vel[i] = 0
            if len(order) >= min(3, n) and fin is None: fin = f
        frames.append((pos.copy(), done.copy(), list(order), sorted(set(hits)), f / FPS))
        f += 1
        if fin is not None and f - fin > 5 * FPS: break
        if f / FPS > max_t: return None
    return dict(frames=frames, order=order, fin=fin, codes=codes, pegs=pegs, spin=spin, r=r, finish=FINISH)

def render_race(sim, out_path, seed):
    frames, order, ff, C, pegs, spin, r = sim['frames'], sim['order'], sim['fin'], sim['codes'], sim['pegs'], sim['spin'], sim['r']
    hue = random.Random(seed).random()
    BG = _bg(glow=(20, 60, 110)); bd = ImageDraw.Draw(BG)
    for x, y in pegs: bd.ellipse([x - 11, y - 11, x + 11, y + 11], fill=(230, 235, 255), outline=(120, 140, 255), width=3)
    bd.rectangle([30, 430, 40, sim['finish']], fill=(120, 140, 255)); bd.rectangle([W - 40, 430, W - 30, sim['finish']], fill=(120, 140, 255))
    for k in range(0, W, 40):  # bitiş çizgisi (dama)
        for row in range(2):
            bd.rectangle([k, sim['finish'] + row * 20, k + 20, sim['finish'] + row * 20 + 20], fill='white' if (k // 40 + row) % 2 else 'black')
            bd.rectangle([k + 20, sim['finish'] + row * 20, k + 40, sim['finish'] + row * 20 + 20], fill='black' if (k // 40 + row) % 2 else 'white')
    p = _ffmpeg(out_path); conf = _confetti(seed); prev = frames[0][0]; hitlog = []; medal = lbs.MEDAL
    for f, (pos, done, ordr, hits, t) in enumerate(frames):
        vel = (pos - prev) * FPS; prev = pos
        if hits: hitlog.append(f)
        im = BG.copy(); dr = ImageDraw.Draw(im, 'RGBA')
        text_c(dr, (CX, 140), 'MARBLE RACE!', font('Black', 90), (255, 255, 255), 7)
        text_c(dr, (CX, 235), 'First to the bottom wins', font('Black', 50), (255, 196, 0), 5)
        for sx, sy, w in spin:
            a = t * w; ux, uy = math.cos(a), math.sin(a)
            dr.line([(sx - ux * 140, sy - uy * 140), (sx + ux * 140, sy + uy * 140)], fill=(255, 80, 140), width=18)
            dr.ellipse([sx - 14, sy - 14, sx + 14, sy + 14], fill='white')
        for i in range(len(C)):
            x, y = pos[i]
            if done[i]: continue
            bi = ball_img(C[i], 2 * r); im.paste(bi, (int(x - bi.width / 2), int(y - bi.height / 2)), bi)
            eyes(dr, x, y, r, vel[i][0], vel[i][1] + 1)
        # bitenler / podyum
        for k, i in enumerate(ordr[:3]):
            gx = CX + (k - 1) * 260; gy = 1830
            dr.ellipse([gx - 46, gy - 46, gx + 46, gy + 46], fill=medal[k])
            sm = circ_flag(C[i], 80); im.paste(sm, (int(gx - 40), int(gy - 40)), sm)
        if len(ordr) and len(ordr) < 3:
            text_c(dr, (CX, 340), f'{NAMES[C[ordr[-1]]]} FINISHED #{len(ordr)}!', font('Black', 48), (120, 255, 150), 5)
        if ff is not None and f >= ff + 8:
            k = (f - ff - 8) / 25; ov = Image.new('RGB', (W, H), (0, 0, 0)); im = Image.blend(im, ov, min(.6, k)); dr = ImageDraw.Draw(im, 'RGBA')
            _winner_screen(im, dr, C[ordr[0]], k, conf, (f - ff) / FPS, 'Race again? Comment your country!')
            for kk, i in enumerate(ordr[:3]):
                text_c(dr, (CX, 1500 + kk * 62), f'#{kk + 1}  {NAMES[C[i]]}', font('Black', 46), medal[kk], 4)
        p.stdin.write(im.tobytes())
    p.stdin.close(); p.wait()
    return dict(n=len(frames), bounces=hitlog, hits=[], elims=[], win=ff + 8)

# ======================================================================= SUMO TURNUVASI
def simulate_duel(rng, ra=62):
    """İki top bir platformda itişir, platformdan çıkan kaybeder. Kazananın indeksi ve kareler."""
    RP = 330; P = np.array([[CX - 170, 1000.], [CX + 170, 1000.]]); V = np.zeros((2, 2)); fr = []; dt = 1 / FPS / 4
    power = [rng.uniform(.85, 1.15), rng.uniform(.85, 1.15)]; out = None; f = 0
    while f < 8 * FPS:
        hit = False
        for _ in range(4):
            for k in range(2):
                tgt = P[1 - k] - P[k]; dist = math.hypot(*tgt) + 1e-6
                V[k] += tgt / dist * 900 * power[k] * dt + np.array([rng.uniform(-1, 1), rng.uniform(-1, 1)]) * 500 * dt
                V[k] *= .995
            P += V * dt
            d = P[1] - P[0]; ds = math.hypot(*d)
            if 0 < ds < 2 * ra:
                nr = d / ds; ov = 2 * ra - ds; P[0] -= nr * ov / 2; P[1] += nr * ov / 2
                rv = np.dot(V[1] - V[0], nr)
                if rv < 0:
                    imp = -rv * 1.6; V[0] -= nr * imp * power[1] / 1.0; V[1] += nr * imp * power[0] / 1.0; hit = True
            for k in range(2):
                if math.hypot(P[k, 0] - CX, P[k, 1] - 1000) > RP and out is None: out = k
        fr.append((P.copy(), hit, out))
        f += 1
        if out is not None and f > 0 and fr[-1][2] is not None and sum(1 for x in fr if x[2] is not None) > 18: break
    if out is None: out = int(math.hypot(P[0, 0] - CX, P[0, 1] - 1000) > math.hypot(P[1, 0] - CX, P[1, 1] - 1000))
    return 1 - out, fr

def simulate_sumo(seed, codes):
    rng = random.Random(seed); codes = list(codes)[:8]; rng.shuffle(codes)
    rounds = [codes]; duels = []
    cur = codes
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            w, fr = simulate_duel(rng)
            duels.append((cur[i], cur[i + 1], fr, cur[i + w], len(rounds)))
            nxt.append(cur[i + w])
        rounds.append(nxt); cur = nxt
    return dict(rounds=rounds, duels=duels, winner=cur[0], codes=codes)

def render_sumo(sim, out_path, seed):
    BG = _bg(glow=(110, 40, 30), cy=1000); bd = ImageDraw.Draw(BG)
    bd.ellipse([CX - 345, 655, CX + 345, 1345], fill=(60, 40, 30)); bd.ellipse([CX - 330, 670, CX + 330, 1330], fill=(225, 190, 130))
    bd.ellipse([CX - 330, 670, CX + 330, 1330], outline=(255, 255, 255), width=10)
    bd.line([(CX - 60, 1000), (CX - 60 + 0, 1000)], fill='black')
    for x in (CX - 60, CX + 60): bd.line([(x, 960), (x, 1040)], fill=(80, 50, 30), width=8)
    p = _ffmpeg(out_path); conf = _confetti(seed); hitlog, elims = [], []; fnum = 0
    rnd_names = {1: 'QUARTER-FINAL', 2: 'SEMI-FINAL', 3: 'FINAL'}
    beaten = set()
    def frame_base(title2, a, b):
        im = BG.copy(); dr = ImageDraw.Draw(im, 'RGBA')
        text_c(dr, (CX, 130), 'SUMO TOURNAMENT!', font('Black', 84), (255, 255, 255), 7)
        text_c(dr, (CX, 225), 'Push your rival out of the ring', font('Black', 48), (255, 196, 0), 5)
        text_c(dr, (CX, 360), title2, font('Black', 56), (255, 120, 90), 5)
        text_c(dr, (CX, 470), f'{NAMES[a].upper()}  vs  {NAMES[b].upper()}', fit_font(dr, f'{NAMES[a].upper()}  vs  {NAMES[b].upper()}', 'Black', 60, 1000), (255, 255, 255), 5)
        # braket (alt kısım)
        for k, c in enumerate(sim['codes']):
            gx = 80 + k * 131; gy = 1560
            sm = circ_flag(c, 74)
            if c in beaten: sm = Image.blend(Image.new('RGBA', sm.size, (12, 10, 30, 255)), sm, .3); sm.putalpha(circ_flag(c, 74).getchannel('A'))
            im.paste(sm, (int(gx - 37), int(gy - 37)), sm)
        alive = [c for c in sim['codes'] if c not in beaten]
        text_c(dr, (CX, 1680), f'{len(alive)} LEFT IN THE TOURNAMENT', font('Black', 40), (255, 255, 255), 4)
        return im, dr
    for di, (a, b, fr, w, rnd) in enumerate(sim['duels']):
        title = rnd_names.get(rnd + (3 - len(sim['rounds']) + 1), 'ROUND')
        # giriş (0.6 sn)
        for k in range(18):
            im, dr = frame_base(title, a, b)
            P = fr[0][0]
            for idx, c in enumerate((a, b)):
                bi = ball_img(c, 124); im.paste(bi, (int(P[idx][0] - bi.width / 2), int(P[idx][1] - bi.height / 2)), bi)
                eyes(dr, P[idx][0], P[idx][1], 62, 1 if idx == 0 else -1, 0)
            text_c(dr, (CX, 1000 - 160), 'READY?' if k < 12 else 'GO!', font('Black', 90), (255, 196, 0), 6)
            p.stdin.write(im.tobytes()); fnum += 1
        prevP = fr[0][0]
        for (P, hit, out) in fr:
            im, dr = frame_base(title, a, b); vel = (P - prevP) * FPS; prevP = P
            if hit: hitlog.append(fnum)
            for idx, c in enumerate((a, b)):
                bi = ball_img(c, 124); im.paste(bi, (int(P[idx][0] - bi.width / 2), int(P[idx][1] - bi.height / 2)), bi)
                eyes(dr, P[idx][0], P[idx][1], 62, P[1 - idx][0] - P[idx][0], P[1 - idx][1] - P[idx][1], scared=out == idx)
            p.stdin.write(im.tobytes()); fnum += 1
        loser = b if w == a else a; beaten.add(loser); elims.append(fnum)
        for k in range(24):  # sonuç
            im, dr = frame_base(title, a, b)
            bi = ball_img(w, 120); im.paste(bi, (int(CX - bi.width / 2), int(1000 - bi.height / 2)), bi); eyes(dr, CX, 1000, 60, 0, -1)
            text_c(dr, (CX, 1000 - 170), f'{NAMES[w].upper()} WINS!', fit_font(dr, f'{NAMES[w].upper()} WINS!', 'Black', 80, 1000), (120, 255, 150), 6)
            p.stdin.write(im.tobytes()); fnum += 1
    win_f = fnum
    for k in range(5 * FPS):
        im = BG.copy(); im = Image.blend(im, Image.new('RGB', (W, H)), .5); dr = ImageDraw.Draw(im, 'RGBA')
        text_c(dr, (CX, 130), 'SUMO CHAMPION!', font('Black', 90), (255, 196, 0), 7)
        _winner_screen(im, dr, sim['winner'], k / 25, conf, k / FPS, 'Who should fight next? Comment!')
        p.stdin.write(im.tobytes()); fnum += 1
    p.stdin.close(); p.wait()
    return dict(n=fnum, bounces=hitlog, hits=hitlog, elims=elims, win=win_f)

# ======================================================================= PENALTI ATIŞLARI
GOAL_L, GOAL_R, GOAL_T, GOAL_B = 170, W - 170, 620, 1010

def simulate_penalties(seed, home, away):
    rng = random.Random(seed); kicks = []; sc = [0, 0]; k = 0
    skill = {home: rng.uniform(.68, .82), away: rng.uniform(.68, .82)}
    while True:
        team = k % 2; shooter = (home, away)[team]
        tx = rng.uniform(GOAL_L + 50, GOAL_R - 50); ty = rng.uniform(GOAL_T + 50, GOAL_B - 40)
        r_ = rng.random()
        if r_ < .07: res = 'miss'; tx = rng.choice([GOAL_L - 60, GOAL_R + 60]); ty = rng.uniform(GOAL_T - 40, GOAL_B - 60)
        elif r_ < .07 + (1 - skill[shooter]): res = 'save'
        else: res = 'goal'
        if res == 'save': kx = tx + rng.uniform(-30, 30)
        else: kx = rng.choice([GOAL_L + 100, CX, GOAL_R - 100]) if res == 'miss' else (GOAL_L + GOAL_R - tx + rng.uniform(-120, 120))
        kx = min(max(kx, GOAL_L + 60), GOAL_R - 60)
        if res == 'goal': sc[team] += 1
        kicks.append(dict(team=team, tx=tx, ty=ty, kx=kx, res=res))
        k += 1
        na, nb = len([x for x in kicks if x['team'] == 0]), len([x for x in kicks if x['team'] == 1])
        if k <= 10:  # ilk 5'er: matematiksel olarak bitti mi?
            if sc[0] > sc[1] + (5 - nb) or sc[1] > sc[0] + (5 - na): break
            if k == 10 and sc[0] != sc[1]: break
        elif na == nb and sc[0] != sc[1]: break
        if k > 24: break
    return dict(kicks=kicks, score=tuple(sc), winner=home if sc[0] > sc[1] else away)

def render_penalties(home, away, sim, out_path, seed):
    BG = _bg(top=(10, 20, 30), glow=(20, 80, 60), cy=900); bd = ImageDraw.Draw(BG)
    bd.rectangle([0, 1010, W, 1700], fill=(40, 150, 75))
    for i in range(8): bd.rectangle([0, 1010 + i * 86, W, 1010 + i * 86 + 43], fill=(46, 165, 84))
    bd.rectangle([GOAL_L - 14, GOAL_T - 14, GOAL_R + 14, GOAL_B], fill=(240, 240, 240))
    bd.rectangle([GOAL_L, GOAL_T, GOAL_R, GOAL_B], fill=(25, 45, 40))
    for x in range(GOAL_L, GOAL_R, 24): bd.line([(x, GOAL_T), (x, GOAL_B)], fill=(170, 190, 185), width=1)
    for y in range(GOAL_T, GOAL_B, 24): bd.line([(GOAL_L, y), (GOAL_R, y)], fill=(170, 190, 185), width=1)
    bd.line([(GOAL_L - 120, GOAL_B), (GOAL_R + 120, GOAL_B)], fill='white', width=6)
    bd.ellipse([CX - 8, 1500 - 8, CX + 8, 1500 + 8], fill='white')
    fbB = Image.new('RGBA', (64, 64), (0, 0, 0, 0)); fd = ImageDraw.Draw(fbB)
    fd.ellipse([1, 1, 62, 62], fill='white', outline='black', width=3); fd.regular_polygon((32, 32, 10), 5, fill='black')
    p = _ffmpeg(out_path); conf = _confetti(seed); kicklog, goals = [], []; fnum = 0
    results = []; names = (home, away)
    def base(shooter_team):
        im = BG.copy(); dr = ImageDraw.Draw(im, 'RGBA')
        text_c(dr, (CX, 110), 'PENALTY SHOOTOUT!', font('Black', 82), (255, 255, 255), 7)
        for t in range(2):  # skor satırları
            y = 230 + t * 110; c = names[t]
            sm = circ_flag(c, 70); im.paste(sm, (70, int(y - 35)), sm)
            dr.text((160, y), NAMES[c].upper(), font=font('Black', 40), fill='white', anchor='lm')
            mine = [r for r in results if r[0] == t]
            for j in range(max(5, len(mine))):
                cx_ = 640 + j * 62 if j < 7 else 640 + 6 * 62
                col = (60, 60, 80) if j >= len(mine) else ((60, 220, 110) if mine[j][1] == 'goal' else (230, 60, 70))
                dr.ellipse([cx_ - 22, y - 22, cx_ + 22, y + 22], fill=col, outline='white', width=3)
            sc = sum(1 for r in results if r[0] == t and r[1] == 'goal')
            text_c(dr, (W - 60, y), str(sc), font('Black', 64), (255, 196, 0), 4)
        if shooter_team is not None:
            text_c(dr, (CX, 470), f'{NAMES[names[shooter_team]].upper()} TO SHOOT', font('Black', 46), (255, 196, 0), 4)
        return im, dr
    for kk in sim['kicks']:
        t = kk['team']; shooter, keeper = names[t], names[1 - t]
        N1, N2, N3 = 18, 16, 26  # hazırlık, şut, sonuç
        for f in range(N1 + N2 + N3):
            im, dr = base(t)
            if f < N1: bx, by, kx = CX, 1500, CX + 30 * math.sin(f / 3)
            else:
                u = min(1, (f - N1) / N2); e = u * u * (3 - 2 * u)
                bx = CX + (kk['tx'] - CX) * e; by = 1500 + (kk['ty'] - 1500) * e - 160 * math.sin(math.pi * e) * .3
                kx = CX + (kk['kx'] - CX) * min(1, (f - N1) / (N2 * .7))
                if f == N1: kicklog.append(fnum)
            if f >= N1 + N2 and kk['res'] == 'save':  # top kaleciden seker
                v = (f - N1 - N2); bx = kk['tx'] + (kk['tx'] - CX) * .02 * v; by = kk['ty'] + 18 * v
            # kaleci
            ky = GOAL_B - 90 - (60 if f >= N1 else 0) * min(1, max(0, (f - N1) / N2))
            kb = ball_img(keeper, 150); im.paste(kb, (int(kx - kb.width / 2), int(ky - kb.height / 2)), kb)
            eyes(dr, kx, ky, 75, bx - kx, by - ky, scared=f >= N1)
            dr.rounded_rectangle([kx - 95, ky + 40, kx - 60, ky + 70], radius=10, fill=(255, 196, 0))
            dr.rounded_rectangle([kx + 60, ky + 40, kx + 95, ky + 70], radius=10, fill=(255, 196, 0))
            # şutçu
            sx_ = CX - 40 + (min(f, N1) / N1) * 0; sb = ball_img(shooter, 170)
            im.paste(sb, (int(sx_ - 120 - sb.width / 2), int(1640 - sb.height / 2)), sb)
            eyes(dr, sx_ - 120, 1640, 85, 1, -1)
            bs = int(64 * (1 - .45 * min(1, max(0, (f - N1) / N2)))); fb2 = fbB.resize((bs, bs))
            im.paste(fb2, (int(bx - bs / 2), int(by - bs / 2)), fb2)
            if f >= N1 + N2:
                if f == N1 + N2:
                    results.append((t, kk['res']))
                    if kk['res'] == 'goal': goals.append(fnum)
                msg, col = {'goal': ('GOAL!', (255, 196, 0)), 'save': ('SAVED!', (80, 200, 255)), 'miss': ('MISSED!', (230, 60, 70))}[kk['res']]
                s = min(1, (f - N1 - N2) / 5)
                text_c(dr, (CX, 1240), msg, font('Black', int(60 + 110 * s)), col, 8)
            p.stdin.write(im.tobytes()); fnum += 1
    win_f = fnum
    for k in range(5 * FPS):
        im, dr = base(None); im = Image.blend(im, Image.new('RGB', (W, H)), .55); dr = ImageDraw.Draw(im, 'RGBA')
        sc = sim['score']; text_c(dr, (CX, 420), f'{NAMES[home]} {sc[0]} - {sc[1]} {NAMES[away]}', fit_font(dr, f'{NAMES[home]} {sc[0]} - {sc[1]} {NAMES[away]}', 'Black', 64, 1000), (255, 255, 255), 6)
        _winner_screen(im, dr, sim['winner'], k / 25, conf, k / FPS, 'Who should take penalties next?')
        p.stdin.write(im.tobytes()); fnum += 1
    p.stdin.close(); p.wait()
    return dict(n=fnum, bounces=kicklog, elims=goals, win=win_f)

# ======================================================================= ortak giriş noktası
def make_extra(style, seed, out_dir, codes=None, pair=None):
    """style: race | sumo | penalty. (video_yolu, meta, ep) döndürür."""
    if style in ('race', 'elim'):  # uzun engebeli misket pistleri (marble.py)
        import marble
        return marble.make(style, seed, out_dir, codes)
    rng = random.Random(seed); out_dir.mkdir(exist_ok=True)
    raw, wav, final = out_dir / 'raw.mp4', out_dir / 'audio.wav', out_dir / f'lbs_{seed}.mp4'
    tags = 'country balls,countryballs,marble race,simulation,satisfying,which country wins,last ball standing'
    if style == 'race':
        codes = list(codes) if codes else rng.sample(list(NAMES), rng.choice([10, 12, 12, 14]))
        for k in range(200):
            sim = simulate_race(seed * 1000 + k, codes)
            if sim and 14 * FPS <= sim['fin'] <= 40 * FPS: break
        cues = render_race(sim, raw, seed); lbs.make_audio(cues, wav, seed)
        top = [NAMES[sim['codes'][i]] for i in sim['order'][:3]]
        title = rng.choice([f'{len(codes)} Countries Marble Race 🏁 Who Wins?', 'Country Ball Marble Race 🏁 First To The Bottom Wins',
                            'Plinko Race: Which Country Is Fastest? 🏁'])
        desc = (f"🏁 {len(codes)} country balls race down a plinko board — first to the bottom wins!\n"
                "Physics decides everything. Which country did you cheer for? 👇\n🔔 Subscribe for a new battle every day.\n\n"
                f"Countries: {', '.join(NAMES[c] for c in codes)}\n\n#countryballs #marblerace #plinko #simulation #satisfying #shorts")
        podium = ' > '.join(top)
    elif style == 'sumo':
        codes = list(codes)[:8] if codes and len(codes) >= 8 else (list(codes or []) + rng.sample([c for c in NAMES if c not in (codes or [])], 8 - len(codes or [])))
        sim = simulate_sumo(seed, codes)
        cues = render_sumo(sim, raw, seed); lbs.make_audio(cues, wav, seed)
        title = rng.choice(['Country Ball SUMO Tournament 🤼 Who Is The Champion?', '8 Countries, 1 Sumo Ring 🤼 Who Wins?',
                            'Sumo Knockout: Push Them Out! 🤼'])
        desc = ("🤼 8 country balls, one sumo ring, knockout tournament! Push your rival out of the ring to advance.\n"
                "Who should be in the next tournament? Comment below! 👇\n🔔 Subscribe for a new battle every day.\n\n"
                f"Countries: {', '.join(NAMES[c] for c in sim['codes'])}\n\n#countryballs #sumo #tournament #simulation #shorts")
        podium = f"Şampiyon: {NAMES[sim['winner']]}"
    else:  # penalty
        home, away = pair if pair else rng.sample(lbs.THEMES['football'][1], 2)
        for c in (home, away):
            if c not in NAMES: NAMES[c] = lbs.EXTRA_NAMES.get(c, c.upper())
        sim = simulate_penalties(seed, home, away)
        cues = render_penalties(home, away, sim, raw, seed); lbs.make_match_audio(cues, wav, seed)
        a, b = NAMES[home], NAMES[away]
        title = rng.choice([f'{a} vs {b} Penalty Shootout ⚽🥅', f'Penalty Shootout: {a} vs {b} — Who Wins? ⚽',
                            f'{a} vs {b}: Penalties Decide It All 😱⚽'])
        desc = (f"⚽ Penalty shootout: {a} vs {b}! Country balls take the penalties — goal, save or miss?\n"
                "Which team should shoot next? Comment below! 👇\n🔔 Subscribe for a new battle every day.\n\n"
                "This is an animated simulation for fun, not a real match result.\n\n"
                f"#{a.replace(' ', '')} #{b.replace(' ', '')} #penalty #football #countryballs #shorts")
        podium = f"{a} {sim['score'][0]} - {sim['score'][1]} {b}"
        tags = f'{a} vs {b},penalty shootout,penalties,football,soccer,country balls,countryballs,simulation'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)], check=True)
    raw.unlink(); wav.unlink()
    meta = dict(title=title + ' #shorts', description=desc, tags=tags, podium=podium)
    return final, meta, dict(mode=style, seed=seed)
