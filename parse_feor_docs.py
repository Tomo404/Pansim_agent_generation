from __future__ import annotations

from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd


# ============================================================
# EZT ÁLLÍTSD BE
# ============================================================
INPUT_DOCX = Path("data/raw/feor08_kozl_melleklet.docx")
OUTPUT_CSV = Path("data/processed/feor_list_from_docx.csv")


def extract_docx_paragraphs(docx_path: Path) -> list[str]:
    """
    A .docx fájlból kinyeri a bekezdések szövegét.
    Nem használ külső csomagot, csak a docx belső XML-jét olvassa.
    """
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    with zipfile.ZipFile(docx_path) as zf:
        xml_bytes = zf.read("word/document.xml")

    root = ET.fromstring(xml_bytes)

    paragraphs: list[str] = []
    for p in root.findall(".//w:p", ns):
        texts = []
        for t in p.findall(".//w:t", ns):
            if t.text:
                texts.append(t.text)
        para = "".join(texts).strip()
        if para:
            paragraphs.append(para)

    return paragraphs


def normalize_paragraphs(paragraphs: list[str]) -> str:
    """
    Bekezdésekből egy nagy szöveget csinál.
    Közben megpróbáljuk szétvágni azokat az eseteket,
    ahol több 4 jegyű FEOR-kód egy sorba csúszott.
    """
    text = "\n".join(paragraphs)

    # Új sor minden 4 számjegyű kód elé, ha nincs már ott
    text = re.sub(r"(?<!\n)(?=(?<!\d)\d{4}(?!\d))", "\n", text)

    # Néha 3 jegyű heading + utána 4 jegyű rekord egy sorban van
    # pl: "211 Ipari... 2111 Bányamérnök"
    text = re.sub(
        r"(?<!\n)(?=(?<!\d)\d{3}(?!\d)\s+[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])",
        "\n",
        text,
    )

    # Többszörös sortörések egyszerűsítése
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


def is_heading_line(line: str) -> bool:
    """
    1 / 2 / 3 jegyű FEOR headingek és tipikus címsorok kiszűrése.
    """
    line = line.strip()

    if not line:
        return True

    # klasszikus 1/2/3 jegyű heading
    if re.match(r"^\d{1,3}\s+.+$", line):
        return True

    # sor eleji heading szám nélkül
    heading_keywords = [
        "GAZDASÁGI, IGAZGATÁSI",
        "FELSŐFOKÚ KÉPZETTSÉG",
        "EGYÉB FELSŐFOKÚ",
        "IRODAI ÉS ÜGYVITELI",
        "KERESKEDELMI ÉS SZOLGÁLTATÁSI",
        "MEZŐGAZDASÁGI ÉS ERDŐGAZDÁLKODÁSI",
        "IPARI ÉS ÉPÍTŐIPARI",
        "GÉPKEZELŐK, ÖSSZESZERELŐK",
        "SZAKKÉPZETTSÉGET NEM IGÉNYLŐ",
        "FEGYVERES SZERVEK",
        "Törvényhozók, igazgatási és érdek-képviseleti vezetők",
        "Országos és területi közigazgatás, igazságszolgáltatás vezetői",
        "Gazdasági, költségvetési szervezetek vezetői",
        "Termelési és szolgáltatást nyújtó egységek vezetői",
        "Termelési egységek vezetői",
        "Szolgáltatást nyújtó egységek vezetői",
        "Kereskedelmi, vendéglátó és hasonló szolgáltatási tevékenységet folytató egységek vezetői",
        "Gazdasági tevékenységet segítő egységek vezetői",
        "Műszaki, informatikai és természettudományi foglalkozások",
        "Elektromérnökök",
        "Egyéb mérnökök",
        "Szoftver- és alkalmazásfejlesztők, -elemzők",
        "Adatbázis- és hálózati elemzők, üzemeltetők",
        "Természettudományi foglalkozások",
        "Egészségügyi foglalkozások",
        "Humán-egészségügyi",
        "Állat- és növény-egészségügyi foglalkozások",
        "Szociális szolgáltatási foglalkozások",
        "Oktatók, pedagógusok",
        "Gazdálkodási jellegű foglalkozások",
        "Jogi és társadalomtudományi foglalkozások",
        "Kulturális, sport-, művészeti és vallási foglalkozások",
        "Technikusok és hasonló műszaki foglalkozások",
        "Egészségügyi asszisztensek",
        "Üzleti jellegű szolgáltatások ügyintézői, hatósági ügyintézők, ügynökök",
        "Művészeti és kulturális foglalkozások",
        "Irodai, ügyviteli foglalkozások",
        "Ügyfélkapcsolati foglalkozások",
        "Kereskedelmi és vendéglátó-ipari foglalkozások",
        "Szolgáltatási foglalkozások",
        "Mezőgazdasági foglalkozások",
        "Élelmiszer-ipari foglalkozások",
        "Könnyűipari foglalkozások",
        "Fém- és villamosipari foglalkozások",
        "Kézműipari foglalkozások",
        "Építőipari foglalkozások",
        "Feldolgozóipari gépek kezelői",
        "Összeszerelők",
        "Helyhez kötött gépek kezelői",
        "Járművezetők és mobil gépek kezelői",
        "Takarítók és hasonló jellegű egyszerű foglalkozások",
        "Egyszerű szolgáltatási, szállítási és hasonló foglalkozások",
        "Egyszerű ipari, építőipari, mezőgazdasági foglalkozások",
    ]

    return any(line.startswith(k) for k in heading_keywords)


def parse_feor_from_docx_text(text: str) -> list[dict[str, str]]:
    """
    A teljes docx-szövegből 4 számjegyű FEOR rekordokat gyárt.

    Logika:
    - minden 4 számjegyű kód blokkot kivágunk a következő 4 számjegyű kódig
    - a blokk elejéről kiszedjük a headingeket
    - a maradék lesz a FEOR név
    """
    records: list[dict[str, str]] = []

    # A valódi tartalom elejére ugrunk
    start_markers = [
        "1110",
        "2111",
        "6111",
    ]
    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx
            break
    if start_idx != -1:
        text = text[start_idx:]

    pattern = re.compile(
        r"(?<!\d)(\d{4})(?!\d)\s*(.*?)(?=(?<!\d)\d{4}(?!\d)|\Z)",
        flags=re.S,
    )

    for m in pattern.finditer(text):
        code = m.group(1).strip()
        raw_block = m.group(2).strip()

        lines = [ln.strip() for ln in raw_block.split("\n") if ln.strip()]

        cleaned_lines: list[str] = []
        for line in lines:
            if re.fullmatch(r"\d+", line):
                continue
            if is_heading_line(line):
                continue
            cleaned_lines.append(line)

        name = " ".join(cleaned_lines)
        name = re.sub(r"\s+", " ", name).strip()

        # Ha egy új heading ráfolyt a névre, vágjuk le.
        # Tipikus eset: "Egyházi vezető 12Gazdasági, költségvetési..."
        name = re.split(r"\s+\d{1,3}[A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű]", name)[0].strip()

        # Ha ismert heading szöveg ráfolyt a végére, azt is levágjuk
        trailing_headings = [
            "Gazdasági, költségvetési szervezetek vezetői",
            "Termelési és szolgáltatást nyújtó egységek vezetői",
            "Szolgáltatást nyújtó egységek vezetői",
            "Kereskedelmi, vendéglátó és hasonló szolgáltatási tevékenységet folytató egységek vezetői",
            "Műszaki, informatikai és természettudományi foglalkozások",
            "Egészségügyi foglalkozások",
            "Oktatók, pedagógusok",
            "Gazdálkodási jellegű foglalkozások",
            "Jogi és társadalomtudományi foglalkozások",
            "Technikusok és hasonló műszaki foglalkozások",
            "Egészségügyi asszisztensek",
            "Irodai, ügyviteli foglalkozások",
            "Ügyfélkapcsolati foglalkozások",
            "Kereskedelmi és vendéglátó-ipari foglalkozások",
            "Szolgáltatási foglalkozások",
            "Mezőgazdasági foglalkozások",
            "Élelmiszer-ipari foglalkozások",
            "Építőipari foglalkozások",
            "Feldolgozóipari gépek kezelői",
            "Összeszerelők",
            "Helyhez kötött gépek kezelői",
            "Járművezetők és mobil gépek kezelői",
            "Egyszerű szolgáltatási, szállítási és hasonló foglalkozások",
        ]

        for h in trailing_headings:
            if h in name and not name.startswith(h):
                name = name.split(h)[0].strip()

        name = re.sub(r"\s+", " ", name).strip()

        if not name:
            continue

        records.append({
            "feor_code": code,
            "feor_name": name,
        })

    # duplikátumok kiszűrése
    unique_records = []
    seen = set()
    for rec in records:
        key = (rec["feor_code"], rec["feor_name"])
        if key not in seen:
            seen.add(key)
            unique_records.append(rec)

    return unique_records


def main() -> None:
    print(f"Reading: {INPUT_DOCX}")

    paragraphs = extract_docx_paragraphs(INPUT_DOCX)
    print(f"Paragraphs extracted: {len(paragraphs)}")

    text = normalize_paragraphs(paragraphs)

    raw_codes = sorted(set(re.findall(r"(?<!\d)\d{4}(?!\d)", text)))
    raw_codes = [c for c in raw_codes if c != "2010"]
    print(f"Unique 4-digit codes found in docx text: {len(raw_codes)}")

    records = parse_feor_from_docx_text(text)
    df = pd.DataFrame(records)

    if not df.empty:
        # Először whitespace normalizálás
        df["feor_name"] = df["feor_name"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

        # Azonos kódnál a legrövidebb nevet tartjuk meg,
        # mert a hosszabbak jellemzően heading-ráfolyás miatt hibásak
        df["name_len"] = df["feor_name"].str.len()
        df = (
            df.sort_values(["feor_code", "name_len"])
              .drop_duplicates(subset=["feor_code"], keep="first")
              .drop(columns=["name_len"])
              .reset_index(drop=True)
        )

        df = df.sort_values("feor_code").reset_index(drop=True)

    print(f"Parsed FEOR rows: {len(df)}")

    parsed_codes = set(df["feor_code"].astype(str)) if not df.empty else set()
    missing_codes = sorted(set(raw_codes) - parsed_codes)
    print(f"Codes present in docx text but missing from parsed output: {len(missing_codes)}")
    if missing_codes[:20]:
        print("First missing codes:", missing_codes[:20])

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Saved to: {OUTPUT_CSV.resolve()}")

    if not df.empty:
        print(df.head(30).to_string(index=False))


if __name__ == "__main__":
    main()