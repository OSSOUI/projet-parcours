"""Narratrice externe : raconte un run depuis son journal, sans jamais y toucher.

Un observateur hors du monde. Elle lit runs/<run>.jsonl, ecrit ses syntheses
dans runs/<run>.narration.jsonl (narratrice.v1 puis narration.v1), et rien
d'autre : le simulateur n'ouvre jamais ce fichier, ne l'importe pas, et son
journal refuse les evenements d'observateur. Chaque affirmation cite ses
evenements sources (run#seq) ; ses nombres sont verifies contre les faits
calcules depuis le journal (ephemere/narration.py).

    python3 narratrice.py runs/c1_llm_01.jsonl                 # run termine
    python3 narratrice.py --suivre runs/mon_run.jsonl          # pendant le run
    python3 narratrice.py --rejeu runs/c1_llm_01.narration.jsonl   # sans modele

Desactivee par defaut : sans cette commande, aucune narration n'existe et
aucun appel n'est fait. Le suivi refuse un run asynchrone : la latence d'un
agent y devient du temps simule, et la charge du modele par la narratrice
pourrait alors changer le monde.
"""
import argparse
import json
import os
import sys
import time

from ephemere import journal
from ephemere import narration as N

RACINE = os.path.dirname(os.path.abspath(__file__))
PERMUTATIONS = 1000         # comme emergence.py : memes p que resultats/emergence_reference.json


def emergence_du_run(chemin):
    """L'indicateur corrige sur un run termine, ou None s'il ne se calcule pas."""
    import emergence
    try:
        r = emergence.analyser(chemin, emergence.distributions(), PERMUTATIONS)
    except Exception:
        return None
    return r if r.get("agents_llm") else None


def client(args, graine):
    from ephemere.llm import ClientLLM, charger_env
    charger_env(os.path.join(RACINE, ".env"))
    with open(os.path.join(RACINE, "config", "tessaline.json"), encoding="utf-8") as f:
        modeles = json.load(f)["modeles"][args.fournisseur]
    c = ClientLLM(args.fournisseur, modeles, pause=0.0, temperature=args.temperature,
                  graine=graine)
    c.delai_s = args.delai
    return c, modeles[args.taille]


# Trois canaux, a ne jamais melanger a l'affichage (Godot compris, plus tard) :
# les constats sont calcules depuis le journal et verifies ; les interpretations
# sont des hypotheses ; les incertitudes disent ce que les faits ne tranchent pas.
# Le champ "texte" d'une narration les melange (etiquetes) : un afficheur doit
# partir des affirmations, pas de ce champ. Rejetees : jamais affichees.
CANAUX = {"observation": "constats", "mesure": "constats",
          "interpretation": "hypotheses", "incertitude": "incertitudes"}


def recit(n):
    """Les affirmations verifiees d'une narration, rangees par canal."""
    canaux = {"constats": [], "hypotheses": [], "incertitudes": []}
    for a in n["affirmations"]:
        if a["statut"] == "verifiee":
            canaux[CANAUX[a["type"]]].append(a)
    return canaux


def afficher(n, hypotheses=False):
    """Le recit principal ne montre que les constats. Avec hypotheses=True, les
    interpretations et incertitudes suivent, a part et annoncees comme telles."""
    print(f"\n{n['narration']:>4s}  {n['fenetre']['debut']} -> {n['fenetre']['fin']}  "
          f"[{n['statut']}]" + (f"  incident : {n['incident']}" if n["incident"] else ""))
    canaux = recit(n)
    for a in canaux["constats"] or [{"texte": "(aucun constat verifie)"}]:
        print(f"      {a['texte']}")
    caches = len(canaux["hypotheses"]) + len(canaux["incertitudes"])
    if hypotheses:
        for nom, titre in (("hypotheses", "hypothese, non verifiee"),
                           ("incertitudes", "incertitude")):
            for a in canaux[nom]:
                print(f"      ({titre}) {a['texte']}")
    elif caches:
        print(f"      ({caches} hypothese(s) ou incertitude(s) masquee(s) : --hypotheses)")
    rejetees = [a for a in n["affirmations"] if a["statut"] == "rejetee"]
    if rejetees:
        print(f"      ({len(rejetees)} affirmation(s) rejetee(s) : "
              + "; ".join(a["raison"] for a in rejetees) + ")")
    if n["sources"]:
        print(f"      sources : {', '.join(n['sources'][:8])}"
              + (f" ... (+{len(n['sources']) - 8})" if len(n["sources"]) > 8 else ""))


def ouvrir(args, chemin, mode, entete):
    sortie = args.sortie or chemin[:-len(".jsonl")] + ".narration.jsonl"
    c, modele = client(args, entete.get("graine"))
    s = N.Sortie(sortie, entete["run"], chemin)
    s.ecrire("narratrice.v1", source=os.path.relpath(chemin, RACINE),
             empreinte_source=N.sha256(chemin) if mode == "post" else None, mode=mode,
             periode=args.periode, taille=args.taille, modele=modele,
             temperature=args.temperature, empreinte_prompt=N.EMPREINTE_PROMPT,
             version_contrat=N.contrat.VERSION_CONTRAT)
    return c, s


def narrer_fenetre(c, s, args, fen, av, ap, em):
    n = N.narrer(c, fen, av, ap, args.taille, em, args.max_tokens, args.essais)
    s.narration(n)
    afficher(n, args.hypotheses)
    return n


def post(args):
    evenements = journal.lire(args.journal)
    c, s = ouvrir(args, args.journal, "post", evenements[0])
    em = (emergence_du_run(args.journal)
          if any(e["schema"] == "bilan.v1" for e in evenements) else None)
    try:
        for fen, av, ap, e in N.parcourir(evenements, args.periode, em):
            narrer_fenetre(c, s, args, fen, av, ap, e)
    finally:
        s.fermer()
    print(f"\nnarrations ecrites dans {s.chemin}")


def suivre(args):
    """Lit le journal pendant le run ; narre chaque fenetre des qu'elle est close."""
    chemin, evenements, reste, faites = args.journal, [], "", set()
    while not os.path.exists(chemin):
        time.sleep(0.5)
    c = s = None
    calme = time.time()
    with open(chemin, encoding="utf-8") as f:
        while True:
            morceau = f.read()
            if morceau:
                calme = time.time()
                reste += morceau
                *lignes, reste = reste.split("\n")   # seules les lignes completes
                for l in lignes:
                    if l.strip():
                        e = json.loads(l)
                        e.setdefault("seq", len(evenements))
                        evenements.append(e)
            if evenements and s is None:
                if evenements[0].get("mode") == "asynchrone":
                    raise SystemExit("Suivi refuse : run asynchrone (la charge du modele "
                                     "changerait le temps simule). Narrez-le apres coup.")
                c, s = ouvrir(args, chemin, "suivi", evenements[0])
            for fen, av, ap, _ in N.parcourir(evenements, args.periode, None):
                if fen[0] not in faites:
                    faites.add(fen[0])
                    narrer_fenetre(c, s, args, fen, av, ap, None)
            if any(e["schema"] == "bilan.v1" for e in evenements[-3:]):
                break
            if time.time() - calme > args.silence:
                print(f"\n[narratrice] journal muet depuis {args.silence:.0f} s : arret")
                break
            time.sleep(0.5)
    if s:
        s.fermer()
        print(f"\nnarrations ecrites dans {s.chemin}")


def rejeu(args):
    """Reaffiche et revalide les narrations enregistrees. Aucun appel au modele."""
    entete, narrations = N.lire_narrations(args.rejeu)
    chemin = args.journal_rejeu or os.path.join(RACINE, entete["source"])
    if entete["mode"] == "post" and entete["empreinte_source"] != N.sha256(chemin):
        print(f"ATTENTION : {chemin} n'est plus le journal narre (empreinte differente)")
    em = emergence_du_run(chemin) if entete["mode"] == "post" else None
    entete, narrations, ecarts = N.rejouer(args.rejeu, chemin, em)
    for n in narrations:
        afficher(n, args.hypotheses)
    print(f"\nrejeu : {len(narrations)} narrations relues, "
          f"{len(narrations) - len({e[0] for e in ecarts})} identiques au recalcul, "
          f"{len(ecarts)} ecart(s)")
    for nom, quoi in ecarts:
        print(f"  {nom} : {quoi}")
    return 1 if ecarts else 0


def bilan(fichiers):
    """Mesures sur des narrations enregistrees : statuts, affirmations, sources, cout."""
    from collections import Counter
    total = {"narrations": 0, "statuts": Counter(), "types": Counter(), "rejets": Counter(),
             "factuelles": 0, "factuelles_verifiees": 0, "sources_citees": 0,
             "sources_invalides": 0, "latences": [], "tokens": 0, "par_fichier": {}}
    for chemin in fichiers:
        entete, narrations = N.lire_narrations(chemin)
        ids = {journal.identifiant(e) for e in journal.lire(os.path.join(RACINE, entete["source"]))}
        local = Counter()
        for n in narrations:
            total["narrations"] += 1
            total["statuts"][n["statut"]] += 1
            local[n["statut"]] += 1
            for a in n["affirmations"]:
                total["types"][a["type"]] += 1
                if a["type"] in ("observation", "mesure"):
                    total["factuelles"] += 1
                    total["factuelles_verifiees"] += a["statut"] == "verifiee"
                if a["statut"] == "rejetee":
                    total["rejets"][a["raison"].split(" :")[0]] += 1
            total["sources_citees"] += len(n["sources"])
            total["sources_invalides"] += sum(1 for x in n["sources"] if x not in ids)
            if n["mesure"].get("latence_s"):
                total["latences"].append(n["mesure"]["latence_s"])
            total["tokens"] += (n["mesure"].get("tokens_entree") or 0) + (
                n["mesure"].get("tokens_sortie") or 0)
        total["par_fichier"][os.path.basename(chemin)] = dict(local)
    lat = sorted(total.pop("latences"))
    total["latence_s"] = {"n": len(lat), "mediane": lat[len(lat) // 2] if lat else None,
                          "max": lat[-1] if lat else None}
    total["part_factuelles_verifiees"] = (round(total["factuelles_verifiees"] / total["factuelles"], 3)
                                          if total["factuelles"] else None)
    for k in ("statuts", "types", "rejets"):
        total[k] = dict(total[k].most_common())
    print(json.dumps(total, ensure_ascii=False, indent=1))
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("journal", nargs="?", help="runs/<run>.jsonl a narrer")
    p.add_argument("--suivre", action="store_true", help="pendant le run, au fil du journal")
    p.add_argument("--rejeu", metavar="NARRATION", help="rejouer un .narration.jsonl, sans modele")
    p.add_argument("--journal", dest="journal_rejeu",
                   help="avec --rejeu : le journal narre, si ce n'est pas celui de l'en-tete")
    p.add_argument("--sortie", help="defaut : runs/<run>.narration.jsonl")
    p.add_argument("--periode", type=int, default=1, help="releves par narration (1 = un jour)")
    p.add_argument("--fournisseur", default="ollama")
    p.add_argument("--taille", default="llm_grand", choices=["llm_grand", "llm_petit"])
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--delai", type=float, default=60, help="delai maximal d'un appel (s)")
    p.add_argument("--essais", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=600)
    p.add_argument("--hypotheses", action="store_true",
                   help="affiche aussi interpretations et incertitudes, a part des constats")
    p.add_argument("--silence", type=float, default=600,
                   help="en suivi : arret si le journal ne bouge plus (s)")
    p.add_argument("--bilan", nargs="+", metavar="NARRATION",
                   help="mesurer des .narration.jsonl enregistres (sans modele)")
    p.add_argument("--json", help="avec --bilan : ecrire les mesures dans ce fichier")
    args = p.parse_args()
    if args.bilan:
        b = bilan(args.bilan)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(b, f, ensure_ascii=False, indent=1)
        return 0
    if args.rejeu:
        return rejeu(args)
    if not args.journal:
        p.error("donnez un journal runs/<run>.jsonl, ou --rejeu")
    if os.path.basename(args.journal).count(".") > 1:
        p.error("on narre un journal du monde (runs/<run>.jsonl), pas un fichier annexe")
    return suivre(args) if args.suivre else post(args)


if __name__ == "__main__":
    sys.exit(main())
