"""Rejeu complet d'un run, sans aucun appel au modele : monde, ombres, narrations, scene.

  monde        le run est resimule dans la boucle actuelle du simulateur ; chaque
               decision recoit la reponse brute enregistree (perception.v1). Le
               monde rejoue doit etre identique au journal, evenement par evenement.
  ombres       pendant ce rejeu, chaque ombre recoit une reponse DELIBEREMENT
               differente de la decision reelle (port inverse, autre sens). Si
               une ombre touchait au monde, le rejeu divergerait : il ne doit pas.
  narrations   narratrice.py --rejeu : chaque narration est recalculee et revalidee.
  scene        l'etat du campus reconstruit depuis le fichier (ce que le pont
               envoie a la scene) est compare au dernier releve du journal.

    python3 rejeu_integration.py runs/demo_x.jsonl [--json runs/demo_x.rejeu.json]

Limite : les conversations privees (--conversation) ne sont pas rejouees.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import simuler  # noqa: E402
from ephemere import narration as N  # noqa: E402
from ephemere import population  # noqa: E402
from ephemere.agents_llm import DecideurLLM  # noqa: E402
from ephemere.campus import Campus  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.journal import Journal  # noqa: E402
from ephemere.llm import extraire_json  # noqa: E402
from ephemere.monde import Monde  # noqa: E402
from ephemere.rag import Base  # noqa: E402
from ephemere.regles_v1 import Regles  # noqa: E402
from narratrice import emergence_du_run  # noqa: E402
from verifier_comparabilite import VOLATILS, lire, premier_ecart  # noqa: E402

HORS_MONDE = {"run.v1", "run.v2", "population.v1", "energie.v1", "coherence.v1", "bilan.v1", "ombre.v1"}


class Rejeu:
    """Rend la reponse enregistree au premier appel d'une cle (la decision reelle),
    et une reponse contraire aux appels suivants de la meme cle (les ombres)."""

    graine = 0

    def __init__(self, reponses):
        self.reponses, self.vus = reponses, {}
        self.derniere_mesure, self.dernier_brut = {}, None
        self.ombres_perturbees = 0

    def json(self, systeme, consigne, taille="llm_petit", cle=None, **_):
        self.derniere_mesure = {"latence_s": 0.0}
        _, agent, t = cle.split(":")
        n = self.vus[cle] = self.vus.get(cle, 0) + 1
        self.dernier_brut = self.reponses.get((agent, int(t)))
        reel = None if self.dernier_brut is None else extraire_json(self.dernier_brut)
        if n == 1 or not isinstance(reel, dict):
            return reel
        self.ombres_perturbees += 1
        autres = [s for s in SENS if s != reel.get("categorie")]
        return {**reel, "porte": not reel.get("porte"), "categorie": autres[n % len(autres)]}


def monde_de(evenements):
    return [{k: v for k, v in e.items() if k not in VOLATILS}
            for e in evenements if e["schema"] not in HORS_MONDE]


def rejouer_monde(evs):
    tete = evs[0]
    if (tete.get("conversation") or {}).get("par_jour"):
        return {"rejoue": False, "raison": "conversations privees : non rejouees"}
    if tete.get("mode") != "synchrone":
        return {"rejoue": False, "raison": "run asynchrone : le temps depend des latences"}
    client = Rejeu({(e["agent"], e["t_sim"]): e["reponse_brute"]
                    for e in evs if e["schema"] == "perception.v1"})
    agents, config = population.construire(os.path.join(RACINE, "config", tete["config"]),
                                           tete["nb_agents"], tete["graine"])
    base = Base(os.path.join(RACINE, tete.get("corpus", "corpus")))
    regles = Regles()
    moteurs = {t: DecideurLLM(client, t, base=base, memoire_sens=bool(tete.get("memoire_sens")))
               for t in {a["moteur"] for a in agents} - {"regles"}}
    decideurs = {a["id"]: moteurs.get(a["moteur"], regles) for a in agents}
    jours = max(e["t_sim"] for e in evs if e["schema"] == "indicateurs.v1") // simuler.MINUTES_PAR_JOUR
    args = types.SimpleNamespace(jours=jours, pas_min=simuler.MINUTES_PAR_JOUR,
                                 releve_min=simuler.MINUTES_PAR_JOUR,
                                 ombres=list(tete.get("ombres") or []), telemetrie=None,
                                 dialogue=None, pionnieres_simultanees=False)
    with tempfile.TemporaryDirectory() as d:
        with Journal(d, "rejeu", Horloge(0)) as j:
            j.ecrire("run.v2", **{k: v for k, v in tete.items()
                                  if k not in VOLATILS | {"schema", "t_sim", "t_sim_lisible"}})
            j.ecrire("population.v1", resume=population.resume(agents), agents=[
                {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
                for a in agents])
            with contextlib.redirect_stdout(io.StringIO()):
                simuler.tourner_synchrone(Monde(agents, config.get("perception")), decideurs, j,
                                          j.horloge, args)
            chemin = j.chemin
        rejoue = lire(chemin)
    attendu, obtenu = monde_de(evs), monde_de(rejoue)
    ecart = premier_ecart(attendu, obtenu)
    cles = lambda x: sorted((e["agent"], e["t_decision"], e["masque"], e["reel_porte"],
                             e["reel_categorie"]) for e in x if e["schema"] == "ombre.v1")
    ombres_journal = [e for e in evs if e["schema"] == "ombre.v1"]
    # Une ombre n'est jamais appliquee : apres chaque ombre qui differe du reel, l'etat
    # de l'agent dans le journal est celui de la decision reelle.
    differentes = sum(1 for e in ombres_journal if e["valide"] and e["reel_valide"]
                      and (e["porte"], e["categorie"]) != (e["reel_porte"], e["reel_categorie"]))
    return {"rejoue": True, "evenements_du_monde": len(attendu),
            "monde_identique": ecart is None,
            "premier_ecart": None if ecart is None else repr(ecart)[:400],
            "jours": jours, "memoire_sens": bool(tete.get("memoire_sens")),
            "ombres_journal": len(ombres_journal),
            "ombres_rejouees_avec_reponse_contraire": client.ombres_perturbees,
            "ombres_memes_cles_et_reel": cles(ombres_journal) == cles(rejoue),
            "ombres_du_journal_differentes_du_reel": differentes}


def rejouer_narrations(chemin_run):
    chemin_n = chemin_run[:-len(".jsonl")] + ".narration.jsonl"
    if not os.path.exists(chemin_n):
        return {"rejoue": False, "raison": "pas de fichier de narration"}
    entete, _ = N.lire_narrations(chemin_n)
    # Comme narratrice.py --rejeu : une narration faite apres le run cite l'indicateur
    # d'emergence du run, recalcule ici sans modele.
    em = emergence_du_run(chemin_run) if entete["mode"] == "post" else None
    entete, narrations, ecarts = N.rejouer(chemin_n, chemin_run, em)
    aff = [a for n in narrations for a in n["affirmations"]]
    compte = lambda t, s: sum(1 for a in aff if a["type"] in t and a["statut"] == s)
    return {"rejoue": True, "narrations": len(narrations),
            "identiques": len(narrations) - len({e[0] for e in ecarts}), "ecarts": ecarts[:20],
            "statuts": {s: sum(1 for n in narrations if n["statut"] == s)
                        for s in ("valide", "partiel", "vide", "incident")},
            "constats_verifies": compte(("observation", "mesure"), "verifiee"),
            "hypotheses_verifiees": compte(("interpretation",), "verifiee"),
            "incertitudes_verifiees": compte(("incertitude",), "verifiee"),
            "affirmations_rejetees": sum(1 for a in aff if a["statut"] == "rejetee")}


def rejouer_scene(evs):
    """L'etat que le pont construit et envoie a la scene, depuis le seul fichier."""
    c = Campus(en_direct=False)
    for e in evs:
        c.appliquer(dict(e), evs[0]["run"])
    dernier = [e for e in evs if e["schema"] == "indicateurs.v1"][-1]
    i = c.indicateurs()
    return {"evenements_appliques": c.vus, "evenements_du_journal": len(evs),
            "manquants": c.trous, "doublons": c.doublons,
            "adoption_scene": i["taux_adoption"], "adoption_journal": dernier["taux_adoption"],
            "identique_au_dernier_releve": abs(i["taux_adoption"] - dernier["taux_adoption"]) < 1e-9}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("run")
    p.add_argument("--json")
    args = p.parse_args()
    evs = lire(args.run)
    r = {"run": os.path.basename(args.run)[:-6], "monde": rejouer_monde(evs),
         "narrations": rejouer_narrations(args.run), "scene": rejouer_scene(evs)}
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    ok = (r["monde"].get("monde_identique", False) and r["monde"].get("ombres_memes_cles_et_reel")
          and r["scene"]["identique_au_dernier_releve"]
          and (not r["narrations"]["rejoue"] or not r["narrations"]["ecarts"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
