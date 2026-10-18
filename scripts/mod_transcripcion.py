"""MOD-6 (18-oct): la transcripción de las notas de voz (hoy gpt-4o-mini-transcribe, familia gpt-4o) con otros modelos.

No hay audios de clientes en el repo (son datos personales): se generan notas de voz SINTÉTICAS con TTS (tts-1, dos
voces) con lo que suele costar transcribir en este negocio (importes, "Muelle de la Bodeguita", "Isla Grande", fechas,
mezcla de idiomas) y se transcriben con cada candidato por el mismo camino que el bot (`audio.transcriptions.create`,
sin pista de idioma). Mide el error por palabra (WER, sobre texto normalizado) y la latencia. Los audios se quedan en
la carpeta de salida, fuera del repo.

    python -m scripts.mod_transcripcion <carpeta_de_audios> <salida.json>
"""
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openai import OpenAI  # noqa: E402

from src.config import settings  # noqa: E402

TEXTOS = [
    ("es", "nova", "Hola, buenas tardes. Somos cuatro personas y queremos hacer el minicurso de buceo el sábado veinticinco."),
    ("es", "onyx", "Nos quedamos en el hotel San Pedro de Majagua, en Isla Grande. ¿Nos pueden recoger ahí?"),
    ("es", "nova", "¿Cuánto cuesta la salida de dos inmersiones? Vi en la página seiscientos treinta mil pesos."),
    ("es", "onyx", "Yo tengo la certificación Open Water desde hace tres años y mi esposa nunca ha buceado."),
    ("es", "nova", "¿A qué hora hay que estar en el Muelle de la Bodeguita? Llegamos el doce de diciembre."),
    ("en", "alloy", "Hi, my wife and I are certified divers, we would like to book two dives on Friday from Cartagena."),
    ("en", "echo", "How much is the mini course for two people? We are staying in Getsemaní until the fifteenth."),
    ("en", "alloy", "Can my daughter, she is eleven years old, do snorkeling while we dive?"),
    ("es", "onyx", "Ok perfecto, entonces reservo el paquete de cinco inmersiones y pago con tarjeta, gracias."),
    ("en", "echo", "We are coming from Barú, is lunch included in the trip?"),
]
CANDIDATOS = ["gpt-4o-mini-transcribe", "gpt-transcribe", "whisper-1"]
# Pista de vocabulario del negocio (parámetro `prompt` de la API de transcripción): con --vocabulario.
VOCABULARIO = ("Diving Planet, Muelle de la Bodeguita, Islas del Rosario, Isla Grande, Barú, Hotel San Pedro de Majagua, "
               "Cocoliso, Getsemaní, Bocagrande, minicurso, snorkel, Open Water, PADI, refresher, buzo certificado.")


def normalizar(t: str) -> list[str]:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


def wer(ref: str, hyp: str) -> float:
    r, h = normalizar(ref), normalizar(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    carpeta, salida = Path(sys.argv[1]), Path(sys.argv[2])
    carpeta.mkdir(parents=True, exist_ok=True)
    cli = OpenAI(api_key=settings.openai_api_key)
    for i, (_, voz, texto) in enumerate(TEXTOS):
        f = carpeta / f"nota-{i:02d}.mp3"
        if not f.exists():
            f.write_bytes(cli.audio.speech.create(model="tts-1", voice=voz, input=texto).content)
    res = {}
    for modelo in CANDIDATOS:
        filas, ts = [], []
        for i, (lang, _, texto) in enumerate(TEXTOS):
            f = carpeta / f"nota-{i:02d}.mp3"
            t0 = time.perf_counter()
            try:
                extra = {"prompt": VOCABULARIO} if "--vocabulario" in sys.argv else {}
                out = cli.audio.transcriptions.create(model=modelo, file=(f.name, f.read_bytes()),
                                                      **extra).text.strip()
            except Exception as exc:  # noqa: BLE001
                out = f"ERROR {str(exc)[:120]}"
            ts.append(time.perf_counter() - t0)
            filas.append({"lang": lang, "texto": texto, "transcripcion": out, "wer": round(wer(texto, out), 3)})
        res[modelo] = {"wer_medio": round(statistics.mean(x["wer"] for x in filas), 3),
                       "p50": round(statistics.median(ts), 2), "filas": filas}
        print(f"{modelo:26} WER medio {res[modelo]['wer_medio']:.3f}  p50 {res[modelo]['p50']}s")
        for x in filas:
            if x["wer"] > 0:
                print(f"     [{x['wer']:.2f}] {x['transcripcion'][:110]}")
    salida.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
