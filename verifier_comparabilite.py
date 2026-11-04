"""Comparabilite des paires A/E : le code actuel refait-il les runs de reference gelés ?

Chaque run de reference est rejoue dans la boucle actuelle du simulateur avec un
client qui rend, pour chaque decision, la reponse brute que le modele avait
donnee (perception.v1, champ reponse_brute). Si le monde rejoue est identique
evenement par evenement au run gele, alors tout ce qui differe entre A et E vient
des reponses du modele, et non du code.

Trois rejeux par run, sans aucun appel au modele :
  1. configuration du run (ses ombres)       -> monde et perceptions identiques
  2. plus l'ombre sans_souvenirs             -> monde identique (une ombre ne touche pas au monde)
  3. variante --memoire-sens                 -> monde identique ; les prompts ne different
                                                que par la ligne du sens de la veille

    python3 verifier_comparabilite.py runs/exp_reference_llm_reference_0[1-5].jsonl
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import simuler  # noqa: E402
from ephemere import population  # noqa: E402
from ephemere.agents_llm import DecideurLLM  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.llm import extraire_json  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402

VOLATILS = {"t_emission", "t_traitement", "run", "seq"}
LIGNE_SENS = re.compile(r" ; pour toi, le ruban voulait alors dire : [^\n]*")
HORS_MONDE = {"run.v2", "population.v1", "energie.v1", "coherence.v1", "bilan.v1", "ombre.v1"}


class Rejeu:
    """Client qui rend la reponse enregistree pour la cle (agent, instant)."""

    graine = 0   # une graine est presente : le decideur passe la cle de l'appel

    def __init__(self, reponses):
        self.reponses, self.consignes = reponses, []
        self.derniere_mesure, self.dernier_brut = {}, None

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        self.consignes.append((cle, consigne))
        self.derniere_mesure = {"latence_s": 0.0}
        _, agent, t = cle.split(":")
        self.dernier_brut = self.reponses.get((agent, int(t)))
        return None if self.dernier_brut is None else extraire_json(self.dernier_brut)


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def monde_de(evenements):
    return [{k: v for k, v in e.items() if k not in VOLATILS}
            for e in evenements if e["schema"] not in HORS_MONDE]


def rejouer(gele, ombres, memoire_sens):
    tete = gele[0]
    reponses = {(e["agent"], e["t_sim"]): e["reponse_brute"]
                for e in gele if e["schema"] == "perception.v1"}
    client = Rejeu(reponses)
    agents, config = population.construire(os.path.join(RACINE, "config", tete["config"]),
                                           tete["nb_agents"], tete["graine"])
    base = Base(os.path.join(RACINE, tete["corpus"]))
    regles = Regles()
    moteurs = {t: DecideurLLM(client, t, base=base, memoire_sens=memoire_sens)
               for t in {a["moteur"] for a in agents} - {"regles"}}
    decideurs = {a["id"]: moteurs.get(a["moteur"], regles) for a in agents}
    args = types.SimpleNamespace(jours=tete["jours"], pas_min=simuler.MINUTES_PAR_JOUR,
                                 releve_min=simuler.MINUTES_PAR_JOUR, ombres=list(ombres),
                                 telemetrie=None, dialogue=None, pionnieres_simultanees=False)
    with tempfile.TemporaryDirectory() as d:
        with Journal(d, "rejeu", Horloge(0)) as j:
            j.ecrire("run.v2", **{k: v for k, v in tete.items()
                                  if k not in VOLATILS | {"schema", "t_sim", "t_sim_lisible"}})
            j.ecrire("population.v1", resume=population.resume(agents), agents=[
                {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
                for a in agents])
            with contextlib.redirect_stdout(io.StringIO()):   # le simulateur affiche chaque pas
                simuler.tourner_synchrone(Monde(agents, config.get("perception")), decideurs, j,
                                          j.horloge, args)
            chemin = j.chemin
        return lire(chemin), client


def premier_ecart(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, x, y
    return (min(len(a), len(b)), None, None) if len(a) != len(b) else None


def sans_sens_affiche(evenements):
    out = []
    for e in evenements:
        if e["schema"] == "perception.v1":
            e = dict(e, souvenirs=[{k: v for k, v in s.items() if k != "sens_affiche"}
                                   for s in e["souvenirs"]])
        out.append(e)
    return out


def verifier_run(chemin):
    gele = lire(chemin)
    tete = gele[0]
    attendu = monde_de(gele)
    ombres = tete.get("ombres") or []
    res = {"run": os.path.basename(chemin), "graine": tete["graine"],
           "evenements_du_monde": len(attendu),
           "decisions_llm": sum(e["schema"] == "perception.v1" for e in gele)}

    obtenu, c_ref = rejouer(gele, ombres, False)
    res["identique_configuration_du_run"] = premier_ecart(attendu, monde_de(obtenu)) is None
    if not res["identique_configuration_du_run"]:
        res["ecart"] = repr(premier_ecart(attendu, monde_de(obtenu)))[:600]

    obtenu, _ = rejouer(gele, list(ombres) + ["sans_souvenirs"], False)
    res["identique_avec_sans_souvenirs"] = premier_ecart(attendu, monde_de(obtenu)) is None

    obtenu, c_var = rejouer(gele, [], True)
    m = monde_de(obtenu)
    res["monde_identique_variante"] = (premier_ecart(attendu, sans_sens_affiche(m)) is None)
    # Prompts reels (decisions, pas les ombres) : la variante n'ajoute que la ligne du sens.
    reels_ref = [c for k, c in c_ref.consignes][::1 + len(ombres)]
    reels_var = [c for k, c in c_var.consignes]
    nettoyes = [LIGNE_SENS.sub("", c) for c in reels_var]
    res["prompts_variante_moins_ligne_sens_identiques"] = nettoyes == reels_ref
    res["prompts_variante_avec_sens"] = sum(1 for c in reels_var if LIGNE_SENS.search(c))
    res["prompts"] = len(reels_var)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--json", help="ecrit le bilan dans ce fichier")
    args = p.parse_args()
    bilan = []
    for chemin in args.runs:
        r = verifier_run(chemin)
        bilan.append(r)
        ok = all(r[k] for k in ("identique_configuration_du_run", "identique_avec_sans_souvenirs",
                                "monde_identique_variante",
                                "prompts_variante_moins_ligne_sens_identiques"))
        print(f"{'ok  ' if ok else 'ECHEC'} {r['run']} (graine {r['graine']}) : "
              f"{r['evenements_du_monde']} evenements du monde, {r['decisions_llm']} decisions LLM, "
              f"sens affiche dans {r['prompts_variante_avec_sens']}/{r['prompts']} prompts de la "
              f"variante")
        if not ok:
            print("      ", {k: v for k, v in r.items() if isinstance(v, bool)}, r.get("ecart", ""))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(bilan, f, ensure_ascii=False, indent=1)
    sys.exit(0 if all(all(v for v in r.values() if isinstance(v, bool)) for r in bilan) else 1)


if __name__ == "__main__":
    main()
