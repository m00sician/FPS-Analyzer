"""
Verification Pass — "halber Pass" nach dem Vorpass.

ZWECK
Der Vorpass dekodiert aus Geschwindigkeitsgründen auf 128×128 mit
`flags=neighbor` (Punkt-Sampling). Aus 1080p/4K bleibt davon ein Bruchteil
der Pixel übrig. In sehr ruhigen Szenen (driftende Wolken, langsamer
Kameraschwenk) fällt die echte Bewegung dabei unter den Detektor-Threshold —
Ergebnis sind Sektionen mit fälschlich 0 fps.

Dieser Pass prüft NUR die verdächtigen Sektionen nach (fps≈0, ≥1s) und
korrigiert sie. Alles andere bleibt unangetastet.


WARUM NICHT EINFACH "HÖHERE AUFLÖSUNG + NIEDRIGERER THRESHOLD"
Gemessen: die absolute Diff-Größe hängt stark vom Downscale-Filter ab
(AREA mittelt Rauschen weg und liefert ~4× kleinere Werte als NEAREST).
Ein absoluter Threshold ist deshalb prinzipiell fragil — egal bei welcher
Auflösung. Der Pass entscheidet daher über RELATIVE Kriterien.


DIE DREI SIGNALE (alle auf 256px AREA gemessen, echtes h264-Testmaterial)

  Region                      std     medK1      medK30    frac(K1≈0)
  busy 60fps                29.52   0.0068918  0.0452575     0.00
  ruhige Wolken ECHT 60fps   6.88   0.0000730  0.0022819     0.07
  eingefroren SOLL 0 fps     6.88   0.0000016  0.0000847     0.85
  schwarz SOLL 0 fps         0.00   0.0000000  0.0000000     1.00

  K1  = Diff zum direkten Nachbarframe
  K30 = Diff über 30 Frames Abstand (halbe Sekunde)

  1) frac(K1≈0) — Anteil praktisch bit-identischer Nachbarpaare.
     Das ist das SCHÄRFSTE Signal: 0.07 (echte Bewegung) vs 0.85 (eingefroren).
     Grund: h264/HEVC kodiert einen echt wiederholten Frame als Skip-Blocks,
     er dekodiert bit-identisch. Subtile echte Bewegung tut das nie.

  2) Wachstum über die Zeitbasis (K30/K1) — Rückfallebene für den Fall,
     dass Duplikate NICHT bit-identisch sind (z.B. Rauschen vor dem Encode,
     Analog-Capture). Ein eingefrorenes Bild bleibt über 30 Frames genauso
     ähnlich wie über 1; echte Bewegung summiert sich auf.
     ACHTUNG: unbrauchbar wenn K1≈0 (Division durch ~0 → Ratio explodiert),
     deshalb läuft Signal 1 zuerst.

  3) std — einfarbige Frames (Fade, Blackscreen, Ladescreen) sind echte
     0-fps-Abschnitte und werden sofort bestätigt.


BLOCKWEISE, NICHT SEKTIONSWEIT
Eine verdächtige Sektion kann eine Szenengrenze enthalten (z.B. eingefroren →
Blackscreen). Ein Wachstumstest über die ganze Sektion misst dann den
Szenenwechsel statt der Bewegung und liefert ein massives False Positive
(gemessen: Ratio 285237× auf einer in Wahrheit eingefrorenen Sektion).
Deshalb wird jede Sektion in ~1s-Blöcke zerlegt und jeder Block eigenständig
entschieden.

Danach werden fps_seq/ft_seq aus den korrigierten dup_flags KOMPLETT neu
berechnet — nicht nur im Abschnitt, weil das gleitende 1s-Fenster bis zu
eine Sekunde über die Sektionsgrenze hinausreicht.


GRENZE — WANN DER PASS DIE RATE NICHT BESTIMMEN KANN
Gemessen an echtem h264-Testmaterial: in SEHR ruhigen, detailarmen Szenen
kann der Encoder das Duplikat-Signal vollständig zerstören. Beispiel: echtes
30fps-Material (jeder Frame doppelt) in einer Wolkenszene —

    Arbeitsauflösung   medK1 Duplikat-Paare   medK1 echte Paare   Trennung
    128                     0.00008318            0.00009143        1.10×
    256                     0.00008066            0.00008982        1.11×
    512                     0.00008553            0.00009203        1.08×
    1080                    0.00008520            0.00009221        1.08×

Die Quantisierungs-Streuung des Encoders (~8e-5) ist größer als der
Unterschied zwischen Duplikat und echtem Frame. Höhere Auflösung hilft NICHT
(bis 1080px getestet), Phasenkorrelation ebenfalls nicht (0.01px gemessen bei
0.1px echter Drift). Die Information ist im Encode nicht mehr enthalten.

Konsequenz: der Pass beantwortet ZUVERLÄSSIG "ist das wirklich 0 fps?"
(ja/nein), aber nicht immer "wie hoch ist die Rate genau?". Solche Blöcke
werden über den Encoder-Rauschboden erkannt (aus sicher eingefrorenen Blöcken
desselben Videos kalibriert) und als unsicher markiert — sichtbar im Log und
im Report unter 'uncertain'. Per `uncertain_action` einstellbar, ob sie
korrigiert werden ('correct', Default) oder auf 0 fps bleiben ('keep').
"""

import subprocess
import numpy as np


# ── Tunables ─────────────────────────────────────────────────────────────────

WORK_SIZE = 256           # Arbeitsauflösung (Vorpass: 128 NEAREST)
MIN_SECONDS = 1.0         # kürzere 0-fps-Abschnitte ignorieren (echte Drops)
FPS_SUSPECT = 1.0         # fps <= diesem Wert gilt als "0 fps"
UNIFORM_STD = 3.0         # Frame-std darunter = einfarbig → echt 0 fps
NEAR_ZERO_MAD = 2e-5      # K1 darunter = praktisch bit-identisch (Duplikat)
DUP_FRAC_CONFIRM = 0.50   # ab diesem Anteil bit-identischer Paare: 0 fps bestätigt
GROWTH_RATIO_MIN = 3.0    # Rückfallebene: ab hier gilt der Block als bewegt
PAD_SECONDS = 1.0         # Sektionen um je 1s erweitern (siehe find_suspect_sections)
CONFIDENT_NOISE_MULT = 20.0   # Bewegung gilt als sicher ab 20× Encoder-Rauschboden
ABS_CONFIDENT_K1 = 1e-3       # Fallback ohne Referenzblock: K1 darüber = sicher
UNCERTAIN_ACTION = 'correct'  # 'correct' | 'keep' — Verhalten bei unsicherer Rate
DECODE_CHUNK = 900        # max. Frames pro Decode-Aufruf (RAM-Deckel, 900≈59MB@256px)


# ── Sektionen finden ─────────────────────────────────────────────────────────

def find_suspect_sections(fps_seq, source_fps,
                          min_seconds=MIN_SECONDS,
                          fps_suspect=FPS_SUSPECT,
                          fade_excluded=None,
                          pad_seconds=PAD_SECONDS):
    """
    Findet zusammenhängende Läufe mit fps <= fps_suspect von mindestens
    min_seconds Länge. Fade-ausgeschlossene Frames zählen nicht als
    verdächtig — dort ist 0 fps gewollt.

    WICHTIG — PADDING: die fps stammen aus einem gleitenden 1s-Fenster. Am
    Rand einer fehldetektierten Szene fällt der Wert deshalb erst allmählich
    ab, d.h. die falschen dup_flags reichen bis zu 1s WEITER als der Bereich
    mit fps<=1. Ohne Erweiterung bleibt dieser Rand unkorrigiert und zieht
    das Ergebnis nach unten (gemessen: 29 fps Restfehler im Übergang).
    Jede Sektion wird daher um pad_seconds nach beiden Seiten erweitert;
    überlappende Sektionen werden zusammengefasst.

    Returns: Liste von (start_idx, end_idx_exclusive).
    """
    fade_excluded = fade_excluded or set()
    min_len = max(1, int(round(min_seconds * source_fps)))

    runs, start = [], None
    for i, v in enumerate(fps_seq):
        suspect = (v is not None and i not in fade_excluded and v <= fps_suspect)
        if suspect and start is None:
            start = i
        elif not suspect and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(fps_seq) - start >= min_len:
        runs.append((start, len(fps_seq)))

    if not runs:
        return []

    # Padding + Merge
    pad = int(round(pad_seconds * source_fps))
    n = len(fps_seq)
    padded = [(max(0, s - pad), min(n, e + pad)) for s, e in runs]
    merged = [padded[0]]
    for s, e in padded[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


# ── Decode ───────────────────────────────────────────────────────────────────

def _decode_section_gray(input_file, start_frame, n_frames, source_fps,
                         size=WORK_SIZE, use_nvdec=True):
    """
    Dekodiert [start_frame, start_frame+n_frames) als size×size-Graustufen.

    `flags=area` statt `neighbor`: Punkt-Sampling würfelt bei starkem
    Downscale einzelne Pixel heraus und ist gegenüber subtiler Bewegung
    faktisch blind; area mittelt korrekt über den Quellblock.

    Gibt Liste von float32-Arrays (0..255) zurück.
    """
    if n_frames <= 0:
        return []

    variants = ([['-hwaccel', 'cuda'], []] if use_nvdec else [[]])
    fb = size * size

    for hw in variants:
        cmd = ['ffmpeg', '-v', 'error', *hw]
        if start_frame > 0 and source_fps > 0:
            cmd += ['-ss', f'{start_frame / source_fps:.6f}']
        cmd += ['-i', input_file,
                '-frames:v', str(n_frames),
                '-vf', f'scale={size}:{size}:flags=area,format=gray',
                '-f', 'rawvideo', '-']
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL)
            out = []
            while True:
                buf = b''
                while len(buf) < fb:
                    chunk = proc.stdout.read(fb - len(buf))
                    if not chunk:
                        break
                    buf += chunk
                if len(buf) < fb:
                    break
                out.append(np.frombuffer(buf, dtype=np.uint8)
                             .reshape(size, size).astype(np.float32))
            try:
                proc.kill()
            except Exception:
                pass
            if out:
                return out
        except Exception:
            continue
    return []


def _mad(a, b):
    """Mean absolute difference, normiert auf 0..1."""
    return float(np.mean(np.abs(a - b)) / 255.0)


# ── Block-Entscheidung ───────────────────────────────────────────────────────

def classify_block(frames):
    """
    Entscheidet für EINEN ~1s-Block, ob er wirklich eingefroren ist.

    Returns dict mit:
        frozen    – True = 0 fps ist korrekt
        dup_flags – Liste[bool], len == len(frames)
        med_k1    – Median-Nachbardiff (für die Rauschboden-Kalibrierung)
        clean_split – True = sauberer Duplikat-Cluster gefunden (hohe Sicherheit)
        reason    – Klartext für das Log
    """
    n = len(frames)
    if n < 2:
        return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': 0.0,
                'clean_split': True, 'reason': 'zu kurz'}

    # ── Signal 3: einfarbig? ────────────────────────────────────────────
    med_std = float(np.median([f.std() for f in frames]))
    if med_std < UNIFORM_STD:
        return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': 0.0,
                'clean_split': True,
                'reason': f'einfarbig (std={med_std:.2f})'}

    k1 = np.array([_mad(frames[i - 1], frames[i]) for i in range(1, n)],
                  dtype=np.float64)
    med_k1 = float(np.median(k1))

    # ── Signal 1: Anteil bit-identischer Nachbarpaare ───────────────────
    near_zero = k1 < NEAR_ZERO_MAD
    frac_zero = float(near_zero.mean())

    if frac_zero >= DUP_FRAC_CONFIRM:
        # Überwiegend echte Duplikate → 0 fps bestätigt. Flags trotzdem pro
        # Frame: bei 30fps-Material ergibt das korrekt ~50% statt pauschal 100%.
        flags = [True] + [bool(z) for z in near_zero]
        return {'frozen': True, 'dup_flags': flags, 'med_k1': med_k1,
                'clean_split': True,
                'reason': f'{frac_zero*100:.0f}% bit-identische Paare → echt eingefroren'}

    # ── Signal 2: Wachstum über die Zeitbasis (Duplikate mit Rauschen) ──
    # Nur sinnvoll, wenn K1 nicht schon ~0 ist (siehe Modul-Docstring).
    ratio = None
    if med_k1 > NEAR_ZERO_MAD:
        k_far = min(30, n - 1)
        if k_far >= 5:
            far = [_mad(frames[a], frames[a + k_far]) for a in range(0, n - k_far)]
            ratio = float(np.median(far)) / max(med_k1, 1e-12)
            if ratio < GROWTH_RATIO_MIN:
                return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': med_k1,
                        'clean_split': True,
                        'reason': f'Diff wächst nur {ratio:.2f}× über {k_far} Frames '
                                  f'→ eingefrorenes Bild mit Rauschen'}

    # ── Block ist in Wahrheit bewegt → per Verteilung neu klassifizieren ─
    flags = [False] + [bool(z) for z in near_zero]
    clean_split = bool(near_zero.any())

    if not clean_split:
        s = np.sort(k1)
        gaps = np.diff(s)
        if len(gaps):
            i = int(np.argmax(gaps))
            lower_top, upper_bot = s[i], s[i + 1]
            lower_frac = (i + 1) / len(s)
            if upper_bot >= lower_top * 3.0 and 0.05 <= lower_frac <= 0.95:
                thr = (lower_top + upper_bot) / 2.0
                flags = [False] + [bool(m < thr) for m in k1]
                clean_split = True

    dup_pct = 100.0 * sum(flags) / n
    r_txt = f', Wachstum {ratio:.1f}×' if ratio is not None else ''
    return {'frozen': False, 'dup_flags': flags, 'med_k1': med_k1,
            'clean_split': clean_split,
            'reason': f'echte Bewegung ({frac_zero*100:.0f}% identische Paare{r_txt}) '
                      f'→ Duplikat-Rate {dup_pct:.0f}%'}


# ── fps/ft aus dup_flags neu berechnen ───────────────────────────────────────

def recompute_fps_from_flags(dup_flags, source_fps, fade_excluded=None):
    """
    Rechnet fps_seq/ft_seq aus dup_flags neu — exakt mit der Fensterlogik des
    Vorpasses (gleitendes 1s-Fenster, Anteil Unique × source_fps).

    Bewusst über die GESAMTE Sequenz: das Fenster reicht bis zu 1s über eine
    korrigierte Sektion hinaus, eine rein lokale Korrektur würde an der
    Grenze springen.
    """
    import collections
    fade_excluded = fade_excluded or set()
    win = collections.deque(maxlen=int(source_fps))
    fps_seq, ft_seq = [], []
    last_eff = float(source_fps)

    for is_dup in dup_flags:
        win.append(not is_dup)
        ws = len(win)
        eff = (sum(win) / ws) * source_fps if ws >= 4 else last_eff
        eff = max(0.0, min(eff, source_fps))
        last_eff = eff
        fps_seq.append(eff)
        ft_seq.append(1000.0 / eff if eff > 0 else 1000.0)

    for i in fade_excluded:
        if 0 <= i < len(fps_seq):
            fps_seq[i] = None
            ft_seq[i] = None
    return fps_seq, ft_seq


# ── Orchestrierung ───────────────────────────────────────────────────────────

def run_verification_pass(input_file, fps_seq, ft_seq, dup_flags, source_fps,
                          actual_start=0, fade_excluded=None,
                          work_size=WORK_SIZE, use_nvdec=True,
                          uncertain_action=UNCERTAIN_ACTION,
                          progress_cb=None, log=print,
                          is_cancelled=lambda: False):
    """
    Hauptfunktion. Prüft alle verdächtigen 0-fps-Sektionen nach.

    uncertain_action – was mit Blöcken passiert, die als bewegt erkannt
        wurden, deren RATE aber nicht sicher bestimmbar ist (siehe
        Modul-Docstring, Abschnitt GRENZE):
          'correct' – korrigieren (Default; behebt den eigentlichen Bug,
                      kann aber echtes 30fps-Material zu hoch ansetzen)
          'keep'    – 0 fps stehen lassen (konservativ)
        In beiden Fällen werden die betroffenen Zeitbereiche geloggt und
        im Report unter 'uncertain' aufgeführt.

    Returns: (fps_seq, ft_seq, dup_flags, report)
    """
    fade_excluded = fade_excluded or set()
    report = {'sections': [], 'corrected_frames': 0, 'checked_frames': 0,
              'blocks_moving': 0, 'blocks_frozen': 0, 'uncertain': []}

    sections = find_suspect_sections(fps_seq, source_fps, fade_excluded=fade_excluded)
    if not sections:
        log("✅ Verifikations-Pass: keine verdächtigen 0-fps-Sektionen")
        return fps_seq, ft_seq, dup_flags, report

    total = sum(e - s for s, e in sections)
    log(f"🔎 Verifikations-Pass: {len(sections)} verdächtige Sektion(en), "
        f"{total} Frames ({total/max(source_fps,1):.1f}s) @ {work_size}px AREA")

    dup_flags = list(dup_flags)
    block_len = max(4, int(round(source_fps)))
    done = 0

    # ── PHASE 1: alle Blöcke klassifizieren, noch nichts anwenden ───────
    # Zweiphasig, weil der Rauschboden des Encoders erst bekannt ist, wenn
    # ein sicher eingefrorener Block gefunden wurde — der dient als Referenz
    # für die Sicherheitsbewertung der bewegten Blöcke.
    pending = []   # (gpos, n_blk, result)
    for sec_s, sec_e in sections:
        if is_cancelled():
            break
        n_sec = sec_e - sec_s
        report['checked_frames'] += n_sec

        for chunk_off in range(0, n_sec, DECODE_CHUNK):
            if is_cancelled():
                break
            chunk_n = min(DECODE_CHUNK, n_sec - chunk_off)
            frames = _decode_section_gray(
                input_file, actual_start + sec_s + chunk_off, chunk_n,
                source_fps, size=work_size, use_nvdec=use_nvdec)

            if len(frames) < 2:
                log(f"   ⚠️ Decode fehlgeschlagen bei Frame "
                    f"{sec_s + chunk_off}, Bereich übersprungen")
                continue

            for b0 in range(0, len(frames), block_len):
                blk = frames[b0:b0 + block_len]
                if len(blk) < 2:
                    continue
                res = classify_block(blk)
                pending.append((sec_s + chunk_off + b0, len(blk), res))

            done += chunk_n
            if progress_cb:
                progress_cb(int(100 * done / max(1, total)),
                            f"Verifikation {done}/{total}")

    if not pending:
        log("⚠️ Verifikations-Pass: nichts auswertbar")
        return fps_seq, ft_seq, dup_flags, report

    # ── Rauschboden aus sicher eingefrorenen Blöcken schätzen ───────────
    frozen_k1 = [r['med_k1'] for _, _, r in pending
                 if r['frozen'] and r['med_k1'] > 0]
    noise_floor = float(np.median(frozen_k1)) if frozen_k1 else None
    if noise_floor:
        log(f"   Encoder-Rauschboden aus {len(frozen_k1)} eingefrorenen Block/Blöcken: "
            f"{noise_floor:.2e}")
    else:
        log(f"   Kein eingefrorener Referenzblock — Sicherheitsbewertung über "
            f"Absolutwert (Schwelle {ABS_CONFIDENT_K1:.0e})")

    # ── PHASE 2: anwenden ───────────────────────────────────────────────
    any_corrected = False
    for gpos, n_blk, res in pending:
        if res['frozen']:
            report['blocks_frozen'] += 1
            confident = True
        else:
            report['blocks_moving'] += 1
            # Sicher, wenn ein sauberer Duplikat-Cluster gefunden wurde ODER
            # die Bewegung klar über dem Encoder-Rauschen liegt.
            if res['clean_split']:
                confident = True
            elif noise_floor:
                confident = res['med_k1'] > noise_floor * CONFIDENT_NOISE_MULT
            else:
                confident = res['med_k1'] > ABS_CONFIDENT_K1

        t0 = gpos / max(source_fps, 1)
        if not res['frozen'] and not confident:
            report['uncertain'].append({'start': gpos, 'end': gpos + n_blk,
                                        'time_s': t0, 'med_k1': res['med_k1']})
            if uncertain_action == 'keep':
                log(f"   ❓ Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): bewegt, aber Rate "
                    f"unsicher (K1={res['med_k1']:.1e} nahe Rauschboden) → 0 fps beibehalten")
                continue
            log(f"   ❓ Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): bewegt, aber Rate "
                f"unsicher (K1={res['med_k1']:.1e} nahe Rauschboden) → korrigiert, bitte prüfen")

        changed = 0
        for i, f in enumerate(res['dup_flags']):
            gi = gpos + i
            if 0 <= gi < len(dup_flags) and dup_flags[gi] != f:
                dup_flags[gi] = f
                changed += 1
        if changed:
            any_corrected = True
            report['corrected_frames'] += changed

        if res['frozen'] or confident:
            mark = "✓" if res['frozen'] else "⚠️"
            log(f"   {mark} Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): {res['reason']}"
                + (f" [{changed} Frames korrigiert]" if changed else ""))

    if any_corrected:
        fps_seq, ft_seq = recompute_fps_from_flags(dup_flags, source_fps, fade_excluded)
        log(f"🔧 Verifikations-Pass: {report['corrected_frames']} Frames korrigiert "
            f"({report['blocks_moving']} bewegte / {report['blocks_frozen']} eingefrorene Blöcke), "
            f"fps/ft neu berechnet")
    else:
        log(f"✅ Verifikations-Pass: alle {report['blocks_frozen']} Blöcke bestätigt, "
            f"keine Korrektur nötig")

    if report['uncertain']:
        times = ", ".join(f"{u['time_s']:.1f}s" for u in report['uncertain'][:8])
        more = "" if len(report['uncertain']) <= 8 else f" (+{len(report['uncertain'])-8} weitere)"
        log(f"❓ {len(report['uncertain'])} Block/Blöcke mit unsicherer Rate bei: {times}{more}")

    return fps_seq, ft_seq, dup_flags, report
