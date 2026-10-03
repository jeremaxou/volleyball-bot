import json
import os
import re
import shutil
from itertools import groupby
from pathlib import Path

import requests
from dotenv import load_dotenv

from analyse_dispo import FICHIER_SORTIE as FICHIER_ACTUELLES, cle, trier

load_dotenv()

TOPIC_URL = os.environ["NTFY_URL"].strip()   # .strip() retire les espaces et retours à la ligne parasites   # dans .env en local, dans les Secrets GitHub sur le serveur
FICHIER_PASSEES = "dispos_interessantes_passes.json"
NOTIFIER_SANS_CHANGEMENT = True   # True = notification à chaque exécution, même sans changement

# ---------------------------------------------------------------------------
# Tables de conversion japonais -> anglais
# ---------------------------------------------------------------------------
GYMNASES = {
    "神奈川スポーツセンター": "Kanagawa",
    "南スポーツセンター": "Minami",
    "旭スポーツセンター": "Asahi",
    "港北スポーツセンター": "Kohoku",
    "緑スポーツセンター": "Midori",
    "戸塚スポーツセンター": "Totsuka",
}

# remplacements appliqués dans l'ordre sur le nom de la salle
SALLES = [
    ("第一体育室", "Gym 1"),
    ("第二体育室", "Gym 2"),
    ("体育室", "Gym"),
    ("（全面）", " (full)"),
    ("（半面）", " (half)"),
    ("Ａ", " A"),
    ("Ｂ", " B"),
    ("Ｃ", " C"),
]

JOURS = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun", "祝": "Hol"}


def gymnase_en(nom):
    return GYMNASES.get(nom, nom)   # nom inconnu -> laissé en japonais


def salle_en(nom):
    for jp, en in SALLES:
        nom = nom.replace(jp, en)
    return nom.strip()


def date_en(d):
    """'2026年10月5日(月)' -> 'Mon 10/5'"""
    _, m, j = re.findall(r"\d+", d)[:3]
    jour_jp = re.search(r"\((.)\)", d)
    jour_jp = jour_jp.group(1) if jour_jp else ""
    return f"{JOURS.get(jour_jp, jour_jp)} {m}/{j}"


def lieu(c):
    return f"{gymnase_en(c['gymnase'])} · {salle_en(c['salle'])}"


# ---------------------------------------------------------------------------
# Comparaison et message
# ---------------------------------------------------------------------------
def charger(chemin):
    if not Path(chemin).exists():
        return []
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def construire_message(nouvelles, disparues, toutes):
    lignes = []

    if nouvelles:
        lignes.append(f"🆕🆕 NEW SLOTS ({len(nouvelles)}) 🆕🆕")
        lignes += [f"▶ {date_en(c['date'])}  {c['debut']}-{c['fin']}  {lieu(c)}" for c in nouvelles]
        lignes.append("")
    if disparues:
        lignes.append(f"❌ GONE ({len(disparues)})")
        lignes += [f"✕ {date_en(c['date'])}  {c['debut']}-{c['fin']}  {lieu(c)}" for c in disparues]
        lignes.append("")
    if not nouvelles and not disparues:
        lignes += ["No change.", ""]

    lignes.append("━━━━━━━━━━━━━━")
    lignes.append(f"ALL SLOTS ({len(toutes)})")
    for d, groupe in groupby(toutes, key=lambda c: c["date"]):
        lignes.append("")
        lignes.append(date_en(d))
        lignes += [f"  {c['debut']}-{c['fin']}  {lieu(c)}" for c in groupe]

    return "\n".join(lignes)


def main():
    with open(FICHIER_ACTUELLES, encoding="utf-8") as f:
        actuelles = trier(json.load(f))
    passees = charger(FICHIER_PASSEES)

    cles_actuelles = {cle(c) for c in actuelles}
    cles_passees = {cle(c) for c in passees}
    nouvelles = trier([c for c in actuelles if cle(c) not in cles_passees])
    disparues = trier([c for c in passees if cle(c) not in cles_actuelles])

    if not nouvelles and not disparues and not NOTIFIER_SANS_CHANGEMENT:
        print("Aucun changement : pas de notification.")
        return

    message = construire_message(nouvelles, disparues, actuelles)
    r = requests.post(
        TOPIC_URL,
        data=message.encode("utf-8"),
        headers={
            "Title": f"Volley: {len(nouvelles)} new, {len(disparues)} gone",
            "Priority": "high" if nouvelles else "default",
            "Tags": "volleyball",
        },
    )
    r.raise_for_status()   # en cas d'échec d'envoi, on ne met pas à jour l'historique

    shutil.copyfile(FICHIER_ACTUELLES, FICHIER_PASSEES)
    print(message)
    print(f"\nNotification envoyée, {FICHIER_PASSEES} mis à jour.")


if __name__ == "__main__":
    main()