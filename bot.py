"""Telegram istek botu: Telegram'dan menüyle mod seçilir, ülke/takım yazılır, video üretilip gönderilir.

GitHub Actions birkaç dakikada bir çalıştırır (.github/workflows/bot.yml).
Sadece TELEGRAM_CHAT_ID'deki kişiden gelen istekleri dinler.
"""
import json, os, random, re, subprocess, sys, unicodedata
from pathlib import Path
import requests
import lbs

TOKEN, CHAT = os.environ['TELEGRAM_BOT_TOKEN'], str(os.environ['TELEGRAM_CHAT_ID'])
API = f'https://api.telegram.org/bot{TOKEN}/'

def api(method, **data):
    files = data.pop('files', None)
    r = requests.post(API + method, data=data, files=files, timeout=300)
    j = r.json()
    if not j.get('ok'): print('telegram hata:', method, j.get('description'))
    return j

def send(text, **kw): return api('sendMessage', chat_id=CHAT, text=text, **kw)

# ---- ülke adları (Türkçe / İngilizce / kod) ----
EXTRA = {'hr': 'Croatia', 'rs': 'Serbia', 'ge': 'Georgia', 'ir': 'Iran', 'qa': 'Qatar', 'uy': 'Uruguay',
         'cz': 'Czechia', 'ro': 'Romania', 'hu': 'Hungary', 'sk': 'Slovakia', 'sc': 'Scotland', 'gb-sct': 'Scotland',
         'gb-wls': 'Wales', 'gb-eng': 'England', 'dz': 'Algeria', 'tn': 'Tunisia', 'sn': 'Senegal', 'gh': 'Ghana',
         'cm': 'Cameroon', 'pe': 'Peru', 'ec': 'Ecuador', 'py': 'Paraguay', 've': 'Venezuela', 'kz': 'Kazakhstan',
         'uz': 'Uzbekistan', 'il': 'Israel', 'ae': 'UAE', 'iq': 'Iraq', 'al': 'Albania', 'ba': 'Bosnia', 'mk': 'North Macedonia',
         'si': 'Slovenia', 'is': 'Iceland', 'cy': 'Cyprus', 'th': 'Thailand', 'vn': 'Vietnam', 'ph': 'Philippines', 'nz': 'New Zealand'}
TR = {'turkiye': 'tr', 'turkey': 'tr', 'abd': 'us', 'amerika': 'us', 'usa': 'us', 'almanya': 'de', 'japonya': 'jp',
      'brezilya': 'br', 'fransa': 'fr', 'ingiltere': 'gb-eng', 'birlesik krallik': 'gb', 'italya': 'it', 'ispanya': 'es',
      'guney kore': 'kr', 'kore': 'kr', 'cin': 'cn', 'hindistan': 'in', 'rusya': 'ru', 'kanada': 'ca', 'meksika': 'mx',
      'azerbaycan': 'az', 'hollanda': 'nl', 'suudi arabistan': 'sa', 'arjantin': 'ar', 'polonya': 'pl', 'portekiz': 'pt',
      'isvec': 'se', 'yunanistan': 'gr', 'misir': 'eg', 'endonezya': 'id', 'avustralya': 'au', 'guney afrika': 'za',
      'nijerya': 'ng', 'ukrayna': 'ua', 'isvicre': 'ch', 'belcika': 'be', 'avusturya': 'at', 'norvec': 'no',
      'danimarka': 'dk', 'finlandiya': 'fi', 'irlanda': 'ie', 'fas': 'ma', 'pakistan': 'pk', 'kolombiya': 'co',
      'sili': 'cl', 'hirvatistan': 'hr', 'sirbistan': 'rs', 'gurcistan': 'ge', 'iran': 'ir', 'katar': 'qa',
      'uruguay': 'uy', 'cekya': 'cz', 'cek cumhuriyeti': 'cz', 'romanya': 'ro', 'macaristan': 'hu', 'slovakya': 'sk',
      'iskocya': 'gb-sct', 'galler': 'gb-wls', 'cezayir': 'dz', 'tunus': 'tn', 'senegal': 'sn', 'gana': 'gh',
      'kamerun': 'cm', 'peru': 'pe', 'ekvador': 'ec', 'paraguay': 'py', 'venezuela': 've', 'kazakistan': 'kz',
      'ozbekistan': 'uz', 'israil': 'il', 'bae': 'ae', 'birlesik arap emirlikleri': 'ae', 'irak': 'iq',
      'arnavutluk': 'al', 'bosna': 'ba', 'bosna hersek': 'ba', 'kuzey makedonya': 'mk', 'slovenya': 'si',
      'izlanda': 'is', 'kibris': 'cy', 'tayland': 'th', 'vietnam': 'vn', 'filipinler': 'ph', 'yeni zelanda': 'nz'}

def norm(s):
    s = s.replace('İ', 'i').replace('I', 'ı').lower().replace('ı', 'i')
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).strip()

ALIASES = {}
for c, n in {**lbs.NAMES, **EXTRA}.items():
    ALIASES[norm(n)] = c; ALIASES[c] = c
for k, c in TR.items(): ALIASES[k] = c
ALIASES['england'] = 'gb-eng'; ALIASES['uk'] = 'gb'

def parse_countries(text):
    """'Türkiye, Güney Kore ve İspanya' -> ['tr','kr','es'] ; tanınmayanları da döndürür"""
    words = re.split(r'[\s,;/]+|\bve\b|\bvs\b|-', norm(text))
    words = [w for w in words if w]
    out, bad, i = [], [], 0
    while i < len(words):
        for L in (3, 2, 1):
            key = ' '.join(words[i:i + L])
            if key in ALIASES:
                c = ALIASES[key]
                if c not in out: out.append(c)
                i += L; break
        else:
            bad.append(words[i]); i += 1
    return out, bad

def ensure_name(c):
    if c not in lbs.NAMES: lbs.NAMES[c] = EXTRA.get(c, {'gb-eng': 'England'}.get(c, c.upper()))

# ---- menü ----
MENU = [('⚽ Maç', 'match'), ('🏆 Son Kalan Kazanır', 'classic'), ('🏃 İlk Kaçan Kazanır', 'escape'),
        ('⚔️ Battle Royale', 'hp'), ('🔻 Daralan Arena', 'shrink'), ('🎈 Büyüyen Toplar', 'grow'),
        ('🚪 İki Çıkış', 'double'), ('🌍 Dev Arena (40 ülke)', 'mega'), ('🎲 Sürpriz', 'random')]
KEYWORDS = {'mac': 'match', 'match': 'match', 'klasik': 'classic', 'son kalan': 'classic', 'classic': 'classic',
            'kacis': 'escape', 'ilk kacan': 'escape', 'escape': 'escape', 'battle': 'hp', 'battle royale': 'hp',
            'savas': 'hp', 'daralan': 'shrink', 'shrink': 'shrink', 'buyuyen': 'grow', 'grow': 'grow',
            'iki cikis': 'double', 'double': 'double', 'dev': 'mega', 'dev arena': 'mega', 'mega': 'mega',
            'surpriz': 'random', 'rastgele': 'random', 'random': 'random'}
HELP = {'match': '⚽ Hangi maç? İki takımı yaz.\nÖrnek:  maç Türkiye İspanya',
        'mega': '🌍 Dev Arena: 40 ülkenin hepsi. Başlatmak için yaz:  dev arena',
        'random': '🎲 Sürpriz video için yaz:  sürpriz'}
NAMES_TR = dict((v, k) for k, v in MENU)

def menu():
    kb = {'inline_keyboard': [[{'text': t, 'callback_data': 'm:' + m}] for t, m in MENU]}
    send('Ne tür bir video istiyorsun? Birini seç 👇\n(İstediğin zaman "menü" yazarak bu listeyi açabilirsin.)',
         reply_markup=json.dumps(kb))

def mode_help(m):
    if m in HELP: return send(HELP[m])
    word = {'classic': 'klasik', 'escape': 'kaçış', 'hp': 'battle', 'shrink': 'daralan', 'grow': 'büyüyen', 'double': 'iki çıkış'}[m]
    kb = {'inline_keyboard': [[{'text': '🎲 Rastgele ülkelerle yap', 'callback_data': 'g:' + m}]]}
    send(f'{NAMES_TR.get(m, m)} seçildi.\nİstersen ülkeleri yaz (4–18 ülke):\n  {word} Türkiye Almanya Fransa Japonya Brezilya\n'
         f'ya da aşağıdaki butona bas.', reply_markup=json.dumps(kb))

def make(mode, codes=None, match=None):
    seed = random.randrange(1, 10 ** 6); out = Path('out'); out.mkdir(exist_ok=True)
    send('⏳ Hazırlıyorum, birkaç dakika sürer...')
    raw, wav, final = out / 'raw.mp4', out / 'audio.wav', out / f'lbs_{seed}.mp4'
    if match:
        home, away = match
        for c in match: ensure_name(c)
        sim = lbs.pick_match(seed, home, away)
        cues = lbs.render_match(home, away, sim, raw, seed); lbs.make_match_audio(cues, wav, seed)
        meta = lbs.match_metadata(home, away, sim, False); ep = dict(mode='match', seed=seed)
    else:
        if mode == 'random': mode = random.choice(lbs.MODE_ORDER)
        for c in codes or []: ensure_name(c)
        ep, sim = lbs.pick_episode(seed, mode, codes)
        cues, place, winner = lbs.render(ep, sim, raw); lbs.make_audio(cues, wav, seed)
        meta = lbs.metadata(ep, place, winner)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-i', str(wav), '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)], check=True)
    raw.unlink(); wav.unlink()
    lbs.send_telegram(final, meta, ep)

def handle_text(text):
    t = norm(text)
    if t in ('/start', 'menu', '/menu', 'menü', 'basla', 'yardim', '/help') or t.startswith('/start'):
        return menu()
    mode, rest = None, ''
    for k in sorted(KEYWORDS, key=len, reverse=True):
        if t == k or t.startswith(k + ' '):
            mode, rest = KEYWORDS[k], text.strip()[len(k):]; break
    if not mode:
        return send('Anlayamadım 🤔 "menü" yaz, seçenekleri göstereyim.')
    if mode == 'match':
        codes, bad = parse_countries(rest)
        if len(codes) != 2:
            return send('Maç için 2 takım yazmalısın. Örnek:  maç Türkiye İspanya' + (f'\nTanımadığım: {" ".join(bad)}' if bad else ''))
        return make('match', match=codes)
    if mode in ('mega', 'random') and not rest.strip():
        return make(mode)
    codes, bad = parse_countries(rest)
    if bad: send(f'Şunları tanıyamadım, onlarsız devam ediyorum: {", ".join(bad)}')
    if codes and not (4 <= len(codes) <= (40 if mode == 'mega' else 18)):
        return send('Bu mod için 4–18 ülke yazmalısın (Dev Arena\'da 40\'a kadar).')
    make(mode, codes or None)

def main():
    upd = api('getUpdates', timeout=0).get('result', [])
    if not upd: print('yeni mesaj yok'); return
    last = upd[-1]['update_id']
    api('getUpdates', offset=last + 1, timeout=0)        # mesajları "okundu" say (tekrar işlenmesin)
    for u in upd:
        try:
            if 'callback_query' in u:
                q = u['callback_query']
                if str(q['message']['chat']['id']) != CHAT: continue
                api('answerCallbackQuery', callback_query_id=q['id'])
                kind, m = q['data'].split(':', 1)
                if kind == 'm':
                    if m in ('mega', 'random'): make(m)
                    else: mode_help(m)
                elif kind == 'g': make(m)
            elif 'message' in u and 'text' in u['message']:
                if str(u['message']['chat']['id']) != CHAT: continue
                handle_text(u['message']['text'])
        except Exception as e:
            print('hata:', repr(e)); send(f'⚠️ Bir sorun oldu: {e}')

if __name__ == '__main__':
    main()
