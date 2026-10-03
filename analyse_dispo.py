import json
import re
from datetime import date
from itertools import groupby

FICHIER_ENTREE = "dispos.json"
FICHIER_SORTIE = "dispos_interessantes_actuelles.json"

HEURE_MIN_4H = "13:00"     # blocs de 4h : début à cette heure ou après
HEURE_MIN_2H = "19:00"     # blocs de 2h : début à cette heure ou après
GYMNASE_TOUT = "港北"      # gymnase dont on garde tous les créneaux

CHAMPS = ("gymnase", "salle", "date", "debut", "fin")


def cle(c):
    """Identifiant unique d'un créneau (sert à dédoublonner et à comparer)."""
    return tuple(c[k] for k in CHAMPS)


def minutes(h):
    """'13:30' -> 810"""
    hh, mm = h.split(":")
    return int(hh) * 60 + int(mm)


def jour(d):
    """'2026年10月5日(月)' -> date(2026, 10, 5), pour trier chronologiquement"""
    y, m, j = map(int, re.findall(r"\d+", d)[:3])
    return date(y, m, j)


def trier(creneaux):
    return sorted(creneaux, key=lambda c: (jour(c["date"]), minutes(c["debut"]), c["gymnase"], c["salle"]))


def blocs_4h(creneaux):
    """Deux créneaux consécutifs, même gymnase, même salle, même jour, début >= HEURE_MIN_4H."""
    groupe_de = lambda c: (c["gymnase"], c["salle"], c["date"])
    tries = sorted(creneaux, key=lambda c: (groupe_de(c), minutes(c["debut"])))
    blocs = []
    for _, groupe in groupby(tries, key=groupe_de):
        groupe = list(groupe)
        for a, b in zip(groupe, groupe[1:]):
            if a["fin"] == b["debut"] and minutes(a["debut"]) >= minutes(HEURE_MIN_4H):
                blocs.append({**a, "fin": b["fin"]})
    return blocs


def blocs_2h_soir(creneaux):
    """Créneaux d'au moins 2h commençant à HEURE_MIN_2H ou après."""
    return [c for c in creneaux
            if minutes(c["debut"]) >= minutes(HEURE_MIN_2H)
            and minutes(c["fin"]) - minutes(c["debut"]) >= 120]


def tout_kohoku(creneaux):
    return [c for c in creneaux if GYMNASE_TOUT in c["gymnase"]]


def afficher(titre, creneaux):
    print(f"\n=== {titre} ({len(creneaux)}) ===")
    if not creneaux:
        print("  (aucun)")
        return
    for d, groupe in groupby(trier(creneaux), key=lambda c: c["date"]):
        print(f"\n{d}")
        for c in groupe:
            print(f"  {c['debut']:>5} - {c['fin']:<5}  {c['gymnase']} | {c['salle']}")


def main():
    with open(FICHIER_ENTREE, encoding="utf-8") as f:
        creneaux = json.load(f)

    # union des 3 règles, sans doublons (un même créneau peut matcher plusieurs règles)
    interessantes = {}
    for c in blocs_4h(creneaux) + blocs_2h_soir(creneaux) + tout_kohoku(creneaux):
        interessantes[cle(c)] = c
    interessantes = trier(interessantes.values())

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(interessantes, f, ensure_ascii=False, indent=2)

    afficher("Créneaux intéressants", interessantes)
    print(f"\n-> {len(interessantes)} créneaux enregistrés dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()