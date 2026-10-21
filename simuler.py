"""Ephemere : naissance, gloire et mort d'une mode a Tessaline.

    python3 simuler.py --agents 20 --jours 25 --tout-regles --nom baseline
    python3 simuler.py --agents 20 --jours 25 --mode synchrone  --fournisseur ollama
    python3 simuler.py --agents 20 --jours 25 --mode asynchrone --fournisseur groq

Les deux modes relevent les indicateurs sur la MEME grille de temps simule,
sinon leur comparaison (exigence C5) ne voudrait rien dire.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ephemere import population
from ephemere.agents_llm import DecideurLLM
from ephemere import commandes as cmd
from ephemere.rag import Base
from ephemere.contrat import VERSION_CONTRAT
from ephemere.horloge import MINUTES_PAR_JOUR, Echeancier, Horloge
from ephemere.journal import Journal
from ephemere.monde import Monde, memoriser
from ephemere.regles import Regles

RACINE = os.path.dirname(os.path.abspath(__file__))


def fabriquer_decideurs(agents, args, config, base=None):
    """Un moteur de decision par agent (exigences A5 et A6).

    Renvoie (decideurs, client). Les agents a regles et les agents LLM
    cohabitent dans le meme run : c'est A6. Deux tailles de modele sont
    reellement appelees : c'est A5.
    """
    regles = Regles()
    if getattr(args, "tout_grand", False):
        # Reference de l'exigence E5 : meme population, meme graine, mais
        # chaque agent raisonne avec le plus grand modele.
        for a in agents:
            a["moteur"] = "llm_grand"
    if args.tout_regles:
        for a in agents:
            a["moteur"] = "regles"
        return {a["id"]: regles for a in agents}, None

    tailles = sorted({a["moteur"] for a in agents if a["moteur"] != "regles"})
    moteurs, client = {"regles": regles}, None
    if tailles:
        from ephemere.llm import ClientLLM, charger_env
        charger_env(os.path.join(RACINE, ".env"))
        modeles = config.get("modeles", {}).get(args.fournisseur)
        if not modeles:
            raise SystemExit(f"Aucun modele configure pour {args.fournisseur} "
                             f"dans {os.path.basename(args.config)}.")
        client = ClientLLM(args.fournisseur, modeles, pause=args.pause,
                           attente_max=args.attente_max)
        for taille in tailles:
            moteurs[taille] = DecideurLLM(client, taille, base=base, k=args.passages)
            print(f"  {taille:10s} -> {modeles[taille]}")
    return {a["id"]: moteurs[a["moteur"]] for a in agents}, client


def enregistrer(journal, monde, agent, d, horloge):
    """Ecrit la decision, l'incident eventuel et la parole de l'agent."""
    journal.ecrire("decision.v1", agent=agent["id"], porte=d["porte"],
                   categorie=d["categorie"], sens=d["sens"], raison=d["raison"],
                   moteur=agent["moteur"], valide=d["valide"])
    rec = d.get("recuperation")
    if rec and rec.get("requete"):
        # Trace de ce qui a ete retrouve : c'est la preuve demandee par F2.
        journal.ecrire("recuperation.v1", agent=agent["id"], requete=rec["requete"],
                       resultats=[{"id": r["id"], "score": r["score"],
                                   "jour": r["jour"], "numero": r["numero"]}
                                  for r in rec["resultats"]],
                       nb_resultats=len(rec["resultats"]),
                       corpus={"passages_demandes": len(rec["resultats"])})
    perception = d.get("perception")
    if perception:
        journal.ecrire("perception.v1", agent=agent["id"], moteur=agent["moteur"],
                       **perception)
        if perception["violations_c6"]:
            print(f"  [C6 : {len(perception['violations_c6'])} info(s) venue(s) du futur "
                  f"dans le contexte de {agent['nom']}]")
    if d.get("incident"):
        journal.ecrire("incident.v1", agent=agent["id"],
                       nature=d["incident"]["nature"], details=d["incident"]["details"])
    texte = (d.get("publication") or "").strip()
    if not texte:
        return
    nom_cible = (d.get("destinataire") or "").strip()
    cible = monde.adresser(agent["id"], nom_cible, texte,
                           horloge.minutes, horloge.lisible()) if nom_cible else None
    if cible:
        journal.ecrire("publication.v1", agent=agent["id"], texte=texte,
                       portee="personne", destinataire=cible)
    else:
        # Destinataire inconnu ou absent : le message part sur le reseau public.
        monde.publier(agent["id"], texte, horloge.minutes)
        journal.ecrire("publication.v1", agent=agent["id"], texte=texte,
                       portee="campus", destinataire=None)


def appliquer(agent, d, monde, horloge):
    """Ecrit la decision dans l'etat de l'agent.

    Le temps de port s'accumule depuis la decision PRECEDENTE de l'agent, et
    non depuis sa derniere lecture du fil : le relais massif remet la lecture
    a zero sans gonfler le temps de port (et sans lasser la figure populaire).
    """
    ecoule = horloge.minutes - agent.get("derniere_decision", 0)
    if d["porte"]:
        agent["minutes_porte"] += max(0, ecoule)
    agent["porte"] = d["porte"]
    agent["categorie"] = d["categorie"]
    agent["sens"] = d["sens"]
    agent["derniere_decision"] = horloge.minutes
    agent["memoire"] = memoriser(agent["memoire"], {
        "genre": "decision",
        "t_sim": horloge.minutes,
        "t_sim_lisible": horloge.lisible(),
        "fait": f"j'ai decide de {'porter' if d['porte'] else 'ne pas porter'} le ruban",
        "raison": d.get("raison", ""),
    })


def tracer(horloge, agent, d):
    lat = (d.get("mesure") or {}).get("latence_s")
    chrono = f"{lat:5.1f}s" if lat is not None else "     "
    marque = "RUBAN" if d["porte"] else "     "
    alerte = " !" if not d["valide"] else "  "
    print(f"{horloge.lisible()} {agent['nom']:10s} {marque} {d['categorie']:16s} "
          f"{chrono}{alerte}{(d.get('publication') or '')[:48]}")


def traiter_injections(ecoute, monde, journal, horloge):
    """Applique les injections venues de la scene, s'il y en a (exigence D3)."""
    if ecoute is None:
        return
    for commande in ecoute.recuperer():
        nature, details = cmd.appliquer(commande, monde, horloge)
        journal.ecrire("injection.v1", nature=nature, details=details,
                       source=commande.get("source", "inconnue"))
        print(f"{horloge.lisible()}  >> INJECTION {nature} {details}")


def relever(monde, journal, horloge):
    ind = monde.indicateurs()
    monde.noter(horloge.minutes, ind)
    journal.ecrire("indicateurs.v1", **ind)
    print(f"{horloge.lisible()}  >> adoption {ind['taux_adoption']:5.0%}   "
          f"sens dominant {ind['sens_dominant']:16s} {ind['part_sens_dominant']:4.0%}")
    return ind


def tourner_synchrone(monde, decideurs, journal, horloge, args, ecoute=None):
    """Tous les agents decident au meme pas de temps, sur l'etat precedent.

    Sauf les pionnieres, qui se relaient : une sur deux reevalue a chaque pas.
    Toutes ensemble, elles voyaient le meme etat, abandonnaient le meme jour
    puis revenaient le meme jour, et l'adoption oscillait avec une periode de
    deux pas (13 runs sur 30 en baseline, 24 sur 30 dans le temoin). Ce n'etait
    pas un phenomene du campus mais un artefact de la simultaneite.
    --pionnieres-simultanees retablit l'ancien comportement pour le montrer.
    """
    fin = args.jours * MINUTES_PAR_JOUR
    pionnieres = [a["id"] for a in monde.agents.values() if a["profil"] == "pionnier"]
    phase = {aid: i % 2 for i, aid in enumerate(pionnieres)}
    if getattr(args, "pionnieres_simultanees", False):
        phase = {}
    relever(monde, journal, horloge)
    while horloge.minutes < fin:
        horloge.aller_a(horloge.minutes + args.pas_min)
        traiter_injections(ecoute, monde, journal, horloge)
        pas = horloge.minutes // args.pas_min
        decisions = []
        for agent in monde.agents.values():
            if agent["id"] in phase and (pas + phase[agent["id"]]) % 2:
                continue
            d = decideurs[agent["id"]].decider(agent, monde, horloge.minutes,
                                               horloge.lisible())
            monde.marquer_lu(agent, horloge.minutes)
            decisions.append((agent, d))
            tracer(horloge, agent, d)
        # Simultaneite : on n'applique qu'apres avoir interroge tout le monde.
        for agent, d in decisions:
            enregistrer(journal, monde, agent, d, horloge)
            appliquer(agent, d, monde, horloge)
        if horloge.minutes % args.releve_min == 0:
            relever(monde, journal, horloge)


def tourner_asynchrone(monde, decideurs, journal, horloge, args, rng, ecoute=None):
    """Chacun decide a sa cadence. Le monde change entre deux agents.

    Le temps que met le modele a repondre est converti en temps simule
    (--minutes-par-seconde) : un gros modele lent reflechit donc plus
    longtemps dans le monde, et son avis arrive apres celui des autres.
    """
    fin = args.jours * MINUTES_PAR_JOUR
    echeancier = Echeancier()
    for agent in monde.agents.values():
        echeancier.planifier(agent["heure_reveil"] + agent["decalage_min"], agent["id"])
    # Decisions prises mais pas encore effectives : l'agent reflechit encore.
    # Elles reviennent par l'echeancier a t + reflexion, si bien que l'horloge
    # n'a jamais a reculer quand un autre agent se reveille entre-temps.
    en_reflexion = {}
    prochaine_releve = 0
    relever(monde, journal, horloge)

    while len(echeancier):
        t_sim, agent_id = echeancier.prochain()
        if t_sim > fin:
            break
        while prochaine_releve + args.releve_min <= t_sim:
            prochaine_releve += args.releve_min
            horloge.aller_a(prochaine_releve)
            relever(monde, journal, horloge)
        horloge.aller_a(t_sim)
        traiter_injections(ecoute, monde, journal, horloge)
        agent = monde.agents[agent_id]

        if agent_id in en_reflexion:
            d = en_reflexion.pop(agent_id)
        else:
            d = decideurs[agent_id].decider(agent, monde, t_sim, horloge.lisible())
            monde.marquer_lu(agent, t_sim)
            latence = (d.get("mesure") or {}).get("latence_s") or 0
            reflexion = int(latence * args.minutes_par_seconde)
            if reflexion:
                en_reflexion[agent_id] = d
                echeancier.planifier(t_sim + reflexion, agent_id)
                continue
        tracer(horloge, agent, d)
        enregistrer(journal, monde, agent, d, horloge)
        appliquer(agent, d, monde, horloge)
        echeancier.planifier(horloge.minutes + agent["cadence_min"]
                             + rng.randint(-120, 120), agent_id)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agents", type=int, default=12, help="nombre d'agents (C2)")
    p.add_argument("--jours", type=int, default=30, help="duree simulee, en jours")
    p.add_argument("--mode", choices=["synchrone", "asynchrone"], default="synchrone")
    p.add_argument("--graine", type=int, default=42)
    p.add_argument("--config", default=os.path.join(RACINE, "config", "tessaline.json"))
    p.add_argument("--fournisseur", default="ollama", help="ollama, groq ou openrouter")
    p.add_argument("--pause", type=float, default=0.0,
                   help="secondes entre deux appels LLM, pour rester sous le quota")
    p.add_argument("--attente-max", type=float, default=90,
                   help="abandonne l'appel si le quota demande d'attendre plus (s)")
    p.add_argument("--minutes-par-seconde", type=float, default=5.0,
                   help="minutes simulees par seconde de reflexion du modele (mode asynchrone)")
    p.add_argument("--pas-min", type=int, default=MINUTES_PAR_JOUR,
                   help="pas de temps du mode synchrone, en minutes simulees")
    p.add_argument("--pionnieres-simultanees", action="store_true",
                   help="mode synchrone : toutes les pionnieres reevaluent au meme pas "
                        "(artefact d'oscillation, garde pour comparaison)")
    p.add_argument("--releve-min", type=int, default=MINUTES_PAR_JOUR,
                   help="intervalle entre deux releves d'indicateurs")
    p.add_argument("--tout-regles", action="store_true",
                   help="aucun agent LLM : c'est la baseline de l'exigence E1")
    p.add_argument("--tout-grand", action="store_true",
                   help="tous les agents sur le grand modele : reference de l'exigence E5")
    p.add_argument("--energie", choices=["auto", "non"], default="auto",
                   help="mesure l'energie avec CodeCarbon s'il est installe (E4)")
    p.add_argument("--corpus", default=os.path.join(RACINE, "corpus"),
                   help="dossier de la base de connaissances (exigence F1)")
    p.add_argument("--passages", type=int, default=3,
                   help="nombre de passages retrouves par decision")
    p.add_argument("--kafka", nargs="?", const="localhost:9092", default=None,
                   metavar="SERVEUR",
                   help="publie aussi les evenements dans Kafka (defaut localhost:9092)")
    p.add_argument("--nom", default=None)
    args = p.parse_args()

    rng = random.Random(args.graine)
    agents, config = population.construire(args.config, args.agents, args.graine)
    resume = population.resume(agents)
    print(f"Tessaline, {resume['total']} agents")
    print(f"  profils : {resume['par_profil']}")
    print(f"  moteurs : {resume['par_moteur']}")

    base = Base(args.corpus)
    print(f"  corpus  : {base.resume()}")
    decideurs, client = fabriquer_decideurs(agents, args, config, base=base)
    print()
    monde = Monde(agents, config.get("perception"))
    horloge = Horloge(0)
    nom = args.nom or f"{args.mode}_{datetime.now():%Y%m%d_%H%M%S}"

    bus, ecoute = None, None
    if args.kafka:
        from ephemere.bus import Bus
        bus = Bus(args.kafka, nom_run=nom)   # echoue vite, avant tout appel LLM
        ecoute = cmd.Ecoute(args.kafka)      # injections venues de la scene (D3)

    if args.tout_regles and args.tout_grand:
        raise SystemExit("--tout-regles et --tout-grand s'excluent.")
    mesureur = Energie(args.energie == "auto", nom)
    t0 = time.perf_counter()
    interrompu = False
    with Journal(os.path.join(RACINE, "runs"), nom, horloge, bus=bus) as journal:
        journal.ecrire("run.v1", mode=args.mode, nb_agents=len(agents),
                       graine=args.graine, jours=args.jours,
                       config=os.path.basename(args.config),
                       version_contrat=VERSION_CONTRAT)
        # Qui habite ce monde. Publie dans le flux pour que tout consommateur
        # puisse afficher des noms et des groupes sans fichier annexe.
        journal.ecrire("population.v1", resume=resume, agents=[
            {k: a[k] for k in ("id", "nom", "profil", "groupe", "moteur", "porte")}
            for a in agents])
        mesureur.demarrer()
        try:
            if args.mode == "synchrone":
                tourner_synchrone(monde, decideurs, journal, horloge, args, ecoute)
            else:
                tourner_asynchrone(monde, decideurs, journal, horloge, args, rng, ecoute)
        except KeyboardInterrupt:
            interrompu = True
            print("\n!! Run arrete a la main. Les evenements deja ecrits restent valides.")

        journal.ecrire("energie.v1", **mesureur.arreter())
        journal.ecrire("coherence.v1", **_controler_coherence(journal.chemin))
        bilan = client.bilan() if client else {
            "appels": 0, "tokens_entree": 0, "tokens_sortie": 0,
            "temps_llm_s": 0.0, "temps_attente_s": 0.0, "erreurs": 0, "par_taille": {}}
        incidents = _compter_incidents(journal.chemin)
        journal.ecrire("bilan.v1", appels=bilan["appels"],
                       tokens_entree=bilan["tokens_entree"],
                       tokens_sortie=bilan["tokens_sortie"],
                       duree_run_s=round(time.perf_counter() - t0, 2),
                       interrompu=interrompu, incidents=incidents,
                       par_taille=bilan["par_taille"])
        ecrits, rejets, chemin = journal.nb_ecrits, journal.nb_rejets, journal.chemin

    print(f"\n{ecrits} evenements conformes, {rejets} rejetes, {incidents} incidents d'agent")
    if bilan["appels"]:
        print(f"Appels LLM : {bilan['appels']}, "
              f"{bilan['tokens_entree']} tokens entree, "
              f"{bilan['tokens_sortie']} tokens sortie")
        for taille, c in sorted(bilan["par_taille"].items()):
            print(f"  {taille:10s} {c['modele']:38s} {c['appels']:4d} appels, "
                  f"latence moyenne {c['latence_moy_s']}s")
        print(f"Temps : LLM {bilan['temps_llm_s']}s, attente {bilan['temps_attente_s']}s")
    print(f"Run enregistre dans {chemin}")


class Energie:
    """Energie de la machine locale pendant le run, via CodeCarbon (E4).

    Avec Ollama, c'est l'energie de l'inference elle-meme. Avec une API, la
    mesure ne couvre que la machine locale : le cout du serveur distant s'estime
    a part (EcoLogits, par exemple), et la note le dit.
    """

    def __init__(self, active, nom_run):
        self.suivi = None
        self.note = ""
        if not active:
            self.note = "mesure desactivee (--energie non)"
            return
        try:
            from codecarbon import OfflineEmissionsTracker
        except ImportError:
            self.note = "CodeCarbon absent : pip install codecarbon"
            return
        self.suivi = OfflineEmissionsTracker(
            project_name=nom_run, country_iso_code="MAR", log_level="error",
            save_to_file=False)

    def demarrer(self):
        if self.suivi:
            self.suivi.start()

    def arreter(self):
        if not self.suivi:
            return {"outil": None, "kwh": None, "co2_kg": None,
                    "portee": "machine locale", "note": self.note}
        co2 = self.suivi.stop()
        donnees = getattr(self.suivi, "final_emissions_data", None)
        kwh = getattr(donnees, "energy_consumed", None)
        return {"outil": "codecarbon", "kwh": None if kwh is None else float(kwh),
                "co2_kg": None if co2 is None else float(co2),
                "portee": "machine locale",
                "note": "inference locale comprise si le fournisseur est ollama"}


def _controler_coherence(chemin):
    """Total des controles C6 du run, relus dans le journal comme les incidents."""
    controles, details = 0, []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if '"perception.v1"' not in ligne:
                continue
            e = json.loads(ligne)
            controles += 1
            for v in e["violations_c6"]:
                details.append({"agent": e["agent"], "t_sim": e["t_sim"], **v})
    return {"controles": controles, "violations": len(details), "details": details[:50]}


def _compter_incidents(chemin):
    """Nombre d'evenements incident.v1 du run (taux de sortie de role, A4)."""
    n = 0
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if '"incident.v1"' in ligne:
                n += 1
    return n


if __name__ == "__main__":
    main()
