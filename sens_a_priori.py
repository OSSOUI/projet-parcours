"""Sens a priori du ruban : le point zero de la question Q2.

Q2 : quand les agents LLM s'accordent sur un sens, est-ce le fruit de leurs
echanges, ou de ce qu'ils ont en commun avant meme de se parler (le meme
modele, le meme prompt, le meme corpus) ? Pour trancher, il faut savoir ce
que chaque agent dit du ruban SANS AUCUNE information sociale.

Chaque personnage de la population recoit le prompt de sa premiere decision,
sans rien de social : ni qui le porte dans son groupe ou sur le campus, ni
message, ni souvenir. Quatre variantes (decidees le 28 octobre) ajoutent le
socle commun couche par couche :

  nu       le meme prompt systeme et le meme modele ; ni profil, ni
           personnalite, ni histoire du ruban, ni document
  profil   + son profil, sa personnalite et sa situation (une pionniere sait
           qu'elle a lance le ruban), sans document
  neutre   + les passages retrouves dans corpus_neutre/ (chartes et reglement
           tels quels, chroniques sans trajectoire ni morale)
  complet  + les passages retrouves dans corpus/, celui des runs deja faits

Un appel par personnage et par variante. Le meme personnage garde le meme
modele dans les quatre variantes : les ecarts se lisent agent par agent. Les
agents a regles n'ont pas de modele : ils repondent avec llm_petit. La
temperature est celle des runs (0,9) : c'est un tirage, pas une verite.

    python3 sens_a_priori.py --tirages 5              # graine 100, 4 variantes, 5 tirages
    python3 sens_a_priori.py --variantes nu profil    # une partie seulement
    python3 sens_a_priori.py --graine 101

Ecrit resultats/sens_a_priori_g<graine>_<variante>.json (reponses, prompts, resume).
"""
import argparse
import collections
import json
import math
import os
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from ephemere import population  # noqa: E402
from ephemere.agents_llm import CONSIGNE, SYSTEME, DecideurLLM, detecter_derive  # noqa: E402
from ephemere.contrat import SENS  # noqa: E402
from ephemere.horloge import Horloge  # noqa: E402
from ephemere.llm import ClientLLM, charger_env  # noqa: E402
from ephemere.rag import Base  # noqa: E402

INCONNU = "tu ne sais pas encore qui le porte"
VARIANTES = ("nu", "profil", "neutre", "complet")
CORPUS = {"neutre": "corpus_neutre", "complet": "corpus"}
SITUATION_NUE = "Un ruban de couleur noue au poignet est apparu sur le campus."


def consigne_neutre(decideur, agent, t_sim, documents, nu=False):
    """Le prompt de la premiere decision, sans aucune information sociale.

    nu : ni profil, ni personnalite, ni histoire du ruban ; le prenom et le
    groupe restent, parce que le prompt des runs les nomme toujours.
    """
    h = Horloge(0)
    h.aller_a(t_sim)
    return CONSIGNE.format(
        nom=agent["nom"], profil="etudiant" if nu else agent["profil"].replace("_", " "),
        groupe=agent["groupe"],
        personnalite="" if nu else agent.get("personnalite", ""), date=h.lisible(),
        situation=SITUATION_NUE if nu else decideur._situation(agent),
        nb_groupe=INCONNU, noms_groupe="", campus=INCONNU,
        messages="- (rien de nouveau)", souvenirs="- (rien pour l'instant)",
        documents="\n".join(f"- {d['titre']} ({d['source']}) : {d['passage'][:220]}"
                            for d in documents) or "- (rien qui te revienne)",
        etat="portes" if agent["porte"] else "ne portes pas",
        categories="\n".join(f"- {cle} : {texte}" for cle, texte in SENS.items()),
        voisins="",
    )


def entropie(compte):
    n = sum(compte.values())
    if not n:
        return None
    return -sum(k / n * math.log(k / n) for k in compte.values() if k) / math.log(len(SENS))


def resumer(reponses):
    valides = [r for r in reponses if r["incident"] is None]
    tout = collections.Counter(r["categorie"] for r in valides)
    dominant, nb = tout.most_common(1)[0] if tout else (None, 0)
    return {
        "appels": len(reponses), "valides": len(valides),
        "repartition": dict(tout.most_common()),
        "dominant": dominant, "part_dominant": round(nb / len(valides), 3) if valides else None,
        "entropie": round(entropie(tout), 3) if valides else None,
        "porte": sum(r["porte"] for r in valides),
        "par_modele": {m: dict(collections.Counter(r["categorie"] for r in valides
                                                   if r["modele"] == m).most_common())
                       for m in sorted({r["modele"] for r in valides})},
        "par_profil": {p: dict(collections.Counter(r["categorie"] for r in valides
                                                   if r["profil"] == p).most_common())
                       for p in sorted({r["profil"] for r in valides})},
        "incidents": dict(collections.Counter(r["incident"] for r in reponses if r["incident"])),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--graine", type=int, default=100)
    p.add_argument("--agents", type=int, default=20)
    p.add_argument("--config", default=os.path.join(RACINE, "config", "tessaline.json"))
    p.add_argument("--variantes", nargs="+", choices=VARIANTES, default=list(VARIANTES))
    p.add_argument("--tirages", type=int, default=1,
                   help="tirages par agent et par variante, chacun avec sa graine LLM : "
                        "a temperature 0,9, un seul tirage est trop bruite")
    p.add_argument("--fournisseur", default="ollama")
    p.add_argument("--passages", type=int, default=3)
    args = p.parse_args()

    agents, config = population.construire(args.config, args.agents, args.graine)
    charger_env(os.path.join(RACINE, ".env"))
    modeles = config["modeles"][args.fournisseur]
    client = ClientLLM(args.fournisseur, modeles)
    clients = [ClientLLM(args.fournisseur, modeles, graine=f"apriori:{args.graine}:{t}")
               for t in range(args.tirages)]
    t_sim = 1440   # moment de la premiere decision dans un run synchrone
    print(f"Sens a priori, graine {args.graine}, {len(agents)} personnages, "
          f"temperature {client.temperature}, variantes {' '.join(args.variantes)}")
    os.makedirs(os.path.join(RACINE, "resultats"), exist_ok=True)
    for variante in args.variantes:
        base = Base(os.path.join(RACINE, CORPUS[variante])) if variante in CORPUS else None
        print(f"\n== {variante}")
        reponses = []
        for tirage, client_t in enumerate(clients):
            for a in agents:
                taille = a["moteur"] if a["moteur"] != "regles" else "llm_petit"
                decideur = DecideurLLM(client_t, taille, base=base, k=args.passages)
                requete, documents = decideur._recuperer(a, t_sim)
                consigne = consigne_neutre(decideur, a, t_sim, documents, nu=variante == "nu")
                rep = client_t.json(SYSTEME, consigne, taille, cle=f"{variante}:{a['id']}")
                nature, _ = detecter_derive(rep)
                ok = nature is None
                r = {"tirage": tirage, "graine_llm": client_t.graine_appel(f"{variante}:{a['id']}"),
                     "agent": a["id"], "profil": a["profil"], "groupe": a["groupe"],
                     "moteur_du_run": a["moteur"], "taille": taille, "modele": modeles[taille],
                     "porte_avant": a["porte"], "incident": nature,
                     "porte": bool(rep["porte"]) if ok else None,
                     "categorie": rep["categorie"] if ok else None,
                     "sens": str(rep.get("sens", ""))[:300] if ok else "",
                     "raison": str(rep.get("raison", ""))[:300] if ok else "",
                     "documents": [f"{d['id']}#{d['numero']}" for d in documents],
                     "requete": requete, "consigne": consigne}
                reponses.append(r)
                print(f"  {a['nom']:9s} {a['profil']:17s} {modeles[taille]:12s} "
                      + (f"{r['categorie']:16s} {'porte' if r['porte'] else '-':6s} {r['sens'][:60]}"
                         if ok else f"INCIDENT {nature}"))
        resume = resumer(reponses)
        print(f"  repartition : {resume['repartition']}")
        print(f"  sens dominant : {resume['dominant']} a {resume['part_dominant']:.0%}, "
              f"entropie {resume['entropie']}")
        for m, c in resume["par_modele"].items():
            print(f"    {m:12s} {c}")
        suffixe = f"_t{args.tirages}" if args.tirages > 1 else ""
        sortie = os.path.join(RACINE, "resultats",
                              f"sens_a_priori_g{args.graine}_{variante}{suffixe}.json")
        with open(sortie, "w", encoding="utf-8") as f:
            json.dump({"date": datetime.now().isoformat(timespec="seconds"),
                       "graine": args.graine, "variante": variante, "tirages": args.tirages,
                       "corpus": CORPUS.get(variante), "agents": len(agents),
                       "fournisseur": args.fournisseur, "modeles": modeles,
                       "temperature": client.temperature, "t_sim": t_sim, "systeme": SYSTEME,
                       "resume": resume, "reponses": reponses}, f, ensure_ascii=False, indent=1)
        print(f"  ecrit dans {sortie}")


if __name__ == "__main__":
    main()
