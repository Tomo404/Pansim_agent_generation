from __future__ import annotations

import re
import unicodedata
from typing import Dict

from structure import teaor


# ============================================================
# SZÖVEGNORMALIZÁLÁS
# ============================================================
def normalize_text(text: str) -> str:
    text = str(text).lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ============================================================
# SEGÉD
# ============================================================
def weights(**kwargs: float) -> Dict[str, float]:
    total = sum(kwargs.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in kwargs.items()}


# ============================================================
# 1) ERŐS KÓD ALAPÚ SZABÁLYOK
#    Ezeket előbb nézzük, mert megbízhatóbbak
# ============================================================
def map_by_feor_code(feor_code: str) -> Dict[str, float] | None:
    code = str(feor_code).strip()

    # 4 számjegy -> 3 számjegy -> 2 számjegy prefixek
    code4 = code[:4]
    code3 = code[:3]
    code2 = code[:2]
    code1 = code[:1]

    # ---- KONKRÉT 4 JEGYŰ VEZETŐI FEOR-OK
    if code4 == "1311":
        return weights(A=0.85, C=0.05, F=0.05, M=0.05)

    if code4 == "1312":
        return weights(C=0.75, D=0.10, E=0.05, B=0.05, M=0.05)

    if code4 == "1313":
        return weights(F=0.85, C=0.10, M=0.05)

    if code4 == "1321":
        return weights(H=0.85, N=0.05, G=0.05, M=0.05)

    if code4 == "1322":
        return weights(J=0.80, M=0.15, C=0.05)

    if code4 == "1323":
        return weights(K=0.85, M=0.10, N=0.05)

    if code4 == "1324":
        return weights(Q=0.80, O=0.15, N=0.05)

    if code4 == "1325":
        return weights(Q=0.70, O=0.20, P=0.10)

    if code4 == "1326":
        return weights(Q=0.80, O=0.15, N=0.05)

    if code4 == "1327":
        return weights(Q=0.90, M=0.05, O=0.05)

    if code4 == "1328":
        return weights(P=0.85, O=0.10, Q=0.05)

    if code4 == "1329":
        return weights(S=0.35, N=0.20, R=0.15, I=0.10, G=0.10, M=0.10)

    if code4 == "1331":
        return weights(I=0.85, R=0.05, S=0.05, G=0.05)

    if code4 == "1332":
        return weights(I=0.90, G=0.10)

    if code4 == "1333":
        return weights(G=0.90, I=0.10)

    if code4 == "1334":
        return weights(M=0.35, N=0.25, G=0.15, J=0.10, K=0.10, S=0.05)

    if code4 == "1335":
        return weights(R=0.75, S=0.10, J=0.10, P=0.05)

    if code4 == "1336":
        return weights(R=0.80, S=0.10, I=0.10)

    if code4 == "1339":
        return weights(S=0.40, I=0.20, G=0.15, R=0.15, N=0.10)

    if code4 == "1411":
        return weights(K=0.70, M=0.15, O=0.10, N=0.05)

    if code4 == "1412":
        return weights(N=0.45, M=0.30, O=0.15, K=0.10)

    if code4 == "1413":
        return weights(M=0.75, J=0.10, C=0.05, Q=0.05, P=0.05)

    if code4 == "1414":
        return weights(M=0.50, K=0.20, N=0.15, O=0.10, J=0.05)

    if code4 == "1415":
        return weights(G=0.35, M=0.25, N=0.15, J=0.15, K=0.10)

    if code4 == "1416":
        return weights(M=0.45, J=0.25, G=0.20, N=0.10)

    if code4 == "1419":
        return weights(N=0.30, M=0.25, S=0.15, G=0.10, O=0.10, K=0.10)

    # ---- FEOR 0: fegyveres szervek
    if code1 == "0":
        return weights(O=1.0)

    # ---- FEOR 6: mezőgazdaság, erdőgazdálkodás
    if code2 in {"61", "62"}:
        return weights(A=1.0)

    # ---- FEOR 7: ipari és építőipari
    if code2 == "71":
        return weights(C=1.0)  # élelmiszeripar
    if code2 == "72":
        return weights(C=1.0)  # könnyűipar
    if code2 == "73":
        return weights(C=1.0)  # fém- és villamosipar
    if code2 == "74":
        return weights(C=0.8, R=0.2)  # kézműipar részben művészeti is lehet
    if code2 == "75":
        return weights(F=1.0)  # építőipar
    if code2 == "79":
        return weights(C=0.7, F=0.3)

    # ---- FEOR 8: gépkezelők, járművezetők
    if code2 == "81":
        return weights(C=1.0)
    if code2 == "82":
        return weights(C=1.0)
    if code3 == "831":
        return weights(B=0.7, C=0.3)
    if code3 == "832":
        return weights(D=0.25, E=0.25, C=0.30, H=0.20)
    if code2 == "84":
        return weights(H=0.75, A=0.10, F=0.10, E=0.05)

    # ---- FEOR 9: egyszerű foglalkozások
    if code2 == "91":
        return weights(N=0.35, I=0.20, Q=0.20, S=0.15, O=0.10)
    if code2 == "92":
        return weights(H=0.35, G=0.20, N=0.20, I=0.15, E=0.10)
    if code3 == "931":
        return weights(C=1.0)
    if code3 == "932":
        return weights(F=1.0)
    if code3 == "933":
        return weights(A=1.0)

    # ---- FEOR 5: kereskedelmi és szolgáltatási
    if code3 == "511":
        return weights(G=1.0)
    if code3 == "512":
        return weights(G=0.8, I=0.2)
    if code3 == "513":
        return weights(I=1.0)
    if code3 == "521":
        return weights(S=0.7, I=0.2, R=0.1)
    if code3 == "522":
        return weights(Q=0.8, P=0.2)
    if code3 == "523":
        return weights(H=0.8, I=0.2)
    if code3 == "524":
        return weights(N=0.6, S=0.2, O=0.2)
    if code3 == "525":
        return weights(O=0.6, N=0.2, S=0.2)
    if code3 == "529":
        return weights(S=0.5, H=0.2, R=0.2, I=0.1)

    # ---- FEOR 4: irodai / ügyviteli
    if code2 == "41":
        return weights(N=0.20, G=0.15, K=0.10, O=0.20, P=0.10, Q=0.10, M=0.15)
    if code2 == "42":
        return weights(G=0.20, H=0.15, I=0.20, K=0.10, O=0.10, N=0.15, S=0.10)

    # ---- FEOR 3: technikusok, ügyintézők
    if code3 in {"311", "312"}:
        return weights(C=0.55, F=0.20, D=0.15, E=0.10)
    if code3 == "313":
        return weights(A=0.35, M=0.20, C=0.20, E=0.15, F=0.10)
    if code3 == "314":
        return weights(J=0.75, M=0.15, C=0.10)
    if code3 == "315":
        return weights(C=0.35, D=0.30, E=0.20, B=0.15)
    if code3 == "316":
        return weights(C=0.35, D=0.20, E=0.15, F=0.10, M=0.20)
    if code3 == "317":
        return weights(H=1.0)
    if code2 == "32":
        return weights(C=0.25, F=0.15, G=0.10, I=0.10, O=0.15, N=0.15, M=0.10)
    if code2 == "33":
        return weights(Q=1.0)
    if code2 == "34":
        return weights(P=1.0)
    if code2 == "35":
        return weights(Q=0.7, O=0.3)
    if code2 == "36":
        return weights(K=0.25, G=0.20, N=0.15, O=0.20, M=0.20)
    if code2 == "37":
        return weights(R=0.6, I=0.1, S=0.1, O=0.1, P=0.1)
    if code2 == "39":
        return weights(N=0.25, O=0.25, M=0.25, S=0.25)

    # ---- FEOR 2: felsőfokú
    if code3 == "211":
        return weights(C=0.45, F=0.20, M=0.20, B=0.10, D=0.05)
    if code3 == "212":
        return weights(C=0.35, D=0.25, J=0.20, M=0.10, H=0.10)
    if code3 == "213":
        return weights(A=0.20, M=0.30, F=0.15, N=0.05, C=0.10, E=0.10, H=0.10)
    if code3 == "214":
        return weights(J=0.85, M=0.15)
    if code3 == "215":
        return weights(J=0.70, M=0.10, C=0.10, H=0.10)
    if code3 == "216":
        return weights(M=0.75, P=0.05, Q=0.05, E=0.10, R=0.05)
    if code2 == "22":
        return weights(Q=0.90, M=0.05, A=0.05)
    if code2 == "23":
        return weights(Q=0.85, O=0.15)
    if code2 == "24":
        return weights(P=0.90, Q=0.05, R=0.05)
    if code2 == "25":
        return weights(K=0.35, M=0.35, G=0.10, J=0.10, N=0.10)
    if code2 == "26":
        return weights(M=0.40, O=0.35, K=0.10, P=0.05, Q=0.05, R=0.05)
    if code2 == "27":
        return weights(R=0.70, P=0.10, S=0.10, I=0.10)
    if code2 == "29":
        return weights(M=0.40, O=0.20, N=0.20, K=0.10, P=0.10)

    # ---- FEOR 1: vezetők
    if code3 == "131":
        return weights(A=0.25, B=0.05, C=0.35, D=0.05, E=0.05, F=0.25)
    if code3 == "132":
        return weights(H=0.10, J=0.10, K=0.10, Q=0.30, P=0.10, I=0.05, N=0.10, S=0.05, R=0.10)
    if code3 == "133":
        return weights(G=0.45, I=0.35, N=0.05, R=0.10, S=0.05)
    if code3 == "141":
        return weights(K=0.20, M=0.30, N=0.15, G=0.10, J=0.10, O=0.05, C=0.05, S=0.05)
    if code2 in {"11", "12"}:
        return weights(O=0.45, K=0.10, M=0.15, G=0.05, Q=0.05, P=0.05, N=0.05, S=0.05, R=0.05)

    return None


# ============================================================
# 2) NÉV ALAPÚ KULCSSZAVAS SZABÁLYOK
#    Ezek akkor futnak, ha a kód alapján nincs találat
# ============================================================
KEYWORD_RULES = [
    (["informatikai", "szoftver", "rendszergazda", "adatbazis", "halozat", "telekommunikacio", "web"], weights(J=0.85, M=0.15)),
    (["egeszsegugyi", "orvos", "apolo", "gyogyszeresz", "fizioterapia", "fogasz", "vedo no", "mentotiszt"], weights(Q=0.95, M=0.05)),
    (["oktato", "tanar", "pedagog", "ovodapedagogus", "nevelo"], weights(P=0.95, R=0.05)),
    (["szocialis", "gondozo", "gondozasi", "ifjusagsegito"], weights(Q=0.75, O=0.25)),
    (["mezogazdasagi", "noveny", "allattenyeszto", "erdesz", "halasz", "vadasz"], weights(A=1.0)),
    (["banyasz", "koolaj", "foldgaz", "erc", "ko fejto"], weights(B=0.85, C=0.15)),
    (["epito", "epites", "komuves", "acs", "burkolo", "tetofedo", "villanyszerelo", "gipszkartonos"], weights(F=0.9, C=0.1)),
    (["vegyesz", "vegyipari", "gyogyszergyarto"], weights(C=0.7, M=0.3)),
    (["gepesz", "femmegmunkalo", "hegeszto", "lakatos", "esztergalyos", "villamos"], weights(C=0.85, F=0.15)),
    (["kereskedelmi", "elado", "penztaros", "arufeltolto"], weights(G=0.9, I=0.1)),
    (["vendeglato", "pincer", "szakacs", "cukrasz", "recepcios", "szallodai"], weights(I=0.9, G=0.1)),
    (["szallitasi", "raktarozasi", "logisztikai", "jarmuvezeto", "kamionsofor", "targoncavezeto", "futar"], weights(H=0.9, G=0.1)),
    (["penzugyi", "banki", "biztositas", "broker", "ado"], weights(K=0.8, M=0.2)),
    (["jogi", "ugyved", "biro", "kozjegyzo", "ugyesz"], weights(M=0.6, O=0.4)),
    (["marketing", "pr", "piackutato", "reklam"], weights(M=0.6, G=0.2, J=0.2)),
    (["kutatasi", "fejlesztesi", "fizikus", "kemikus", "geologus", "matematikus", "biologus"], weights(M=0.85, P=0.05, Q=0.05, E=0.05)),
    (["kulturalis", "muveszeti", "muzeumi", "konyvtaros", "ujsagiro", "zenesz", "szinesz", "sport"], weights(R=0.8, J=0.1, P=0.1)),
    (["takarito", "haztarto", "portas", "konyhai kisegito"], weights(N=0.35, I=0.25, Q=0.15, O=0.10, S=0.15)),
]


def map_by_keywords(feor_name: str) -> Dict[str, float] | None:
    name = normalize_text(feor_name)

    for keywords, rule_weights in KEYWORD_RULES:
        for kw in keywords:
            if normalize_text(kw) in name:
                return rule_weights

    return None


# ============================================================
# 3) VÉGSŐ MAPPER
# ============================================================
def map_feor_to_teaor(feor_code: str, feor_name: str) -> Dict[str, float]:
    code_based = map_by_feor_code(feor_code)
    if code_based is not None:
        return code_based

    keyword_based = map_by_keywords(feor_name)
    if keyword_based is not None:
        return keyword_based

    # fallback: szélesen elosztjuk admin/szolgáltatás irányba
    return weights(N=0.25, M=0.20, G=0.15, S=0.15, O=0.15, C=0.10)


# ============================================================
# 4) SEGÉD A TESZTHEZ
# ============================================================
def pretty_mapping(mapping: Dict[str, float]) -> str:
    parts = []
    for k, v in sorted(mapping.items(), key=lambda x: x[1], reverse=True):
        teaor_name = teaor.get(k, {}).get("name", "Ismeretlen")
        parts.append(f"{k} ({teaor_name}): {v:.2f}")
    return " | ".join(parts)


def main() -> None:
    examples = [
        ("2142", "Szoftverfejlesztő"),
        ("2117", "Vegyészmérnök"),
        ("7511", "Kőműves"),
        ("6111", "Szántóföldinövény-termesztő"),
        ("5113", "Bolti eladó"),
        ("2212", "Szakorvos"),
        ("2421", "Középiskolai tanár"),
        ("8417", "Tehergépkocsi-vezető, kamionsofőr"),
        ("8311", "Szilárdásvány-kitermelő gép kezelője"),
    ]

    for code, name in examples:
        mapping = map_feor_to_teaor(code, name)
        print(f"{code} - {name}")
        print(pretty_mapping(mapping))
        print("-" * 80)


if __name__ == "__main__":
    main()