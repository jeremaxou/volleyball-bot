import json
import re
import os

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright


load_dotenv()

TAILLE_LOT = 20               # le site n'accepte que 20 cases cochées à la fois
STATUTS_PAGE1 = ["some"]      # classe CSS du ▲ (一部空き). Ajoute celle du ○ si tu veux aussi les cases entièrement libres
FICHIER_SORTIE = "dispos.json"


# ---------------------------------------------------------------------------
# 1. Navigation jusqu'à la page 施設別空き状況 (tableau des ▲ et ×)
# ---------------------------------------------------------------------------
def aller_a_la_page_des_dispos(page):
    # COLLE ICI TON CODE EXISTANT : login + onglet + case バレーボール + validation
    # À la fin de cette fonction, la page doit afficher le tableau des ▲ / ×.
    URL = "https://www.shisetsu.city.yokohama.lg.jp/user/Home"
    page.goto(URL)
    page.get_by_label("ログイン").click()  
    page.get_by_label("利用者ID").fill(os.environ["LOGIN_ID"])    
    page.get_by_label("パスワード").fill(os.environ["LOGIN_PWD"])
    page.get_by_label("ログイン").click()  

    page.get_by_role("tab", name="利用目的から探す").click()
    page.get_by_role("tabpanel", name="利用目的から探す").get_by_text(" バレーボール ６人制").click()
    page.get_by_role("button", name="検索").click()


    page.get_by_text("さらに読み込む").click()
    page.get_by_text("さらに読み込む").click()
    page.get_by_text("神奈川スポーツセンター").click()
    page.get_by_text("南スポーツセンター", exact=True).click()
    page.get_by_text("旭スポーツセンター").click()
    page.get_by_text("港北スポーツセンター").click()
    page.get_by_text("緑スポーツセンター").click()
    page.get_by_text("戸塚スポーツセンター").click()
    page.get_by_label("次へ進む").click() 


    page.get_by_text("1ヶ月").click()
    page.get_by_text("表示の変更").click() 


# ---------------------------------------------------------------------------
# 2. Lecture des pages (BeautifulSoup sur le HTML fourni par Playwright)
# ---------------------------------------------------------------------------
def cases_a_verifier(html):
    """Page 1 : liste toutes les cases ▲ avec de quoi les retrouver ensuite."""
    soup = BeautifulSoup(html, "html.parser")
    cases = []
    for label in soup.select("td.btn-group-toggle label"):
        if not any(statut in label["class"] for statut in STATUTS_PAGE1):
            continue
        bloc = label.find_parent("div", class_="mb-4")
        cases.append({
            # nom du champ caché : stable entre deux chargements, sert à retrouver la case
            "champ": label.select_one("input[name$='.IsChecked']")["name"],
            "gymnase": bloc.select_one("h3.facility-title").get_text(strip=True),
            "salle": next(label.find_parent("tr").select_one("td.startdate").stripped_strings),
            "date": label.select_one("input[name$='.UseDate']")["value"][:10],
        })
    return cases


def heure(valeur):
    """'730' -> '7:30', '1300' -> '13:00'"""
    v = int(valeur)
    return f"{v // 100}:{v % 100:02d}"


def creneaux_libres(html):
    """Page 2 : liste les créneaux ○ (classe 'vacant')."""
    soup = BeautifulSoup(html, "html.parser")
    resultats = []
    for jour in soup.select("div.events"):
        date = jour.select_one("li.events-date").get_text("", strip=True)
        gymnase = jour.find_previous("h3", class_="facility-title").get_text(strip=True)
        for groupe in jour.select("li.events-group"):
            salle = groupe.select_one(".room-name span").get_text(strip=True)
            for item in groupe.select("li.selection-item"):
                if "vacant" not in item.select_one("div.btn-group-toggle")["class"]:
                    continue
                resultats.append({
                    "gymnase": gymnase,
                    "salle": salle,
                    "date": date,
                    "debut": heure(item.select_one("input[name$='.TimeFrom']")["value"]),
                    "fin": heure(item.select_one("input[name$='.TimeTo']")["value"]),
                })
    return resultats


# ---------------------------------------------------------------------------
# 3. Cocher / décocher une case de la page 1
# ---------------------------------------------------------------------------
ACTIF = re.compile(r"\bactive\b")


def regler_case(page, champ, cochee):
    """Met la case dans l'état voulu (ne clique que si nécessaire), puis vérifie."""
    label = page.locator(f"label:has(input[name='{champ}'])")
    est_cochee = "active" in (label.get_attribute("class") or "").split()
    if est_cochee != cochee:
        # centre la case à l'écran (verticalement et horizontalement) pour qu'elle
        # ne soit pas cachée par la barre fixe du bas ni hors du tableau défilant
        label.evaluate("el => el.scrollIntoView({block: 'center', inline: 'center'})")
        label.click()
    if cochee:
        expect(label).to_have_class(ACTIF)
    else:
        expect(label).not_to_have_class(ACTIF)


# ---------------------------------------------------------------------------
# 4. Boucle principale
# ---------------------------------------------------------------------------

def attendre_vue_mois(page):
    """Attend que le premier tableau affiche plus de 7 jours (= vue 1 mois chargée)."""
    page.wait_for_function(
        "() => (document.querySelector('table.table-schedule')"
        "?.querySelectorAll('thead th.month').length ?? 0) > 7"
    )


def main():
    tous_les_creneaux = []
    sur_serveur = os.environ.get("CI") == "true"   # GitHub Actions définit CI=true

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=None if sur_serveur else "chrome",   # serveur : Chromium fourni par Playwright
            headless=sur_serveur,                         # serveur : pas de fenêtre
            slow_mo=0 if sur_serveur else 200,
        )
        page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
        page.on("dialog", lambda d: d.accept())   # accepte d'éventuelles alertes/confirmations

        try:
            aller_a_la_page_des_dispos(page)
            attendre_vue_mois(page)

            cases = cases_a_verifier(page.content())
            nb_lots = (len(cases) + TAILLE_LOT - 1) // TAILLE_LOT
            dates = sorted({c["date"] for c in cases})
            print(f"{len(cases)} cases ▲ trouvées -> {nb_lots} lot(s)")
            if dates:
                print(f"Dates couvertes : du {dates[0]} au {dates[-1]}")

            # Point de départ propre : rien de coché
            for case in cases:
                regler_case(page, case["champ"], False)

            for i in range(0, len(cases), TAILLE_LOT):
                lot = cases[i:i + TAILLE_LOT]
                print(f"\nLot {i // TAILLE_LOT + 1}/{nb_lots} ({len(lot)} cases)")

                # a. cocher le lot
                for case in lot:
                    regler_case(page, case["champ"], True)

                # b. page suivante : 時間帯別空き状況
                page.get_by_role("button", name="次へ進む").click()
                page.locator("div.events").first.wait_for()

                # c. lire les créneaux libres
                creneaux = creneaux_libres(page.content())
                tous_les_creneaux.extend(creneaux)
                for c in creneaux:
                    print(f"  ○ {c['gymnase']} | {c['salle']} | {c['date']} | {c['debut']}-{c['fin']}")

                # d. retour à la page 1
                page.get_by_role("button", name="前に戻る").click()
                attendre_vue_mois(page)

                # e. décocher le lot
                for case in lot:
                    regler_case(page, case["champ"], False)

        except Exception:
            # capture de l'écran au moment du plantage (récupérable sur GitHub)
            page.screenshot(path="erreur.png", full_page=True)
            raise
        finally:
            browser.close()

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(tous_les_creneaux, f, ensure_ascii=False, indent=2)
    print(f"\n{len(tous_les_creneaux)} créneaux libres enregistrés dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()